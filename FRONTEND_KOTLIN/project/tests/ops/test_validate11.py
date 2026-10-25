"""Pruebas de validate11.py con Gradle, adb y HTTP simulados."""

from __future__ import annotations

import json
from pathlib import Path

import comun
import pytest
import validate11

URL = "https://api.example.com/v1"


def test_lineas_salud_filtra_por_hora_y_reconoce_fallos():
    texto = "\n".join(
        [
            "2026-10-25 17:00:00.000 I/Api [OkHttp https://x/...] [-] GET /v1/health -> 200 (80 ms) rid=viejo",
            "2026-10-25 17:05:01.123 I/Api [OkHttp https://x/...] [-] GET /v1/health -> falla UnknownHostException "
            "(3 ms) rid=r1",
            "2026-10-25 17:05:16.500 I/Api [OkHttp https://x/...] [-] GET /v1/health -> 200 (95 ms) rid=r2",
            "2026-10-25 17:05:17.000 I/App [main] [-] otra cosa",
        ]
    )
    assert validate11.lineas_salud(texto, "2026-10-25 17:05:00") == [
        ("2026-10-25 17:05:01", "falla", "r1"),
        ("2026-10-25 17:05:16", "200", "r2"),
    ]


class _Simulado:
    """Gradle, adb y HTTP falsos para recorrer el validador entero."""

    def __init__(self, tmp_path: Path, *, salud=200, url_app=URL, fallos_c2=0):
        self.tmp = tmp_path
        self.salud = salud
        self.url_app = url_app
        self.fallos_c2 = fallos_c2

    def instalar(self, monkeypatch):
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: self.url_app)
        monkeypatch.setattr(comun, "http_get", self.http_get)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "adb", self.adb)
        monkeypatch.setattr(comun, "leer_archivo_app", self.leer)
        monkeypatch.setattr(validate11.time, "sleep", lambda s: None)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")

    def gradle(self, *args, timeout=0):
        if "testDebugUnitTest" in args:
            for clase in validate11.CLASES_C2:
                (self.tmp / f"TEST-com.example.myapplication.data.remote.{clase}.xml").write_text(
                    f'<testsuite tests="10" failures="{self.fallos_c2}" errors="0" skipped="0"/>', encoding="utf-8"
                )
            return comun.Resultado(1 if self.fallos_c2 else 0, "", "")
        return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11\n", "")

    def http_get(self, url, timeout=15.0):
        cuerpo = json.dumps({"estado": "ok", "version": "0.1.0", "commit": "9f6ed19"})
        return comun.RespuestaHttp(self.salud, {}, cuerpo if self.salud == 200 else '{"message":"x"}', 50)

    def adb(self, *args, timeout=0):
        if args[:2] == ("shell", "date"):
            return comun.Resultado(0, "2026-10-25_17:05:00\n", "")
        return comun.Resultado(0, "Status: ok\n", "")

    def leer(self, ruta):
        return "2026-10-25 17:05:02.000 I/Api [OkHttp] [-] GET /v1/health -> 200 (90 ms) rid=abc\n"


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate11.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def test_dev_todo_bien(tmp_path, monkeypatch):
    _Simulado(tmp_path).instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0
    assert _estados(datos) == {"C1a": "pasa", "C2": "pasa", "C4a": "pasa", "C4b": "pasa"}
    assert [m["id"] for m in datos["manuales"]] == ["C1b", "C3"]


def test_local_omite_lo_del_telefono(tmp_path, monkeypatch):
    _Simulado(tmp_path).instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0
    assert _estados(datos) == {"C1a": "omitida", "C2": "pasa", "C4a": "pasa", "C4b": "omitida"}
    assert [p["id"] for p in datos["precondiciones"]] == ["P1"]


def test_backend_caido_es_bloqueo(tmp_path, monkeypatch):
    _Simulado(tmp_path, salud=500).instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert datos["resultado"] == "bloqueado"
    assert datos["comprobaciones"] == []


def test_api_config_desactualizado_falla_c4a(tmp_path, monkeypatch):
    _Simulado(tmp_path, url_app="https://vieja.example.com/v1").instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 1
    assert _estados(datos)["C4a"] == "falla"


def test_pruebas_que_fallan_fallan_c2(tmp_path, monkeypatch):
    _Simulado(tmp_path, fallos_c2=2).instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local", ["--solo", "C2"])
    assert codigo == 1
    assert _estados(datos) == {"C1a": "omitida", "C2": "falla", "C4a": "omitida", "C4b": "omitida"}


def test_sin_dispositivo_es_3(tmp_path, monkeypatch):
    _Simulado(tmp_path).instalar(monkeypatch)

    def sin_telefono():
        raise comun.ErrorConfiguracion("adb devices no muestra ningún dispositivo")

    monkeypatch.setattr(comun, "dispositivo_fisico", sin_telefono)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert datos["resultado"] == "error"


@pytest.mark.parametrize("linea", ["", "2026-10-25 17:05:02.000 I/Api [x] [-] GET /v1/health -> falla X (1 ms) rid=r"])
def test_c1a_sin_200_falla(tmp_path, monkeypatch, linea):
    sim = _Simulado(tmp_path)
    sim.instalar(monkeypatch)
    monkeypatch.setattr(comun, "leer_archivo_app", lambda ruta: linea)
    monkeypatch.setattr(validate11, "ESPERA_C1A_S", 0)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert _estados(datos)["C1a"] == "falla"
