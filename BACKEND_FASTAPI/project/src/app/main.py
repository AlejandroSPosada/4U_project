"""Aplicación FastAPI (proceso `api`).

Comando de la imagen (ARCHITECTURE §5.9):
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-server-header

Un solo proceso de uvicorn (la tarea tiene 0,25 vCPU, §4.2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.v1 import router_v1
from app.config import Settings, get_settings
from app.db import sesion
from app.errores import registrar_manejadores
from app.esquemas.errores import ErrorRespuesta
from app.logs import configurar_logs, obtener_logger, registrar
from app.middleware import MiddlewareSolicitud

log = obtener_logger(__name__)


def crear_app(ajustes: Settings | None = None) -> FastAPI:
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
        registrar(log, "api_iniciada", version=__version__, commit=ajustes.commit_corto, entorno=ajustes.app_env)
        try:
            yield
        finally:
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

    registrar_manejadores(app)
    app.add_middleware(MiddlewareSolicitud)
    app.include_router(router_v1)
    return app


app = crear_app()
