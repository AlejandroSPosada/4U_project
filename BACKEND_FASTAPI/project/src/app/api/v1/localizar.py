"""Localización (ARCHITECTURE §4.10, §5.3): `POST /v1/localize` (BE-3.2). Público: no pide token y no lo mira.

Orden de las respuestas (el primero que aplica):
1. `400 FOTOS_INVALIDAS` si el cuerpo pasa de `LOC_MAX_FOTOS × LOC_MAX_BYTES_FOTO + MARGEN_MULTIPART` o no es
   `multipart/form-data`; `400 SOLICITUD_INVALIDA` si el multipart está mal formado.
2. `400 FOTOS_INVALIDAS` por las partes `fotos` (ninguna, más de `LOC_MAX_FOTOS`, o una que no vale), con el índice.
3. Parte `metadatos`: `422 VALIDACION` (falta, repetida, demasiado grande o campos que no valen; `detalle.campos` con
   `metadatos…`) o `400 SOLICITUD_INVALIDA` (no es JSON UTF-8); `400 FOTOS_INVALIDAS` si `rumbos` no tiene un
   elemento por foto.
4. `503 BASE_NO_DISPONIBLE` sin motor; `503 EMBEDDING_NO_DISPONIBLE` o `400 FOTOS_INVALIDAS` (embeddings); `503
   BASE_NO_DISPONIBLE` durante la búsqueda o al escribir el evento → `200`.
"""

from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from app.api.cuerpo import CuerpoDemasiadoGrande, leer_cuerpo
from app.api.dependencias import obtener_ajustes, obtener_motor
from app.api.v1.admin_diagnostico import MARGEN_MULTIPART
from app.clientes import embedding
from app.config import Settings
from app.dominio.fotos import motivo_foto_no_valida
from app.dominio.lugares import DECIMALES_DISTANCIA
from app.dominio.multipart import MultipartInvalido, NoEsMultipart, Parte, partes_multipart
from app.errores import ErrorApi, motivo_en_espanol, nombre_campo
from app.esquemas.errores import ErrorRespuesta
from app.esquemas.localizacion import (
    DECIMALES_COORDENADA,
    DECIMALES_RADIO,
    DECIMALES_RUMBO,
    METADATOS_MAX_BYTES,
    PARTE_FOTOS,
    PARTE_METADATOS,
    LocalizacionRespuesta,
    LugarCercano,
    MetadatosLocalizacion,
    PosicionRespuesta,
    ReferenciaLugar,
)
from app.logs import obtener_logger, registrar, request_id_actual
from app.servicios import localizar as servicio

log = obtener_logger(__name__)
router = APIRouter(tags=["localización"])

_CUERPO_MULTIPART = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": [PARTE_FOTOS, PARTE_METADATOS],
                "properties": {
                    PARTE_FOTOS: {
                        "type": "array",
                        "items": {"type": "string", "format": "binary"},
                        "minItems": 1,
                        "description": "1 a LOC_MAX_FOTOS partes image/jpeg de ≤ LOC_MAX_BYTES_FOTO, en orden",
                    },
                    PARTE_METADATOS: {
                        "type": "string",
                        "description": 'JSON: {"rumbos": [número | null, …], "origen": "escaneo", "app_version": …}',
                    },
                },
            }
        }
    },
}


def _foto_invalida(motivo: str, indice: int = 0) -> ErrorApi:
    return ErrorApi(400, "FOTOS_INVALIDAS", detalle={"indice": indice, "motivo": motivo})


def _metadatos_invalidos(campos: list[dict[str, str]]) -> ErrorApi:
    return ErrorApi(422, "VALIDACION", detalle={"campos": campos})


async def partes_de_la_peticion(request: Request, ajustes: Settings) -> list[Parte]:
    """El cuerpo leído en memoria con tope y partido en partes (paso 1 del orden de arriba)."""
    tope = ajustes.loc_max_fotos * ajustes.loc_max_bytes_foto + MARGEN_MULTIPART
    try:
        cuerpo = await leer_cuerpo(request, tope)
    except CuerpoDemasiadoGrande as exc:
        motivo = (
            f"la petición pasa de {exc.max_bytes} bytes (hasta {ajustes.loc_max_fotos} fotos de "
            f"{ajustes.loc_max_bytes_foto} bytes como mucho)"
        )
        raise _foto_invalida(motivo) from None
    try:
        return partes_multipart(request.headers.get("content-type"), cuerpo)
    except NoEsMultipart:
        raise _foto_invalida("falta la parte fotos (se espera multipart/form-data)") from None
    except MultipartInvalido:
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "El cuerpo multipart/form-data está mal formado.") from None


def fotos_de(partes: list[Parte], ajustes: Settings) -> list[bytes]:
    """Las partes `fotos`, en el orden en que llegan (ese orden es el `indice` y el de `rumbos`), validadas."""
    fotos = [parte for parte in partes if parte.nombre == PARTE_FOTOS]
    if not fotos:
        raise _foto_invalida("falta la parte fotos")
    if len(fotos) > ajustes.loc_max_fotos:
        raise _foto_invalida(f"como mucho {ajustes.loc_max_fotos} fotos", indice=ajustes.loc_max_fotos)
    for indice, parte in enumerate(fotos):
        motivo = motivo_foto_no_valida(parte.tipo, parte.datos, ajustes.loc_max_bytes_foto)
        if motivo is not None:
            raise _foto_invalida(motivo, indice=indice)
    return [parte.datos for parte in fotos]


def metadatos_de(partes: list[Parte], n_fotos: int) -> MetadatosLocalizacion:
    """La parte `metadatos` (JSON en UTF-8; su `Content-Type` no se mira) validada, con un rumbo por foto."""
    candidatas = [parte for parte in partes if parte.nombre == PARTE_METADATOS]
    if not candidatas:
        raise _metadatos_invalidos([{"campo": PARTE_METADATOS, "motivo": "Falta la parte metadatos."}])
    if len(candidatas) > 1:
        raise _metadatos_invalidos([{"campo": PARTE_METADATOS, "motivo": "Solo se admite una parte metadatos."}])
    datos = candidatas[0].datos
    if len(datos) > METADATOS_MAX_BYTES:
        motivo = f"Pesa {len(datos)} bytes (máximo {METADATOS_MAX_BYTES})."
        raise _metadatos_invalidos([{"campo": PARTE_METADATOS, "motivo": motivo}])
    try:
        valor = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ErrorApi(400, "SOLICITUD_INVALIDA", "La parte metadatos no es un JSON válido en UTF-8.") from None
    try:
        metadatos = MetadatosLocalizacion.model_validate(valor)
    except ValidationError as exc:
        campos = [
            {
                "campo": PARTE_METADATOS + (f".{nombre_campo(e['loc'])}" if e.get("loc") else ""),
                "motivo": motivo_en_espanol(e),
            }
            for e in exc.errors()
        ]
        raise _metadatos_invalidos(campos) from None
    if len(metadatos.rumbos) != n_fotos:
        motivo = f"rumbos tiene {len(metadatos.rumbos)} elementos y hay {n_fotos} fotos"
        raise _foto_invalida(motivo, indice=min(len(metadatos.rumbos), n_fotos))
    return metadatos


def _rumbo_salida(grados: float) -> float:
    """Redondeado a `DECIMALES_RUMBO` y en [0, 360) (359,96 no sale como 360,0)."""
    valor = round(grados, DECIMALES_RUMBO) % 360.0
    return 0.0 if valor >= 360.0 else valor


def _correccion_salida(grados: float | None) -> float | None:
    """Redondeada a `DECIMALES_RUMBO` y en (−180, 180]."""
    if grados is None:
        return None
    valor = round(grados, DECIMALES_RUMBO)
    return 180.0 if valor <= -180.0 else valor


def respuesta_de(resultado: servicio.ResultadoLocalizar) -> LocalizacionRespuesta:
    loc = resultado.localizacion
    pos = loc.posicion
    cercano = resultado.lugar_cercano
    return LocalizacionRespuesta(
        resultado=loc.resultado.value,
        posicion=None
        if pos is None
        else PosicionRespuesta(
            lat=round(pos.lat, DECIMALES_COORDENADA),
            lng=round(pos.lng, DECIMALES_COORDENADA),
            radio_m=round(pos.radio_m, DECIMALES_RADIO),
        ),
        confianza=loc.confianza,
        nivel=None if loc.nivel is None else loc.nivel.value,
        correccion_rumbo_grados=_correccion_salida(loc.correccion_rumbo_grados),
        lugar_cercano=None
        if cercano is None
        else LugarCercano(
            id=cercano.lugar.id,
            nombre=cercano.lugar.nombre,
            distancia_m=round(cercano.distancia_m, DECIMALES_DISTANCIA),
        ),
        referencias=[
            ReferenciaLugar(
                id=r.lugar.id,
                nombre=r.lugar.nombre,
                distancia_m=round(r.distancia_m, DECIMALES_DISTANCIA),
                rumbo_grados=_rumbo_salida(r.rumbo_grados),
            )
            for r in resultado.referencias
        ],
        fotos_usadas=loc.fotos_usadas,
        fotos_con_coincidencia=loc.fotos_con_coincidencia,
        version_vector=resultado.version_vector,
        latencia_ms=resultado.latencia_ms,
    )


@router.post(
    "/localize",
    response_model=LocalizacionRespuesta,
    summary="Ubicarse con 1–5 fotos (escaneo 360°)",
    openapi_extra={"requestBody": _CUERPO_MULTIPART},
    responses={
        400: {
            "model": ErrorRespuesta,
            "description": "FOTOS_INVALIDAS (detalle.indice y .motivo) · SOLICITUD_INVALIDA",
        },
        422: {"model": ErrorRespuesta, "description": "VALIDACION (metadatos)"},
        503: {"model": ErrorRespuesta, "description": "EMBEDDING_NO_DISPONIBLE · BASE_NO_DISPONIBLE"},
    },
)
async def localizar(request: Request, ajustes: Settings = Depends(obtener_ajustes)) -> LocalizacionRespuesta:
    inicio = time.perf_counter()
    partes = await partes_de_la_peticion(request, ajustes)
    fotos = fotos_de(partes, ajustes)
    metadatos = metadatos_de(partes, len(fotos))
    motor = obtener_motor(request)
    try:
        resultado = await servicio.localizar(
            motor,
            ajustes,
            fotos,
            metadatos.rumbos,
            origen=metadatos.origen,
            app_version=metadatos.app_version,
            inicio=inicio,
            request_id=request_id_actual.get(),
        )
    except embedding.ImagenRechazada as exc:
        raise _foto_invalida(f"embeddings la rechazó ({exc.codigo})", indice=exc.indice) from None
    except embedding.EmbeddingNoDisponible as exc:
        registrar(log, "embedding_no_disponible", logging.WARNING, motivo=str(exc))
        raise ErrorApi(503, "EMBEDDING_NO_DISPONIBLE") from None
    except embedding.RespuestaNoValida as exc:
        registrar(log, "embedding_no_disponible", logging.ERROR, motivo=f"respuesta no válida: {exc}")
        raise ErrorApi(503, "EMBEDDING_NO_DISPONIBLE") from None
    except servicio.VersionVectorDistinta as exc:
        registrar(log, "version_vector_distinta", logging.ERROR, esperada=exc.esperada, recibida=exc.recibida)
        raise ErrorApi(503, "EMBEDDING_NO_DISPONIBLE") from None
    loc = resultado.localizacion
    registrar(
        log,
        "localizacion_calculada",
        resultado=loc.resultado.value,
        nivel_confianza=None if loc.nivel is None else loc.nivel.value,
        confianza=loc.confianza,
        fotos_usadas=loc.fotos_usadas,
        fotos_con_coincidencia=loc.fotos_con_coincidencia,
        coincidencias=loc.coincidencias,
        grupos=loc.grupos,
        similitud_max=None if loc.similitud_max is None else round(loc.similitud_max, 6),
        bytes=sum(len(f) for f in fotos),
        embedding_ms=resultado.embedding_ms,
        busqueda_ms=resultado.busqueda_ms,
        latencia_ms=resultado.latencia_ms,
    )
    return respuesta_de(resultado)
