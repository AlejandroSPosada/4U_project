"""Dependencias comunes de los routers (ARCHITECTURE §4.4).

- `obtener_ajustes(request)`: los `Settings` con que se creó la app.
- `obtener_motor(request)`: el motor de `api` (`app.state.motor`). Sin motor (faltan `DB_*` o `DB_SSLMODE` no válido)
  lanza `BaseNoDisponible`, que se responde `503 BASE_NO_DISPONIBLE`. Cada unidad de trabajo abre su transacción con
  `async with sesion.transaccion(motor) as conexion:` (§4.4).
- `obtener_cola_hash(request)`: la `ColaHash` de la app, que acota las verificaciones argon2id del login
  (`LOGIN_HASH_*`, §5.10).
"""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db import sesion
from app.servicios.autenticacion import ColaHash


def obtener_ajustes(request: Request) -> Settings:
    return request.app.state.ajustes


def obtener_motor(request: Request) -> AsyncEngine:
    motor = getattr(request.app.state, "motor", None)
    if motor is None:
        raise sesion.BaseNoDisponible(getattr(request.app.state, "motivo_sin_motor", "configuracion_incompleta"))
    return motor


def obtener_cola_hash(request: Request) -> ColaHash:
    cola = getattr(request.app.state, "cola_hash", None)
    if cola is None:
        cola = request.app.state.cola_hash = ColaHash.desde(request.app.state.ajustes)
    return cola
