"""Pruebas de validate51.py con Gradle, adb, el teléfono (uiautomator) y la API simulados (sin teléfono ni JDK)."""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate51

URL = "https://api.ejemplo/v1"
CASOS = {
    "LectorGrafoTest": 7,
    "ProyeccionRutaTest": 9,
    "InstruccionesTest": 8,
    "EmparejamientoTest": 3,
    "PlanificadorTest": 7,
    "RutaEnMapaTest": 3,
}
# GET /v1/places en dev el 2026-10-28 (un solo lugar) y uno inventado lejos del grafo (~40 m al oeste de n0002).
BLOQUE_35 = {"id": "b35", "nombre": "Bloque 35", "categoria": "bloque", "lat": 6.201286, "lng": -75.578834}
LEJANO = {"id": "x", "nombre": "Auditorio", "categoria": "auditorio", "lat": 6.2014317, "lng": -75.5791977}
TRAS_TOQUE = ("Ruta a bloque 35: 47 m por el camino", "Gira a tu izquierda y sigue recto 30 metros.")


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), paquete=comun.PAQUETE):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'package={quoteattr(paquete)} focused="false" '
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="true" password="false"/>'
    )


def _nodos(*textos: str) -> list[comun.Nodo]:
    xml = "<hierarchy>" + "".join(_nodo(texto=t, limites=(0, 100 * i, 10, 100 * i + 50)) for i, t in enumerate(textos))
    return comun.parsear_ui(xml + "</hierarchy>")


class _Simulado:
    """Gradle, adb (con un teléfono que muestra el mapa) y la API falsos para recorrer `main()` entero."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        casos=None,
        fallos=None,
        lugares=None,
        aviso=(validate51.TITULO_ESPERADO, validate51.PRIMERA_ESPERADA),
        tras_toque=TRAS_TOQUE,
        be31_hecho=True,
        eof=False,
    ):
        self.tmp = tmp_path
        self.casos = casos or dict(CASOS)
        self.fallos = fallos or {}
        self.lugares = [BLOQUE_35] if lugares is None else lugares
        self.aviso = aviso
        self.tras_toque = tras_toque
        self.be31_hecho = be31_hecho
        self.eof = eof
        self.pantalla = "inicio"
        self.t = 0.0
        self.gradle_llamadas: list[tuple[str, ...]] = []
        self.adb_llamadas: list[tuple[str, ...]] = []
        self.http_llamadas: list[str] = []
        self.pasos_guiados: list[str] = []

    def instalar_en(self, monkeypatch):
        plan = self.tmp / "PLAN.md"
        plan.write_text("| FE-3.1 | 3 | Hecho | x | `b553390` 2026-10-26 | 0.8.1 | | |\n", encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        estado = "Hecho" if self.be31_hecho else "En curso"
        plan_be.write_text(f"| BE-3.1 | 3 | {estado} | x | | | |\n", encoding="utf-8")
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "PLAN_BACKEND", plan_be)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "http_get", self.http_get)
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", lambda: self.t)
        monkeypatch.setattr(comun, "dormir", self.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")

    def dormir(self, s):
        self.t += s

    def gradle(self, *args, timeout=0):
        self.gradle_llamadas.append(args)
        if "testDebugUnitTest" in args:
            for clase, n in self.casos.items():
                if f"*.{clase}" not in args:
                    continue
                (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                    f'<testsuite tests="{n}" failures="{self.fallos.get(clase, 0)}" errors="0" skipped="0"/>',
                    encoding="utf-8",
                )
            return comun.Resultado(1 if self.fallos else 0, "BUILD", "")
        if "installDebug" in args:
            return comun.Resultado(0, "Installed on 1 device.", "")
        return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11 (JetBrains s.r.o. 21.0.11+1-b1163.116)\n", "")

    def http_get(self, url, *, timeout=15, token=None):
        assert token is None  # GET /v1/places es pública
        self.http_llamadas.append(url)
        ruta = url.removeprefix(URL)
        if ruta == "/health":
            cuerpo = {"estado": "ok"}
        elif ruta == "/places":
            cuerpo = {"items": self.lugares, "total": len(self.lugares)}
        else:
            return comun.RespuestaHttp(404, {}, "{}", 1)
        return comun.RespuestaHttp(200, {}, json.dumps(cuerpo), 5)

    def adb(self, *args, timeout=0):
        self.adb_llamadas.append(args)
        if args[:2] == ("shell", "getprop"):
            valor = {"ro.product.model": "23028RA60L", "ro.build.version.release": "14", "ro.build.version.sdk": "34"}
            return comun.Resultado(0, valor.get(args[2], "") + "\n", "")
        if args[:3] == ("shell", "am", "force-stop"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "", "")
        if args[:3] == ("shell", "am", "start"):
            extras = dict(zip(args[7::3], args[8::3], strict=False)) if "--es" in args else {}
            if extras.get("ruta") == "mapa" and extras.get("destino_prueba") and extras.get("posicion_prueba"):
                self.pantalla = "mapa"
            return comun.Resultado(0, "Status: ok\nActivity: com.example.myapplication/.MainActivity\n", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            return comun.Resultado(0, "UI hierchary dumped to: /x\n" + self._xml(), "")
        return comun.Resultado(0, "", "")

    def _xml(self) -> str:
        if self.pantalla == "mapa":
            titulo, detalle = self.aviso
            nodos = [_nodo(texto=titulo, limites=(40, 120, 1000, 170))]
            if detalle:
                nodos.append(_nodo(texto=detalle, limites=(40, 175, 1000, 215)))
            nodos.append(_nodo(desc="StepTracker", clase="android.webkit.WebView", limites=(0, 230, 1080, 2300)))
        else:
            nodos = [_nodo(texto="Bienvenido", limites=(40, 100, 600, 160))]
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(nodos)}</hierarchy>"

    def esperar_enter(self, instruccion):
        if self.eof:
            raise comun.ErrorConfiguracion("el paso guiado necesita una terminal: la entrada estándar está cerrada")
        self.pasos_guiados.append(instruccion)
        if self.tras_toque is not None:
            self.aviso = self.tras_toque


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate51.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {e["id"]: e["estado"] for e in datos["precondiciones"] + datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(e["detalle"] for e in datos["precondiciones"] + datos["comprobaciones"] if e["id"] == id_)


# --- piezas puras --------------------------------------------------------------------------------------------------


def test_revisar_el_grafo_real_de_assets():
    r = validate51.revisar_grafo(validate51.GRAFO.read_text(encoding="utf-8"))
    assert (r.version, r.nodos, r.aristas, r.entradas, r.bloqueadas) == (209, 28, 33, 8, 0)
    assert r.lugares == ["bloque 33", "bloque 35", "biblioteca", "bloque 38", "cocnverso", "bloque 34", "cafeteria"]
    assert round(r.metros, 1) == 647.2
    assert len(r.posiciones) == 28 and len(r.lista_aristas) == 33


def _grafo(nodos, aristas, formato=1):
    return json.dumps({"formato": formato, "version": 1, "nodos": nodos, "aristas": aristas})


N1 = {"id": "n1", "lat": 6.2, "lng": -75.5, "tipo": "cruce"}
N2 = {"id": "n2", "lat": 6.2001, "lng": -75.5, "tipo": "entrada", "lugar": "Bloque 35"}
A1 = {"id": "a1", "a": "n1", "b": "n2", "metros": 11.1}


@pytest.mark.parametrize(
    ("texto", "mensaje"),
    [
        ("{roto", "no es JSON"),
        (_grafo([N1, N2], [A1], formato=2), "formato 2"),
        (_grafo([N1, N2, N1], [A1]), "id de nodo repetido: n1"),
        (_grafo([N1, N2], [A1, {"id": "a2", "a": "n1", "b": "n9", "metros": 3}]), "nodo inexistente n9"),
        (_grafo([N1, N2, {**N1, "id": "n3"}], [A1]), "2 componentes; fuera del principal: n3"),
        (_grafo([N1, N2], [{**A1, "metros": 0}]), "sin metros > 0"),
    ],
)
def test_revisar_grafo_invalido(texto, mensaje):
    with pytest.raises(comun.Falla, match=mensaje):
        validate51.revisar_grafo(texto)


def test_lugar_opcional_e_informativo():
    sin_lugar = validate51.revisar_grafo(_grafo([N1, {**N2, "lugar": " "}], [A1]))
    assert sin_lugar.lugares == [] and sin_lugar.entradas == 1
    sin_entradas = validate51.revisar_grafo(_grafo([N1, {**N2, "tipo": "cruce"}], [A1]))
    assert sin_entradas.entradas == 0 and sin_entradas.lugares == ["Bloque 35"]


def _real():
    return validate51.revisar_grafo(validate51.GRAFO.read_text(encoding="utf-8"))


def test_proyectar_como_la_app():
    r = _real()
    # La posición de prueba de C4b cae sobre a0032 (n0002–n0008), casi en la mitad.
    pr = validate51.proyectar(r, *validate51.POSICION_PRUEBA)
    assert pr is not None and pr.arista == "a0032" and abs(pr.t - 0.5) < 0.01 and pr.distancia_m < 1
    # Bloque 35 del backend: sobre a0007, a menos de 1 m (EmparejamientoTest dice lo mismo).
    b35 = validate51.proyectar(r, BLOQUE_35["lat"], BLOQUE_35["lng"])
    assert b35 is not None and b35.arista == "a0007" and b35.distancia_m < 1
    lejano = validate51.proyectar(r, LEJANO["lat"], LEJANO["lng"])
    assert lejano is not None and 38 < lejano.distancia_m < 42


def test_revisar_lugares():
    r = _real()
    revisados = validate51.revisar_lugares(
        r, [BLOQUE_35, LEJANO, {"id": "s", "nombre": "Sin coordenadas", "lat": None, "lng": -75.5}]
    )
    assert [(x.nombre, x.con_ruta, x.lejos) for x in revisados] == [
        ("Bloque 35", True, False),
        ("Auditorio", True, True),
        ("Sin coordenadas", False, False),
    ]
    assert validate51.describir_lugar(revisados[0]) == "Bloque 35 a 0 m del grafo (a0007)"
    assert validate51.describir_lugar(revisados[2]) == "Sin coordenadas (sin coordenadas válidas)"


def test_revisar_lugares_con_arista_que_no_se_alcanza():
    # Dos piezas unidas solo por una arista bloqueada: un lugar junto a la pieza pequeña no tiene ruta.
    n3 = {"id": "n3", "lat": 6.2010, "lng": -75.5, "tipo": "cruce"}
    n4 = {"id": "n4", "lat": 6.2011, "lng": -75.5, "tipo": "cruce"}
    n5 = {"id": "n5", "lat": 6.2012, "lng": -75.5, "tipo": "cruce"}
    aristas = [
        {"id": "a1", "a": "n1", "b": "n2", "metros": 11.1},
        {"id": "a2", "a": "n2", "b": "n3", "metros": 11.1},
        {"id": "a3", "a": "n3", "b": "n4", "metros": 11.1, "bloqueada": True},
        {"id": "a4", "a": "n4", "b": "n5", "metros": 11.1},
    ]
    nodos = [{**N1, "lat": 6.2008}, {**N2, "lat": 6.2009}, n3, n4, n5]
    r = validate51.revisar_grafo(_grafo(nodos, aristas))
    cerca, lejos = validate51.revisar_lugares(
        r, [{"nombre": "A", "lat": 6.2008, "lng": -75.5}, {"nombre": "B", "lat": 6.2012, "lng": -75.5}]
    )
    assert cerca.con_ruta and not lejos.con_ruta
    assert "no se alcanza" in lejos.motivo


def test_aviso_en_pantalla_y_metros():
    nodos = _nodos("Ruta a bloque 35: 29 m por el camino", "Camina 14 metros por el camino.", "otro")
    assert validate51.aviso_en_pantalla(nodos) == (
        "Ruta a bloque 35: 29 m por el camino",
        "Camina 14 metros por el camino.",
    )
    assert validate51.aviso_en_pantalla(_nodos("Destino: X. Toca el mapa…")) == ("Destino: X. Toca el mapa…", None)
    assert validate51.aviso_en_pantalla(_nodos("Bienvenido")) is None
    assert validate51.metros_del_aviso("Ruta a bloque 35: 29 m por el camino") == 29
    assert validate51.metros_del_aviso("Destino: X") is None


def _archivos_reales():
    raiz = validate51.DIR_KOTLIN
    return {str(p.relative_to(raiz)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in raiz.rglob("*.kt")}


def test_modo_prueba_solo_en_el_apk_depurable():
    main_activity = validate51.MAIN_ACTIVITY.read_text(encoding="utf-8")
    app_js = validate51.APP_JS.read_text(encoding="utf-8")
    assert "PruebaMapa solo en MainActivity" in validate51.comprobar_modo_prueba(
        _archivos_reales(), main_activity, app_js
    )
    otro = {**_archivos_reales(), "ui/Otra.kt": "PruebaMapa.fijar(a, b)"}
    with pytest.raises(comun.Falla, match="solo en MainActivity.kt"):
        validate51.comprobar_modo_prueba(otro, main_activity, app_js)
    sin_bandera = main_activity.replace("FLAG_DEBUGGABLE", "FLAG_SYSTEM")
    with pytest.raises(comun.Falla, match="FLAG_DEBUGGABLE"):
        validate51.comprobar_modo_prueba(_archivos_reales(), sin_bandera, app_js)
    with pytest.raises(comun.Falla, match="onNativeRuta"):
        validate51.comprobar_modo_prueba(_archivos_reales(), main_activity, app_js.replace("onNativeRuta", "x"))


# --- main() entero ---------------------------------------------------------------------------------------------


def test_local_pasa_sin_telefono_ni_red(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0
    e = _estados(datos)
    assert e == {"P1": "pasa", "C1a": "pasa", "C1b": "pasa", "C2a": "pasa", "C3a": "pasa", "C4a": "pasa",
                 "C3b": "omitida", "C4b": "omitida"}  # fmt: skip
    assert "v209: 28 nodos, 33 aristas (0 bloqueadas), 8 entradas, 7 nombres de lugar (informativos), 647 m" in (
        _detalle(datos, "C1b")
    )
    assert [m["id"] for m in datos["manuales"]] == ["C4c"]
    assert len([g for g in s.gradle_llamadas if "testDebugUnitTest" in g]) == 1
    assert s.adb_llamadas == [] and s.http_llamadas == []


def test_dev_feliz(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert all(estado == "pasa" for estado in _estados(datos).values())
    assert _detalle(datos, "C3b").startswith("los 1 lugares tienen ruta (GET /v1/places -> 1 lugares; a ≤ 15 m del")
    assert "Bloque 35 a 0 m del grafo (a0007)" in _detalle(datos, "C3b")
    c4b = _detalle(datos, "C4b")
    assert validate51.TITULO_ESPERADO in c4b and TRAS_TOQUE[0] in c4b
    inicio = next(a for a in s.adb_llamadas if a[:3] == ("shell", "am", "start"))
    assert inicio[-6:] == ("--es", "destino_prueba", "bloque35", "--es", "posicion_prueba", "6.201434,-75.578707")
    assert len(s.pasos_guiados) == 1
    assert ("shell", "am", "force-stop", comun.PAQUETE) == s.adb_llamadas[-1]  # limpieza
    assert not any("pm" in a and "clear" in a for a in s.adb_llamadas)


def test_dev_lugar_lejos_avisa_sin_fallar(tmp_path, monkeypatch, capsys):
    s = _Simulado(tmp_path, lugares=[BLOQUE_35, LEJANO])
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 0
    detalle = _detalle(datos, "C3b")
    assert detalle.startswith("los 2 lugares tienen ruta")
    assert "aviso: 1 a más de 15 m del grafo" in detalle and "Auditorio a 40 m del grafo" in detalle
    assert "aviso: 1 a más de 15 m del grafo" in capsys.readouterr().err
    assert _estados(datos)["P2"] == "no evaluada"
    assert s.adb_llamadas == []


def test_dev_lugar_sin_coordenadas_falla(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, lugares=[BLOQUE_35, {"id": "s", "nombre": "Sin coordenadas", "lng": -75.5}])
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 1
    assert _detalle(datos, "C3b").startswith("1 de 2 lugares sin ruta: Sin coordenadas (sin coordenadas válidas)")


def test_dev_sin_lugares_no_hay_nada_que_comprobar(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, lugares=[])
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 0
    assert _detalle(datos, "C3b") == "GET /v1/places -> 0 lugares: nada que comprobar"


def test_dev_aviso_distinto(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, aviso=("Ruta a bloque 35: 30 m por el camino", "Camina 15 metros por el camino."))
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C4b"])
    assert codigo == 1
    assert "se esperaba «Ruta a bloque 35: 29 m por el camino»" in _detalle(datos, "C4b")
    assert s.pasos_guiados == []


def test_dev_sin_ruta_en_el_mapa(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, aviso=("Destino: bloque 35. Toca el mapa para fijar tu posición y ver la ruta.", None))
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C4b"])
    assert codigo == 1
    assert "en vez de la ruta (¿sin internet para Leaflet?" in _detalle(datos, "C4b")


def test_dev_el_toque_no_cambia_la_ruta(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, tras_toque=None)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C4b"])
    assert codigo == 1
    assert "no apareció un aviso de ruta distinto tras tocar el mapa" in _detalle(datos, "C4b")
    assert _estados(datos)["P3"] == "no evaluada"


def test_dev_jvm_que_falla_omite_el_telefono(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, fallos={"PlanificadorTest": 1})
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    e = _estados(datos)
    assert e["C4a"] == "falla" and e["C4b"] == "omitida"
    assert "falló C4a" in _detalle(datos, "C4b")
    assert not any(a[:3] == ("shell", "am", "start") for a in s.adb_llamadas)


def test_dev_solo_jvm_no_usa_telefono_ni_api(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C2a"])
    assert codigo == 0
    e = _estados(datos)
    assert e["P2"] == e["P3"] == e["P4"] == "no evaluada"
    assert s.adb_llamadas == [] and s.http_llamadas == []


def test_dev_eof_en_el_paso_guiado(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, eof=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C4b"])
    assert codigo == 3
    assert _estados(datos)["C4b"] == "error"
    assert ("shell", "am", "force-stop", comun.PAQUETE) == s.adb_llamadas[-1]


def test_dev_be31_sin_hecho_bloquea(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, be31_hecho=False)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert _estados(datos)["P4"] == "falla"
    assert "C1a" not in _estados(datos)
