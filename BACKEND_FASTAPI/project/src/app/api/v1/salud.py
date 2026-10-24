"""`GET /v1/health` y `GET /v1/health/ready` (ARCHITECTURE §4.2, §5.3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app import __version__
from app.clientes import embedding
from app.config import Settings
from app.esquemas.salud import PreparacionRespuesta, SaludRespuesta

router = APIRouter(prefix="/health", tags=["salud"])


def obtener_ajustes(request: Request) -> Settings:
    return request.app.state.ajustes


@router.get("", response_model=SaludRespuesta, summary="Indicador de conexión")
async def salud(ajustes: Settings = Depends(obtener_ajustes)) -> SaludRespuesta:
    """No consulta la base ni embeddings: lo usan la app y el *health check* del contenedor."""
    return SaludRespuesta(estado="ok", version=__version__, commit=ajustes.commit_corto)


@router.get("/ready", response_model=PreparacionRespuesta, summary="Diagnóstico de dependencias")
async def preparado(ajustes: Settings = Depends(obtener_ajustes)) -> PreparacionRespuesta:
    """Estado de las dependencias. `embedding` apagado (fuera de horario) **no** produce 503.

    Hasta BE-1.2 no existe la conexión a la base: `db` se informa como `no_configurada`.
    """
    listo = await embedding.esta_listo(ajustes)
    return PreparacionRespuesta(estado="ok", db="no_configurada", embedding="ok" if listo else "no_disponible")
