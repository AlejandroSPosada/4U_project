"""Rutas `/v1` (ARCHITECTURE §5.3–§5.5). Cada lote añade aquí su router.

Todo lo que cuelga de `/v1/admin` y `/v1/collect` exige `requiere_admin` (§4.4): esos dos routers la llevan como
dependencia, y un lote que añada rutas ahí incluye su router (sin prefijo `/admin` ni `/collect`) en `RUTAS_ADMIN` o
`RUTAS_COLLECT`, nunca directamente en `router_v1`. Una prueba (`tests/api/test_auth.py`) comprueba que toda ruta de
esos prefijos responde 401 sin token.
"""

from fastapi import APIRouter, Depends

from app.api.v1 import admin_diagnostico, admin_videos, auth, collect, lugares, reservados, salud
from app.esquemas.errores import ErrorRespuesta
from app.seguridad.dependencias import requiere_admin

#: Respuestas de `requiere_admin` que se documentan en cada ruta protegida del OpenAPI.
RESPUESTAS_PROTEGIDAS = {
    401: {"model": ErrorRespuesta, "description": "NO_AUTENTICADO · TOKEN_INVALIDO · TOKEN_EXPIRADO"},
    403: {"model": ErrorRespuesta, "description": "SIN_PERMISOS"},
    503: {"model": ErrorRespuesta, "description": "BASE_NO_DISPONIBLE"},
}

#: Routers de `/v1/admin/*` (BE-2.1: videos; BE-2.3: stats; BE-2.4: diagnóstico; BE-3.1: lugares; BE-3.3: alertas…).
RUTAS_ADMIN: list[APIRouter] = [
    reservados.router_admin,
    admin_videos.router,
    admin_diagnostico.router,
    lugares.router_admin,
]
#: Routers de `/v1/collect/*` (BE-2.1).
RUTAS_COLLECT: list[APIRouter] = [collect.router]


def _protegido(prefijo: str, routers: list[APIRouter]) -> APIRouter:
    protegido = APIRouter(prefix=prefijo, dependencies=[Depends(requiere_admin)], responses=RESPUESTAS_PROTEGIDAS)
    for router in routers:
        protegido.include_router(router)
    return protegido


router_v1 = APIRouter(prefix="/v1")
router_v1.include_router(salud.router)
router_v1.include_router(auth.router)
router_v1.include_router(reservados.router_publico)
router_v1.include_router(lugares.router_publico)
router_v1.include_router(_protegido("/admin", RUTAS_ADMIN))
router_v1.include_router(_protegido("/collect", RUTAS_COLLECT))
