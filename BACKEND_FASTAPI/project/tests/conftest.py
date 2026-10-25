"""Fixtures comunes: una app con ajustes controlados (sin leer variables del entorno de quien prueba) y, para las
pruebas marcadas `base`, una base PostgreSQL efímera.

Pruebas con base (`@pytest.mark.base`): necesitan `PRUEBAS_DB_URL`, p. ej.
`postgresql://campus_app:pruebas@localhost:5432/campus_locator` (un rol que pueda crear bases y la extensión `vector`;
en CI, el servicio `pgvector/pgvector:pg17` de `backend.yml`). Cada prueba recibe una base nueva, que se borra al
terminar. Sin `PRUEBAS_DB_URL` se omiten, salvo con `PRUEBAS_DB_OBLIGATORIA=1` (CI), que las hace fallar.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.logs import crear_manejador
from app.main import crear_app

SHA_PRUEBA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def ajustes() -> Settings:
    return Settings(app_commit=SHA_PRUEBA, embedding_url=None, app_env="test", log_level="DEBUG")


@pytest.fixture
def app(ajustes: Settings) -> FastAPI:
    return crear_app(ajustes)


@pytest.fixture
def cliente(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


class CapturaJson:
    """Recoge las líneas JSON que produciría el manejador real (mismo formato y filtro)."""

    def __init__(self) -> None:
        self.flujo = io.StringIO()
        self.manejador = crear_manejador("api", self.flujo)
        self.manejador.setLevel(logging.DEBUG)

    @property
    def lineas(self) -> list[dict]:
        return [json.loads(linea) for linea in self.flujo.getvalue().splitlines() if linea.strip()]


@pytest.fixture
def logs_json() -> Iterator[CapturaJson]:
    captura = CapturaJson()
    raiz = logging.getLogger()
    raiz.addHandler(captura.manejador)
    try:
        yield captura
    finally:
        raiz.removeHandler(captura.manejador)


# --- Base de datos efímera (pruebas `base`) ----------------------------------------------------------------------
ADMIN_PRUEBA = "admin.pruebas@campus.edu.co"
PASSWORD_ADMIN_PRUEBA = "Pruebas-admin-123"


def _url_pruebas():
    from sqlalchemy.engine import make_url

    texto = os.environ.get("PRUEBAS_DB_URL", "").strip()
    if not texto:
        if os.environ.get("PRUEBAS_DB_OBLIGATORIA", "").strip() == "1":
            pytest.fail("PRUEBAS_DB_OBLIGATORIA=1 y falta PRUEBAS_DB_URL: las pruebas con base no pueden omitirse")
        pytest.skip("sin PRUEBAS_DB_URL (pruebas con base de datos)")
    return make_url(texto)


async def _sql_administracion(url, sentencia: str) -> None:
    import asyncpg

    conexion = await asyncpg.connect(
        host=url.host, port=url.port or 5432, user=url.username, password=url.password, database=url.database
    )
    try:
        await conexion.execute(sentencia)
    finally:
        await conexion.close()


@pytest.fixture
def base_vacia() -> Iterator[Settings]:
    """Ajustes que apuntan a una base recién creada (sin extensión ni tablas), borrada al terminar."""
    url = _url_pruebas()
    nombre = f"pruebas_{uuid.uuid4().hex[:12]}"
    asyncio.run(_sql_administracion(url, f'CREATE DATABASE "{nombre}"'))
    try:
        yield Settings(
            app_commit=SHA_PRUEBA,
            app_env="test",
            log_level="DEBUG",
            embedding_url=None,
            db_host=url.host,
            db_port=url.port or 5432,
            db_name=nombre,
            db_user=url.username,
            db_password=url.password,
            db_sslmode=url.query.get("sslmode", "disable"),
            db_connect_timeout_s=5,
            admin_inicial_correo=ADMIN_PRUEBA,
            admin_inicial_password=PASSWORD_ADMIN_PRUEBA,
        )
    finally:
        asyncio.run(_sql_administracion(url, f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))


@pytest.fixture
def base_migrada(base_vacia: Settings) -> Settings:
    """`base_vacia` tras `python -m app.cli migrar` (esquema de §5.7 y admin inicial)."""
    from app import cli

    assert cli.main(["migrar"], ajustes=base_vacia) == 0
    return base_vacia
