"""Localización (ARCHITECTURE §4.10, §5.3 `POST /v1/localize`), BE-3.2.

`localizar(motor, ajustes, fotos, rumbos, *, origen, app_version, inicio, request_id=None, vectorizar=None)` →
`ResultadoLocalizar`:
1. Vectoriza las 1–5 fotos en **una** llamada a `POST /v1/embed` con prioridad `alta`, con un tope total de
   `TOPE_EMBEDDING_S` (el de BE-2.4: los plazos de httpx son por fase, §4.6).
2. Compara la `version_vector` devuelta con `EMBEDDING_VERSION_VECTOR`: si no coincide, `VersionVectorDistinta` (no
   se busca con un vector incomparable).
3. En **una** transacción: `db.consultas.buscar_vecinos` (un vector por foto, `LOC_TOP_K`, `LOC_EF_SEARCH`), el
   algoritmo de `dominio.localizacion` (Python puro, microsegundos), los lugares (`lugares.leer_todos`, solo si hay
   posición) y la fila anónima de `eventos_localizacion` (§5.7). Si la escritura o el `COMMIT` fallan, la petición
   responde `503 BASE_NO_DISPONIBLE`: la respuesta y la tabla no se contradicen.

Las fotos no se guardan en ningún sitio ni se registran (ADR-BE-06). Excepciones (las traduce el router, §5.3):
`EmbeddingNoDisponible`, `ImagenRechazada` y `RespuestaNoValida` de `app.clientes.embedding`,
`servicios.diagnostico.VersionVectorDistinta` y `BaseNoDisponible` (de `sesion.transaccion`).
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass

import anyio
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clientes import embedding
from app.config import Settings
from app.db import consultas, sesion
from app.db.modelos import EventoLocalizacion
from app.dominio import localizacion
from app.esquemas.localizacion import DECIMALES_EVENTO
from app.servicios import lugares
from app.servicios.diagnostico import TOPE_EMBEDDING_S, Vectorizar, VersionVectorDistinta

__all__ = ["ResultadoLocalizar", "VersionVectorDistinta", "localizar", "parametros_de"]


@dataclass(frozen=True)
class ResultadoLocalizar:
    localizacion: localizacion.Localizacion
    lugar_cercano: localizacion.LugarContexto | None
    referencias: list[localizacion.LugarContexto]
    version_vector: str
    embedding_ms: int
    busqueda_ms: int
    latencia_ms: int


def parametros_de(ajustes: Settings) -> localizacion.Parametros:
    """Los `LOC_*` de §5.10 que usa el algoritmo."""
    return localizacion.Parametros(
        sim_min=ajustes.loc_sim_min,
        sim_alta=ajustes.loc_sim_alta,
        radio_grupo_m=ajustes.loc_radio_grupo_m,
        peso_exponente=ajustes.loc_peso_exponente,
        radio_min_m=ajustes.loc_radio_min_m,
        nivel_alta_min=ajustes.loc_nivel_alta_min,
        nivel_media_min=ajustes.loc_nivel_media_min,
        dispersion_rumbo_max=ajustes.loc_dispersion_rumbo_max,
        lugar_cercano_m=ajustes.loc_lugar_cercano_m,
        referencias_m=ajustes.loc_referencias_m,
        referencias_max=ajustes.loc_referencias_max,
    )


def _ms(desde: float) -> int:
    return max(0, int((time.perf_counter() - desde) * 1000))


async def localizar(
    motor: AsyncEngine,
    ajustes: Settings,
    fotos: Sequence[bytes],
    rumbos: Sequence[float | None],
    *,
    origen: str,
    app_version: str | None,
    inicio: float,
    request_id: str | None = None,
    vectorizar: Vectorizar | None = None,
) -> ResultadoLocalizar:
    """Lo del docstring del módulo. `inicio` es el `time.perf_counter()` del principio del endpoint (para
    `latencia_ms`); `vectorizar` sustituye a `embedding.vectorizar` en las pruebas."""

    async def por_defecto(imagenes: Sequence[bytes]) -> embedding.Vectores:
        return await embedding.vectorizar(ajustes, imagenes, prioridad="alta", request_id=request_id)

    llamar = vectorizar or por_defecto
    marca = time.perf_counter()
    try:
        with anyio.fail_after(TOPE_EMBEDDING_S):
            vectores = await llamar(list(fotos))
    except TimeoutError:
        raise embedding.EmbeddingNoDisponible(f"sin respuesta en {TOPE_EMBEDDING_S:g} s (tope total)") from None
    embedding_ms = _ms(marca)
    if vectores.version_vector != ajustes.embedding_version_vector:
        raise VersionVectorDistinta(ajustes.embedding_version_vector, vectores.version_vector)

    parametros = parametros_de(ajustes)
    marca = time.perf_counter()
    async with sesion.transaccion(motor) as conexion:
        vecinos = await consultas.buscar_vecinos(
            conexion,
            vectores.vectores,
            k=ajustes.loc_top_k,
            version_vector=ajustes.embedding_version_vector,
            ef_search=ajustes.loc_ef_search,
        )
        resultado = localizacion.localizar(vecinos, rumbos, parametros)
        cercano: localizacion.LugarContexto | None = None
        referencias: list[localizacion.LugarContexto] = []
        if resultado.posicion is not None:
            cercano, referencias = localizacion.contexto(
                resultado.posicion, await lugares.leer_todos(conexion), parametros
            )
        busqueda_ms = _ms(marca)
        latencia_ms = _ms(inicio)
        pos = resultado.posicion
        await conexion.execute(
            insert(EventoLocalizacion).values(
                origen=origen,
                resultado=str(resultado.resultado),
                nivel=None if resultado.nivel is None else str(resultado.nivel),
                confianza=resultado.confianza,
                lat=None if pos is None else round(pos.lat, DECIMALES_EVENTO),
                lng=None if pos is None else round(pos.lng, DECIMALES_EVENTO),
                fotos_usadas=resultado.fotos_usadas,
                fotos_con_coincidencia=resultado.fotos_con_coincidencia,
                latencia_ms=latencia_ms,
                version_vector=ajustes.embedding_version_vector,
                app_version=app_version,
            )
        )
    return ResultadoLocalizar(
        localizacion=resultado,
        lugar_cercano=cercano,
        referencias=referencias,
        version_vector=ajustes.embedding_version_vector,
        embedding_ms=embedding_ms,
        busqueda_ms=busqueda_ms,
        latencia_ms=latencia_ms,
    )
