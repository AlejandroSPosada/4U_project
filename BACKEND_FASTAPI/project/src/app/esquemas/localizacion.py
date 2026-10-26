"""`POST /v1/localize` (ARCHITECTURE §5.3), BE-3.2: la parte `metadatos` y la respuesta.

La petición es `multipart/form-data` (partes `fotos` y `metadatos`): las fotos las valida el router con
`app.dominio.fotos`; `metadatos` es JSON y se valida con `MetadatosLocalizacion` (campos de más, ignorados). Las
respuestas prohíben campos de más, como las demás de la API.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.esquemas.comun import texto_admitido
from app.esquemas.videos import APP_VERSION_MAX

#: Nombres de las partes del multipart (§5.3). Las partes con otro nombre se ignoran.
PARTE_FOTOS = "fotos"
PARTE_METADATOS = "metadatos"
#: Tamaño máximo de la parte `metadatos` (bytes): 5 rumbos, `origen` y `app_version` caben de sobra.
METADATOS_MAX_BYTES = 16_384
#: Cifras decimales de la respuesta (el cálculo usa los valores sin redondear).
DECIMALES_COORDENADA = 6
DECIMALES_RADIO = 1
DECIMALES_RUMBO = 1
#: Cifras decimales de `lat`/`lng` en `eventos_localizacion` (~1 m, §5.7).
DECIMALES_EVENTO = 5

Rumbo = Annotated[float, Field(ge=0, lt=360, allow_inf_nan=False)]


class MetadatosLocalizacion(BaseModel):
    """`{"rumbos": [12.0, null, …], "origen": "escaneo", "app_version": "0.9.0"}`. `rumbos[i]` es el rumbo (norte
    verdadero, [0, 360)) de `fotos[i]` o `null`; su largo se compara con las fotos en el router (`400`)."""

    model_config = ConfigDict(extra="ignore")

    rumbos: list[Rumbo | None]
    origen: Literal["escaneo"]
    app_version: str | None = None

    @field_validator("app_version")
    @classmethod
    def _app_version(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        valor = texto_admitido(valor).strip()
        if not valor:
            return None
        if len(valor) > APP_VERSION_MAX:
            raise ValueError(f"Debe tener como máximo {APP_VERSION_MAX} caracteres.")
        return valor


class PosicionRespuesta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float
    lng: float
    radio_m: float


class LugarCercano(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    distancia_m: float


class ReferenciaLugar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    nombre: str
    distancia_m: float
    rumbo_grados: float


class LocalizacionRespuesta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resultado: Literal["ok", "sin_coincidencias"]
    posicion: PosicionRespuesta | None
    confianza: float
    nivel: Literal["alta", "media", "baja"] | None
    correccion_rumbo_grados: float | None
    lugar_cercano: LugarCercano | None
    referencias: list[ReferenciaLugar]
    fotos_usadas: int
    fotos_con_coincidencia: int
    version_vector: str
    latencia_ms: int
