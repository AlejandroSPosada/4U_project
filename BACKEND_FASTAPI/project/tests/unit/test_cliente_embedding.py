"""Comprobación de disponibilidad de embeddings."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from app.clientes.embedding import esta_listo
from app.config import Settings

AJUSTES = Settings(embedding_url="http://embedding.prueba:8080")


def _transporte(manejador) -> httpx.MockTransport:
    return httpx.MockTransport(manejador)


@pytest.mark.parametrize(("estado", "esperado"), [(200, True), (503, False), (404, False)])
def test_segun_el_estado_de_health_ready(estado, esperado):
    vistas: list[str] = []

    def manejador(peticion: httpx.Request) -> httpx.Response:
        vistas.append(str(peticion.url))
        return httpx.Response(estado)

    assert asyncio.run(esta_listo(AJUSTES, _transporte(manejador))) is esperado
    assert vistas == ["http://embedding.prueba:8080/health/ready"]


def test_sin_conexion_es_no_disponible():
    def manejador(peticion: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin DNS", request=peticion)

    assert asyncio.run(esta_listo(AJUSTES, _transporte(manejador))) is False


def test_sin_url_configurada_es_no_disponible():
    assert asyncio.run(esta_listo(Settings(embedding_url=None))) is False
