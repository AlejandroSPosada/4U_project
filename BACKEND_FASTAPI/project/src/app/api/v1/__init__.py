"""Rutas `/v1` (ARCHITECTURE §5.3–§5.5). Cada lote añade aquí su router."""

from fastapi import APIRouter

from app.api.v1 import salud

router_v1 = APIRouter(prefix="/v1")
router_v1.include_router(salud.router)
