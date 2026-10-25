"""Línea de comandos del backend: `python -m app.cli <comando>` (ARCHITECTURE §5.9).

Comandos de BE-1.2, que corren como tarea suelta con la definición `campus-locator-dev-migrate`:
- `migrar`: migraciones Alembic y admin inicial (§4.3). Es el comando de la tarea `migrate` y el paso 2 de
  `backend.yml` (infra §5.9).
- `verificar-esquema`: compara la base con §5.7 sin modificar nada.

Todo lo que escriben son líneas JSON (§5.10) con `proceso = migrate`; los resultados son eventos de log.

Códigos de salida, comunes a todos los comandos de `app.cli` (§5.9):
- 0: hecho (`verificar-esquema`: la base coincide);
- 1: resultado negativo (`verificar-esquema`: difiere; `migrar`: falló una migración o el admin inicial);
- 2: no se pudo trabajar con la base (no conecta, credenciales, TLS, tiempo agotado o se perdió la conexión; en
  `verificar-esquema`, también un error al leer el catálogo);
- 3: uso o configuración (argumentos, variables con un valor no válido, `DB_*` o `ADMIN_INICIAL_*` que faltan).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import NoReturn

from pydantic import ValidationError

from app import __version__
from app.config import Settings, get_settings
from app.db import sesion
from app.logs import configurar_logs, obtener_logger, registrar
from app.servicios import migracion

PROCESO = "migrate"
SALIDA_OK, SALIDA_NEGATIVA, SALIDA_BASE, SALIDA_CONFIGURACION = 0, 1, 2, 3

log = obtener_logger("app.cli")  # estable también con `python -m app.cli`


class _Parser(argparse.ArgumentParser):
    """argparse sale con 2 ante un error de uso; aquí el 2 es «base no disponible», así que se usa el 3."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(SALIDA_CONFIGURACION, f"{self.prog}: error: {message}\n")


def crear_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m app.cli", description="Comandos del backend (ARCHITECTURE §5.9).")
    comandos = parser.add_subparsers(dest="comando", required=True, metavar="comando", parser_class=_Parser)
    comandos.add_parser("migrar", help="Aplica las migraciones y crea el admin inicial si no hay ningún admin")
    comandos.add_parser("verificar-esquema", help="Compara la base con el esquema de §5.7 (no modifica nada)")
    return parser


def _motor(ajustes: Settings):
    """Motor sin pool para la CLI, o `None` si la configuración está incompleta (ya registrado)."""
    try:
        return sesion.crear_motor(ajustes, PROCESO)
    except sesion.ConfiguracionIncompleta as exc:
        registrar(
            log, "configuracion_incompleta", logging.ERROR, faltan=exc.faltan, invalidas=exc.invalidas, motivo=str(exc)
        )
        return None


def _base_no_disponible(exc: BaseException) -> int:
    registrar(log, "base_no_disponible", logging.ERROR, motivo=sesion.describir(exc))
    return SALIDA_BASE


async def comando_migrar(ajustes: Settings) -> int:
    motor = _motor(ajustes)
    if motor is None:
        return SALIDA_CONFIGURACION
    inicio = time.perf_counter()
    try:
        registrar(
            log,
            "migracion_iniciada",
            version=__version__,
            commit=ajustes.commit_corto,
            entorno=ajustes.app_env,
            revision_objetivo=migracion.revision_head(),
        )
        resultado = await migracion.migrar(motor, ajustes)
    except migracion.AdminInicialSinConfigurar as exc:
        registrar(log, "configuracion_incompleta", logging.ERROR, faltan=exc.faltan, invalidas=[], motivo=str(exc))
        return SALIDA_CONFIGURACION
    except Exception as exc:
        if sesion.es_fallo_de_conexion(exc):
            return _base_no_disponible(exc)
        registrar(log, "migracion_fallida", logging.ERROR, motivo=sesion.describir(exc), exc_info=True)
        return SALIDA_NEGATIVA
    finally:
        await motor.dispose()
    campos = {"usuario_id": resultado.usuario_id} if resultado.usuario_id else {}
    registrar(
        log,
        "migracion_terminada",
        revision_anterior=resultado.revision_anterior,
        revision=resultado.revision,
        aplicada=resultado.revision_anterior != resultado.revision,
        admin_inicial=resultado.admin_inicial,
        duracion_ms=round((time.perf_counter() - inicio) * 1000),
        **campos,
    )
    return SALIDA_OK


async def comando_verificar_esquema(ajustes: Settings) -> int:
    motor = _motor(ajustes)
    if motor is None:
        return SALIDA_CONFIGURACION
    try:
        resultado = await migracion.verificar(motor)
    except Exception as exc:
        if sesion.es_fallo_de_conexion(exc):
            return _base_no_disponible(exc)
        registrar(log, "verificacion_fallida", logging.ERROR, motivo=sesion.describir(exc), exc_info=True)
        return SALIDA_BASE
    finally:
        await motor.dispose()
    for diferencia in resultado.diferencias:
        registrar(log, "esquema_diferencia", logging.WARNING, **diferencia.como_campos())
    coincide = not resultado.diferencias
    registrar(
        log,
        "esquema_verificado",
        logging.INFO if coincide else logging.WARNING,
        resultado="coincide" if coincide else "difiere",
        diferencias=len(resultado.diferencias),
        revision=resultado.catalogo.revision,
        revision_esperada=resultado.revision_esperada,
        servidor=resultado.catalogo.servidor,
        pgvector=resultado.catalogo.extensiones.get("vector"),
    )
    return SALIDA_OK if coincide else SALIDA_NEGATIVA


COMANDOS: dict[str, Callable[[Settings], Awaitable[int]]] = {
    "migrar": comando_migrar,
    "verificar-esquema": comando_verificar_esquema,
}


def main(argv: Sequence[str] | None = None, ajustes: Settings | None = None) -> int:
    try:
        argumentos = crear_parser().parse_args(argv)
    except SystemExit as salida:  # --help (0) o error de uso (3)
        return int(salida.code or 0)
    if ajustes is None:
        try:
            ajustes = get_settings()
        except ValidationError as exc:  # p. ej. DB_PORT=abc: código 3 y un evento JSON, no una traza suelta
            configurar_logs(PROCESO)
            invalidas = sorted({str(error["loc"][0]).upper() for error in exc.errors() if error.get("loc")})
            # `msg` no incluye el valor recibido (podría ser un secreto); `input` sí, y no se registra.
            motivo = "; ".join(f"{str(e['loc'][0]).upper()}: {e['msg']}" for e in exc.errors() if e.get("loc"))
            registrar(
                log, "configuracion_incompleta", logging.ERROR, faltan=[], invalidas=invalidas, motivo=motivo[:500]
            )
            return SALIDA_CONFIGURACION
    configurar_logs(PROCESO, ajustes.log_level)
    return asyncio.run(COMANDOS[argumentos.comando](ajustes))


if __name__ == "__main__":
    sys.exit(main())
