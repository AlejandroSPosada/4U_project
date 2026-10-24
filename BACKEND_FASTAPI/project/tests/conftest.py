"""Fixtures comunes: una app con ajustes controlados (sin leer variables del entorno de quien prueba)."""

from __future__ import annotations

import io
import json
import logging
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
