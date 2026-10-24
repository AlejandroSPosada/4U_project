"""Contrato HTTP de EMB-1.1: /health, /health/ready, /v1/info, X-Request-Id y errores (§5.1, §5.2).

Usa un modelo falso: el modelo real se prueba en test_modelo.py.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import Settings
from app.main import crear_app

COMMIT = "0123456789abcdef0123456789abcdef01234567"


class ModeloFalso:
    def __init__(self, liberar: threading.Event | None = None, falla: bool = False) -> None:
        self.liberar = liberar
        self.falla = falla
        self.calentado = False

    def cargar(self) -> None:
        if self.liberar is not None:
            assert self.liberar.wait(5), "la prueba no liberó la carga"
        if self.falla:
            raise RuntimeError("pesos corruptos")

    def calentar(self) -> None:
        self.calentado = True


def crear(modelo: ModeloFalso, al_fallar=lambda: None):
    settings = Settings(app_env="test", git_commit=COMMIT, torch_num_threads=1)
    return crear_app(
        settings=settings,
        fabrica_modelo=lambda _: modelo,
        al_fallar=al_fallar,
        configurar_registro=False,
    )


def esperar(condicion, plazo_s: float = 5.0) -> None:
    limite = time.monotonic() + plazo_s
    while not condicion():
        assert time.monotonic() < limite, "se venció el plazo"
        time.sleep(0.01)


@pytest.fixture
def cliente_listo():
    modelo = ModeloFalso()
    with TestClient(crear(modelo)) as cliente:
        esperar(lambda: cliente.get("/health/ready").status_code == 200)
        yield cliente


def test_health_responde_mientras_carga_y_ready_espera_al_calentamiento():
    liberar = threading.Event()
    modelo = ModeloFalso(liberar=liberar)
    with TestClient(crear(modelo)) as cliente:
        assert cliente.get("/health").json() == {"estado": "ok"}
        cargando = cliente.get("/health/ready")
        assert cargando.status_code == 503
        assert cargando.json() == {"estado": "cargando"}

        liberar.set()
        esperar(lambda: cliente.get("/health/ready").status_code == 200)
        assert cliente.get("/health/ready").json() == {"estado": "listo"}
        assert modelo.calentado


def test_carga_fallida_avisa_y_nunca_queda_lista():
    fallos = threading.Event()
    with TestClient(crear(ModeloFalso(falla=True), al_fallar=fallos.set)) as cliente:
        assert fallos.wait(5)
        assert cliente.get("/health/ready").status_code == 503
        assert cliente.get("/health").status_code == 200


def test_info_publica_el_contrato(cliente_listo):
    respuesta = cliente_listo.get("/v1/info")
    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "servicio": "campus-locator-embedding",
        "version": "0.1.0",
        "commit": COMMIT[:7],
        "modelo": "facebook/dinov2-small",
        "revision": config.MODELO_REVISION,
        "arquitectura": "ViT-S/14",
        "preprocesamiento": "pp-v1",
        "version_vector": "dinov2-vits14/pp-v1",
        "dim": 384,
        "normalizacion": "l2",
        "metrica": "coseno",
        "lote_max": 8,
        "dispositivo": "cpu",
    }


def test_info_responde_aunque_el_modelo_cargue():
    liberar = threading.Event()
    with TestClient(crear(ModeloFalso(liberar=liberar))) as cliente:
        assert cliente.get("/v1/info").json()["version_vector"] == "dinov2-vits14/pp-v1"
        liberar.set()


def test_x_request_id_se_respeta(cliente_listo):
    respuesta = cliente_listo.get("/health", headers={"X-Request-Id": "validacion-emb11-1"})
    assert respuesta.headers["X-Request-Id"] == "validacion-emb11-1"


def test_x_request_id_se_genera_si_falta_o_no_es_valido(cliente_listo):
    sin = cliente_listo.get("/health").headers["X-Request-Id"]
    invalido = cliente_listo.get("/health", headers={"X-Request-Id": "a b\nc"}).headers[
        "X-Request-Id"
    ]
    assert len(sin) == 32
    assert invalido != "a b\nc"
    assert len(invalido) == 32


def test_ruta_inexistente_usa_el_formato_de_error(cliente_listo):
    respuesta = cliente_listo.get("/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json()["error"]["codigo"] == "NO_ENCONTRADO"
    assert respuesta.json()["error"]["detalle"] is None
    assert "X-Request-Id" in respuesta.headers


def test_metodo_no_permitido_usa_el_formato_de_error(cliente_listo):
    respuesta = cliente_listo.post("/health")
    assert respuesta.status_code == 405
    assert respuesta.json()["error"]["codigo"] == "METODO_NO_PERMITIDO"


def test_error_no_previsto_responde_500_con_formato():
    app = crear(ModeloFalso())

    @app.get("/explota")
    def explota():
        raise RuntimeError("fallo inesperado")

    with TestClient(app, raise_server_exceptions=False) as cliente:
        respuesta = cliente.get("/explota", headers={"X-Request-Id": "validacion-500"})
    assert respuesta.status_code == 500
    assert respuesta.json() == {
        "error": {
            "codigo": "ERROR_INTERNO",
            "mensaje": "Error interno del servicio",
            "detalle": None,
        }
    }
    assert respuesta.headers["X-Request-Id"] == "validacion-500"


def test_sin_documentacion_interactiva_fuera_de_local(cliente_listo):
    assert cliente_listo.get("/docs").status_code == 404
    assert cliente_listo.get("/openapi.json").status_code == 404
