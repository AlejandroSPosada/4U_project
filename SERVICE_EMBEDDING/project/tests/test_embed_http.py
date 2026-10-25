"""Contrato HTTP de POST /v1/embed (§4.3, §5.2, §5.6, §5.7) con un modelo falso.

El modelo falso devuelve un vector derivado de los píxeles preprocesados (media por canal), así se
comprueba el orden y la independencia del lote sin PyTorch. Los vectores reales se prueban con los
dorados (test_dorados.py) y con validate21 sobre la imagen.
"""

from __future__ import annotations

import io
import logging
import threading
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import DIM, VERSION_VECTOR, Settings
from app.main import crear_app
from app.preproceso import preprocesar

PLAZO_S = 5


class ModeloFalso:
    def __init__(self, liberar_carga: threading.Event | None = None) -> None:
        self.liberar_carga = liberar_carga
        self.retener = threading.Event()
        self.retener.set()  # sin retener salvo que la prueba lo pida
        self.empezo = threading.Event()
        self.lotes: list[np.ndarray] = []
        self.falla = False

    def cargar(self) -> None:
        if self.liberar_carga is not None:
            assert self.liberar_carga.wait(PLAZO_S)

    def calentar(self) -> None:
        pass

    def inferir(self, lote: np.ndarray) -> np.ndarray:
        self.empezo.set()
        assert self.retener.wait(PLAZO_S), "la prueba no liberó la inferencia"
        if self.falla:
            raise RuntimeError("sin memoria")
        self.lotes.append(lote)
        vectores = np.zeros((len(lote), DIM), dtype=np.float32)
        vectores[:, :3] = lote.mean(axis=(2, 3))
        vectores[:, 3] = 1.0
        return vectores / np.linalg.norm(vectores, axis=1, keepdims=True)


def crear(modelo: ModeloFalso, **parametros):
    settings = Settings(app_env="test", torch_num_threads=1, **parametros)
    return crear_app(settings=settings, fabrica_modelo=lambda _: modelo, configurar_registro=False)


def esperar(condicion, plazo_s: float = PLAZO_S) -> None:
    limite = time.monotonic() + plazo_s
    while not condicion():
        assert time.monotonic() < limite, "se venció el plazo"
        time.sleep(0.01)


@pytest.fixture
def modelo():
    return ModeloFalso()


@pytest.fixture
def cliente(modelo):
    with TestClient(crear(modelo)) as c:
        esperar(lambda: c.get("/health/ready").status_code == 200)
        yield c


def imagen(color, tamano=(320, 240), formato="JPEG") -> bytes:
    salida = io.BytesIO()
    Image.new("RGB", tamano, color).save(salida, formato)
    return salida.getvalue()


def partes(*imagenes: bytes, tipo: str = "image/jpeg", campo: str = "imagenes"):
    return [(campo, (f"validacion-{i}.jpg", datos, tipo)) for i, datos in enumerate(imagenes)]


def error(respuesta) -> dict:
    return respuesta.json()["error"]


COLORES = [(250, 10, 10), (10, 250, 10), (10, 10, 250), (128, 128, 0)]


def test_vectoriza_un_lote_en_el_orden_recibido(cliente):
    respuesta = cliente.post(
        "/v1/embed", files=partes(*(imagen(c) for c in COLORES[:3])), headers={"X-Request-Id": "x1"}
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["version_vector"] == VERSION_VECTOR
    assert cuerpo["dim"] == DIM
    assert set(cuerpo["tiempos_ms"]) == {"cola", "inferencia"}
    assert all(isinstance(v, int) for v in cuerpo["tiempos_ms"].values())
    vectores = np.array(cuerpo["vectores"], dtype=np.float32)
    assert vectores.shape == (3, DIM)
    np.testing.assert_allclose(np.linalg.norm(vectores, axis=1), 1.0, atol=1e-4)
    for i, color in enumerate(COLORES[:3]):
        sola = cliente.post("/v1/embed", files=partes(imagen(color))).json()["vectores"][0]
        np.testing.assert_array_equal(vectores[i], np.array(sola, dtype=np.float32))
    assert respuesta.headers["X-Request-Id"] == "x1"


def test_cada_peticion_es_un_solo_lote(cliente, modelo):
    cliente.post("/v1/embed", files=partes(*(imagen(c) for c in COLORES)))
    assert [len(lote) for lote in modelo.lotes] == [4]


def test_png_y_jpeg(cliente):
    respuesta = cliente.post(
        "/v1/embed",
        files=[
            ("imagenes", ("a.png", imagen(COLORES[0], formato="PNG"), "image/png")),
            ("imagenes", ("b.jpg", imagen(COLORES[1]), "image/jpeg")),
        ],
    )
    assert respuesta.status_code == 200
    assert len(respuesta.json()["vectores"]) == 2


@pytest.mark.parametrize("valor", ["alta", "baja", "ALTA", " Baja "])
def test_prioridades_admitidas(cliente, valor):
    respuesta = cliente.post(
        "/v1/embed", files=partes(imagen(COLORES[0])), headers={"X-Prioridad": valor}
    )
    assert respuesta.status_code == 200


def test_prioridad_desconocida_es_solicitud_invalida(cliente):
    respuesta = cliente.post(
        "/v1/embed", files=partes(imagen(COLORES[0])), headers={"X-Prioridad": "urgente"}
    )
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "SOLICITUD_INVALIDA"


def test_sin_partes_imagenes(cliente):
    respuesta = cliente.post("/v1/embed", files=partes(imagen(COLORES[0]), campo="fotos"))
    assert respuesta.status_code == 400
    assert error(respuesta) == {
        "codigo": "SOLICITUD_INVALIDA",
        "mensaje": "Faltan partes «imagenes»",
        "detalle": None,
    }


def test_cuerpo_que_no_es_multipart(cliente):
    respuesta = cliente.post("/v1/embed", json={"imagenes": []})
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "SOLICITUD_INVALIDA"


def test_multipart_incompleto(cliente):
    cuerpo = (
        b'--frontera\r\nContent-Disposition: form-data; name="imagenes"; filename="a.jpg"\r\n'
        b"Content-Type: image/jpeg\r\n\r\n" + imagen(COLORES[0])
    )
    respuesta = cliente.post(
        "/v1/embed",
        content=cuerpo,
        headers={"Content-Type": "multipart/form-data; boundary=frontera"},
    )
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "SOLICITUD_INVALIDA"


def test_frontera_demasiado_larga_es_solicitud_invalida(cliente):
    respuesta = cliente.post(
        "/v1/embed",
        content=b"x",
        headers={"Content-Type": "multipart/form-data; boundary=" + "x" * 500},
    )
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "SOLICITUD_INVALIDA"


def test_tipos_de_medio_sin_distinguir_mayusculas(cliente):
    datos = imagen(COLORES[0])
    cuerpo = (
        b'--f\r\nContent-Disposition: Form-Data; name="imagenes"; filename="a.jpg"\r\n'
        b"Content-Type: Image/JPEG\r\n\r\n" + datos + b"\r\n--f--\r\n"
    )
    respuesta = cliente.post(
        "/v1/embed", content=cuerpo, headers={"Content-Type": "Multipart/Form-Data; boundary=f"}
    )
    assert respuesta.status_code == 200
    assert len(respuesta.json()["vectores"]) == 1


def test_muchas_partes_se_cortan_en_la_novena_imagen(cliente):
    partes_vacias = [("otro", ("x", b"", "text/plain"))] * 200
    respuesta = cliente.post("/v1/embed", files=partes_vacias + partes(*[imagen(COLORES[0])] * 20))
    assert respuesta.status_code == 413
    assert error(respuesta)["detalle"] is None


def test_imagen_demasiado_alargada(cliente):
    respuesta = cliente.post("/v1/embed", files=partes(imagen(COLORES[0], tamano=(64, 3000))))
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "IMAGEN_INVALIDA"
    assert error(respuesta)["detalle"] == {"indice": 0}


def test_mas_de_8_imagenes(cliente):
    respuesta = cliente.post("/v1/embed", files=partes(*[imagen(COLORES[0])] * 9))
    assert respuesta.status_code == 413
    assert error(respuesta)["codigo"] == "LOTE_DEMASIADO_GRANDE"
    assert error(respuesta)["detalle"] is None


def test_limites_de_bytes_por_imagen_y_por_peticion(modelo):
    grande = imagen(COLORES[0], tamano=(800, 600), formato="PNG")
    pequena = imagen(COLORES[1], tamano=(100, 100))
    limites = {"bytes_max_imagen": len(grande) - 1, "bytes_max_peticion": 3 * len(grande)}
    with TestClient(crear(modelo, **limites)) as c:
        una = c.post(
            "/v1/embed",
            files=[
                ("imagenes", ("p.jpg", pequena, "image/jpeg")),
                ("imagenes", ("g.png", grande, "image/png")),
            ],
        )
        assert una.status_code == 413
        assert error(una)["codigo"] == "LOTE_DEMASIADO_GRANDE"
        assert error(una)["detalle"] == {"indice": 1}

        total = c.post("/v1/embed", files=partes(*[pequena] * 2, grande[:-10] * 4))
        assert total.status_code == 413
        assert error(total)["detalle"] is None

        troceado = c.post(  # sin Content-Length: se cuenta lo recibido
            "/v1/embed",
            content=iter([b"x" * len(grande)] * 4),
            headers={"Content-Type": "multipart/form-data; boundary=frontera"},
        )
        assert troceado.status_code == 413


@pytest.mark.parametrize("tipo", ["image/gif", "application/octet-stream", "image/jpg"])
def test_tipo_no_soportado_con_su_indice(cliente, tipo):
    respuesta = cliente.post(
        "/v1/embed",
        files=[
            ("imagenes", ("a.jpg", imagen(COLORES[0]), "image/jpeg")),
            ("imagenes", ("b", imagen(COLORES[1]), tipo)),
        ],
    )
    assert respuesta.status_code == 415
    assert error(respuesta)["codigo"] == "TIPO_NO_SOPORTADO"
    assert error(respuesta)["detalle"] == {"indice": 1}


def test_imagen_corrupta_en_la_posicion_3(cliente, modelo):
    buena = imagen(COLORES[0])
    respuesta = cliente.post("/v1/embed", files=partes(buena, buena, buena[:200], buena))
    assert respuesta.status_code == 400
    assert error(respuesta)["codigo"] == "IMAGEN_INVALIDA"
    assert error(respuesta)["detalle"] == {"indice": 2}
    assert modelo.lotes == []  # se rechaza la petición completa


def test_imagen_de_menos_de_64_px(cliente):
    respuesta = cliente.post("/v1/embed", files=partes(imagen(COLORES[0], tamano=(63, 300))))
    assert respuesta.status_code == 400
    assert error(respuesta)["detalle"] == {"indice": 0}
    assert "64 px" in error(respuesta)["mensaje"]


def test_no_listo_mientras_carga():
    liberar = threading.Event()
    with TestClient(crear(ModeloFalso(liberar_carga=liberar))) as c:
        respuesta = c.post("/v1/embed", files=partes(imagen(COLORES[0])))
        assert respuesta.status_code == 503
        assert error(respuesta)["codigo"] == "NO_LISTO"
        liberar.set()


def en_paralelo(cliente, peticiones):
    """Lanza cada (archivos, encabezados) en un hilo, en orden; devuelve las respuestas."""
    respuestas: list = [None] * len(peticiones)

    def enviar(i, archivos, encabezados):
        respuestas[i] = cliente.post("/v1/embed", files=archivos, headers=encabezados)

    hilos = []
    for i, (archivos, encabezados, antes) in enumerate(peticiones):
        antes()
        hilo = threading.Thread(target=enviar, args=(i, archivos, encabezados))
        hilo.start()
        hilos.append(hilo)
    return hilos, respuestas


def test_saturado_con_retry_after(modelo):
    modelo.retener.clear()
    with TestClient(crear(modelo, cola_max_imagenes=2, lote_max=2)) as c:
        esperar(lambda: c.get("/health/ready").status_code == 200)
        planificador = c.app.state.estado.planificador
        hilos, respuestas = en_paralelo(
            c,
            [
                (partes(imagen(COLORES[0])), {}, lambda: None),
                (partes(imagen(COLORES[1]), imagen(COLORES[2])), {}, modelo.empezo.wait),
            ],
        )
        esperar(lambda: planificador.imagenes_en_espera == 2)
        saturada = c.post("/v1/embed", files=partes(imagen(COLORES[3])))
        modelo.retener.set()
        for hilo in hilos:
            hilo.join(PLAZO_S)
    assert saturada.status_code == 503
    assert error(saturada)["codigo"] == "SATURADO"
    assert saturada.headers["Retry-After"] == "5"
    assert [r.status_code for r in respuestas] == [200, 200]


def test_alta_adelanta_a_las_bajas_que_esperan(modelo):
    modelo.retener.clear()
    with TestClient(crear(modelo)) as c:
        esperar(lambda: c.get("/health/ready").status_code == 200)
        planificador = c.app.state.estado.planificador

        def esperar_cola(n):
            return lambda: esperar(lambda: planificador.imagenes_en_espera == n)

        hilos, respuestas = en_paralelo(
            c,
            [
                (partes(imagen(COLORES[0])), {}, lambda: None),
                (partes(imagen(COLORES[1])), {}, modelo.empezo.wait),
                (partes(imagen(COLORES[2])), {}, esperar_cola(1)),
                (partes(imagen(COLORES[3])), {"X-Prioridad": "alta"}, esperar_cola(2)),
            ],
        )
        esperar_cola(3)()
        modelo.retener.set()
        for hilo in hilos:
            hilo.join(PLAZO_S)
    assert [r.status_code for r in respuestas] == [200] * 4
    tensores = [preprocesar(imagen(color)) for color in COLORES]
    orden = [
        next(i for i, tensor in enumerate(tensores) if np.array_equal(lote[0], tensor))
        for lote in modelo.lotes
    ]
    # La 0 ya estaba en curso; después va la alta (3) y luego las bajas por orden de llegada.
    assert orden == [0, 3, 1, 2]


def test_registro_de_la_peticion(cliente, caplog):
    with caplog.at_level(logging.INFO, logger="embedding"):
        cliente.post("/v1/embed", files=partes(imagen(COLORES[0])), headers={"X-Prioridad": "alta"})
    registro = next(r for r in caplog.records if r.getMessage() == "peticion")
    assert registro.ruta == "/v1/embed"
    assert registro.estado_http == 200
    assert registro.prioridad == "alta"
    assert registro.n_imagenes == 1
    assert isinstance(registro.cola_ms, int)
    assert isinstance(registro.inferencia_ms, int)


def test_fallo_del_modelo_es_error_interno(modelo):
    modelo.falla = True
    with TestClient(crear(modelo), raise_server_exceptions=False) as c:
        esperar(lambda: c.get("/health/ready").status_code == 200)
        respuesta = c.post("/v1/embed", files=partes(imagen(COLORES[0])))
    assert respuesta.status_code == 500
    assert error(respuesta)["codigo"] == "ERROR_INTERNO"
    assert "X-Request-Id" in respuesta.headers


def test_get_no_permitido(cliente):
    assert error(cliente.get("/v1/embed"))["codigo"] == "METODO_NO_PERMITIDO"
