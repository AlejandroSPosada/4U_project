"""Pruebas de comun.LectorCola (movida desde validate21.py en INF-3.1) y de su uso en validate21.py."""

from __future__ import annotations

import datetime as dt
import json

import pytest

import comun
import falsos
import validate21

SELLO = "20261028-150000"
URL = f"{falsos.URL_COLA}campus-locator-dev-ingesta"


def mensaje_21(sello: str, n: int = 1) -> str:
    return json.dumps({"Event": "s3:TestEvent", "RequestId": f"validacion-2-1-{sello}-{n}"})


@pytest.fixture
def mundo(monkeypatch):
    m = falsos.Mundo()
    m.colas[URL] = []
    monkeypatch.setattr(comun, "time", falsos.Reloj(m))
    monkeypatch.setattr(comun, "ahora_utc", m.ahora)
    return m


def test_lector_borra_propios_y_restos_y_devuelve_ajenos(mundo):
    sqs = falsos.Sqs(mundo)
    viejo = (mundo.t - dt.timedelta(hours=1)).strftime("%Y%m%d-%H%M%S")
    for cuerpo in (mensaje_21(SELLO), mensaje_21(viejo), '{"Records": []}', "no es json"):
        sqs.send_message(QueueUrl=URL, MessageBody=cuerpo)
    clasificados = {"propio": 0, "resto": 0, "ajeno": 0}

    def clasificar(cuerpo: str) -> str:
        clase = validate21.clasificar(cuerpo, SELLO)
        clasificados[clase] += 1
        return clase

    lec = comun.LectorCola(sqs, URL, "campus-locator-dev-ingesta", clasificar, ocultar_s=120)
    lec.leer(20)
    assert lec.borrados == 2 and len(lec.ajenos) == 2
    restantes = mundo.colas[URL]
    assert all(m["visible_desde"] > mundo.t for m in restantes)  # ocultos hasta devolver
    lec.devolver()
    assert [m["Body"] for m in restantes] == ['{"Records": []}', "no es json"]
    assert all(m["visible_desde"] <= mundo.t and m["recibido"] == 1 for m in restantes)
    assert clasificados == {"propio": 1, "resto": 1, "ajeno": 2}


def test_lector_con_objetivo_para_al_llegar(mundo):
    sqs = falsos.Sqs(mundo)
    for n in range(3):
        sqs.send_message(QueueUrl=URL, MessageBody=mensaje_21(SELLO, n))
    lec = comun.LectorCola(sqs, URL, "cola", lambda c: "propio")
    lec.leer(20, objetivo=1)
    assert lec.borrados == 3  # una lectura trae hasta 10: borra lo que recibió en esa lectura
    assert mundo.colas[URL] == []


def test_lector_traduce_errores_de_permiso(mundo):
    class SinPermiso(falsos.Sqs):
        def receive_message(self, **_):
            raise falsos.error("AccessDenied", "ReceiveMessage")

    lec = comun.LectorCola(SinPermiso(mundo), URL, "cola", lambda c: "propio")
    with pytest.raises(comun.ErrorConfiguracion):
        lec.leer(20)


def test_validate21_usa_el_lector_comun(mundo):
    sqs = falsos.Sqs(mundo)
    sqs.send_message(QueueUrl=URL, MessageBody=mensaje_21(SELLO))
    sqs.send_message(QueueUrl=URL, MessageBody="ajeno")

    class Op:
        def cliente(self, nombre):
            assert nombre == "sqs"
            return sqs

    ctx = validate21.Contexto(sello=SELLO, op=Op(), urls={"ingesta": URL, "purga": URL})
    lec = validate21.lector(ctx, "ingesta")
    assert isinstance(lec, comun.LectorCola) and lec.ocultar_s == validate21.OCULTAR_S
    lec.leer(20)
    lec.devolver()
    assert mundo.borrados == [mensaje_21(SELLO)]
    assert [m["Body"] for m in mundo.colas[URL]] == ["ajeno"]
