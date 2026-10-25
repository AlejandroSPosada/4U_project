"""Cola con prioridad y hilo único de inferencia (§4.3, §5.7, ADR-EMB-07), con un cálculo falso."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from app.planificador import Detenido, Planificador, Saturado

PLAZO_S = 5


class CalculoFalso:
    """Registra el orden y la concurrencia; el primer lote espera a que la prueba lo libere."""

    def __init__(self, retener_primero: bool = True) -> None:
        self.orden: list[str] = []
        self.en_curso = 0
        self.max_en_curso = 0
        self.empezo = threading.Event()
        self.liberar = threading.Event()
        if not retener_primero:
            self.liberar.set()
        self._candado = threading.Lock()

    def __call__(self, imagenes):
        with self._candado:
            self.en_curso += 1
            self.max_en_curso = max(self.max_en_curso, self.en_curso)
        self.empezo.set()
        assert self.liberar.wait(PLAZO_S), "la prueba no liberó el lote"
        self.orden.append(imagenes[0].decode())
        with self._candado:
            self.en_curso -= 1
        if imagenes[0] == b"falla":
            raise ValueError("imagen rota")
        return np.zeros((len(imagenes), 4), dtype=np.float32)


@pytest.fixture
def calculo():
    return CalculoFalso()


@pytest.fixture
def planificador(calculo):
    p = Planificador(calculo, cola_max_imagenes=10).iniciar()
    yield p
    calculo.liberar.set()
    p.detener()


def imagenes(nombre: str, n: int = 1) -> list[bytes]:
    return [nombre.encode()] * n


def test_alta_antes_que_baja_y_fifo_dentro_de_cada_prioridad(planificador, calculo):
    en_curso = planificador.enviar(imagenes("baja-0"), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    futuros = [
        planificador.enviar(imagenes("baja-1"), "baja"),
        planificador.enviar(imagenes("baja-2"), "baja"),
        planificador.enviar(imagenes("alta-1"), "alta"),
        planificador.enviar(imagenes("alta-2"), "alta"),
    ]
    calculo.liberar.set()
    for futuro in [en_curso, *futuros]:
        futuro.result(PLAZO_S)
    # La prioridad no interrumpe el lote en curso (baja-0).
    assert calculo.orden == ["baja-0", "alta-1", "alta-2", "baja-1", "baja-2"]


def test_una_sola_inferencia_a_la_vez():
    calculo = CalculoFalso(retener_primero=False)
    p = Planificador(calculo, cola_max_imagenes=100).iniciar()
    futuros = [p.enviar(imagenes(f"b{i}"), "baja") for i in range(20)]
    for futuro in futuros:
        futuro.result(PLAZO_S)
    p.detener()
    assert calculo.max_en_curso == 1


def test_admision_sin_contar_el_lote_en_curso(planificador, calculo):
    planificador.enviar(imagenes("en-curso", 8), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    planificador.enviar(imagenes("a", 8), "baja")
    planificador.enviar(imagenes("b", 2), "alta")  # 10 en espera = máximo: entra
    assert planificador.imagenes_en_espera == 10
    with pytest.raises(Saturado):
        planificador.enviar(imagenes("c", 1), "alta")
    calculo.liberar.set()


def test_vuelve_a_admitir_cuando_la_cola_baja(planificador, calculo):
    planificador.enviar(imagenes("en-curso"), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    futuro = planificador.enviar(imagenes("llena", 10), "baja")
    with pytest.raises(Saturado):
        planificador.enviar(imagenes("rechazada"), "baja")
    calculo.liberar.set()
    futuro.result(PLAZO_S)
    assert planificador.imagenes_en_espera == 0
    planificador.enviar(imagenes("admitida"), "baja").result(PLAZO_S)


def test_tiempos_de_cola_e_inferencia(planificador, calculo):
    primero = planificador.enviar(imagenes("lento"), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    segundo = planificador.enviar(imagenes("espera"), "alta")
    time.sleep(0.2)
    calculo.liberar.set()
    r1, r2 = primero.result(PLAZO_S), segundo.result(PLAZO_S)
    assert r1.inferencia_ms >= 150  # incluye la espera del cálculo falso
    assert r2.cola_ms >= 150  # esperó a que terminara el lote en curso
    assert r1.vectores.shape == (1, 4)


def test_un_error_falla_solo_su_peticion(planificador, calculo):
    calculo.liberar.set()
    with pytest.raises(ValueError, match="imagen rota"):
        planificador.enviar(imagenes("falla"), "baja").result(PLAZO_S)
    assert planificador.enviar(imagenes("bien"), "baja").result(PLAZO_S).vectores.shape == (1, 4)


def test_una_peticion_cancelada_no_se_calcula(planificador, calculo):
    planificador.enviar(imagenes("en-curso"), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    cancelada = planificador.enviar(imagenes("cancelada"), "baja")
    assert cancelada.cancel()
    siguiente = planificador.enviar(imagenes("siguiente"), "baja")
    calculo.liberar.set()
    siguiente.result(PLAZO_S)
    assert "cancelada" not in calculo.orden


def test_detener_falla_lo_que_esperaba(calculo):
    p = Planificador(calculo, cola_max_imagenes=10).iniciar()
    p.enviar(imagenes("en-curso"), "baja")
    assert calculo.empezo.wait(PLAZO_S)
    esperando = p.enviar(imagenes("esperando"), "baja")
    threading.Timer(0.1, calculo.liberar.set).start()
    p.detener()
    with pytest.raises(Detenido):
        esperando.result(PLAZO_S)
    with pytest.raises(Detenido):
        p.enviar(imagenes("tarde"), "baja")


def test_prioridad_desconocida(planificador):
    with pytest.raises(ValueError):
        planificador.enviar(imagenes("x"), "urgente")
