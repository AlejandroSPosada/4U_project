"""Lectura de videos para el panel (ARCHITECTURE §4.5, §5.5): `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}`.

BE-2.1 entrega solo las dos lecturas; BE-4.1 añade aquí renombrar y borrar. Los videos `eliminado` no aparecen en el
listado y su detalle es `VideoNoEncontrado` (→ 404, §5.6).

- `listar(motor, q=, orden=, direccion=, pagina=, por_pagina=)` → `Pagina[VideoResumen]`.
- `detalle(motor, video_id)` → `VideoDetalle` (fotos en `orden`, con `lugar` y sin URLs hasta BE-4.1).
- `resumen(conexion, video_id)` → `VideoResumen | None` dentro de una transacción ya abierta (lo usa la recolección).
- `contar(conexion, video_id)` → `Conteo` (fotos por estado).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db import sesion
from app.db.modelos import Imagen, Lugar, Usuario, Video
from app.dominio.enumerados import EstadoImagen, EstadoVideo
from app.dominio.recoleccion import Conteo, real_legible
from app.esquemas.comun import Pagina, Referencia
from app.esquemas.videos import ConteoFotos, ImagenAdmin, InicioRecorrido, VideoDetalle, VideoResumen

OrdenVideos = Literal["fecha", "nombre", "fotos"]
Direccion = Literal["desc", "asc"]


class VideoNoEncontrado(Exception):
    """No existe (o, en las lecturas, está `eliminado`)."""


class VideoEliminado(Exception):
    """Existe pero está `eliminado` (en las escrituras de recolección → 409 VIDEO_ELIMINADO)."""


# --- Consultas ----------------------------------------------------------------------------------------------------
def _subconsulta_conteo():
    def contar_estado(estado: EstadoImagen):
        return func.count().filter(Imagen.estado == estado).label(estado.value)

    return (
        select(
            Imagen.video_id.label("video_id"),
            *(contar_estado(estado) for estado in EstadoImagen),
            func.count().label("total"),
        )
        .group_by(Imagen.video_id)
        .subquery("conteo")
    )


def _consulta_resumen(conteo: Any):
    return (
        select(
            *Video.__table__.c,
            Usuario.nombre.label("creador_nombre"),
            *(func.coalesce(conteo.c[estado.value], 0).label(f"n_{estado.value}") for estado in EstadoImagen),
        )
        .join(Usuario, Usuario.id == Video.creado_por)
        .outerjoin(conteo, conteo.c.video_id == Video.id)
    )


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _conteo_de_fila(fila: Any) -> ConteoFotos:
    return ConteoFotos(**{estado.value: int(getattr(fila, f"n_{estado.value}")) for estado in EstadoImagen})


def resumen_de_fila(fila: Any) -> VideoResumen:
    """Fila de `_consulta_resumen` → `VideoResumen` (los `real` con su valor legible, §5.5)."""
    inicio = None
    if fila.inicio_lat is not None and fila.inicio_lng is not None:
        inicio = InicioRecorrido(lat=fila.inicio_lat, lng=fila.inicio_lng, rumbo=real_legible(fila.inicio_rumbo))
    return VideoResumen(
        id=fila.id,
        numero=fila.numero,
        nombre=fila.nombre,
        ref_cliente=fila.ref_cliente,
        estado=fila.estado,
        creado_en=fila.creado_en,
        iniciado_en=fila.iniciado_en,
        finalizado_en=fila.finalizado_en,
        duracion_s=fila.duracion_s,
        distancia_m=real_legible(fila.distancia_m),
        pasos=fila.pasos,
        inicio=inicio,
        total_fotos=fila.total_fotos_declaradas,
        conteo=_conteo_de_fila(fila),
        creado_por=Referencia(id=fila.creado_por, nombre=fila.creador_nombre),
    )


async def contar(conexion: AsyncConnection, video_id: uuid.UUID) -> Conteo:
    filas = await conexion.execute(
        select(Imagen.estado, func.count()).where(Imagen.video_id == video_id).group_by(Imagen.estado)
    )
    return Conteo.desde({str(estado): n for estado, n in filas})


async def resumen(conexion: AsyncConnection, video_id: uuid.UUID) -> VideoResumen | None:
    """`VideoResumen` del video (también si está `eliminado`), o `None` si no existe."""
    fila = (await conexion.execute(_consulta_resumen(_subconsulta_conteo()).where(Video.id == video_id))).first()
    return resumen_de_fila(fila) if fila is not None else None


# --- Casos de uso -------------------------------------------------------------------------------------------------
async def listar(
    motor: AsyncEngine,
    *,
    q: str | None = None,
    orden: OrdenVideos = "fecha",
    direccion: Direccion = "desc",
    pagina: int = 1,
    por_pagina: int = 24,
) -> Pagina[VideoResumen]:
    """Videos no eliminados; `q` filtra por `nombre` (contiene, sin distinguir mayúsculas; `%` y `_` son literales).
    `orden`: `fecha` (`creado_en`), `nombre` (en minúsculas) o `fotos` (fotos registradas); desempata `numero`."""
    conteo = _subconsulta_conteo()
    filtros = [Video.estado != EstadoVideo.eliminado]
    if q:
        filtros.append(Video.nombre.ilike(f"%{_escapar_like(q)}%", escape="\\"))
    columna = {
        "fecha": Video.creado_en,
        "nombre": func.lower(Video.nombre),
        "fotos": func.coalesce(conteo.c.total, 0),
    }[orden]
    criterio = [columna.desc(), Video.numero.desc()] if direccion == "desc" else [columna.asc(), Video.numero.asc()]
    async with sesion.transaccion(motor) as conexion:
        total = (await conexion.execute(select(func.count()).select_from(Video).where(*filtros))).scalar_one()
        filas = await conexion.execute(
            _consulta_resumen(conteo)
            .where(*filtros)
            .order_by(*criterio)
            .limit(por_pagina)
            .offset((pagina - 1) * por_pagina)
        )
        items = [resumen_de_fila(fila) for fila in filas]
    return Pagina[VideoResumen](items=items, total=total, pagina=pagina, por_pagina=por_pagina)


async def detalle(motor: AsyncEngine, video_id: uuid.UUID) -> VideoDetalle:
    """`VideoResumen` + `fotos` en `orden`. `VideoNoEncontrado` si no existe o está `eliminado`."""
    async with sesion.transaccion(motor) as conexion:
        fila = (await conexion.execute(_consulta_resumen(_subconsulta_conteo()).where(Video.id == video_id))).first()
        if fila is None or fila.estado == EstadoVideo.eliminado:
            raise VideoNoEncontrado(str(video_id))
        fotos = await conexion.execute(
            select(*Imagen.__table__.c, Lugar.nombre.label("lugar_nombre"))
            .outerjoin(Lugar, Lugar.id == Imagen.lugar_id)
            .where(Imagen.video_id == video_id)
            .order_by(Imagen.orden)
        )
        imagenes = [
            ImagenAdmin(
                id=foto.id,
                video_id=foto.video_id,
                orden=foto.orden,
                lat=foto.lat,
                lng=foto.lng,
                rumbo=real_legible(foto.rumbo),
                capturada_en=foto.capturada_en,
                estado=foto.estado,
                error=foto.error,
                calidad=foto.calidad,
                lugar=Referencia(id=foto.lugar_id, nombre=foto.lugar_nombre) if foto.lugar_id is not None else None,
                notas=foto.notas,
            )
            for foto in fotos
        ]
    return VideoDetalle(**resumen_de_fila(fila).model_dump(), fotos=imagenes)
