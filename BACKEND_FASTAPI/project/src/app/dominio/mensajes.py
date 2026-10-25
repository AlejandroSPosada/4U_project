"""Mensajes de la cola `ingesta` (ARCHITECTURE §5.8), sin red ni base.

`interpretar(cuerpo)` convierte el cuerpo de un mensaje de SQS en una de estas formas:

- `EventosS3(objetos)`: notificación de S3 (`Records`); un `ObjetoSubido(clave, etag, bytes)` por cada `Record`
  `ObjectCreated:*` (la clave ya decodificada con `unquote_plus`; el ETag sin comillas). Un mensaje puede traer varios.
- `Reprocesar(imagen_id)`: `{"tipo": "reprocesar_imagen", "version": 1, "imagen_id": …}` (lo envía `api`).
- `PruebaS3()`: el `s3:TestEvent` que S3 envía al configurar la notificación: se borra sin hacer nada.
- `NoReconocido(motivo)`: cualquier otra cosa; el `worker` lo registra y lo borra.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus

#: Versiones aceptadas de `reprocesar_imagen` (§5.8: la actual y la anterior durante un despliegue).
VERSIONES_REPROCESAR = frozenset({1})
TIPO_REPROCESAR = "reprocesar_imagen"


@dataclass(frozen=True)
class ObjetoSubido:
    clave: str
    etag: str | None
    bytes: int | None


@dataclass(frozen=True)
class EventosS3:
    objetos: tuple[ObjetoSubido, ...]
    ignorados: int = 0  # `Records` que no son `ObjectCreated:*` o no traen clave


@dataclass(frozen=True)
class Reprocesar:
    imagen_id: uuid.UUID


@dataclass(frozen=True)
class PruebaS3:
    pass


@dataclass(frozen=True)
class NoReconocido:
    motivo: str


Mensaje = EventosS3 | Reprocesar | PruebaS3 | NoReconocido


def _objeto(registro: Any) -> ObjetoSubido | None:
    if not isinstance(registro, dict) or not str(registro.get("eventName", "")).startswith("ObjectCreated:"):
        return None
    objeto = (registro.get("s3") or {}).get("object") if isinstance(registro.get("s3"), dict) else None
    if not isinstance(objeto, dict) or not isinstance(objeto.get("key"), str):
        return None
    etag = objeto.get("eTag")
    tamano = objeto.get("size")
    return ObjetoSubido(
        clave=unquote_plus(objeto["key"]),
        etag=etag.strip('"') if isinstance(etag, str) and etag.strip('"') else None,
        bytes=tamano if isinstance(tamano, int) and not isinstance(tamano, bool) and tamano >= 0 else None,
    )


def interpretar(cuerpo: str) -> Mensaje:
    try:
        datos = json.loads(cuerpo)
    except (ValueError, TypeError):
        return NoReconocido("cuerpo que no es JSON")
    if not isinstance(datos, dict):
        return NoReconocido("cuerpo que no es un objeto JSON")
    if "Records" in datos:
        registros = datos["Records"]
        if not isinstance(registros, list):
            return NoReconocido("Records no es una lista")
        objetos = [o for o in (_objeto(r) for r in registros) if o is not None]
        return EventosS3(objetos=tuple(objetos), ignorados=len(registros) - len(objetos))
    if datos.get("Event") == "s3:TestEvent":
        return PruebaS3()
    if "tipo" in datos:
        if datos["tipo"] != TIPO_REPROCESAR:
            return NoReconocido(f"tipo desconocido: {str(datos['tipo'])[:60]}")
        version = datos.get("version")
        if type(version) is not int or version not in VERSIONES_REPROCESAR:
            return NoReconocido(f"versión no admitida de {TIPO_REPROCESAR}: {str(datos.get('version'))[:20]}")
        try:
            imagen_id = uuid.UUID(str(datos.get("imagen_id")))
        except ValueError:
            return NoReconocido(f"{TIPO_REPROCESAR} sin imagen_id válido")
        return Reprocesar(imagen_id=imagen_id)
    return NoReconocido("ni Records ni tipo")
