"""Consultas de lectura compartidas entre lotes (ARCHITECTURE §4.1). Desde BE-2.4: la búsqueda de vecinos.

`buscar_vecinos(conexion, vectores, *, k, version_vector, ef_search)` es **la** consulta de vecinos del proyecto
(ARCHITECTURE §4.8): la usan `POST /v1/admin/diagnostico/vecinos` (BE-2.4, un vector) y el paso 3 de `/v1/localize`
(BE-3.2, uno por foto). Va dentro de una transacción abierta (`sesion.transaccion`): fija `hnsw.ef_search` solo para
esa transacción y lanza una sentencia por vector, todas con el índice HNSW parcial de la versión (§5.7).

- La versión va **como literal** en el `WHERE` (sale de `EMBEDDING_VERSION_VECTOR`, nunca de la petición): con un
  parámetro, una sentencia preparada de asyncpg puede pasar a un plan genérico que no usa el índice parcial.
  `literal_version` exige el formato de las versiones (`[A-Za-z0-9._/-]`, 1–100) y lo cita.
- El vector viaja como texto `[x1,x2,…]` con `CAST(:vector AS vector)` (§4.3, `Vector(384)` sin numpy).
- Similitud = `1 − distancia coseno` (`<=>`), acotada a [−1, 1]. Orden: distancia y, a igualdad, `imagen_id`.
- No aplica `LOC_SIM_MIN` ni agrupa: devuelve los `k` más cercanos (menos si el índice tiene menos vectores).
- `ef_search` < `k` haría que HNSW devolviera como mucho `ef_search` filas: se usa `max(ef_search, k)`.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_VERSION = re.compile(r"[A-Za-z0-9._/-]{1,100}")


@dataclass(frozen=True)
class Vecino:
    """Una imagen del índice cercana a la consulta. `rumbo` es el `real` de la base tal cual (sin `real_legible`)."""

    imagen_id: uuid.UUID
    video_id: uuid.UUID
    lat: float
    lng: float
    rumbo: float | None
    lugar_id: uuid.UUID | None
    distancia: float
    similitud: float


def literal_version(version_vector: str) -> str:
    """`'dinov2-vits14/pp-v1'` (con comillas) para escribir la versión en el SQL. `ValueError` si no tiene el
    formato de una versión (no debería pasar: viene de la configuración)."""
    if not _VERSION.fullmatch(version_vector):
        raise ValueError(f"version_vector con un formato no admitido: {version_vector!r}")
    return f"'{version_vector}'"


def texto_vector(vector: Sequence[float]) -> str:
    """El vector como texto de pgvector (`[0.1,0.2,…]`). `ValueError` si algún componente no es finito."""
    componentes = [float(x) for x in vector]
    if not componentes or not all(math.isfinite(x) for x in componentes):
        raise ValueError("vector vacío o con componentes no finitos")
    return "[" + ",".join(repr(x) for x in componentes) + "]"


def sql_vecinos(version_vector: str) -> str:
    """La sentencia de una búsqueda (parámetros `:vector` y `:k`). La subconsulta ordena por la expresión del índice
    (`vector <=> …` con `LIMIT`) para que PostgreSQL use `embeddings_hnsw_<versión>`; la unión con `imagenes` va
    fuera. La versión es un literal validado por `literal_version` (S608: no viene de la petición)."""
    literal = literal_version(version_vector)
    return (
        "SELECT i.id, i.video_id, i.lat, i.lng, i.rumbo, i.lugar_id, c.distancia "  # noqa: S608
        "FROM (SELECT e.imagen_id, e.vector <=> CAST(:vector AS vector) AS distancia "
        f"FROM embeddings e WHERE e.version_vector = {literal} "
        "ORDER BY e.vector <=> CAST(:vector AS vector) LIMIT :k) AS c "
        "JOIN imagenes i ON i.id = c.imagen_id "
        "ORDER BY c.distancia, i.id"
    )


async def fijar_ef_search(conexion: AsyncConnection, ef_search: int) -> None:
    """`hnsw.ef_search` solo para la transacción en curso (`set_config(…, true)` = `SET LOCAL`)."""
    if ef_search < 1:
        raise ValueError("ef_search debe ser ≥ 1")
    await conexion.execute(text("SELECT set_config('hnsw.ef_search', :valor, true)"), {"valor": str(ef_search)})


async def buscar_vecinos(
    conexion: AsyncConnection,
    vectores: Sequence[Sequence[float]],
    *,
    k: int,
    version_vector: str,
    ef_search: int,
) -> list[list[Vecino]]:
    """Los `k` vecinos de cada vector (misma posición que en `vectores`), de mayor a menor similitud."""
    if k < 1:
        raise ValueError("k debe ser ≥ 1")
    sentencia = text(sql_vecinos(version_vector))
    await fijar_ef_search(conexion, max(ef_search, k))
    resultado: list[list[Vecino]] = []
    for vector in vectores:
        filas = await conexion.execute(sentencia, {"vector": texto_vector(vector), "k": k})
        vecinos = []
        for imagen_id, video_id, lat, lng, rumbo, lugar_id, distancia in filas.all():
            distancia = float(distancia)
            vecinos.append(
                Vecino(
                    imagen_id=imagen_id,
                    video_id=video_id,
                    lat=float(lat),
                    lng=float(lng),
                    rumbo=None if rumbo is None else float(rumbo),
                    lugar_id=lugar_id,
                    distancia=distancia,
                    similitud=max(-1.0, min(1.0, 1.0 - distancia)),
                )
            )
        resultado.append(vecinos)
    return resultado
