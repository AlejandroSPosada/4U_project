"""Videos del panel (ARCHITECTURE §5.5): `GET /v1/admin/videos` y `GET /v1/admin/videos/{id}` (BE-2.1; el resto de
videos, BE-4.1). Va en `RUTAS_ADMIN` (exige `requiere_admin`)."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencias import obtener_ajustes, obtener_motor
from app.config import Settings
from app.dominio.validaciones import motivo_texto_no_admitido
from app.errores import ErrorApi
from app.esquemas.comun import Pagina
from app.esquemas.errores import ErrorRespuesta
from app.esquemas.videos import Q_MAX, VideoDetalle, VideoResumen
from app.servicios import videos

router = APIRouter(prefix="/videos", tags=["videos"])

#: Tope de `pagina` (un OFFSET enorme desbordaría el entero de PostgreSQL).
PAGINA_TOPE = 100_000


@router.get(
    "",
    response_model=Pagina[VideoResumen],
    summary="Listar videos (sin los eliminados)",
    responses={422: {"model": ErrorRespuesta, "description": "VALIDACION"}},
)
async def listar_videos(
    request: Request,
    q: str | None = Query(None, max_length=Q_MAX, description="Texto contenido en el nombre (sin mayúsculas)"),
    orden: Literal["fecha", "nombre", "fotos"] = Query("fecha"),
    direccion: Literal["desc", "asc"] = Query("desc", alias="dir"),
    pagina: int = Query(1, ge=1, le=PAGINA_TOPE),
    por_pagina: int | None = Query(None, ge=1, description="Por defecto PAGINA_POR_DEFECTO; máximo PAGINA_MAX"),
    ajustes: Settings = Depends(obtener_ajustes),
) -> Pagina[VideoResumen]:
    campos = []
    if q is not None and (motivo := motivo_texto_no_admitido(q)) is not None:
        campos.append({"campo": "q", "motivo": motivo})
    if por_pagina is not None and por_pagina > ajustes.pagina_max:
        campos.append({"campo": "por_pagina", "motivo": f"Debe ser menor o igual que {ajustes.pagina_max}."})
    if campos:
        raise ErrorApi(422, "VALIDACION", detalle={"campos": campos})
    texto = (q or "").strip() or None
    return await videos.listar(
        obtener_motor(request),
        q=texto,
        orden=orden,
        direccion=direccion,
        pagina=pagina,
        por_pagina=por_pagina or ajustes.pagina_por_defecto,
    )


@router.get(
    "/{video_id}",
    response_model=VideoDetalle,
    summary="Detalle de un video con sus fotos en orden",
    responses={404: {"model": ErrorRespuesta, "description": "NO_ENCONTRADO (también si está eliminado)"}},
)
async def detalle_video(video_id: uuid.UUID, request: Request) -> VideoDetalle:
    try:
        return await videos.detalle(obtener_motor(request), video_id)
    except videos.VideoNoEncontrado:
        raise ErrorApi(404, "NO_ENCONTRADO") from None
