"""GET /v1/health y GET /v1/health/ready (ARCHITECTURE §5.3)."""

from __future__ import annotations

import pytest

import app.clientes.embedding as cliente_embedding
from app import __version__


def test_health_responde_estado_version_y_commit_corto(cliente):
    r = cliente.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "version": __version__, "commit": "0123456"}


def test_health_no_redirige_con_barra_final(cliente):
    r = cliente.get("/v1/health/", follow_redirects=False)
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "NO_ENCONTRADO"


def test_ready_sin_base_ni_embedding(cliente):
    r = cliente.get("/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "db": "no_configurada", "embedding": "no_disponible"}


@pytest.mark.parametrize(("listo", "esperado"), [(True, "ok"), (False, "no_disponible")])
def test_ready_informa_embedding_sin_503(cliente, monkeypatch, listo, esperado):
    async def falso(_ajustes):
        return listo

    monkeypatch.setattr(cliente_embedding, "esta_listo", falso)
    r = cliente.get("/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["embedding"] == esperado
