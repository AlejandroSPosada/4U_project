"""Servicio HTTP de embeddings: rutas, arranque (carga + calentamiento) y errores (ARCHITECTURE §5).

El modelo se carga en un hilo aparte: mientras tanto `GET /health` responde 200 y
`GET /health/ready` 503 `{"estado": "cargando"}`; tras el calentamiento, 200 `{"estado": "listo"}`.
Si la carga falla, el proceso termina con código 1 para que ECS reemplace la tarea.

`POST /v1/embed` (§4.3, §5.2) lee el cuerpo con tope, valida la petición (§5.6) y la encola en el
planificador; el hilo único de inferencia preprocesa (pp-v1) y calcula el lote.
"""

from __future__ import annotations

import asyncio
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import MultipartParser, MultipartState, parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app import config
from app.config import Settings, obtener_settings
from app.planificador import PRIORIDAD_POR_DEFECTO, PRIORIDADES, Detenido, Planificador, Saturado
from app.preproceso import ImagenInvalida, preprocesar_lote

if TYPE_CHECKING:
    import numpy as np

log = logging.getLogger("embedding")

RUTAS_SALUD = frozenset({"/health", "/health/ready"})
_PATRON_REQUEST_ID = re.compile(r"[A-Za-z0-9._:\-]{1,128}")

CAMPO_IMAGENES = "imagenes"
TIPOS_IMAGEN = frozenset({"image/jpeg", "image/png"})
# Si una petición declara más de BYTES_MAX_PETICION, se lee y descarta hasta este múltiplo antes
# de responder 413, para que el cliente termine de enviar y pueda leer la respuesta.
FACTOR_DRENAJE = 4


class Modelo(Protocol):
    def cargar(self) -> None: ...

    def calentar(self) -> None: ...

    def inferir(self, lote: np.ndarray) -> np.ndarray: ...


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
        self.planificador: Planificador | None = None


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
    # Los avisos de Python (warnings) también salen en JSON, no como texto en stderr.
    logging.captureWarnings(True)


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


@dataclass(eq=False)
class ErrorApi(Exception):
    """Error de §5.6 que se responde con el formato de §5.1."""

    estado_http: int
    codigo: str
    mensaje: str
    detalle: dict[str, Any] | None = None
    encabezados: dict[str, str] | None = field(default=None)


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


async def _error_api(_: Request, exc: ErrorApi) -> JSONResponse:
    return respuesta_error(exc.estado_http, exc.codigo, exc.mensaje, exc.detalle, exc.encabezados)


# --- Lectura de POST /v1/embed (§5.2, §5.6) ---------------------------------------------------


@dataclass
class Parte:
    nombre: str
    tipo: str
    datos: bytes


async def leer_cuerpo(request: Request, maximo: int) -> bytes:
    """Cuerpo completo; `413 LOTE_DEMASIADO_GRANDE` si supera `maximo` bytes (16 MB, §5.2)."""
    declarado = request.headers.get("content-length")
    if declarado is not None:
        try:
            longitud = int(declarado)
        except ValueError as error:
            raise ErrorApi(400, "SOLICITUD_INVALIDA", "Content-Length no es un número") from error
        if longitud > maximo:
            if longitud <= maximo * FACTOR_DRENAJE:
                await _descartar(request)
            raise _cuerpo_demasiado_grande(longitud, maximo)
    trozos: list[bytes] = []
    recibidos = 0
    try:
        async for trozo in request.stream():
            recibidos += len(trozo)
            if recibidos > maximo * FACTOR_DRENAJE:
                break
            if recibidos <= maximo:
                trozos.append(trozo)
    except ClientDisconnect as error:
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "El cliente cerró la conexión") from error
    if recibidos > maximo:
        raise _cuerpo_demasiado_grande(recibidos, maximo)
    return b"".join(trozos)


async def _descartar(request: Request) -> None:
    try:
        async for _ in request.stream():
            pass
    except ClientDisconnect:
        pass


def _cuerpo_demasiado_grande(recibidos: int, maximo: int) -> ErrorApi:
    return ErrorApi(
        413,
        "LOTE_DEMASIADO_GRANDE",
        f"La petición mide {recibidos} bytes; el máximo es {maximo}",
    )


class _DemasiadasImagenes(Exception):
    """Interrumpe la lectura en cuanto aparece la parte `imagenes` número LOTE_MAX + 1."""


def leer_imagenes(cuerpo: bytes, tipo_contenido: str | None, lote_max: int) -> list[Parte]:
    """Partes `imagenes` de un `multipart/form-data`, en orden (§5.2).

    Las partes con otro nombre se recorren sin guardarlas. `400 SOLICITUD_INVALIDA` si el cuerpo
    no es multipart o está mal formado; `413` en cuanto hay más de `lote_max` imágenes, sin leer el
    resto. Es trabajo de CPU: la ruta lo ejecuta fuera del bucle de eventos.
    """
    tipo, opciones = parse_options_header(tipo_contenido or "")
    frontera = opciones.get(b"boundary")
    if tipo.lower() != b"multipart/form-data" or not frontera:
        raise ErrorApi(
            400, "SOLICITUD_INVALIDA", "La petición debe ser multipart/form-data con frontera"
        )

    imagenes: list[Parte] = []
    encabezados: dict[str, str] = {}
    campo = bytearray()
    valor = bytearray()
    datos = bytearray()
    es_imagen = False

    def inicio_parte() -> None:
        nonlocal es_imagen
        encabezados.clear()
        datos.clear()
        es_imagen = False

    def fin_encabezado() -> None:
        encabezados[campo.decode("latin-1").strip().lower()] = valor.decode("latin-1").strip()
        campo.clear()
        valor.clear()

    def fin_encabezados() -> None:
        nonlocal es_imagen
        disposicion, params = parse_options_header(encabezados.get("content-disposition", ""))
        nombre = params.get(b"name", b"").decode("utf-8", "replace")
        es_imagen = disposicion.lower() == b"form-data" and nombre == CAMPO_IMAGENES
        if es_imagen and len(imagenes) >= lote_max:
            raise _DemasiadasImagenes

    def dato(d: bytes, inicio: int, fin: int) -> None:
        if es_imagen:
            datos.extend(d[inicio:fin])

    def fin_parte() -> None:
        if es_imagen:
            tipo_parte = parse_options_header(encabezados.get("content-type", ""))[0]
            imagenes.append(
                Parte(CAMPO_IMAGENES, tipo_parte.decode("latin-1").lower(), bytes(datos))
            )

    try:
        parser = MultipartParser(
            frontera,
            {
                "on_part_begin": inicio_parte,
                "on_header_field": lambda d, i, f: campo.extend(d[i:f]),
                "on_header_value": lambda d, i, f: valor.extend(d[i:f]),
                "on_header_end": fin_encabezado,
                "on_headers_finished": fin_encabezados,
                "on_part_data": dato,
                "on_part_end": fin_parte,
            },
        )
        parser.write(cuerpo)
        parser.finalize()
    except _DemasiadasImagenes as error:
        raise ErrorApi(
            413,
            "LOTE_DEMASIADO_GRANDE",
            f"Se recibieron más de {lote_max} imágenes; el máximo es {lote_max}",
        ) from error
    except FormParserError as error:  # incluye MultipartParseError y una frontera demasiado larga
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "El multipart está mal formado") from error
    if parser.state not in (MultipartState.END_BOUNDARY, MultipartState.END):
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "El multipart está incompleto")
    return imagenes


def imagenes_validadas(imagenes: list[Parte], settings: Settings) -> list[bytes]:
    """Aplica §5.6 antes de encolar: hay imágenes y cada una tiene tipo y tamaño admitidos."""
    if not imagenes:
        raise ErrorApi(400, "SOLICITUD_INVALIDA", f"Faltan partes «{CAMPO_IMAGENES}»")
    for indice, parte in enumerate(imagenes):
        if parte.tipo not in TIPOS_IMAGEN:
            raise ErrorApi(
                415,
                "TIPO_NO_SOPORTADO",
                f"La imagen {indice} es de tipo «{parte.tipo or 'sin tipo'}»; se admiten "
                "image/jpeg e image/png",
                {"indice": indice},
            )
        if len(parte.datos) > settings.bytes_max_imagen:
            raise ErrorApi(
                413,
                "LOTE_DEMASIADO_GRANDE",
                f"La imagen {indice} mide {len(parte.datos)} bytes; el máximo es "
                f"{settings.bytes_max_imagen}",
                {"indice": indice},
            )
    return [parte.datos for parte in imagenes]


def prioridad_de(request: Request) -> str:
    valor = request.headers.get("x-prioridad")
    if valor is None:
        return PRIORIDAD_POR_DEFECTO
    prioridad = valor.strip().lower()
    if prioridad not in PRIORIDADES:
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "X-Prioridad debe ser «alta» o «baja»")
    return prioridad


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


class TiemposMs(BaseModel):
    cola: int
    inferencia: int


class Vectorizacion(BaseModel):
    version_vector: str
    dim: int
    vectores: list[list[float]]
    tiempos_ms: TiemposMs


class ErrorDetalle(BaseModel):
    codigo: str
    mensaje: str
    detalle: dict[str, Any] | None


class RespuestaError(BaseModel):
    error: ErrorDetalle


def _openapi_embed(settings: Settings) -> dict[str, Any]:
    return {
        "parameters": [
            {
                "name": "X-Prioridad",
                "in": "header",
                "required": False,
                "schema": {"type": "string", "enum": list(PRIORIDADES), "default": "baja"},
            }
        ],
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": [CAMPO_IMAGENES],
                        "properties": {
                            CAMPO_IMAGENES: {
                                "type": "array",
                                "items": {"type": "string", "format": "binary"},
                                "minItems": 1,
                                "maxItems": settings.lote_max,
                            }
                        },
                    }
                }
            },
        },
    }


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
        # El hilo de inferencia preprocesa y calcula cada petición como un solo lote (§4.3).
        estado.planificador = Planificador(
            lambda imagenes: modelo.inferir(
                preprocesar_lote(imagenes, settings.lado_min_px, settings.proporcion_max)
            ),
            cola_max_imagenes=settings.cola_max_imagenes,
        ).iniciar()
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
        if estado.planificador is not None:
            estado.planificador.detener()

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
    app.add_exception_handler(ErrorApi, _error_api)

    @app.middleware("http")
    async def correlacion_y_registro(request: Request, call_next):
        recibido = request.headers.get("x-request-id", "")
        request_id = recibido if _PATRON_REQUEST_ID.fullmatch(recibido) else uuid.uuid4().hex
        request.state.request_id = request_id
        request.state.registro = {}
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
                **request.state.registro,
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

    errores_embed = {codigo: {"model": RespuestaError} for codigo in (400, 413, 415, 500, 503)}

    @app.post(
        "/v1/embed",
        response_model=Vectorizacion,
        responses=errores_embed,
        openapi_extra=_openapi_embed(settings),
    )
    async def vectorizar(request: Request):
        registro = request.state.registro
        # 1) Validación (§5.6): no depende del estado del modelo ni de la cola.
        cuerpo = await leer_cuerpo(request, settings.bytes_max_peticion)
        prioridad = prioridad_de(request)
        registro["prioridad"] = prioridad
        partes = await run_in_threadpool(
            leer_imagenes, cuerpo, request.headers.get("content-type"), settings.lote_max
        )
        del cuerpo
        imagenes = imagenes_validadas(partes, settings)
        registro["n_imagenes"] = len(imagenes)

        # 2) Estado: modelo listo y sitio en la cola.
        planificador = estado.planificador
        if not estado.listo.is_set() or planificador is None:
            raise ErrorApi(503, "NO_LISTO", "El modelo aún se está cargando")
        try:
            futuro = planificador.enviar(imagenes, prioridad)
        except Saturado as error:
            raise ErrorApi(
                503,
                "SATURADO",
                str(error),
                encabezados={"Retry-After": str(settings.retry_after_s)},
            ) from error
        except Detenido as error:
            raise ErrorApi(503, "NO_LISTO", "El servicio se está deteniendo") from error
        del imagenes, partes

        # 3) Resultado del hilo de inferencia.
        try:
            resultado = await asyncio.wrap_future(futuro)
        except ImagenInvalida as error:
            raise ErrorApi(
                400,
                "IMAGEN_INVALIDA",
                f"La imagen {error.indice} {error.motivo}",
                {"indice": error.indice},
            ) from error
        except Detenido as error:
            raise ErrorApi(503, "NO_LISTO", "El servicio se está deteniendo") from error
        registro["cola_ms"] = resultado.cola_ms
        registro["inferencia_ms"] = resultado.inferencia_ms

        vectores = resultado.vectores
        if vectores.shape != (registro["n_imagenes"], config.DIM):
            raise RuntimeError(f"el modelo devolvió una matriz {vectores.shape}")
        return JSONResponse(
            {
                "version_vector": config.VERSION_VECTOR,
                "dim": config.DIM,
                "vectores": vectores.tolist(),
                "tiempos_ms": {"cola": resultado.cola_ms, "inferencia": resultado.inferencia_ms},
            }
        )

    return app


app = crear_app()
