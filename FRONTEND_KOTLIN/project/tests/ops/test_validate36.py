"""Pruebas de validate36.py con Gradle, adb, el teléfono (app.log, caché, uiautomator) y la API simulados."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate36

URL = "https://api.ejemplo/v1"
TOKEN = "token-secreto-123"
PASSWORD = "clave-secreta-456"
CASOS = {"CacheAlertasPublicasTest": 7, "DetectarAlertasCercanasTest": 7, "AlertasEnResultadoTest": 4}
INICIO = dt.datetime(2026, 10, 28, 15, 0, 0)


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), paquete=comun.PAQUETE):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'package={quoteattr(paquete)} focused="false" '
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="true" password="false"/>'
    )


class _Simulado:
    """Backend de alertas, teléfono (app.log, caché pública, pantallas, modo avión) y Gradle falsos."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        casos=None,
        fallos=None,
        be33_hecho=True,
        eof=False,
        activar_avion=True,
        app_no_guarda=False,
        siempre_completa=False,
        resultado_sin_alertas=False,
        restos=(),
        password_mala=False,
    ):
        self.tmp = tmp_path
        self.casos = casos or dict(CASOS)
        self.fallos = fallos or {}
        self.be33_hecho = be33_hecho
        self.eof = eof
        self.activar_avion = activar_avion
        self.app_no_guarda = app_no_guarda
        self.siempre_completa = siempre_completa
        self.resultado_sin_alertas = resultado_sin_alertas
        self.password_mala = password_mala
        self.t = 0.0
        self.seq = 1
        self.backend: dict[str, dict] = {}
        self.cambios: dict[str, int] = {}  # id → seq del último cambio
        self.tombstones: dict[str, int] = {}
        for i, mensaje in enumerate(restos):
            self.backend[f"resto-{i}"] = self._alerta(f"resto-{i}", mensaje, "normal")
            self.cambios[f"resto-{i}"] = 1
        self.cache: dict[str, dict] = {}
        self.generado: str | None = None
        self.log: list[str] = []
        self.avion = False
        self.pantalla = "inicio"
        self.banner: str | None = None
        self.alertas_6_3: list[str] = []
        self.gradle_llamadas: list[tuple[str, ...]] = []
        self.adb_llamadas: list[tuple[str, ...]] = []
        self.http_llamadas: list[str] = []
        self.pasos_guiados: list[str] = []

    # --- montaje ---

    def instalar_en(self, monkeypatch):
        plan = self.tmp / "PLAN.md"
        plan.write_text("| FE-3.1 | 3 | Hecho | x | `b553390` 2026-10-26 | 0.8.1 | | |\n", encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(
            f"| BE-3.3 | 3 | {'Hecho' if self.be33_hecho else 'En curso'} | x | | | |\n", encoding="utf-8"
        )
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "PLAN_BACKEND", plan_be)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "credenciales_admin", lambda entorno: ("admin@campus.edu.co", PASSWORD))
        monkeypatch.setattr(comun, "http_get", self.http_get)
        monkeypatch.setattr(comun, "http_post_json", self.http_post_json)
        monkeypatch.setattr(comun, "http_delete", self.http_delete)
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", lambda: self.t)
        monkeypatch.setattr(comun, "dormir", self.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")

    def dormir(self, s):
        self.t += s

    def hora(self) -> dt.datetime:
        return INICIO + dt.timedelta(seconds=self.t)

    def escribir_log(self, nivel: str, tag: str, texto: str):
        self.log.append(f"{self.hora():%Y-%m-%d %H:%M:%S}.123 {nivel}/{tag} [main] [-] {texto}")

    # --- Gradle ---

    def gradle(self, *args, timeout=0):
        self.gradle_llamadas.append(args)
        if "testDebugUnitTest" in args:
            for clase, n in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{n}" failures="{self.fallos.get(clase, 0)}" errors="0" skipped="0"/>',
                        encoding="utf-8",
                    )
            return comun.Resultado(1 if self.fallos else 0, "BUILD", "")
        if "installDebug" in args:
            return comun.Resultado(0, "Installed on 1 device.", "")
        return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11 (JetBrains)\n", "")

    # --- backend ---

    @staticmethod
    def _alerta(id_, mensaje, prioridad, lat=6.201484, lng=-75.578427, radio=15, activa=True):
        return {"id": id_, "lat": lat, "lng": lng, "mensaje": mensaje, "tipo": "otro", "prioridad": prioridad,
                "radio_m": radio, "activa": activa}  # fmt: skip

    def _generado(self) -> str:
        return f"2026-10-28T15:00:00Z#{self.seq}"

    def _foto(self, desde: str | None) -> dict:
        self.seq += 1
        generado = self._generado()
        if desde is None or self.siempre_completa:
            return {"generado_en": generado, "completo": True, "alertas": list(self.backend.values()), "eliminadas": []}
        base = int(desde.split("#")[1])
        alertas = [a for i, a in self.backend.items() if self.cambios[i] > base]
        eliminadas = [i for i, s in self.tombstones.items() if s > base]
        return {"generado_en": generado, "completo": False, "alertas": alertas, "eliminadas": eliminadas}

    def http_get(self, url, *, timeout=15, token=None):
        self.http_llamadas.append(url)
        ruta = url.removeprefix(URL)
        if ruta == "/health":
            return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok"}), 5)
        if ruta.startswith("/alerts"):
            assert token is None
            desde = ruta.split("desde=")[1].replace("%23", "#") if "desde=" in ruta else None
            return comun.RespuestaHttp(200, {}, json.dumps(self._foto(desde)), 5)
        if ruta.startswith("/admin/alerts"):
            assert token == TOKEN
            items = [a for a in self.backend.values() if validate36.PREFIJO_PRUEBA in a["mensaje"]]
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 5)
        return comun.RespuestaHttp(404, {}, "{}", 1)

    def http_post_json(self, url, cuerpo, *, timeout=15, token=None):
        self.http_llamadas.append(url)
        ruta = url.removeprefix(URL)
        if ruta == "/auth/login":
            if self.password_mala:
                return comun.RespuestaHttp(401, {}, json.dumps({"error": {"codigo": "CREDENCIALES_INVALIDAS"}}), 5)
            usuario = {"id": "u1", "nombre": "Admin", "rol": "admin"}
            return comun.RespuestaHttp(200, {}, json.dumps({"token": TOKEN, "usuario": usuario}), 5)
        if ruta == "/admin/alerts/sincronizar":
            assert token == TOKEN
            resultados = []
            for c in cuerpo["cambios"]:
                a = c["alerta"]
                self.seq += 1
                self.backend[a["id"]] = dict(a)
                self.cambios[a["id"]] = self.seq
                resultados.append({"id": a["id"], "op": "upsert", "estado": "ok", "codigo": None})
            return comun.RespuestaHttp(200, {}, json.dumps({"generado_en": "x", "resultados": resultados}), 5)
        return comun.RespuestaHttp(404, {}, "{}", 1)

    def http_delete(self, url, *, timeout=15, token=None):
        assert token == TOKEN
        self.http_llamadas.append("DELETE " + url)
        id_ = url.rsplit("/", 1)[1]
        if id_ in self.backend:
            del self.backend[id_]
            self.seq += 1
            self.tombstones[id_] = self.seq
        return comun.RespuestaHttp(204, {}, "", 5)

    # --- la app en el teléfono ---

    def _sincronizar(self):
        if self.avion:
            self.escribir_log("W", "AlertasPublicas", "Alertas públicas: no se pudo sincronizar (primer plano): Sin…")
            return
        f = self._foto(self.generado)
        if not self.app_no_guarda:
            if f["completo"]:
                self.cache = {a["id"]: a for a in f["alertas"] if a["activa"]}
            else:
                for a in f["alertas"]:
                    self.cache[a["id"]] = a
                for i in f["eliminadas"]:
                    self.cache.pop(i, None)
            tipo = "completa" if f["completo"] else f"diferencias desde {self.generado}"
            self.generado = f["generado_en"]
        else:
            tipo = "completa"
        self.escribir_log(
            "I", "AlertasPublicas",
            f"Alertas públicas sincronizadas (primer plano): {tipo}, {len(f['alertas'])} recibidas, "
            f"{len(f['eliminadas'])} eliminadas, {len(self.cache)} en caché (generado_en {f['generado_en']})",
        )  # fmt: skip

    def _anunciar(self, donde: str) -> list[str]:
        orden = sorted(self.cache.values(), key=lambda a: a["prioridad"] != "alta")
        for a in orden:
            self.escribir_log(
                "I", "AlertasPublicas",
                f"Alerta anunciada ({donde}): {a['id']} a 6 m (radio {a['radio_m']} m, incertidumbre 5 m, "
                f"{a['prioridad']})",
            )  # fmt: skip
        return [a["mensaje"] for a in orden]

    def _mapa_desde_ubicarme(self):
        self.escribir_log(
            "I", "MapaPublico", "Inicio desde Ubicarme (radio 5 m): seguimiento iniciado sin tocar el mapa"
        )
        self.escribir_log("I", "Pdr", "sensores registrados (iniciar; rotación sí, acelerómetro sí)")
        mensajes = self._anunciar("mapa")
        self.banner = f"Alerta: {mensajes[0]}." if mensajes else None
        self.pantalla = "mapa"

    def adb(self, *args, timeout=0):
        self.adb_llamadas.append(args)
        if args[:2] == ("shell", "getprop"):
            valor = {"ro.product.model": "23028RA60L", "ro.build.version.release": "14", "ro.build.version.sdk": "34"}
            return comun.Resultado(0, valor.get(args[2], "") + "\n", "")
        if args[:2] == ("shell", "date"):
            return comun.Resultado(0, f"{self.hora():%Y-%m-%d_%H:%M:%S}\n", "")
        if args[:3] == ("shell", "am", "force-stop"):
            self.pantalla = "inicio"
            self.banner = None
            return comun.Resultado(0, "", "")
        if args[:3] == ("shell", "am", "start"):
            self.t += 1
            extras = dict(zip(args[7::3], args[8::3], strict=False))
            self._sincronizar()
            if extras.get("ruta") == "mapa":
                if "ubicacion_prueba" in extras:
                    self._mapa_desde_ubicarme()
                else:
                    self.pantalla = "mapa"
            elif extras.get("ruta") == "resultado":
                self.escribir_log("I", "ResultadoVM", "Resultado: alta, destino no")
                self.alertas_6_3 = [] if self.resultado_sin_alertas else [m + "." for m in self._anunciar("resultado")]
                self.pantalla = "resultado"
            self.t += 1
            return comun.Resultado(0, "Status: ok\n", "")
        if args[:3] == ("shell", "wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        if args[:5] == ("shell", "settings", "get", "global", "airplane_mode_on"):
            return comun.Resultado(0, "1\n" if self.avion else "0\n", "")
        if args[:3] == ("shell", "input", "tap"):
            if self.pantalla == "resultado" and int(args[4]) >= 1900:  # «Caminar con el mapa»
                self.t += 1
                self._mapa_desde_ubicarme()
            return comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1:4] == ("run-as", comun.PAQUETE, "cat"):
            if args[4] == comun.LOG_APP:
                return comun.Resultado(0, "\n".join(self.log) + "\n", "")
            if args[4] == validate36.CACHE:
                if self.generado is None:
                    return comun.Resultado(1, "", "No such file")
                cache = {"version": 1, "generado_en": self.generado, "alertas": [
                    {**a, "radio": a["radio_m"]} for a in self.cache.values()]}  # fmt: skip
                return comun.Resultado(0, json.dumps(cache), "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            return comun.Resultado(0, "UI hierchary dumped to: /x\n" + self._xml(), "")
        return comun.Resultado(0, "", "")

    def _xml(self) -> str:
        if self.pantalla == "mapa":
            nodos = [_nodo(texto=self.banner, limites=(0, 120, 1080, 180))] if self.banner else []
            nodos.append(_nodo(desc="StepTracker", clase="android.webkit.WebView", limites=(0, 200, 1080, 2300)))
        elif self.pantalla == "resultado":
            nodos = [_nodo(texto="Tu ubicación", limites=(40, 100, 600, 150)),
                     _nodo(texto=validate36.TITULO_SIN_LUGARES, limites=(40, 160, 1000, 240))]  # fmt: skip
            if self.alertas_6_3:
                nodos.append(_nodo(texto=validate36.TITULO_ALERTAS, limites=(60, 600, 1000, 650)))
                nodos += [
                    _nodo(texto=m, limites=(60, 660 + 60 * i, 1000, 710 + 60 * i))
                    for i, m in enumerate(self.alertas_6_3)
                ]
            nodos.append(_nodo(texto=validate36.BOTON_MAPA, limites=(40, 1900, 1040, 1960)))
        else:
            nodos = [_nodo(texto="Bienvenido", limites=(40, 100, 600, 160))]
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(nodos)}</hierarchy>"

    def esperar_enter(self, instruccion):
        if self.eof:
            raise comun.ErrorConfiguracion("el paso guiado necesita una terminal: la entrada estándar está cerrada")
        self.pasos_guiados.append(instruccion)
        if "Activa el MODO AVIÓN" in instruccion:
            self.avion = self.activar_avion
        elif "DESACTIVA" in instruccion:
            self.avion = False


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate36.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {e["id"]: e["estado"] for e in datos["precondiciones"] + datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(e["detalle"] for e in datos["precondiciones"] + datos["comprobaciones"] if e["id"] == id_)


# --- piezas puras --------------------------------------------------------------------------------------------------


def test_lineas_de_la_app_se_leen():
    texto = "\n".join([
        "2026-10-28 15:00:01.001 I/AlertasPublicas [main] [-] Alertas públicas sincronizadas (primer plano): "
        "diferencias desde 2026-10-28T15:00:00Z, 3 recibidas, 1 eliminadas, 2 en caché "
        "(generado_en 2026-10-28T15:06:00Z)",
        "2026-10-28 15:00:02.001 W/AlertasPublicas [main] [-] Alertas públicas: no se pudo sincronizar (conexión): X",
        "2026-10-28 15:00:03.001 I/AlertasPublicas [main] [-] Alerta anunciada (mapa): 1d6e a 3 m (radio 15 m, "
        "incertidumbre 5 m, alta)",
        "    at una.traza(Archivo.kt:1)",
        "2026-10-28 14:59:59.001 I/AlertasPublicas [main] [-] Alerta anunciada (resultado): viejo a 1 m (radio 15 m, "
        "incertidumbre 0 m, normal)",
    ])  # fmt: skip
    lineas = validate36.lineas_log(texto, "2026-10-28 15:00:00")
    s = validate36.sincronizaciones(lineas)
    assert len(s) == 1 and not s[0].completa and s[0].desde == "2026-10-28T15:00:00Z" and s[0].eliminadas == 1
    assert s[0].generado_en == "2026-10-28T15:06:00Z" and s[0].total == 2
    assert validate36.fallos_sincronizacion(lineas) == ["Alertas públicas: no se pudo sincronizar (conexión): X"]
    a = validate36.anuncios(lineas)
    assert [(x.donde, x.id, x.distancia_m, x.incertidumbre_m, x.prioridad) for x in a] == [
        ("mapa", "1d6e", 3, 5, "alta")
    ]


def test_leer_cache():
    alertas, generado = validate36.leer_cache(
        json.dumps({"version": 1, "generado_en": "2026-10-28T15:00:00Z", "alertas": [{"id": "a", "radio": 15}]})
    )
    assert list(alertas) == ["a"] and generado == "2026-10-28T15:00:00Z"
    assert validate36.leer_cache(None) == ({}, None)
    with pytest.raises(comun.Falla, match="no es JSON"):
        validate36.leer_cache("{roto")


def test_alertas_de_prueba_solo_por_mensaje_exacto():
    items = [{"id": "1", "mensaje": "VALIDACION-3-6-C1"}, {"id": "2", "mensaje": "validacion-3-6-c1 de otro"},
             {"id": "3", "mensaje": " validacion-3-6-c2 "}]  # fmt: skip
    assert [i["id"] for i in validate36.alertas_de_prueba(items)] == ["1", "3"]


def _archivos_reales():
    raiz = validate36.DIR_KOTLIN
    return {str(p.relative_to(raiz)).replace("\\", "/"): p.read_text(encoding="utf-8") for p in raiz.rglob("*.kt")}


def test_modo_prueba_contra_el_codigo_real_y_variantes_rotas():
    main = validate36.MAIN_ACTIVITY.read_text(encoding="utf-8")
    mapa = validate36.MAPA_PUBLICO.read_text(encoding="utf-8")
    js = validate36.APP_JS.read_text(encoding="utf-8")
    assert "ubicación de prueba solo en MainActivity" in validate36.comprobar_modo_prueba(
        _archivos_reales(), main, mapa, js
    )
    otro = {**_archivos_reales(), "ui/Otra.kt": "PruebaUbicacion.resultado(x)"}
    with pytest.raises(comun.Falla, match="solo en MainActivity.kt"):
        validate36.comprobar_modo_prueba(otro, main, mapa, js)
    with pytest.raises(comun.Falla, match='no incluye "resultado"'):
        validate36.comprobar_modo_prueba(
            _archivos_reales(),
            re.sub(r"RUTAS_DE_PRUEBA = setOf\([^)]*\)", 'RUTAS_DE_PRUEBA = setOf("mapa")', main),
            mapa,
            js,
        )
    with pytest.raises(comun.Falla, match="onNativeRastreoIniciado"):
        validate36.comprobar_modo_prueba(_archivos_reales(), main, mapa, js.replace("onNativeRastreoIniciado", "x"))
    with pytest.raises(comun.Falla, match="onVerMapa"):
        validate36.comprobar_modo_prueba(_archivos_reales(), main.replace("onVerMapa = {", "onOtra = {"), mapa, js)


# --- main() entero ---------------------------------------------------------------------------------------------


def test_local_pasa_sin_telefono_ni_red(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0, datos
    e = _estados(datos)
    assert e == {"P1": "pasa", "C1a": "pasa", "C3a": "pasa", "C4a": "pasa", "C1b": "omitida", "C1c": "omitida",
                 "C2b": "omitida", "C4b": "omitida", "C5a": "omitida"}  # fmt: skip
    assert [m["id"] for m in datos["manuales"]] == ["C5"]
    assert len([g for g in s.gradle_llamadas if "testDebugUnitTest" in g]) == 1
    assert s.adb_llamadas == [] and s.http_llamadas == []


def test_dev_feliz(tmp_path, monkeypatch, capsys):
    s = _Simulado(tmp_path, restos=["validacion-3-6-c2", "validacion-3-6 ajena"])
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert all(estado == "pasa" for estado in _estados(datos).values())
    assert "diferencias desde" in _detalle(datos, "C1c")
    assert "en modo avión" in _detalle(datos, "C2b")
    assert "«Alertas cercanas» con «validacion-3-6-c2.»" in _detalle(datos, "C4b")
    assert "Caminar con el mapa" in _detalle(datos, "C5a")
    # Limpieza: las dos de prueba y el resto borrados; la ajena se queda; la caché del teléfono se puso al día.
    assert [a["mensaje"] for a in s.backend.values()] == ["validacion-3-6 ajena"]
    assert not any(validate36.PREFIJO_PRUEBA + "-c" in a["mensaje"] for a in s.cache.values())
    assert ("shell", "am", "force-stop", comun.PAQUETE) == s.adb_llamadas[-1]
    assert not any("pm" in a and "clear" in a for a in s.adb_llamadas)
    assert len(s.pasos_guiados) == 2 and not s.avion
    salida = capsys.readouterr()
    for secreto in (TOKEN, PASSWORD):
        assert secreto not in salida.out + salida.err + json.dumps(datos)


def test_dev_la_app_no_guarda_la_alerta(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, app_no_guarda=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    e = _estados(datos)
    assert e["C1b"] == "falla" and e["C1c"] == e["C2b"] == e["C4b"] == e["C5a"] == "omitida"
    assert "no tiene validacion-3-6-c1, validacion-3-6-c2" in _detalle(datos, "C1b")
    assert not s.backend  # la limpieza borró las dos


def test_dev_sin_diferencias_falla_c1c(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, siempre_completa=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert _estados(datos)["C1c"] == "falla"
    assert "no fue por diferencias" in _detalle(datos, "C1c")


def test_dev_sin_modo_avion_falla_c2b(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, activar_avion=False)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "el modo avión no está activado" in _detalle(datos, "C2b")


def test_dev_6_3_sin_alertas_falla_c4b(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, resultado_sin_alertas=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C4b"])
    assert codigo == 1
    assert "no muestra «Alertas cercanas»" in _detalle(datos, "C4b")


def test_dev_solo_jvm_no_usa_telefono_ni_api(tmp_path, monkeypatch):
    s = _Simulado(tmp_path)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C3a"])
    assert codigo == 0
    e = _estados(datos)
    assert e["P2"] == e["P3"] == e["P4"] == e["P5"] == "no evaluada"
    assert s.adb_llamadas == [] and s.http_llamadas == []


def test_dev_jvm_que_falla_omite_el_telefono(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, fallos={"DetectarAlertasCercanasTest": 1})
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    e = _estados(datos)
    assert e["C3a"] == "falla" and e["C1b"] == "omitida" and "C3a" in _detalle(datos, "C1b")
    assert not s.backend and not any(a[:3] == ("shell", "am", "start") for a in s.adb_llamadas)


def test_dev_eof_en_el_paso_guiado_limpia(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, eof=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 3
    assert _estados(datos)["C2b"] == "error"
    assert not s.backend
    assert ("shell", "am", "force-stop", comun.PAQUETE) == s.adb_llamadas[-1]


def test_dev_be33_sin_hecho_bloquea(tmp_path, monkeypatch):
    s = _Simulado(tmp_path, be33_hecho=False)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert _estados(datos)["P5"] == "falla"
    assert "C1a" not in _estados(datos)


def test_dev_credenciales_malas(tmp_path, monkeypatch, capsys):
    s = _Simulado(tmp_path, password_mala=True)
    s.instalar_en(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert _estados(datos)["P4"] == "falla" and _estados(datos)["P5"] == "no evaluada"
    assert PASSWORD not in capsys.readouterr().err
