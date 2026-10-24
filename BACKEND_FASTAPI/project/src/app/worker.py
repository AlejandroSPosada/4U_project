"""Proceso `worker` (`python -m app.worker`, ARCHITECTURE §5.9).

**BE-1.1: solo latido.** `backend.yml` despliega `api` y `worker` con la misma imagen (infra §5.9); para que una tarea
de `worker` no falle al arrancar antes de BE-2.2, el proceso existe, registra un latido cada 60 s (`evento = latido`)
y termina limpio con SIGTERM. **No consume las colas**: la ingesta (§4.6) y la purga (§4.11) llegan con BE-2.2 y
BE-4.1, que reemplazan el cuerpo de `ejecutar`.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from app import __version__
from app.config import get_settings
from app.logs import configurar_logs, obtener_logger, registrar

INTERVALO_LATIDO_S = 60.0

log = obtener_logger("app.worker")  # estable también con `python -m app.worker`


async def ejecutar(detener: asyncio.Event, intervalo_s: float = INTERVALO_LATIDO_S) -> None:
    """Emite un latido cada `intervalo_s` hasta que se activa `detener`."""
    while not detener.is_set():
        registrar(log, "latido", modo="sin_consumo")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(detener.wait(), timeout=intervalo_s)


async def _principal() -> None:
    detener = asyncio.Event()
    bucle = asyncio.get_running_loop()
    for senal in (signal.SIGTERM, signal.SIGINT):
        # En Windows no hay add_signal_handler; ahí Ctrl+C llega como KeyboardInterrupt.
        with contextlib.suppress(NotImplementedError, RuntimeError):
            bucle.add_signal_handler(senal, detener.set)
    ajustes = get_settings()
    registrar(
        log,
        "worker_iniciado",
        version=__version__,
        commit=ajustes.commit_corto,
        entorno=ajustes.app_env,
        modo="sin_consumo",
    )
    await ejecutar(detener)
    registrar(log, "worker_detenido")


def main() -> None:
    configurar_logs("worker", get_settings().log_level)
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_principal())


if __name__ == "__main__":
    main()
