"""Pruebas de contrato: las respuestas cumplen exactamente los esquemas de ARCHITECTURE §5.1 y §5.3."""

from __future__ import annotations

import tomllib
from pathlib import Path

from app import __version__
from app.esquemas.errores import ErrorRespuesta
from app.esquemas.salud import PreparacionRespuesta, SaludRespuesta

RAIZ = Path(__file__).resolve().parents[2]


def test_health_cumple_el_esquema(cliente):
    cuerpo = cliente.get("/v1/health").json()
    SaludRespuesta.model_validate(cuerpo)  # extra="forbid": ni más ni menos campos
    assert set(cuerpo) == {"estado", "version", "commit"}


def test_ready_cumple_el_esquema(cliente):
    cuerpo = cliente.get("/v1/health/ready").json()
    PreparacionRespuesta.model_validate(cuerpo)
    assert set(cuerpo) == {"estado", "db", "embedding"}


def test_errores_cumplen_el_esquema(cliente):
    for metodo, ruta in (("GET", "/v1/no-existe"), ("DELETE", "/v1/health"), ("GET", "/no-v1")):
        r = cliente.request(metodo, ruta)
        assert r.status_code >= 400
        ErrorRespuesta.model_validate(r.json())


def test_openapi_publica_las_rutas_del_lote(cliente):
    rutas = cliente.get("/v1/openapi.json").json()["paths"]
    assert {"/v1/health", "/v1/health/ready"} <= set(rutas)


def test_version_del_paquete_coincide_con_pyproject():
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert datos["project"]["version"] == __version__
