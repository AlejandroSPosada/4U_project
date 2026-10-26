"""Pruebas de validate34.py con un teléfono, Gradle y la API simulados.

El backend falso guarda lugares con la regla de nombre único del backend (normalizado sin tildes ni mayúsculas →
`409 NOMBRE_DUPLICADO`) y responde `GET /v1/places` con y sin posición (haversine, como backend §5.3). El teléfono falso
dibuja Inicio, Login, el Panel, la lista 7.6 («Vista de lista»), el formulario 7.7 (campo Nombre, pie «Punto: …» y
«Guardar») y Selección de destino (buscador y filas con el `content-desc` de `FilaLugar`). Tocar «Guardar» hace lo que
hace la app: `POST /v1/admin/places` con la coordenada del pie; con `409`, el mensaje bajo el nombre. Los pasos guiados
(`comun.esperar_enter`) se sustituyen por lo que hace la persona.
"""

from __future__ import annotations

import json
import math
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate34

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
NOMBRE_ADMIN = "Alejandro Gómez"
PLAN_APP = "| FE-1.2 | 1 | Hecho | [1-2](x) | `4d578c5` 2026-10-25 | 0.5.0 | | |\n| FE-3.4 | 3 | En curso | | | | | |\n"
PLAN_BACKEND = "| BE-3.1 | 3 | Hecho | [3-1](x) | `86fc024` 2026-10-25 | 0.11.0 | |\n"
PUNTO_ELEGIDO = ("6.201234", "-75.577777")  # lo que toca la persona en el mapa de 7.7
DUPLICADO = "Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes)."


def _norm(texto: str) -> str:
    sin = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin.casefold().split())


def _distancia(lat1, lng1, lat2, lng2) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), enabled=True):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="{str(enabled).lower()}" password="false"/>'
    )


class Api:
    """Backend falso: salud, login y lugares (públicos y de administración) con la regla de nombre único."""

    def __init__(self) -> None:
        self.lugares: dict[str, dict] = {}
        self.siguiente = 1
        self.login_estado = 200
        self.creados: list[dict] = []
        self.borrados: list[str] = []
        self.rechazados_409 = 0
        self._crear({"nombre": "Biblioteca Central", "categoria": "biblioteca", "lat": 6.2009, "lng": -75.5783})
        self._crear({"nombre": "Bloque 19", "categoria": "bloque", "lat": 6.2002, "lng": -75.5779})

    def _crear(self, cuerpo: dict) -> dict:
        lugar = {"alias": [], **cuerpo, "id": f"uuid-{self.siguiente}", "imagen_url": None, "total_fotos": 0}
        self.siguiente += 1
        self.lugares[lugar["id"]] = lugar
        return lugar

    def crear(self, cuerpo: dict) -> comun.RespuestaHttp:
        if any(_norm(lug["nombre"]) == _norm(cuerpo["nombre"]) for lug in self.lugares.values()):
            self.rechazados_409 += 1
            error = {"error": {"codigo": "NOMBRE_DUPLICADO", "mensaje": DUPLICADO, "detalle": None}}
            return comun.RespuestaHttp(409, {}, json.dumps(error), 30)
        lugar = self._crear(dict(cuerpo))
        self.creados.append(lugar)
        return comun.RespuestaHttp(201, {}, json.dumps(lugar), 30)

    def publicos(self, lat: float | None = None, lng: float | None = None) -> list[dict]:
        items = [{k: v for k, v in lug.items() if k != "total_fotos"} for lug in self.lugares.values()]
        if lat is None:
            return sorted([i | {"distancia_m": None} for i in items], key=lambda lug: _norm(lug["nombre"]))
        con = [i | {"distancia_m": _distancia(lat, lng, i["lat"], i["lng"])} for i in items]
        con.sort(key=lambda lug: lug["distancia_m"])
        return [i | {"distancia_m": round(i["distancia_m"], 1)} for i in con]

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta = u.path.removeprefix("/v1")
        q = parse_qs(u.query)
        if ruta == "/health":
            return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok"}), 30)
        if ruta == "/places":
            assert token is None
            lat = float(q["lat"][0]) if "lat" in q else None
            lng = float(q["lng"][0]) if "lng" in q else None
            items = self.publicos(lat, lng)
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            filtro = _norm(q["q"][0]) if "q" in q else ""
            items = [lug for lug in self.lugares.values() if filtro in _norm(lug["nombre"])]
            items.sort(key=lambda lug: _norm(lug["nombre"]))
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        ruta = urlparse(url).path.removeprefix("/v1")
        if ruta == "/auth/login":
            if self.login_estado != 200:
                return comun.RespuestaHttp(401, {}, json.dumps({"error": {"codigo": "CREDENCIALES_INVALIDAS"}}), 30)
            assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
            usuario = {"id": "u1", "nombre": NOMBRE_ADMIN, "correo": ADMIN[0], "rol": "admin"}
            return comun.RespuestaHttp(200, {}, json.dumps({"token": TOKEN, "usuario": usuario}), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            return self.crear(cuerpo)
        raise AssertionError(url)

    def http_delete(self, url, *, timeout=15.0, token=None):
        assert token == TOKEN
        lugar_id = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        self.lugares.pop(lugar_id, None)
        self.borrados.append(lugar_id)
        return comun.RespuestaHttp(204, {}, "", 30)

    def nombres(self) -> list[str]:
        return sorted(lug["nombre"] for lug in self.lugares.values())


class Telefono:
    """La app en un teléfono falso: Inicio, Login, Panel, 7.6, 7.7 y Selección de destino."""

    def __init__(self, api: Api) -> None:
        self.api = api
        self.ordenes: list[tuple[str, ...]] = []
        self.pantalla: str | None = None
        self.campos = ["", ""]
        self.foco: str | int | None = None
        self.login_listo = False
        # formulario 7.7
        self.nombre = ""
        self.alias = ""
        self.categoria: str | None = None
        self.punto: tuple[str, str] | None = None
        self.error: str | None = None
        # Selección de destino
        self.busqueda = ""
        # Defectos que se pueden simular
        self.desvio_lat = 0.0  # la app guarda otra latitud que la del pie
        self.sin_red = False  # «Guardar» falla sin red
        self.ignora_409 = False  # la app vuelve a 7.6 aunque el backend dé 409
        self.destino_oculta: str | None = None  # nombre que Destino no muestra

    # --- lo que hace la app

    def _guardar(self) -> None:
        if self.sin_red:
            self.error = "Sin conexión. Revisa tu conexión a internet e inténtalo de nuevo."
            return
        assert self.punto is not None and self.categoria is not None
        cuerpo = {
            "nombre": self.nombre.strip(),
            "categoria": self.categoria,
            "lat": float(self.punto[0]) + self.desvio_lat,
            "lng": float(self.punto[1]),
            "alias": [a.strip() for a in self.alias.split(",") if a.strip()],
        }
        r = self.api.crear(cuerpo)
        if r.estado == 409 and not self.ignora_409:
            self.error = DUPLICADO
            return
        self.pantalla, self.error = "lista", None

    # --- pantallas

    def _nodos(self) -> list[str]:
        if self.login_listo:
            self.login_listo, self.pantalla = False, "panel"
        if self.pantalla == "inicio":
            return [
                _nodo(desc="Acceso administrador", clase="android.view.View", limites=(100, 2000, 980, 2100)),
                _nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080)),
            ]
        if self.pantalla == "login":
            puede = bool(self.campos[0]) and bool(self.campos[1])
            return [
                _nodo(texto=self.campos[0], clase="android.widget.EditText", limites=(60, 900, 1020, 1060)),
                _nodo(texto="•" * len(self.campos[1]), clase="android.widget.EditText", limites=(60, 1100, 1020, 1260)),
                _nodo(clase="android.widget.Button", limites=(60, 1330, 1020, 1500), enabled=puede),
                _nodo(texto="Iniciar sesión", limites=(300, 1380, 800, 1450)),
            ]
        if self.pantalla == "panel":
            return [_nodo(texto=validate34.saludo_esperado(NOMBRE_ADMIN), limites=(100, 200, 900, 280))]
        if self.pantalla == "lista":
            return [
                _nodo(texto="Lugares", limites=(100, 100, 400, 160)),
                _nodo(texto=f"{len(self.api.lugares)} lugares registrados", limites=(100, 170, 600, 210)),
                _nodo(desc="Vista de lista", clase="android.view.View", limites=(40, 240, 540, 300)),
                _nodo(texto="Nuevo lugar", limites=(700, 2200, 1000, 2280)),
            ]
        if self.pantalla == "form":
            punto = f"Punto: {self.punto[0]}, {self.punto[1]}" if self.punto else "Punto: sin elegir (toca el mapa)"
            nodos = [
                _nodo(texto="Nuevo lugar", limites=(100, 100, 500, 160)),
                _nodo(texto=self.nombre, clase="android.widget.EditText", limites=(40, 300, 1040, 420)),
                _nodo(texto="Único: no distingue mayúsculas ni tildes.", limites=(60, 430, 900, 470)),
                _nodo(texto=punto, limites=(40, 2100, 1040, 2150)),
                _nodo(texto="Cancelar", limites=(80, 2200, 500, 2280)),
                _nodo(clase="android.widget.Button", limites=(540, 2180, 1040, 2300)),
                _nodo(texto="Guardar", limites=(700, 2210, 900, 2270)),
            ]
            if self.error:
                nodos.append(_nodo(texto=self.error, limites=(60, 480, 1000, 520)))
            return nodos
        if self.pantalla == "destino":
            nodos = [
                _nodo(texto=validate34.TITULO_DESTINO, limites=(100, 300, 1000, 380)),
                _nodo(texto=self.busqueda, clase="android.widget.EditText", limites=(40, 900, 1040, 1000)),
            ]
            palabras = _norm(self.busqueda).replace("-", " ").split()
            y = 1100
            for lug in sorted(self.api.lugares.values(), key=lambda x: _norm(x["nombre"])):
                if lug["nombre"] == self.destino_oculta:
                    continue
                texto = _norm(lug["nombre"]).replace("-", " ")
                if all(p in texto for p in palabras):
                    etiqueta = {"bloque": "Bloque", "biblioteca": "Biblioteca"}[lug["categoria"]]
                    desc = f"{lug['nombre']}, {etiqueta}. Toca para elegir este destino."
                    nodos.append(_nodo(desc=desc, clase="android.view.View", limites=(40, y, 1040, y + 200)))
                    y += 220
            return nodos
        return [_nodo(texto="Escritorio", limites=(0, 0, 1080, 2400))]

    def _xml(self) -> str:
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(self._nodos())}</hierarchy>"

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
        elif self.pantalla == "form" and 2180 <= y <= 2300 and x >= 540:
            self._guardar()
        elif self.pantalla == "destino" and 900 <= y <= 1000:
            self.foco = "busqueda"

    # --- adb

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.ordenes.append(args)
        ok = comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            return comun.Resultado(0, self._xml(), "")
        if args[0] != "shell":
            return ok
        orden = args[1:]
        if orden[:2] == ("getprop", "ro.product.model"):
            return comun.Resultado(0, "23028RA60L\n", "")
        if orden[:2] == ("getprop", "ro.build.version.release"):
            return comun.Resultado(0, "14\n", "")
        if orden[:2] == ("getprop", "ro.build.version.sdk"):
            return comun.Resultado(0, "34\n", "")
        if orden[:2] == ("am", "force-stop"):
            self.pantalla, self.login_listo = None, False
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "Status: ok\n", "")
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
        self.casos = {"RemoteLugaresAdminRepositoryTest": 11, "FormularioLugarTest": 12, "ErroresLugarTest": 5}
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []
        self.enter_eof = False
        self.be31_hecho = True
        # Lo que hace la persona en cada paso guiado
        self.nombre_c1b = validate34.LUGAR_PRUEBA
        self.toca_mapa = True

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP, encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(PLAN_BACKEND if self.be31_hecho else PLAN_BACKEND.replace("Hecho", "En curso"), "utf-8")
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

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos_guiados.append(instruccion)
        if self.enter_eof:
            raise comun.ErrorConfiguracion(
                "el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)"
            )
        t = self.telefono
        if "validacion-3-4-lugar" in instruccion:
            t.pantalla, t.nombre, t.alias, t.categoria, t.error = "form", self.nombre_c1b, "validacion", "bloque", None
            t.punto = PUNTO_ELEGIDO if self.toca_mapa else None
        elif "«dos»" in instruccion:
            t.pantalla, t.busqueda, t.foco = "destino", "", None
        elif validate34.NOMBRE_DUPLICADO_ESCRITO in instruccion:
            t.pantalla, t.nombre, t.alias, t.categoria, t.error = "form", "VALIDACIÓN-3-4-DUP", "", "bloque", None
            t.punto = ("6.200000", "-75.500000")
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
    codigo = validate34.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


def test_punto_del_formulario_y_pantallas():
    nodos = comun.parsear_ui(
        "<hierarchy>"
        + _nodo(texto="Punto: 6.200512, -75.578311", limites=(0, 0, 9, 9))
        + _nodo(texto="Ya existe un lugar con ese nombre (sin distinguir mayúsculas ni tildes).", limites=(0, 0, 9, 9))
        + "</hierarchy>"
    )
    assert validate34.punto_del_formulario(nodos) == ("6.200512", "-75.578311")
    assert validate34.en_formulario(nodos)
    assert validate34.error_del_formulario(nodos).startswith("Ya existe")
    sin = comun.parsear_ui("<hierarchy>" + _nodo(texto="Punto: sin elegir (toca el mapa)") + "</hierarchy>")
    assert validate34.punto_del_formulario(sin) is None and validate34.en_formulario(sin)
    # Con coma decimal (teléfono en español sin Locale.ROOT) no se acepta: la app debe mostrar punto decimal.
    coma = comun.parsear_ui("<hierarchy>" + _nodo(texto="Punto: 6,200512, -75,578311") + "</hierarchy>")
    assert validate34.punto_del_formulario(coma) is None


def test_nombre_de_fila_destino_y_lugares_de_prueba():
    assert (
        validate34.nombre_de_fila_destino("validacion-3-4-lugar, Bloque, a 12 metros. Toca para elegir este destino.")
        == "validacion-3-4-lugar, Bloque"
    )
    assert validate34.nombre_de_fila_destino("Biblioteca Central, Biblioteca. Toca para editar.") is None
    items = [
        {"id": "1", "nombre": "VALIDACIÓN-3-4-LUGAR"},
        {"id": "2", "nombre": "validacion-3-4-dup"},
        {"id": "3", "nombre": "validacion-3-4-lugar viejo"},  # contiene el prefijo, pero no es de la prueba
        {"id": "4", "nombre": "Bloque 19"},
    ]
    assert [i["id"] for i in validate34.lugares_de_prueba(items)] == ["1", "2"]
    assert validate34.normalizar_nombre("  Café   NORTE ") == "cafe norte"


# --- validador completo ------------------------------------------------------------------------------------------


def test_dev_todo_bien_limpia_y_no_imprime_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    resto = m.api._crear({"nombre": "Validacion-3-4-Lugar", "categoria": "bloque", "lat": 6.2, "lng": -75.5})
    real = m.api._crear({"nombre": "validacion-3-4-lugar viejo", "categoria": "bloque", "lat": 6.21, "lng": -75.5})
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5", "P6"]
    assert _estados(datos) == {
        "C1a": "pasa", "C2a": "pasa", "C3a": "pasa", "C1b": "pasa", "C2b": "pasa", "C1c": "pasa", "C3b": "pasa",
    }  # fmt: skip
    assert [c["id"] for c in datos["comprobaciones"]] == ["C1a", "C2a", "C3a", "C1b", "C2b", "C1c", "C3b"]
    assert "aparece una vez en GET /v1/places (categoria bloque, alias [validacion]" in _detalle(datos, "C1b")
    assert "GET /v1/places?lat=6.201234&lng=-75.577777" in _detalle(datos, "C2b")
    assert "distancia_m = 0.0" in _detalle(datos, "C2b")
    assert "muestra la fila «validacion-3-4-lugar, Bloque»" in _detalle(datos, "C1c")
    assert "«VALIDACIÓN-3-4-DUP» → 409" in _detalle(datos, "C3b")
    assert m.api.rechazados_409 == 1
    # Limpieza: el resto se borró al empezar; al terminar, el lugar de la app y el duplicado; el real se queda.
    assert m.api.borrados[0] == resto["id"]
    assert real["id"] in m.api.lugares
    assert m.api.nombres() == ["Biblioteca Central", "Bloque 19", "validacion-3-4-lugar viejo"]
    assert m.telefono.pantalla is None  # am force-stop
    assert len(m.pasos_guiados) == 3
    assert m.telefono.busqueda == validate34.BUSQUEDA_DESTINO
    assert not any(o[:3] == ("shell", "pm", "clear") for o in m.telefono.ordenes)
    assert [o for o in m.gradle_ordenes if "testDebugUnitTest" in o] == [
        (
            "testDebugUnitTest",
            "--tests",
            "*.RemoteLugaresAdminRepositoryTest",
            "--tests",
            "*.FormularioLugarTest",
            "--tests",
            "*.ErroresLugarTest",
        )
    ]
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
        "C1a": "pasa", "C2a": "pasa", "C3a": "pasa",
        "C1b": "omitida", "C2b": "omitida", "C1c": "omitida", "C3b": "omitida",
    }  # fmt: skip
    assert m.telefono.ordenes == [] and m.api.creados == [] and m.pasos_guiados == []


def test_la_app_guarda_otra_posicion_c2b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.desvio_lat = 0.0001  # ~11 m al norte del punto del pie
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1, datos
    assert _estados(datos)["C1b"] == "pasa" and _estados(datos)["C2b"] == "falla"
    assert "está a 11.1 m" in _detalle(datos, "C2b")
    assert validate34.LUGAR_PRUEBA not in m.api.nombres()  # la limpieza lo borró igual


def test_nombre_equivocado_no_guarda_y_omite_lo_que_depende(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.nombre_c1b = "Mi lugar"
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1, datos
    estados = _estados(datos)
    assert estados["C1b"] == "falla" and "«Mi lugar», no «validacion-3-4-lugar»" in _detalle(datos, "C1b")
    assert estados["C2b"] == "omitida" and estados["C1c"] == "omitida" and estados["C3b"] == "pasa"
    assert "C1b no creó el lugar" in _detalle(datos, "C2b")
    assert "Mi lugar" not in m.api.nombres() and m.api.creados[0]["nombre"] == validate34.LUGAR_DUPLICADO


def test_sin_tocar_el_mapa_c1b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.toca_mapa = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert "falta tocar el mapa" in _detalle(datos, "C1b")
    assert m.api.creados == []


def test_error_al_guardar_se_informa(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.sin_red = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1, datos
    assert "el formulario no guardó: «Sin conexión." in _detalle(datos, "C1b")


def test_la_app_cierra_el_formulario_con_un_409_c3b_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.ignora_409 = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C3b"])
    assert codigo == 1, datos
    assert "se cerró como si hubiera guardado" in _detalle(datos, "C3b")
    assert validate34.LUGAR_DUPLICADO not in m.api.nombres()  # limpieza


def test_destino_sin_la_fila_c1c_falla(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.telefono.destino_oculta = validate34.LUGAR_PRUEBA
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b,C1c"])
    assert codigo == 1, datos
    assert _estados(datos)["C1b"] == "pasa" and _estados(datos)["C1c"] == "falla"
    assert "no muestra «validacion-3-4-lugar, Bloque»" in _detalle(datos, "C1c")


def test_c2b_sin_c1b_se_omite(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2b"])
    assert codigo == 0, datos
    assert _estados(datos)["C2b"] == "omitida" and "necesita C1b" in _detalle(datos, "C2b")
    assert m.pasos_guiados == []


def test_be31_sin_hecho_bloquea(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.be31_hecho = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2, datos
    assert "BE-3.1 no está «Hecho»" in _detalle(datos, "P6")
    assert ("installDebug",) not in m.gradle_ordenes and m.api.creados == []


def test_credenciales_malas_dan_3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.login_estado = 401
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3, datos
    assert "las credenciales del admin no sirven" in _detalle(datos, "P4")


def test_solo_jvm_en_dev_no_usa_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1a,C2a,C3a"])
    assert codigo == 0, datos
    assert [p["estado"] for p in datos["precondiciones"]] == ["pasa"] + ["no evaluada"] * 5
    assert m.telefono.ordenes == [] and m.pasos_guiados == []


def test_jvm_que_falla_omite_el_telefono(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos["FormularioLugarTest"] = 3
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1, datos
    assert _estados(datos)["C2a"] == "falla"
    for id_ in ("C1b", "C2b", "C1c", "C3b"):
        assert _estados(datos)[id_] == "omitida" and "falló C2a" in _detalle(datos, id_)
    assert ("installDebug",) not in m.gradle_ordenes


def test_eof_en_el_paso_guiado_da_3_y_limpia(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.enter_eof = True
    resto = m.api._crear({"nombre": "validacion-3-4-dup", "categoria": "bloque", "lat": 6.2, "lng": -75.5})
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 3, datos
    assert _estados(datos)["C1b"] == "error"
    assert resto["id"] in m.api.borrados and m.telefono.pantalla is None


@pytest.mark.parametrize(
    "instruccion", [validate34.INSTRUCCION_C1B, validate34.INSTRUCCION_C1C, validate34.INSTRUCCION_C3B]
)
def test_instrucciones_sin_talkback_ni_guardar_por_la_persona(instruccion):
    assert "TalkBack" not in instruccion
    assert "Enter" in instruccion
