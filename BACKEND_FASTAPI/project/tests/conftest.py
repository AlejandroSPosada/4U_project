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


# --- S3 simulado (BE-2.1) ------------------------------------------------------------------------------------------
class AlmacenFalso:
    """Doble de `app.clientes.s3.AlmacenS3` con los objetos en memoria (§4.5). `subir(clave)` simula el `PUT` de la
    app; `fallar_head` (claves) y `fallar_firma` provocan `FalloS3`. Las URL llevan una firma falsa reconocible
    (`FIRMA_FALSA`) para comprobar que nunca llegan a los logs."""

    FIRMA_FALSA = "X-Amz-Signature=firma-falsa-de-pruebas"

    def __init__(self) -> None:
        from app.clientes.s3 import ObjetoS3

        self._objeto = ObjetoS3
        self.bucket = "bucket-de-pruebas"
        self.objetos: dict[str, object] = {}
        self.firmadas: list[str] = []
        self.consultadas: list[str] = []
        self.fallar_head: set[str] = set()
        self.fallar_firma = False

    def subir(self, clave: str, n_bytes: int = 1234) -> None:
        self.objetos[clave] = self._objeto(bytes=n_bytes, etag=f"etag{len(self.objetos)}")

    def firmar_put(self, clave: str, ttl_s: int):
        from datetime import UTC, datetime, timedelta

        from app.clientes.s3 import FalloS3, UrlFirmada

        if self.fallar_firma:
            raise FalloS3("firmar: NoCredentialsError")
        self.firmadas.append(clave)
        ahora = datetime.now(UTC).replace(microsecond=0)
        return UrlFirmada(
            url=f"https://{self.bucket}.s3.amazonaws.com/{clave}?{self.FIRMA_FALSA}",
            expira_en=ahora + timedelta(seconds=ttl_s),
        )

    def consultar(self, clave: str):
        from app.clientes.s3 import FalloS3

        self.consultadas.append(clave)
        if clave in self.fallar_head:
            raise FalloS3("head: ClientError: 500")
        return self.objetos.get(clave)

    def contar_prefijo(self, prefijo: str) -> int:
        return sum(1 for clave in self.objetos if clave.startswith(prefijo))

    def borrar_prefijo(self, prefijo: str) -> int:
        claves = [clave for clave in self.objetos if clave.startswith(prefijo)]
        for clave in claves:
            del self.objetos[clave]
        return len(claves)


@pytest.fixture
def almacen_falso() -> AlmacenFalso:
    return AlmacenFalso()
