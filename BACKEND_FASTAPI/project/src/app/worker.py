"""Proceso `worker` (`python -m app.worker`, ARCHITECTURE §4.6, §5.9).

**BE-2.2: ingesta.** Consume la cola `ingesta` (`SQS_URL_INGESTA`) con espera larga, hasta `WORKER_MAX_MENSAJES` por
vez, y procesa cada lote con `servicios.ingesta.procesar_lote`. Antes de cada recepción comprueba
`GET {EMBEDDING_URL}/health/ready`: si embeddings no está listo, no recibe (los mensajes esperan en la cola sin gastar
recepciones, así no llegan a la DLQ) y espera `WORKER_ESPERA_EMBEDDING_S`. Si deja de estarlo justo mientras esperaba
mensajes, los devuelve con visibilidad 0. Borra los mensajes terminados y deja los transitorios (vuelven tras la
visibilidad de la cola, 180 s). Registra un `latido` cada 60 s y termina limpio con SIGTERM.

Sin la configuración que necesita (`SQS_URL_INGESTA`, `S3_BUCKET_DATASET`, `EMBEDDING_URL`, `DB_*`), registra
`configuracion_incompleta` y sigue vivo solo con latidos (`modo = sin_consumo`), como en BE-1.1: así `docker compose`
local (sin SQS) no reinicia el contenedor en bucle. La cola `purga` llega con BE-4.1.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anyio.to_thread

from app import __version__
from app.clientes import embedding
from app.clientes.sqs import FalloSqs
from app.config import Settings, get_settings
from app.logs import configurar_logs, obtener_logger, registrar

INTERVALO_LATIDO_S = 60.0
ESPERA_COLA_S = 20  # espera larga de `ingesta` (infra §5.6)
MODO_INGESTA = "ingesta"
MODO_SIN_CONSUMO = "sin_consumo"

log = obtener_logger("app.worker")  # estable también con `python -m app.worker`


async def _pausa(detener: asyncio.Event, segundos: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(detener.wait(), timeout=segundos)


async def ejecutar(detener: asyncio.Event, intervalo_s: float = INTERVALO_LATIDO_S) -> None:
    """Sin consumo: emite un latido cada `intervalo_s` hasta que se activa `detener`."""
    while not detener.is_set():
        registrar(log, "latido", modo=MODO_SIN_CONSUMO)
        await _pausa(detener, intervalo_s)


async def consumir(
    detener: asyncio.Event,
    ajustes: Settings,
    *,
    cola: Any,
    deps: Any,
    esta_listo: Callable[[Settings], Awaitable[bool]] = embedding.esta_listo,
    espera_cola_s: int = ESPERA_COLA_S,
    intervalo_latido_s: float = INTERVALO_LATIDO_S,
) -> None:
    """Bucle de ingesta. `cola` tiene `recibir`, `borrar` y `devolver` (`ColaSqs`); `deps`, las de `procesar_lote`."""
    from app.servicios.ingesta import procesar_lote

    listo_antes: bool | None = None
    ultimo_latido = float("-inf")
    while not detener.is_set():
        if time.monotonic() - ultimo_latido >= intervalo_latido_s:
            registrar(log, "latido", modo=MODO_INGESTA, embedding_listo=listo_antes)
            ultimo_latido = time.monotonic()
        listo = await esta_listo(ajustes)
        if listo != listo_antes:
            registrar(log, "embedding_listo" if listo else "embedding_no_listo")
            listo_antes = listo
        if not listo:
            await _pausa(detener, ajustes.worker_espera_embedding_s)
            continue
        try:
            recibidos = await anyio.to_thread.run_sync(cola.recibir, ajustes.worker_max_mensajes, espera_cola_s)
        except FalloSqs as exc:
            registrar(log, "cola_fallida", logging.WARNING, operacion="recibir", motivo=str(exc))
            await _pausa(detener, ajustes.worker_espera_embedding_s)
            continue
        if not recibidos:
            continue
        if detener.is_set() or not await esta_listo(ajustes):
            # Embeddings se apagó (o el proceso se detiene) mientras esperaba: los devuelve ya, sin procesarlos.
            for mensaje in recibidos:
                with contextlib.suppress(FalloSqs):
                    await anyio.to_thread.run_sync(cola.devolver, mensaje.recibo)
            registrar(log, "mensajes_devueltos", mensajes=len(recibidos))
            continue
        inicio = time.monotonic()
        decisiones = await procesar_lote(deps, recibidos)
        borrados = 0
        for decision in decisiones:
            if not decision.borrar:
                continue
            try:
                await anyio.to_thread.run_sync(cola.borrar, decision.mensaje.recibo)
                borrados += 1
            except FalloSqs as exc:
                registrar(log, "cola_fallida", logging.WARNING, operacion="borrar", motivo=str(exc))
        retenidos = len(decisiones) - borrados
        registrar(
            log,
            "lote_ingesta",
            mensajes=len(decisiones),
            borrados=borrados,
            retenidos=retenidos,
            duracion_ms=round((time.monotonic() - inicio) * 1000),
        )
        if retenidos:
            await _pausa(detener, ajustes.worker_espera_embedding_s)


def faltan_para_ingesta(ajustes: Settings) -> list[str]:
    """Variables que necesita la ingesta y no están (infra §5.4)."""
    from app.db import sesion

    faltan = [
        nombre
        for nombre, valor in (
            ("SQS_URL_INGESTA", ajustes.sqs_url_ingesta),
            ("S3_BUCKET_DATASET", ajustes.s3_bucket_dataset),
            ("EMBEDDING_URL", ajustes.embedding_url),
        )
        if not valor
    ]
    return faltan + sesion.faltan_variables(ajustes)


async def _principal() -> None:
    detener = asyncio.Event()
    bucle = asyncio.get_running_loop()
    for senal in (signal.SIGTERM, signal.SIGINT):
        # En Windows no hay add_signal_handler; ahí Ctrl+C llega como KeyboardInterrupt.
        with contextlib.suppress(NotImplementedError, RuntimeError):
            bucle.add_signal_handler(senal, detener.set)
    ajustes = get_settings()
    faltan = faltan_para_ingesta(ajustes)
    motor = None
    if not faltan:
        from app.db import sesion

        try:
            motor = sesion.crear_motor(ajustes, "worker", pool=ajustes.db_pool_worker)
        except sesion.ConfiguracionIncompleta as exc:
            faltan = [*exc.faltan, *exc.invalidas]
    modo = MODO_INGESTA if motor is not None else MODO_SIN_CONSUMO
    registrar(
        log, "worker_iniciado", version=__version__, commit=ajustes.commit_corto, entorno=ajustes.app_env, modo=modo
    )
    if motor is None:
        registrar(log, "configuracion_incompleta", logging.ERROR, faltan=faltan, motivo="la ingesta no puede empezar")
        await ejecutar(detener)
    else:
        from app.clientes.s3 import AlmacenS3
        from app.clientes.sqs import ColaSqs
        from app.servicios.ingesta import Dependencias

        try:
            almacen = await anyio.to_thread.run_sync(lambda: AlmacenS3(ajustes.s3_bucket_dataset, ajustes.aws_region))
            cola = await anyio.to_thread.run_sync(lambda: ColaSqs(ajustes.sqs_url_ingesta, ajustes.aws_region))
            await consumir(
                detener, ajustes, cola=cola, deps=Dependencias(motor=motor, almacen=almacen, ajustes=ajustes)
            )
        finally:
            await motor.dispose()
    registrar(log, "worker_detenido")


def main() -> None:
    configurar_logs("worker", get_settings().log_level)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_principal())


if __name__ == "__main__":
    main()
