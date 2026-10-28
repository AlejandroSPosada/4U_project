"""Pruebas de validate53.py con Gradle, adb, el teléfono (uiautomator, app.log) y la API simulados."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate53

URL = "https://api.ejemplo/v1"
CASOS = {
    "TrazadoRutaTest": 4,
    "AnunciadorTest": 5,
    "GuiaNavegacionTest": 6,
    "AlertasEnRutaTest": 2,
    "ReglaMezclaTest": 6,
    "RemoteFrameRepositoryTest": 4,
    "ComandoGuiaTest": 2,
    "ColaVozTest": 2,
}
HORA = "2026-10-28 15:00:00"


def _linea(hora: str, tag: str, texto: str, nivel: str = "I") -> str:
    return f"{hora}.123 {nivel}/{tag} [main] [-] {texto}"


def _log_caminata(*, codigos=("200", "200"), extra=(), voz_extra=()) -> str:
    """El app.log de una caminata simulada correcta (lo que escribe NavegacionViewModel)."""
    h = "2026-10-28 15:00:1"
    lineas = [
        _linea(
            "2026-10-28 14:59:00",
            "Guia",
            "Guía iniciada: ruta 29 m, 3 instrucciones, datos de prueba, simulación 0.7 m cada 500 ms",
        ),
        _linea("2026-10-28 14:59:01", "Guia", "Voz: vieja"),  # de una guía anterior: no cuenta
        _linea(
            h + "0", "Guia", "Guía iniciada: ruta 29 m, 3 instrucciones, datos de prueba, simulación 0.7 m cada 500 ms"
        ),
        _linea(h + "0", "Guia", f"Voz: {validate53.INICIO_ESPERADO}"),
        _linea(h + "3", "Guia", "Voz: En 10 metros, gira a la izquierda."),
        *[_linea(h + "4", "Guia", f"Voz: {t}") for t in voz_extra],
        _linea(h + "7", "Guia", "Enviando foto a POST /v1/localize/frame (radio 40 m)"),
        _linea(h + "7", "Api", f"POST /v1/localize/frame -> {codigos[0]} (480 ms) rid=x"),
        _linea(h + "7", "Guia", "Foto: sin_coincidencias en_radio=0 (520 ms)"),
        _linea(h + "7", "Guia", "Foto descartada (sin_coincidencias)"),
        _linea(h + "8", "Guia", "Voz (ya): Gira a la izquierda y sigue recto 14 metros."),
        _linea(h + "9", "Guia", "Voz: En 9 metros, llegas a <destino>."),
        _linea(h + "9", "Guia", "Enviando foto a POST /v1/localize/frame (radio 40 m)"),
        _linea(h + "9", "Api", f"POST /v1/localize/frame -> {codigos[1]} (430 ms) rid=y"),
        _linea(h + "9", "Guia", "Foto: sin_coincidencias en_radio=0 (450 ms)"),
        _linea(h + "9", "Guia", "Foto descartada (sin_coincidencias)"),
        *extra,
        _linea("2026-10-28 15:00:25", "Guia", "Llegada: Has llegado a <destino>."),
        _linea("2026-10-28 15:00:26", "Guia", "Llegada mostrada (6.6)"),
    ]
    return "\n".join(lineas) + "\n"


def _guia(texto: str) -> list[validate53.LineaLog]:
    return validate53.ultima_guia(validate53.lineas_log(texto, "2026-10-28 15:00:00"))


# --- piezas puras --------------------------------------------------------------------------------------------------


def test_secuencia_correcta_y_sin_avisos_de_red():
    lineas = _guia(_log_caminata(voz_extra=["Sin conexión: sigo con tus pasos; la precisión puede bajar."]))
    detalle = validate53.revisar_secuencia(lineas)
    assert detalle.startswith("ruta 29 m, 3 instrucciones; dijo: Lleva el teléfono en la mano")
    assert "vieja" not in detalle and "Sin conexión" not in detalle


@pytest.mark.parametrize(
    ("cambio", "mensaje"),
    [
        (lambda t: t.replace("Voz: En 10 metros, gira a la izquierda.\n", ""), "la guía dijo"),
        (
            lambda t: t.replace("Gira a la izquierda y sigue recto 14", "Gira a la derecha y sigue recto 14"),
            "la guía dijo",
        ),
        (lambda t: t.replace("Llegada mostrada (6.6)", "otra cosa"), "Llegada mostrada"),
        (lambda t: t.replace(", simulación 0.7 m cada 500 ms", ""), "modo de simulación"),
        (lambda t: t + _linea("2026-10-28 15:00:27", "CRASH", "boom", "E") + "\n", "CRASH"),
        (lambda t: "", "Guía iniciada"),
    ],
)
def test_secuencia_que_falla(cambio, mensaje):
    with pytest.raises(comun.Falla, match=mensaje):
        validate53.revisar_secuencia(_guia(cambio(_log_caminata())))


def test_fotos():
    f = validate53.fotos_de(_guia(_log_caminata()))
    assert (f.pedidas, f.codigos, len(f.respuestas), len(f.decisiones)) == (2, ["200", "200"], 2, 2)
    assert validate53.revisar_fotos(f).startswith("2 fotos enviadas, POST /v1/localize/frame -> 200, 200")
    con_503 = validate53.fotos_de(_guia(_log_caminata(codigos=("503", "503"))))
    with pytest.raises(comun.Falla, match="ninguna respuesta 200"):
        validate53.revisar_fotos(con_503)
    oscuras = validate53.Fotos(no_enviadas=["oscura", "oscura"])
    with pytest.raises(comun.Falla, match="descartadas por calidad"):
        validate53.revisar_fotos(oscuras)


def test_estatica_con_el_codigo_real():
    archivos = {
        str(p.relative_to(validate53.DIR_KOTLIN)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in sorted(validate53.DIR_KOTLIN.rglob("*.kt"))
    }
    main_activity = validate53.MAIN_ACTIVITY.read_text(encoding="utf-8")
    assert "PruebaGuia solo en MainActivity" in validate53.comprobar_estatica(archivos, main_activity)
    otro = dict(archivos, **{"ui/navegacion/Otro.kt": "PruebaGuia.fijar(x)"})
    with pytest.raises(comun.Falla, match="solo en MainActivity"):
        validate53.comprobar_estatica(otro, main_activity)
    with pytest.raises(comun.Falla, match="decisión del usuario"):
        validate53.comprobar_estatica(dict(archivos, **{"domain/guia/ParametrosGuia.kt": "x"}), main_activity)
    with pytest.raises(comun.Falla, match="navegacion"):
        validate53.comprobar_estatica(archivos, main_activity.replace(', "navegacion")', ")"))


# --- main() con todo simulado ---------------------------------------------------------------------------------------


def _nodo(texto: str, y: int) -> str:
    return (
        f'<node text={quoteattr(texto)} content-desc="" class="android.widget.TextView" '
        f'package="{comun.PAQUETE}" focused="false" bounds="[0,{y}][100,{y + 50}]" enabled="true" password="false"/>'
    )


class _Simulado:
    def __init__(self, tmp_path: Path, *, log=None, fe51_hecho=True, casos=None):
        self.tmp = tmp_path
        self.log = _log_caminata() if log is None else log
        self.fe51_hecho = fe51_hecho
        self.casos = casos or dict(CASOS)
        self.pantalla = "inicio"
        self.volcados = 0
        self.t = 0.0
        self.adb_llamadas: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []

    def instalar_en(self, monkeypatch):
        plan = self.tmp / "PLAN.md"
        plan.write_text(
            f"| FE-5.1 | 5 | {'Hecho' if self.fe51_hecho else 'En curso'} | x | | | | |\n", encoding="utf-8"
        )
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text("| BE-5.1 | 5 | Hecho | x | | | |\n", encoding="utf-8")
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "PLAN_BACKEND", plan_be)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "http_get", lambda url, **_: comun.RespuestaHttp(200, {}, '{"estado": "ok"}', 5))
        monkeypatch.setattr(comun, "esperar_enter", self.pasos_guiados.append)
        monkeypatch.setattr(comun, "reloj", lambda: self.t)
        monkeypatch.setattr(comun, "dormir", self.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")

    def dormir(self, s):
        self.t += s

    def gradle(self, *args, timeout=0):
        if "testDebugUnitTest" in args:
            for clase, n in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{n}" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
                    )
            return comun.Resultado(0, "BUILD", "")
        if "installDebug" in args:
            return comun.Resultado(0, "Installed on 1 device.", "")
        return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11 (JetBrains)\n", "")

    def adb(self, *args, timeout=0):
        self.adb_llamadas.append(args)
        if args[:2] == ("shell", "getprop"):
            return comun.Resultado(0, "23028RA60L\n", "")
        if args[:2] == ("shell", "date"):
            return comun.Resultado(0, HORA.replace(" ", "_") + "\n", "")
        if args[:3] == ("shell", "am", "start"):
            extras = dict(zip(args[7::3], args[8::3], strict=False))
            if extras.get("ruta") == "navegacion" and extras.get("simular_pasos") == validate53.SIMULAR_PASOS:
                self.pantalla = "guia"
            return comun.Resultado(0, "Status: ok\n", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            self.volcados += 1
            if self.pantalla == "guia" and self.volcados > 3:
                self.pantalla = "llegada"
            textos = {
                "inicio": ["Bienvenido"],
                "guia": ["Hacia bloque 35", "Repetir instrucción", "Terminar"],
                "llegada": ["Has llegado a bloque 35.", "Ir a otro lugar", "Volver al inicio"],
            }[self.pantalla]
            nodos = "".join(_nodo(t, 100 * i) for i, t in enumerate(textos))
            return comun.Resultado(0, f'UI hierchary dumped\n<hierarchy rotation="0">{nodos}</hierarchy>', "")
        if args[:3] == ("exec-out", "run-as", comun.PAQUETE) and args[3] == "cat":
            return comun.Resultado(0, self.log, "")
        return comun.Resultado(0, "", "")


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate53.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {e["id"]: e["estado"] for e in datos["precondiciones"] + datos["comprobaciones"]}


def test_local_pasa_sin_telefono(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0
    estados = _estados(datos)
    assert estados["C1a"] == estados["C2a"] == estados["C3a"] == "pasa"
    assert estados["C1b"] == estados["C2b"] == "omitida"
    assert s.adb_llamadas == []


def test_dev_camina_y_lee_app_log(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    estados = _estados(datos)
    assert estados["C1b"] == estados["C2b"] == "pasa"
    assert len(s.pasos_guiados) == 1  # un solo paso guiado (sostener el teléfono) para C1b y C2b
    starts = [a for a in s.adb_llamadas if a[:3] == ("shell", "am", "start")]
    assert len(starts) == 1
    assert ("shell", "pm", "grant", comun.PAQUETE, "android.permission.CAMERA") in s.adb_llamadas


def test_dev_bloqueado_sin_fe51(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, fe51_hecho=False)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert _estados(datos)["P4"] == "falla"


def test_dev_falla_si_las_fotos_dan_503(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, log=_log_caminata(codigos=("503", "503")))
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    estados = _estados(datos)
    assert codigo == 1
    assert estados["C1b"] == "pasa" and estados["C2b"] == "falla"
