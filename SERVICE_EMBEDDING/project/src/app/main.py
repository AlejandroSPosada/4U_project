"""Servicio HTTP de embeddings: rutas, arranque (carga + calentamiento) y errores (ARCHITECTURE §5).

El modelo se carga en un hilo aparte: mientras tanto `GET /health` responde 200 y
`GET /health/ready` 503 `{"estado": "cargando"}`; tras el calentamiento, 200 `{"estado": "listo"}`.
Si la carga falla, el proceso termina con código 1 para que ECS reemplace la tarea.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.config import Settings, obtener_settings

log = logging.getLogger("embedding")

RUTAS_SALUD = frozenset({"/health", "/health/ready"})
_PATRON_REQUEST_ID = re.compile(r"[A-Za-z0-9._:\-]{1,128}")


class Modelo(Protocol):
    def cargar(self) -> None: ...

    def calentar(self) -> None: ...


FabricaModelo = Callable[[Settings], Modelo]


def _modelo_dinov2(settings: Settings) -> Modelo:
    from app.modelo import ModeloDinov2

    return ModeloDinov2(settings.modelo_dir, settings.torch_num_threads)


def _terminar_proceso() -> None:
    logging.shutdown()
    os._exit(1)


class EstadoServicio:
    def __init__(self) -> None:
        self.listo = threading.Event()
        self.modelo: Modelo | None = None


# --- Logs: JSON por línea (§5.7). Nunca bytes de imagen. ---------------------------------------

CAMPOS_LOG = (
    "request_id",
    "prioridad",
    "n_imagenes",
    "cola_ms",
    "inferencia_ms",
    "metodo",
    "ruta",
    "estado_http",
    "duracion_ms",
    "carga_ms",
    "calentamiento_ms",
    "revision",
    "version_vector",
    "hilos",
    "commit",
)


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        instante = datetime.fromtimestamp(record.created, UTC)
        datos: dict[str, Any] = {
            "ts": instante.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "nivel": record.levelname,
            "evento": record.getMessage(),
        }
        for campo in CAMPOS_LOG:
            valor = getattr(record, campo, None)
            if valor is not None:
                datos[campo] = valor
        if record.exc_info:
            datos["traza"] = self.formatException(record.exc_info)
        return json.dumps(datos, ensure_ascii=False)


def configurar_logs(nivel: str) -> None:
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(FormatoJson())
    raiz = logging.getLogger()
    raiz.handlers = [manejador]
    raiz.setLevel(nivel.upper())
    for nombre in ("uvicorn", "uvicorn.error"):
        registro = logging.getLogger(nombre)
        registro.handlers = []
        registro.propagate = True
    # El acceso ya se registra en JSON desde el middleware; el de uvicorn es texto plano.
    logging.getLogger("uvicorn.access").disabled = True


# --- Errores (§5.1, §5.6) -------------------------------------------------------------------------


def respuesta_error(
    estado_http: int,
    codigo: str,
    mensaje: str,
    detalle: dict[str, Any] | None = None,
    encabezados: dict[str, str] | None = None,
) -> JSONResponse:
    cuerpo = {"error": {"codigo": codigo, "mensaje": mensaje, "detalle": detalle}}
    return JSONResponse(status_code=estado_http, content=cuerpo, headers=encabezados)


CODIGOS_HTTP = {
    404: ("NO_ENCONTRADO", "Ruta inexistente"),
    405: ("METODO_NO_PERMITIDO", "Método no permitido"),
}


async def _error_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code in CODIGOS_HTTP:
        codigo, mensaje = CODIGOS_HTTP[exc.status_code]
    else:
        codigo = "ERROR_INTERNO" if exc.status_code >= 500 else "SOLICITUD_INVALIDA"
        mensaje = exc.detail if isinstance(exc.detail, str) else "Solicitud no atendida"
    return respuesta_error(exc.status_code, codigo, mensaje, encabezados=exc.headers)


async def _error_validacion(_: Request, __: RequestValidationError) -> JSONResponse:
    return respuesta_error(400, "SOLICITUD_INVALIDA", "La solicitud está mal formada")


# --- Esquemas de respuesta (§5.2) ---------------------------------------------------------------


class Salud(BaseModel):
    estado: str


class Info(BaseModel):
    servicio: str
    version: str
    commit: str
    modelo: str
    revision: str
    arquitectura: str
    preprocesamiento: str
    version_vector: str
    dim: int
    normalizacion: str
    metrica: str
    lote_max: int
    dispositivo: str


# --- Aplicación ---------------------------------------------------------------------------------


def crear_app(
    settings: Settings | None = None,
    fabrica_modelo: FabricaModelo = _modelo_dinov2,
    al_fallar: Callable[[], None] = _terminar_proceso,
    configurar_registro: bool = True,
) -> FastAPI:
    settings = settings or obtener_settings()
    if configurar_registro:
        # Al crear la app (uvicorn la importa antes de su primer log), así todo sale en JSON.
        configurar_logs(settings.log_level)
    estado = EstadoServicio()

    def preparar_modelo() -> None:
        inicio = time.perf_counter()
        try:
            modelo = fabrica_modelo(settings)
            modelo.cargar()
            cargado = time.perf_counter()
            modelo.calentar()
        except Exception:
            log.critical("carga_del_modelo_fallida", exc_info=True)
            al_fallar()
            return
        fin = time.perf_counter()
        estado.modelo = modelo
        estado.listo.set()
        log.info(
            "modelo_listo",
            extra={
                "carga_ms": round((cargado - inicio) * 1000),
                "calentamiento_ms": round((fin - cargado) * 1000),
                "revision": config.MODELO_REVISION,
                "version_vector": config.VERSION_VECTOR,
                "hilos": settings.torch_num_threads,
            },
        )

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI):
        log.info(
            "arranque",
            extra={
                "commit": settings.commit_corto,
                "version_vector": config.VERSION_VECTOR,
                "hilos": settings.torch_num_threads,
            },
        )
        threading.Thread(target=preparar_modelo, name="carga-modelo", daemon=True).start()
        yield

    local = settings.app_env == "local"
    app = FastAPI(
        title="Campus Locator — embeddings",
        version=config.VERSION_SERVICIO,
        lifespan=ciclo_de_vida,
        docs_url="/docs" if local else None,
        redoc_url=None,
        openapi_url="/openapi.json" if local else None,
    )
    app.state.settings = settings
    app.state.estado = estado
    app.add_exception_handler(StarletteHTTPException, _error_http)
    app.add_exception_handler(RequestValidationError, _error_validacion)

    @app.middleware("http")
    async def correlacion_y_registro(request: Request, call_next):
        recibido = request.headers.get("x-request-id", "")
        request_id = recibido if _PATRON_REQUEST_ID.fullmatch(recibido) else uuid.uuid4().hex
        request.state.request_id = request_id
        inicio = time.perf_counter()
        try:
            respuesta = await call_next(request)
        except Exception:
            log.exception("error_no_previsto", extra={"request_id": request_id})
            respuesta = respuesta_error(500, "ERROR_INTERNO", "Error interno del servicio")
        respuesta.headers["X-Request-Id"] = request_id
        ruta = request.url.path
        nivel = logging.DEBUG if ruta in RUTAS_SALUD else logging.INFO
        log.log(
            nivel,
            "peticion",
            extra={
                "request_id": request_id,
                "metodo": request.method,
                "ruta": ruta,
                "estado_http": respuesta.status_code,
                "duracion_ms": round((time.perf_counter() - inicio) * 1000),
            },
        )
        return respuesta

    @app.get("/health", response_model=Salud)
    def salud() -> Salud:
        return Salud(estado="ok")

    @app.get("/health/ready", response_model=Salud, responses={503: {"model": Salud}})
    def salud_lista():
        if estado.listo.is_set():
            return Salud(estado="listo")
        return JSONResponse(status_code=503, content={"estado": "cargando"})

    @app.get("/v1/info", response_model=Info)
    def info() -> Info:
        return Info(
            servicio=config.SERVICIO,
            version=config.VERSION_SERVICIO,
            commit=settings.commit_corto,
            modelo=config.MODELO_ID,
            revision=config.MODELO_REVISION,
            arquitectura=config.ARQUITECTURA,
            preprocesamiento=config.PREPROCESAMIENTO,
            version_vector=config.VERSION_VECTOR,
            dim=config.DIM,
            normalizacion=config.NORMALIZACION,
            metrica=config.METRICA,
            lote_max=settings.lote_max,
            dispositivo=config.DISPOSITIVO,
        )

    return app


app = crear_app()
