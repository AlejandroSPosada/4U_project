"""Aplicación FastAPI (proceso `api`).

Comando de la imagen (ARCHITECTURE §5.9):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-server-header

Un solo proceso de uvicorn (la tarea tiene 0,25 vCPU, §4.2).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio.to_thread
from fastapi import FastAPI

from app import __version__
from app.api.v1 import router_v1
from app.clientes.s3 import AlmacenS3
from app.config import Settings, get_settings
from app.db import sesion
from app.errores import registrar_manejadores
from app.esquemas.errores import ErrorRespuesta
from app.logs import configurar_logs, obtener_logger, registrar
from app.middleware import MiddlewareSolicitud
from app.seguridad import hash as hash_password
from app.servicios import alertas
from app.servicios.autenticacion import ColaHash

log = obtener_logger(__name__)


async def _crear_almacen(aplicacion: FastAPI, ajustes: Settings) -> AlmacenS3 | None:
    """BE-2.1: cliente de S3 del bucket del dataset, creado una vez (crear un cliente de boto3 cuesta CPU) y en un hilo.
    Sin `S3_BUCKET_DATASET`, `None`: las rutas de recolección responden 500 (`obtener_almacen`)."""
    bucket = (ajustes.s3_bucket_dataset or "").strip()
    if not bucket:
        aplicacion.state.motivo_sin_almacen = "falta S3_BUCKET_DATASET"
        return None
    try:
        return await anyio.to_thread.run_sync(lambda: AlmacenS3(bucket, ajustes.aws_region))
    except Exception as exc:
        aplicacion.state.motivo_sin_almacen = f"no se pudo crear el cliente de S3: {type(exc).__name__}"
        registrar(log, "s3_fallido", logging.ERROR, operacion="crear_cliente", motivo=type(exc).__name__)
        return None


def crear_app(ajustes: Settings | None = None, *, almacen: AlmacenS3 | None = None) -> FastAPI:
    """`almacen` sustituye al cliente de S3 (las pruebas pasan un doble); sin él, se crea al arrancar."""
    ajustes = ajustes or get_settings()
    configurar_logs("api", ajustes.log_level)

    @asynccontextmanager
    async def ciclo_de_vida(aplicacion: FastAPI) -> AsyncIterator[None]:
        # El motor no se conecta al crearse: `api` arranca aunque la base no responda (lo informa /v1/health/ready).
        try:
            aplicacion.state.motor = sesion.crear_motor(
                ajustes, "api", pool=ajustes.db_pool_api, desborde=ajustes.db_pool_api_desborde
            )
        except sesion.ConfiguracionIncompleta as exc:
            aplicacion.state.motor = None
            aplicacion.state.motivo_sin_motor = f"configuracion_incompleta: {exc}"
        # BE-1.3: cola de verificaciones argon2id nueva para este bucle y el hash ficticio del login calculado antes de
        # la primera petición.
        aplicacion.state.cola_hash = ColaHash.desde(ajustes)
        await anyio.to_thread.run_sync(hash_password.hash_ficticio)
        aplicacion.state.almacen = almacen if almacen is not None else await _crear_almacen(aplicacion, ajustes)
        registrar(log, "api_iniciada", version=__version__, commit=ajustes.commit_corto, entorno=ajustes.app_env)
        # BE-3.3: purga diaria de los tombstones de alertas (ALERTAS_TOMBSTONE_DIAS, §5.10); la primera, 60 s después
        # de arrancar. Sin motor no hay nada que purgar.
        limpieza = None
        if aplicacion.state.motor is not None:
            limpieza = asyncio.create_task(
                alertas.limpieza_diaria(aplicacion.state.motor, ajustes.alertas_tombstone_dias),
                name="limpieza-diaria-alertas",
            )
        try:
            yield
        finally:
            if limpieza is not None:
                limpieza.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await limpieza
            if aplicacion.state.motor is not None:
                await aplicacion.state.motor.dispose()
            registrar(log, "api_detenida")

    documentacion = not ajustes.es_produccion
    app = FastAPI(
        title="Campus Locator — Backend",
        version=__version__,
        lifespan=ciclo_de_vida,
        redirect_slashes=False,
        openapi_url="/v1/openapi.json" if documentacion else None,
        docs_url="/v1/docs" if documentacion else None,
        redoc_url=None,
        responses={500: {"model": ErrorRespuesta, "description": "ERROR_INTERNO"}},
    )
    app.state.ajustes = ajustes
    app.state.motor = None  # lo crea el ciclo de vida (BE-1.2)
    app.state.motivo_sin_motor = "configuracion_incompleta: faltan DB_*"
    app.state.cola_hash = ColaHash.desde(ajustes)  # el ciclo de vida la renueva al arrancar (BE-1.3)
    app.state.almacen = almacen  # sin doble, lo crea el ciclo de vida (BE-2.1)
    app.state.motivo_sin_almacen = "falta S3_BUCKET_DATASET"

    registrar_manejadores(app)
    app.add_middleware(MiddlewareSolicitud)
    app.include_router(router_v1)
    return app


app = crear_app()
