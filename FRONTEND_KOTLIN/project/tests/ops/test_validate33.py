"""Pruebas de validate33.py con un teléfono, Gradle y la API simulados.

El backend falso guarda alertas como BE-3.3 (backend §4.11 y §5.5): `sincronizar` con `upsert` (crea, edita o
restaura) y `eliminar` (un id vivo deja *tombstone*; uno desconocido no deja nada), `DELETE` con *tombstone*,
`GET /v1/admin/alerts?q=` (contiene, sin tildes ni mayúsculas) y `GET /v1/alerts[?desde=]` con la foto completa o las
diferencias (con un margen que repite el cambio anterior, como los 60 s del backend). El teléfono falso dibuja Inicio,
Login, el Panel, el editor 7.8 y la lista 7.10 (buscador y filas con el `content-desc` de `descripcionFilaAlerta`; tocar
una abre «Editar alerta»), y guarda `files/recoleccion` y `files/logs/app.log`. Los pasos guiados
(`comun.esperar_enter`) se sustituyen por lo que hace la persona (y la app al sincronizar).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate33

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
NOMBRE_ADMIN = "Alejandro Gómez"
PLAN_APP = "| FE-1.2 | 1 | Hecho | [1-2](x) | `4d578c5` 2026-10-25 | 0.5.0 | | |\n| FE-3.3 | 3 | En curso | | | | | |\n"
PLAN_BACKEND = "| BE-3.3 | 3 | Hecho | [3-3](x) | `4885ad6` 2026-10-26 | 0.14.1 | |\n"
FOTO = (6.200100, -75.578100)  # primera foto del recorrido de C1b
TIPOS = {"agua": "Agua", "mobiliario": "Mobiliario", "escalones": "Escalones", "obra": "Obra", "otro": "Otro"}


def _norm(texto: str) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin.casefold().split())


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10)):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="true" password="false"/>'
    )


def _r(estado: int, cuerpo: object = "") -> comun.RespuestaHttp:
    return comun.RespuestaHttp(estado, {}, cuerpo if isinstance(cuerpo, str) else json.dumps(cuerpo), 30)


class Api:
    """Backend falso de alertas (y salud y login)."""

    def __init__(self) -> None:
        self.alertas: dict[str, dict] = {}
        self.tombstones: dict[str, int] = {}
        self.tick = 0
        self.login_estado = 200
        self.sincronizaciones: list[list[dict]] = []
        self.borrados: list[str] = []

    def _hora(self, tick: int) -> str:
        return f"2026-10-26T10:{tick // 60:02d}:{tick % 60:02d}Z"

    def upsert(self, a: dict) -> None:
        self.tick += 1
        previa = self.alertas.get(a["id"])
        version = (previa or {}).get("version", 0) + 1
        self.tombstones.pop(a["id"], None)
        self.alertas[a["id"]] = {"activa": True, **a, "version": version, "_tick": self.tick}

    def eliminar(self, alerta_id: str) -> None:
        if alerta_id in self.alertas:
            self.tick += 1
            self.alertas.pop(alerta_id)
            self.tombstones[alerta_id] = self.tick

    def _publica(self, a: dict) -> dict:
        return {k: v for k, v in a.items() if not k.startswith("_")}

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta, q = u.path.removeprefix("/v1"), parse_qs(u.query)
        if ruta == "/health":
            return _r(200, {"estado": "ok"})
        if ruta == "/admin/alerts":
            assert token == TOKEN
            filtro = _norm(q["q"][0]) if "q" in q else ""
            items = [self._publica(a) for a in self.alertas.values() if filtro in _norm(a["mensaje"])]
            return _r(200, {"items": items, "total": len(items)})
        if ruta == "/alerts":
            assert token is None
            if "desde" not in q:
                activas = [self._publica(a) for a in self.alertas.values() if a.get("activa")]
                return _r(
                    200, {"generado_en": self._hora(self.tick), "completo": True, "alertas": activas, "eliminadas": []}
                )
            texto = q["desde"][0]
            desde = int(texto[14:16]) * 60 + int(texto[17:19]) - 1  # margen: repite el cambio anterior
            cambios = [self._publica(a) for a in self.alertas.values() if a["_tick"] >= desde]
            eliminadas = [i for i, t in self.tombstones.items() if t >= desde]
            cuerpo = {
                "generado_en": self._hora(self.tick),
                "completo": False,
                "alertas": cambios,
                "eliminadas": eliminadas,
            }
            return _r(200, cuerpo)
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        ruta = urlparse(url).path.removeprefix("/v1")
        if ruta == "/auth/login":
            if self.login_estado != 200:
                return _r(401, {"error": {"codigo": "CREDENCIALES_INVALIDAS"}})
            assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
            usuario = {"id": "u1", "nombre": NOMBRE_ADMIN, "correo": ADMIN[0], "rol": "admin"}
            return _r(200, {"token": TOKEN, "usuario": usuario})
        if ruta == "/admin/alerts/sincronizar":
            assert token == TOKEN
            self.sincronizaciones.append(cuerpo["cambios"])
            resultados = []
            for c in cuerpo["cambios"]:
                if c["op"] == "upsert":
                    self.upsert(c["alerta"])
                    resultados.append({"id": c["alerta"]["id"], "op": "upsert", "estado": "ok", "codigo": None})
                else:
                    self.eliminar(c["id"])
                    resultados.append({"id": c["id"], "op": "eliminar", "estado": "ok", "codigo": None})
            return _r(200, {"generado_en": self._hora(self.tick), "resultados": resultados})
        raise AssertionError(url)

    def http_delete(self, url, *, timeout=15.0, token=None):
        assert token == TOKEN
        alerta_id = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        self.eliminar(alerta_id)
        self.borrados.append(alerta_id)
        return _r(204)

    def mensajes(self) -> list[str]:
        return sorted(a["mensaje"] for a in self.alertas.values())


class Telefono:
    """La app en un teléfono falso: Inicio, Login, Panel, editor 7.8, lista 7.10 y la hoja 7.9; archivos privados."""

    def __init__(self, api: Api) -> None:
        self.api = api
        self.ordenes: list[tuple[str, ...]] = []
        self.pantalla: str | None = None
        self.campos = ["", ""]
        self.foco: str | int | None = None
        self.login_listo = False
        self.busqueda = ""
        self.editando: dict | None = None
        self.archivos: dict[str, str] = {}  # ruta relativa → contenido
        self.segundos = 0  # hora del teléfono: 10:00:00 + segundos
        self.lista_vieja = False  # la lista 7.10 no relee el backend al abrirse

    def hora(self, avance: int = 0) -> str:
        self.segundos += avance
        return f"2026-10-26 10:{self.segundos // 60:02d}:{self.segundos % 60:02d}"

    def log(self, nivel: str, tag: str, texto: str) -> None:
        linea = f"{self.hora(5)}.123 {nivel}/{tag} [main] [admin-1] {texto}\n"
        self.archivos[comun.LOG_APP] = self.archivos.get(comun.LOG_APP, "") + linea

    def recorrido(self, carpeta: str, nombre: str, fotos: int = 3, remoto: bool = False) -> None:
        manifest = {
            "name": nombre,
            "estado": "finalizado",
            "photos": [
                {"id": f"{i:04d}", "file": f"photos/{i:04d}.jpg", "lat": FOTO[0] + i * 1e-5, "lng": FOTO[1]}
                for i in range(1, fotos + 1)
            ],
        }
        if remoto:
            manifest |= {"remote_video_id": "uuid-v", "subida_estado": "subiendo"}
        self.archivos[f"files/recoleccion/{carpeta}/manifest.json"] = json.dumps(manifest)

    def _filas(self) -> list[dict]:
        palabras = _norm(self.busqueda)
        alertas = list(self.api.alertas.values())
        if self.lista_vieja:
            alertas = [a for a in alertas if a["mensaje"] != validate33.MENSAJE_C3]
        return [a for a in alertas if palabras in _norm(a["mensaje"])]

    def _nodos(self) -> list[str]:
        if self.login_listo:
            self.login_listo, self.pantalla = False, "panel"
        if self.pantalla == "inicio":
            return [_nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080))]
        if self.pantalla == "login":
            return [
                _nodo(texto=self.campos[0], clase="android.widget.EditText", limites=(60, 900, 1020, 1060)),
                _nodo(texto="•" * len(self.campos[1]), clase="android.widget.EditText", limites=(60, 1100, 1020, 1260)),
                _nodo(texto="Iniciar sesión", limites=(300, 1380, 800, 1450)),
            ]
        if self.pantalla == "panel":
            return [_nodo(texto=validate33.saludo_esperado(NOMBRE_ADMIN), limites=(100, 200, 900, 280))]
        if self.pantalla == "editor":
            return [_nodo(texto="Guardar / Sincronizar", limites=(500, 2200, 1000, 2280))]
        if self.pantalla == "lista":
            nodos = [
                _nodo(texto="Alertas", limites=(100, 100, 400, 160)),
                _nodo(texto=self.busqueda, clase="android.widget.EditText", limites=(40, 300, 1040, 400)),
            ]
            if not self.busqueda:
                nodos.append(_nodo(texto=validate33.BUSCADOR_LISTA, limites=(120, 320, 600, 380)))
            y = 600
            for a in self._filas():
                desc = (
                    f"{a['mensaje']}, {TIPOS[a.get('tipo', 'otro')]}, prioridad {a.get('prioridad', 'normal')}, "
                    f"{'activa' if a.get('activa', True) else 'inactiva'}. Toca para editar."
                )
                nodos.append(_nodo(desc=desc, clase="android.view.View", limites=(40, y, 1040, y + 200)))
                y += 220
            return nodos
        if self.pantalla == "form":
            assert self.editando is not None
            return [
                _nodo(texto="Editar alerta", limites=(60, 1000, 600, 1060)),
                _nodo(texto=self.editando["mensaje"], clase="android.widget.EditText", limites=(40, 1100, 1040, 1250)),
            ]
        return [_nodo(texto="Escritorio", limites=(0, 0, 1080, 2400))]

    def _tocar(self, x: int, y: int) -> None:
        if self.pantalla == "inicio" and 2000 <= y <= 2100:
            self.pantalla, self.campos = "login", ["", ""]
        elif self.pantalla == "login":
            if 900 <= y <= 1060:
                self.foco = 0
            elif 1100 <= y <= 1260:
                self.foco = 1
            elif 1330 <= y <= 1500 and tuple(self.campos) == ADMIN:
                self.login_listo = True
        elif self.pantalla == "lista":
            if 300 <= y <= 400:
                self.foco = "busqueda"
            elif y >= 600:
                filas = self._filas()
                i = (y - 600) // 220
                if i < len(filas):
                    self.pantalla, self.editando = "form", filas[i]

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.ordenes.append(args)
        ok = comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            xml = (
                f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(self._nodos())}</hierarchy>"
            )
            return comun.Resultado(0, xml, "")
        if args[:3] == ("exec-out", "run-as", comun.PAQUETE):
            if args[3] == "cat":
                contenido = self.archivos.get(args[4])
                return (
                    comun.Resultado(0, contenido, "")
                    if contenido is not None
                    else comun.Resultado(1, "", "No such file")
                )
            if args[3:5] == ("ls", "-1"):
                prefijo = args[5] + "/"
                nombres = sorted({r[len(prefijo) :].split("/")[0] for r in self.archivos if r.startswith(prefijo)})
                return comun.Resultado(0, "\n".join(nombres) + "\n", "") if nombres else comun.Resultado(1, "", "")
        if args[0] != "shell":
            return ok
        orden = args[1:]
        if orden[:2] == ("getprop", "ro.product.model"):
            return comun.Resultado(0, "23028RA60L\n", "")
        if orden[:2] == ("getprop", "ro.build.version.release"):
            return comun.Resultado(0, "14\n", "")
        if orden[:2] == ("getprop", "ro.build.version.sdk"):
            return comun.Resultado(0, "34\n", "")
        if orden[:1] == ("date",):
            return comun.Resultado(0, self.hora(1).replace(" ", "_") + "\n", "")
        if orden[:2] == ("am", "force-stop"):
            self.pantalla, self.login_listo = None, False
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "Status: ok\n", "")
        if orden[:3] == ("run-as", comun.PAQUETE, "rm"):
            carpeta = orden[-1] + "/"
            self.archivos = {r: c for r, c in self.archivos.items() if not r.startswith(carpeta)}
            return ok
        if orden[:2] == ("input", "tap"):
            self._tocar(int(orden[2]), int(orden[3]))
            return ok
        if orden[:2] == ("input", "text"):
            texto = orden[2].replace("\\", "").replace("%s", " ")
            if self.foco == "busqueda":
                self.busqueda += texto
            elif isinstance(self.foco, int):
                self.campos[self.foco] += texto
            return ok
        if orden[:2] == ("input", "keyevent") and orden[2] == comun.TECLA_ATRAS and self.pantalla == "form":
            self.pantalla, self.editando = "lista", None
            return ok
        if orden[:2] == ("dumpsys", "input_method"):
            return comun.Resultado(0, "  mInputShown=false\n", "")
        if orden[:2] == ("wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        return ok


class Mundo:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.t = 1000.0
        self.api = Api()
        self.telefono = Telefono(self.api)
        self.casos = {
            "RemoteAlertasRepositoryTest": 11,
            "AlmacenAlertasTest": 3,
            "ReglasAlertasTest": 8,
            "FormularioAlertaTest": 9,
        }
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []
        self.enter_eof = False
        self.be33_hecho = True
        # Lo que hace la persona (y la app) en cada paso guiado
        self.desvio_c1 = 0.0  # grados de latitud entre la alerta y la primera foto
        self.sincroniza = True
        self.c2_con_upsert = False  # una app con el defecto de FE-3.3: envía upsert + eliminar
        self.error_en_log = False

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP, encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(PLAN_BACKEND if self.be33_hecho else PLAN_BACKEND.replace("Hecho", "En curso"), "utf-8")
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "PLAN_BACKEND", plan_be)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.telefono.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "http_get", self.api.http_get)
        monkeypatch.setattr(comun, "http_post_json", self.api.http_post_json)
        monkeypatch.setattr(comun, "http_delete", self.api.http_delete)
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", lambda: self.t)
        monkeypatch.setattr(comun, "dormir", self.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def dormir(self, s: float) -> None:
        self.t += s

    def _sincronizar_app(self, cambios: list[dict]) -> None:
        """Lo que hace la app al pulsar «Guardar / Sincronizar» (RemoteAlertasRepository): POST y su línea de log."""
        if not self.sincroniza:
            return
        self.api.http_post_json(f"{URL}/admin/alerts/sincronizar", {"cambios": cambios}, token=TOKEN)
        n = len(cambios)
        self.telefono.log("I", "Api", "POST /v1/admin/alerts/sincronizar -> 200 (80 ms) rid=x")
        self.telefono.log("I", "Alertas", f"Alertas sincronizadas: {n} enviadas, {n} aplicadas, 0 rechazadas")

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos_guiados.append(instruccion)
        if self.enter_eof:
            raise comun.ErrorConfiguracion(
                "el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)"
            )
        t = self.telefono
        if validate33.MENSAJE_C1 in instruccion:
            t.recorrido("rec_0007", validate33.VIDEO_PRUEBA)
            alerta = {
                "id": "a-c1",
                "lat": round(FOTO[0] + self.desvio_c1, 6),
                "lng": FOTO[1],
                "mensaje": validate33.MENSAJE_C1,
            }
            self._sincronizar_app([{"op": "upsert", "alerta": alerta}])
            t.pantalla = "editor"
        elif validate33.MENSAJE_C2 in instruccion:
            if self.error_en_log:
                t.log("E", "EditorMapa", "Uncaught TypeError en editor_mapa.js")
            cambios = [{"op": "eliminar", "id": "a-c2"}]
            if self.c2_con_upsert:
                alerta = {"id": "a-c2", "lat": 6.2, "lng": -75.57, "mensaje": validate33.MENSAJE_C2}
                cambios = [{"op": "upsert", "alerta": alerta}, *cambios]
            self._sincronizar_app(cambios)
            t.pantalla = "editor"
        elif "Ver lista" in instruccion:
            t.pantalla, t.busqueda, t.foco = "lista", "", None
        else:
            raise AssertionError(instruccion)

    def gradle(self, *args, timeout=0):
        self.gradle_ordenes.append(args)
        if "--version" in args:
            return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11\n", "")
        if "installDebug" in args:
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        if "testDebugUnitTest" in args:
            for clase, casos in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{casos}" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
                    )
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        return comun.Resultado(0, "", "")


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate33.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


def test_fila_de_710_y_alertas_de_prueba():
    desc = "validacion-3-3-c3, Obra, prioridad normal, activa, sin sincronizar. Toca para editar."
    assert validate33.mensaje_de_fila(desc) == "validacion-3-3-c3"
    assert validate33.mensaje_de_fila(
        "Hay bancas, cuidado, Mobiliario, prioridad alta, inactiva. Toca para editar."
    ) == ("Hay bancas, cuidado")
    assert validate33.mensaje_de_fila("Biblioteca, Biblioteca. Toca para elegir este destino.") is None
    items = [
        {"id": "1", "mensaje": "VALIDACIÓN-3-3-C1"},
        {"id": "2", "mensaje": "validacion-3-3-c3"},
        {"id": "3", "mensaje": "validacion-3-3-c1 de otra persona"},  # contiene el prefijo, no es de la prueba
    ]
    assert [i["id"] for i in validate33.alertas_de_prueba(items)] == ["1", "2"]
    assert [i["id"] for i in validate33.alertas_de_prueba(items, validate33.MENSAJE_C3)] == ["2"]


def test_recorrido_log_y_distancia():
    texto = json.dumps(
        {
            "name": "validacion-3-3",
            "estado": "finalizado",
            "photos": [{"id": "0002", "lat": 6.3, "lng": -75.5}, {"id": "0001", "lat": 6.2, "lng": -75.6}],
        }
    )
    r = validate33.leer_recorrido("rec_0001", texto)
    assert r is not None and r.primera == (6.2, -75.6) and r.fotos == 2 and validate33.borrable(r)
    assert validate33.leer_recorrido("rec_0002", "{roto") is None
    log = (
        "2026-10-26 10:00:01.000 I/Alertas [main] [s] Alertas sincronizadas: 2 enviadas, 1 aplicadas, 1 rechazadas\n"
        "2026-10-26 10:00:02.000 E/CRASH [main] [s] java.lang.IllegalStateException\n"
        "\tat com.example.Algo\n"
        "2026-10-26 09:59:59.000 I/Alertas [main] [s] Alertas sincronizadas: 9 enviadas, 9 aplicadas, 0 rechazadas\n"
    )
    lineas = validate33.lineas_log(log, "2026-10-26 10:00:00")
    assert validate33.sincronizaciones(lineas) == [(2, 1, 1)]
    assert [linea.tag for linea in validate33.errores_log(lineas)] == ["CRASH"]
    assert validate33.distancia_m(6.2, -75.5, 6.2003, -75.5) == pytest.approx(33.36, abs=0.01)


# --- validador completo ------------------------------------------------------------------------------------------


def test_dev_todo_bien_limpia_y_no_imprime_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    m.api.upsert({"id": "resto", "lat": 6.2, "lng": -75.5, "mensaje": "Validacion-3-3-C3"})
    m.api.upsert({"id": "real", "lat": 6.2, "lng": -75.5, "mensaje": "validacion-3-3-c1 de otra persona"})
    m.telefono.recorrido("rec_0003", validate33.VIDEO_PRUEBA)  # resto local de otra ejecución
    m.telefono.recorrido("rec_0004", validate33.VIDEO_PRUEBA, remoto=True)  # ya lo conoce el backend: se queda
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert _estados(datos) == {"C1a": "pasa", "C2a": "pasa", "C3a": "pasa", "C1b": "pasa", "C2b": "pasa", "C3b": "pasa"}
    assert "activa, a 1.1 m de la primera foto (máximo 30)" in _detalle(datos, "C1b")
    assert "sin borradas ajenas" in _detalle(datos, "C2b")
    assert "muestra validacion-3-3-c1, validacion-3-3-c1 de otra persona, validacion-3-3-c3;" in _detalle(datos, "C3b")
    assert "sigue en la versión 1" in _detalle(datos, "C3b")
    assert [x["id"] for x in datos["manuales"]] == ["C3c"]
    # La sonda de P6 no dejó rastro (eliminar de un id desconocido); C2 tampoco.
    assert not any(validate33.MENSAJE_C2 in json.dumps(c) for c in m.api.sincronizaciones if c[0]["op"] == "upsert")
    # Limpieza: el resto al empezar; al terminar, c1 y c3; la ajena se queda. Recorridos: los de prueba sin subir.
    assert m.api.borrados[0] == "resto"
    assert m.api.mensajes() == ["validacion-3-3-c1 de otra persona"]
    rutas = set(m.telefono.archivos)
    assert not any(
        r.startswith("files/recoleccion/rec_0003/") or r.startswith("files/recoleccion/rec_0007/") for r in rutas
    )
    assert "files/recoleccion/rec_0004/manifest.json" in rutas
    assert m.telefono.pantalla is None  # am force-stop
    assert len(m.pasos_guiados) == 3
    assert not any(o[:3] == ("shell", "pm", "clear") for o in m.telefono.ordenes)
    assert [o for o in m.gradle_ordenes if "testDebugUnitTest" in o] == [
        (
            "testDebugUnitTest",
            "--tests", "*.RemoteAlertasRepositoryTest",
            "--tests", "*.AlmacenAlertasTest",
            "--tests", "*.ReglasAlertasTest",
            "--tests", "*.FormularioAlertaTest",
        )
    ]  # fmt: skip
    salida = capsys.readouterr()
    informe = json.dumps(datos, ensure_ascii=False)
    for secreto in (ADMIN[1], TOKEN):
        assert secreto not in salida.out
        assert secreto not in salida.err
        assert secreto not in informe


def test_local_sin_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1"]
    assert _estados(datos) == {
        "C1a": "pasa", "C2a": "pasa", "C3a": "pasa", "C1b": "omitida", "C2b": "omitida", "C3b": "omitida",
    }  # fmt: skip
    assert m.telefono.ordenes == [] and m.api.sincronizaciones == []
    assert [x["id"] for x in datos["manuales"]] == ["C3c"]


def test_c2_con_upsert_y_eliminar_deja_tombstone(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.c2_con_upsert = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    assert _estados(datos)["C2b"] == "falla"
    assert "borrada(s) que no borró el validador" in _detalle(datos, "C2b")
    assert _estados(datos)["C3b"] == "pasa"  # las demás siguen


def test_c2_con_error_en_el_log(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.error_en_log = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 1
    assert "E/EditorMapa" in _detalle(datos, "C2b")


def test_c1_lejos_de_la_foto_y_sin_sincronizar(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.desvio_c1 = 0.0005  # ~55 m
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "m de la primera foto de rec_0007 (máximo 30 m)" in _detalle(datos, "C1b")

    m2 = Mundo(tmp_path)
    m2.sincroniza = False
    m2.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "no hay «Alertas sincronizadas: …»" in _detalle(datos, "C1b")


def test_c3_la_lista_no_trae_la_alerta_del_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.lista_vieja = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 1
    assert "no apareció las filas validacion-3-3-c3" in _detalle(datos, "C3b")
    assert m.api.mensajes() == []  # la limpieza borró la creada por la API


def test_be33_sin_hecho_y_credenciales_malas(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.be33_hecho = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert "BE-3.3 no está «Hecho»" in _detalle(datos, "P6")

    m2 = Mundo(tmp_path)
    m2.api.login_estado = 401
    m2.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert m2.telefono.ordenes[:1] != [("shell", "pm", "clear")]


def test_solo_jvm_en_dev_no_usa_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C2a,C3a"])
    assert codigo == 0, datos
    assert {p["id"]: p["estado"] for p in datos["precondiciones"]}["P6"] == "no evaluada"
    assert m.telefono.ordenes == [] and m.api.sincronizaciones == []


def test_jvm_que_falla_omite_el_telefono(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos["ReglasAlertasTest"] = 2
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    assert _estados(datos)["C2a"] == "falla"
    assert _estados(datos)["C1b"] == "omitida" and "falló C2a" in _detalle(datos, "C1b")
    assert m.pasos_guiados == []


def test_eof_en_el_paso_guiado(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.enter_eof = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 3
    assert m.api.mensajes() == []  # la limpieza corrió
