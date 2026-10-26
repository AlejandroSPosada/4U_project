"""Pruebas de validate31.py con un teléfono, Gradle y la API de lugares simulados.

El teléfono falso dibuja Inicio y Selección de destino como los vuelca uiautomator (la lista de lugares es una
columna que se desplaza con `input swipe` y solo vuelca las filas visibles, con el `content-desc` de `FilaLugar`).
La API falsa guarda los lugares: así se ejercitan de verdad la limpieza de restos, la creación y el borrado del lugar
de prueba. El paso guiado (`comun.esperar_enter`) se sustituye por «la persona dice dos».
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate31

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
PLAN_APP = "| FE-1.1 | 1 | Hecho | [1-1](x) | `c5917bd` | 0.4.0 | | |\n| FE-3.1 | 3 | En curso | | | | | |\n"
PLAN_BACKEND = "| BE-3.1 | 3 | Hecho | [3-1](x) | `86fc024` 2026-10-25 | 0.11.0 | |\n"
ALTO, FIN_LISTA, CABECERA, FILA = 2400, 2200, 1100, 230  # px: pantalla, borde del botón Volver, cabecera, fila


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def reloj(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.t += s


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10)):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="true" password="false"/>'
    )


class Api:
    """Lugares del backend falso (`GET /v1/places`, `/v1/admin/places`)."""

    def __init__(self, nombres: list[str]) -> None:
        self.lugares: dict[str, dict] = {}
        self.siguiente = 1
        self.login_estado = 200
        self.be31_hecho = True
        self.borrados: list[str] = []
        self.creados: list[dict] = []
        for n in nombres:
            self._crear({"nombre": n, "categoria": "bloque", "lat": 6.2 + len(self.lugares) * 0.001, "lng": -75.57})

    def _crear(self, cuerpo: dict) -> dict:
        lugar = {**cuerpo, "id": f"uuid-{self.siguiente}"}
        self.siguiente += 1
        self.lugares[lugar["id"]] = lugar
        return lugar

    def nombres(self) -> list[str]:
        return sorted((lugar["nombre"] for lugar in self.lugares.values()), key=validate31.normalizar_nombre)

    def _publico(self) -> dict:
        items = [{**lugar, "distancia_m": None, "imagen_url": None} for lugar in self.lugares.values()]
        items.sort(key=lambda i: validate31.normalizar_nombre(i["nombre"]))
        return {"items": items, "total": len(items)}

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta = u.path.removeprefix("/v1")
        if ruta == "/health":
            return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok"}), 30)
        if ruta == "/places":
            return comun.RespuestaHttp(200, {}, json.dumps(self._publico()), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            q = validate31.normalizar_nombre(parse_qs(u.query)["q"][0])
            items = [lug for lug in self.lugares.values() if q in validate31.normalizar_nombre(lug["nombre"])]
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        ruta = urlparse(url).path.removeprefix("/v1")
        if ruta == "/auth/login":
            if self.login_estado != 200:
                return comun.RespuestaHttp(401, {}, json.dumps({"error": {"codigo": "CREDENCIALES_INVALIDAS"}}), 30)
            assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
            usuario = {"id": "u1", "nombre": "Admin", "correo": ADMIN[0], "rol": "admin"}
            return comun.RespuestaHttp(200, {}, json.dumps({"token": TOKEN, "usuario": usuario}), 30)
        if ruta == "/admin/places":
            assert token == TOKEN
            n = validate31.normalizar_nombre(cuerpo["nombre"])
            if any(validate31.normalizar_nombre(lug["nombre"]) == n for lug in self.lugares.values()):
                return comun.RespuestaHttp(409, {}, json.dumps({"error": {"codigo": "NOMBRE_DUPLICADO"}}), 30)
            lugar = self._crear(dict(cuerpo))
            self.creados.append(lugar)
            return comun.RespuestaHttp(201, {}, json.dumps(lugar), 30)
        raise AssertionError(url)

    def http_delete(self, url, *, timeout=15.0, token=None):
        assert token == TOKEN
        lugar_id = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        self.lugares.pop(lugar_id, None)
        self.borrados.append(lugar_id)
        return comun.RespuestaHttp(204, {}, "", 30)


class Telefono:
    """La app en un teléfono falso: Inicio y Selección de destino con una lista desplazable."""

    def __init__(self, reloj: Reloj, api: Api, *, sin_lugar_nuevo=False, error_carga=False, carga_s=1.0) -> None:
        self.reloj = reloj
        self.api = api
        self.sin_lugar_nuevo = sin_lugar_nuevo
        self.error_carga = error_carga
        self.carga_s = carga_s
        self.ordenes: list[tuple[str, ...]] = []
        self.pantalla: str | None = None
        self.lista: list[str] = []
        self.listo_en = 0.0
        self.desplazamiento = 0

    def abrir_destino(self) -> None:
        """Lo que pasa cuando la persona dice «dos»: Destino carga GET /v1/places (o la lista vieja)."""
        self.pantalla = "destino"
        self.desplazamiento = 0
        nombres = self.api.nombres()
        self.lista = [n for n in nombres if n != validate31.LUGAR_PRUEBA] if self.sin_lugar_nuevo else nombres
        self.listo_en = self.reloj.t + self.carga_s

    def _nodos(self) -> list[str]:
        if self.pantalla == "inicio":
            return [
                _nodo(desc="Acceso administrador", clase="android.view.View", limites=(100, 2000, 980, 2100)),
                _nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080)),
            ]
        if self.pantalla != "destino":
            return [_nodo(texto="Escritorio", limites=(0, 0, 1080, 2400))]
        d = self.desplazamiento
        nodos = []
        if d < 280:
            nodos.append(_nodo(texto="¿A dónde quieres ir?", limites=(60, 200 - d, 1020, 280 - d)))
        nodos.append(_nodo(texto="Volver", limites=(40, FIN_LISTA, 1040, ALTO)))
        if self.reloj.t < self.listo_en:
            return nodos  # cargando
        if self.error_carga:
            return nodos + [_nodo(texto="Sin conexión"), _nodo(texto="No se pudo cargar la lista de lugares.")]
        for i, nombre in enumerate(self.lista):
            arriba = CABECERA + i * FILA - d
            if arriba + FILA > 0 and arriba < FIN_LISTA:
                desc = f"{nombre}, Bloque. Toca para elegir este destino."
                nodos.append(_nodo(desc=desc, clase="android.view.View", limites=(40, arriba, 1040, arriba + FILA)))
                nodos.append(_nodo(texto=nombre, limites=(150, arriba + 20, 900, arriba + 80)))
        return nodos

    def _xml(self) -> str:
        return f"<?xml version='1.0' encoding='UTF-8'?><hierarchy rotation=\"0\">{''.join(self._nodos())}</hierarchy>"

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.reloj.t += 0.3
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
            self.pantalla = None
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            return comun.Resultado(0, "Status: ok\n", "")
        if orden[:2] == ("input", "swipe"):
            alto_lista = CABECERA + len(self.lista) * FILA
            self.desplazamiento = max(0, min(self.desplazamiento + 960, alto_lista - FIN_LISTA))
            return ok
        if orden[:2] == ("wm", "size"):
            return comun.Resultado(0, f"Physical size: 1080x{ALTO}\n", "")
        return ok


class Mundo:
    def __init__(self, tmp_path: Path, nombres: list[str] | None = None, **opciones_telefono) -> None:
        self.tmp = tmp_path
        self.reloj = Reloj()
        nombres = nombres if nombres is not None else [f"Lugar {i:02d}" for i in range(1, 16)] + ["Ágora"]
        self.api = Api(nombres)
        self.telefono = Telefono(self.reloj, self.api, **opciones_telefono)
        self.casos = {"RemoteLugaresRepositoryTest": 9, "ComandoParserTest": 5, "ObservadorPrimerPlanoTest": 6}
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos_guiados: list[str] = []
        self.abre_destino = True
        self.enter_eof = False

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP, encoding="utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(PLAN_BACKEND if self.api.be31_hecho else PLAN_BACKEND.replace("Hecho", "En curso"), "utf-8")
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
        monkeypatch.setattr(comun, "reloj", self.reloj.reloj)
        monkeypatch.setattr(comun, "dormir", self.reloj.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos_guiados.append(instruccion)
        if self.enter_eof:
            raise comun.ErrorConfiguracion(
                "el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)"
            )
        if self.abre_destino:
            self.telefono.abrir_destino()

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
    codigo = validate31.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("desc", "nombre"),
    [
        ("Biblioteca Central, Biblioteca. Toca para elegir este destino.", "Biblioteca Central"),
        ("Bloque 19, Bloque, a 85 metros. Toca para elegir este destino.", "Bloque 19"),
        ("Baños, piso 2, Baño. Toca para elegir este destino.", "Baños, piso 2"),
        ("validacion-3-1-lugar, Bloque. Toca para elegir este destino.", "validacion-3-1-lugar"),
        ("Café, Administración, a 1200 metros. Toca para elegir este destino.", "Café"),
        ("Bloque. Toca para elegir este destino.", None),  # sin nombre
        ("Micrófono. Toca dos veces para decir el nombre del lugar.", None),
        ("Biblioteca Central, Piscina. Toca para elegir este destino.", None),  # categoría que no existe
    ],
)
def test_nombre_de_fila(desc, nombre):
    assert validate31.nombre_de_fila(desc) == nombre


def test_normalizar_nombre_como_el_backend():
    assert validate31.normalizar_nombre("  Café   Norte ") == "cafe norte"
    assert validate31.normalizar_nombre("VALIDACION-3-1-Lugar") == "validacion-3-1-lugar"
    assert validate31.normalizar_nombre("Baño") == "bano"


def _archivos_reales() -> tuple[str, str, str, str]:
    return tuple(
        p.read_text(encoding="utf-8")
        for p in (
            validate31.MAIN_ACTIVITY,
            validate31.INICIO_SCREEN,
            validate31.INICIO_VIEWMODEL,
            validate31.MAPA_PUBLICO,
        )
    )


def test_c2b_pasa_con_el_codigo_real():
    detalle = validate31.comprobar_entrada_mapa(*_archivos_reales())
    assert 'navigate("mapa")' in detalle


@pytest.mark.parametrize(
    ("indice", "viejo", "nuevo", "mensaje"),
    [
        (0, 'onVerMapa = { nav.navigate("mapa")', "onVerMapa = { /* nada */ ", "onVerMapa"),
        (0, 'composable("mapa") {', 'composable("mapa2") {', "ruta mapa"),
        (1, 'CustomAccessibilityAction("Ver mapa")', 'CustomAccessibilityAction("Mapa")', "Ver mapa"),
        (1, "InicioEvento.VerMapa -> onVerMapa()", "InicioEvento.VerMapa -> Unit", "InicioEvento.VerMapa"),
        (2, "Comando.VER_MAPA -> navegar(InicioEvento.VerMapa)", "Comando.VER_MAPA -> repetirOpciones()", "VER_MAPA"),
        (3, "PdrTracker(ctx, cicloDeVida = cicloPantalla)", "PdrTracker(ctx)", "ciclo de vida"),
    ],
)
def test_c2b_falla_si_falta_una_pieza(indice, viejo, nuevo, mensaje):
    textos = list(_archivos_reales())
    assert viejo in textos[indice]
    textos[indice] = textos[indice].replace(viejo, nuevo)
    with pytest.raises(comun.Falla, match=re.escape(mensaje)):
        validate31.comprobar_entrada_mapa(*textos)


# --- validador completo ------------------------------------------------------------------------------------------


def test_dev_todo_bien_crea_y_borra_el_lugar_y_no_imprime_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    # Un resto de una ejecución anterior (con otras mayúsculas) y un lugar real que también contiene el prefijo.
    resto = m.api._crear({"nombre": "Validacion-3-1-Lugar", "categoria": "bloque", "lat": 6.2, "lng": -75.5})
    m.api._crear({"nombre": "validacion-3-1-lugar del backend", "categoria": "bloque", "lat": 6.2, "lng": -75.5})
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5"]
    assert _estados(datos) == {"C1a": "pasa", "C1b": "pasa", "C2a": "pasa", "C2b": "pasa"}
    assert "18 lugares en Selección de destino = GET /v1/places" in _detalle(datos, "C1b")
    assert [x["id"] for x in datos["manuales"]] == ["C2c"]
    # El resto se borró al empezar (solo el de nombre exacto); el creado, al terminar; lo demás sigue.
    assert m.api.borrados == [resto["id"], m.api.creados[0]["id"]]
    assert "validacion-3-1-lugar del backend" in m.api.nombres()
    assert validate31.LUGAR_PRUEBA not in m.api.nombres()
    creado = m.api.creados[0]
    assert (creado["nombre"], creado["categoria"]) == (validate31.LUGAR_PRUEBA, "bloque")
    # Teléfono: instalado, permisos de Inicio, un paso guiado, la lista desplazada y la app cerrada al final.
    assert ("installDebug",) in m.gradle_ordenes
    concedidos = [o[4] for o in m.telefono.ordenes if o[:3] == ("shell", "pm", "grant")]
    assert concedidos == validate31.PERMISOS_INICIO + [validate31.PERMISO_ACTIVIDAD]
    assert len(m.pasos_guiados) == 1 and "«dos»" in m.pasos_guiados[0]
    assert any(o[:3] == ("shell", "input", "swipe") for o in m.telefono.ordenes)
    assert m.telefono.pantalla is None
    assert not any(o[:3] == ("shell", "pm", "clear") for o in m.telefono.ordenes)
    # Una sola ejecución de Gradle para las tres clases.
    pruebas = [o for o in m.gradle_ordenes if "testDebugUnitTest" in o]
    assert pruebas == [
        (
            "testDebugUnitTest",
            "--tests",
            "*.RemoteLugaresRepositoryTest",
            "--tests",
            "*.ComandoParserTest",
            "--tests",
            "*.ObservadorPrimerPlanoTest",
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
    assert _estados(datos) == {"C1a": "pasa", "C1b": "omitida", "C2a": "pasa", "C2b": "pasa"}
    assert m.telefono.ordenes == []
    assert m.api.creados == [] and m.api.borrados == []
    assert m.pasos_guiados == []
    assert [x["id"] for x in datos["manuales"]] == ["C2c"]


def test_lista_vieja_sin_el_lugar_nuevo_falla_c1b_y_borra_el_lugar(tmp_path, monkeypatch):
    m = Mundo(tmp_path, sin_lugar_nuevo=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "faltan 1 («validacion-3-1-lugar»)" in _detalle(datos, "C1b")
    assert validate31.LUGAR_PRUEBA not in m.api.nombres()


def test_error_de_carga_en_destino_falla_c1b(tmp_path, monkeypatch):
    m = Mundo(tmp_path, error_carga=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert "No se pudo cargar la lista de lugares" in _detalle(datos, "C1b")
    assert _estados(datos)["C1a"] == "pasa"
    assert m.api.creados and validate31.LUGAR_PRUEBA not in m.api.nombres()


def test_si_no_se_abre_destino_falla_con_lo_que_se_ve(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.abre_destino = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 1
    assert "no se vio Selección de destino" in _detalle(datos, "C1b")
    assert "Acceso administrador" in _detalle(datos, "C1b")


def test_sin_terminar_el_paso_guiado_es_3_y_limpia(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.enter_eof = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 3
    assert _estados(datos)["C1b"] == "error"
    assert m.api.creados and validate31.LUGAR_PRUEBA not in m.api.nombres()
    assert m.telefono.pantalla is None


def test_backend_sin_lugares_crea_el_de_prueba_en_el_campus(tmp_path, monkeypatch):
    m = Mundo(tmp_path, nombres=[])
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 0, datos
    assert "(0 lugares)" in _detalle(datos, "P5")
    assert (m.api.creados[0]["lat"], m.api.creados[0]["lng"]) == validate31.POSICION_CAMPUS
    assert "1 lugares en Selección de destino" in _detalle(datos, "C1b")


def test_lista_larga_carga_lenta(tmp_path, monkeypatch):
    m = Mundo(tmp_path, nombres=[f"Sitio {i:03d}" for i in range(60)], carga_s=6)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1b"])
    assert codigo == 0, datos
    assert "61 lugares" in _detalle(datos, "C1b")


def test_be31_sin_hecho_es_bloqueo(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.be31_hecho = False
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert "BE-3.1" in _detalle(datos, "P5")
    assert datos["comprobaciones"] == []
    assert m.api.creados == []


def test_credenciales_malas_son_3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.api.login_estado = 401
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert "credenciales del admin" in _detalle(datos, "P4")
    assert next(p for p in datos["precondiciones"] if p["id"] == "P5")["estado"] == "no evaluada"


def test_dev_sin_c1b_no_usa_telefono_ni_backend(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2"])
    assert codigo == 0, datos
    assert {p["id"]: p["estado"] for p in datos["precondiciones"]} == {
        "P1": "pasa",
        "P2": "no evaluada",
        "P3": "no evaluada",
        "P4": "no evaluada",
        "P5": "no evaluada",
    }
    assert _estados(datos) == {"C1a": "omitida", "C1b": "omitida", "C2a": "pasa", "C2b": "pasa"}
    assert m.telefono.ordenes == []


def test_pocos_casos_fallan_c2a(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos["ObservadorPrimerPlanoTest"] = 2
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local", ["--solo", "C2a"])
    assert codigo == 1
    assert "mínimo 4" in _detalle(datos, "C2a")


# --- ayudas nuevas de comun (FE-3.1) -------------------------------------------------------------------------------


def test_esperar_enter_lee_una_linea_y_sin_terminal_es_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    comun.esperar_enter("Haz algo")
    assert "PASO GUIADO — Haz algo" in capsys.readouterr().err
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with pytest.raises(comun.ErrorConfiguracion, match="EOF"):
        comun.esperar_enter("Haz algo")


def test_http_delete_con_token(monkeypatch):
    vistas = []

    class Respuesta:
        status = 204
        headers: dict = {}

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(peticion, timeout=0):
        vistas.append((peticion.get_method(), peticion.get_header("Authorization")))
        return Respuesta()

    monkeypatch.setattr(comun.urllib.request, "urlopen", urlopen)
    r = comun.http_delete("https://a.com/v1/admin/places/x", token="t-secreto")
    assert r.estado == 204
    assert vistas == [("DELETE", "Bearer t-secreto")]
