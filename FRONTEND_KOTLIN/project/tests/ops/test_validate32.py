"""Pruebas de validate32.py con un teléfono, Gradle, la API y `embedding` simulados.

El teléfono falso tiene la hora (avanza con el reloj falso), `files/logs/app.log` (con el formato de AppLog), las
carpetas de `files/camera/photos/`, `dumpsys package` (`lastUpdateTime` = cuándo corrió `installDebug`) y Inicio en
uiautomator. Los pasos guiados (`comun.esperar_enter`) se sustituyen por «la persona hace las vueltas»: escriben en
app.log las líneas que deja la app de verdad (ARCHITECTURE §5.2 y §5.10). `embedding` es un doble de
`comun.EmbeddingDev` que cambia lo que responde `/v1/health/ready`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate32

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1")
TOKEN = "eyJ.token.secreto"
PLAN_APP = (
    "| FE-3.1 | Lugares | FE-1.1 | FE-1.1, BE-3.1 | x |\n| FE-3.1 | 3 | Hecho | [3-1](x) | `b553390` | 0.8.1 | | |\n"
)
PLAN_BACKEND = "| BE-3.2 | Localización | BE-2.4 | x | x |\n| BE-3.2 | 3 | Hecho | [3-2](x) | `abc` | 0.13.0 | |\n"
INICIO_TELEFONO = datetime(2026, 10, 26, 10, 0, 0)
CLASES = {
    "RemoteLocalizacionRepositoryTest": 11,
    "DescribirUbicacionTest": 11,
    "SesionDeNavegacionTest": 5,
    "ConversionRumboTest": 7,
    "FotosEscaneoTest": 6,
    "ErrorEscaneoTest": 7,
}


class Reloj:
    def __init__(self) -> None:
        self.t = 0.0

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
    def __init__(self) -> None:
        self.embedding = "no_disponible"
        self.login_estado = 200
        self.sonda = (400, "FOTOS_INVALIDAS")
        self.procesadas = 120
        self.sondas: list[list] = []
        self.lugares = ["Biblioteca Central", "Bloque 19"]

    def http_get(self, url, *, timeout=15.0, token=None):
        u = urlparse(url)
        ruta = u.path.removeprefix("/v1")
        if ruta == "/health":
            return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok"}), 30)
        if ruta == "/health/ready":
            return comun.RespuestaHttp(
                200, {}, json.dumps({"estado": "ok", "db": "ok", "embedding": self.embedding}), 30
            )
        if ruta == "/places":
            items = [{"id": f"u{i}", "nombre": n} for i, n in enumerate(self.lugares)]
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": len(items)}), 30)
        if ruta == "/admin/videos":
            assert token == TOKEN
            assert parse_qs(u.query)["por_pagina"] == ["100"]
            items = [
                {"nombre": "validacion-21-casa", "conteo": {"procesada": 56}},  # de prueba: no cuenta
                {"nombre": "Campus norte", "conteo": {"procesada": self.procesadas}},
            ]
            return comun.RespuestaHttp(200, {}, json.dumps({"items": items, "total": 2}), 30)
        raise AssertionError(url)

    def http_post_json(self, url, cuerpo, *, timeout=15.0, token=None):
        assert urlparse(url).path == "/v1/auth/login"
        if self.login_estado != 200:
            return comun.RespuestaHttp(401, {}, json.dumps({"error": {"codigo": "CREDENCIALES_INVALIDAS"}}), 30)
        assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
        usuario = {"id": "u1", "nombre": "Admin", "correo": ADMIN[0], "rol": "admin"}
        return comun.RespuestaHttp(200, {}, json.dumps({"token": TOKEN, "usuario": usuario}), 30)

    def http_post_multipart(self, url, partes, *, timeout=15.0, token=None):
        assert urlparse(url).path == "/v1/localize"
        assert token is None  # ruta pública
        self.sondas.append(partes)
        estado, codigo = self.sonda
        return comun.RespuestaHttp(estado, {}, json.dumps({"error": {"codigo": codigo, "detalle": {"indice": 0}}}), 30)


class Telefono:
    def __init__(self, reloj: Reloj) -> None:
        self.reloj = reloj
        self.log: list[str] = []
        self.instalado_en: str | None = None
        self.carpetas: dict[str, list[str]] = {}
        self.vivo = True
        self.ordenes: list[tuple[str, ...]] = []

    def ahora(self) -> datetime:
        return INICIO_TELEFONO + timedelta(seconds=self.reloj.t)

    def hora(self) -> str:
        return self.ahora().strftime("%Y-%m-%d %H:%M:%S")

    def escribir(self, nivel: str, tag: str, sesion: str, texto: str) -> None:
        self.reloj.t += 1
        self.log.append(f"{self.hora()}.123 {nivel}/{tag} [main] [{sesion}] {texto}")

    def adb(self, *args: str, timeout: int = 0) -> comun.Resultado:
        self.reloj.t += 0.2
        self.ordenes.append(args)
        ok = comun.Resultado(0, "", "")
        if args[0] == "exec-out" and args[1].startswith("uiautomator dump"):
            nodos = _nodo(desc="Acceso administrador", clase="android.view.View", limites=(100, 2000, 980, 2100))
            return comun.Resultado(0, f"<?xml version='1.0'?><hierarchy>{nodos}</hierarchy>", "")
        if args[:4] == ("exec-out", "run-as", comun.PAQUETE, "cat"):
            if args[4] == comun.LOG_APP:
                return comun.Resultado(0, "\n".join(self.log) + "\n", "")
            return comun.Resultado(1, "", "No such file")
        if args[:5] == ("exec-out", "run-as", comun.PAQUETE, "ls", "-1"):
            ruta = args[5]
            if ruta == validate32.DIR_FOTOS:
                return (
                    comun.Resultado(0, "".join(f"{c}\n" for c in self.carpetas), "")
                    if self.carpetas
                    else (comun.Resultado(1, "", "No such file or directory"))
                )
            nombre = ruta.rsplit("/", 1)[-1]
            if nombre in self.carpetas:
                return comun.Resultado(0, "".join(f"{a}\n" for a in self.carpetas[nombre]), "")
            return comun.Resultado(1, "", "No such file or directory")
        if args[0] != "shell":
            return ok
        orden = args[1:]
        if orden[:2] == ("getprop", "ro.product.model"):
            return comun.Resultado(0, "23028RA60L\n", "")
        if orden[:2] == ("getprop", "ro.build.version.release"):
            return comun.Resultado(0, "14\n", "")
        if orden[:2] == ("getprop", "ro.build.version.sdk"):
            return comun.Resultado(0, "34\n", "")
        if orden[0] == "date":
            return comun.Resultado(0, self.ahora().strftime("%Y-%m-%d_%H:%M:%S") + "\n", "")
        if orden[:2] == ("dumpsys", "package"):
            if self.instalado_en is None:
                return comun.Resultado(0, "Unable to find package\n", "")
            return comun.Resultado(
                0, f"    firstInstallTime=2026-10-01 09:00:00\n    lastUpdateTime={self.instalado_en}\n", ""
            )
        if orden[0] == "pidof":
            return comun.Resultado(0, "12345\n" if self.vivo else "", "")
        if orden[:2] == ("am", "start"):
            return comun.Resultado(0, "Status: ok\n", "")
        return ok


class EmbeddingFalso:
    """Doble de comun.EmbeddingDev: cambia lo que responde /v1/health/ready."""

    def __init__(self, mundo: Mundo) -> None:
        self.mundo = mundo

    def __call__(self, cluster, servicio_embedding="embedding", servicio_worker="worker"):
        self.mundo.emb_creados.append((cluster, servicio_embedding, servicio_worker))
        return self

    def comprobar_inf21(self):
        return "ok"

    def latido(self, cuando=None):
        self.mundo.emb_ordenes.append("latido")

    def encender(self, listo):
        self.mundo.emb_ordenes.append("encender")
        self.mundo.api.embedding = "ok"
        assert listo()
        return 180.0

    def apagar(self):
        self.mundo.emb_ordenes.append("apagar")
        self.mundo.api.embedding = "no_disponible"


class Mundo:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.reloj = Reloj()
        self.api = Api()
        self.telefono = Telefono(self.reloj)
        self.casos = dict(CLASES)
        self.conservar = "false"
        self.gradle_ordenes: list[tuple[str, ...]] = []
        self.pasos: list[str] = []
        self.emb_creados: list[tuple] = []
        self.emb_ordenes: list[str] = []
        self.puntos_c1 = 10
        self.c1_deja_fotos = False
        self.c4_estado = "503"
        self.c4_crash = False
        self.hora_bogota = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)  # 10:00 en Bogotá
        self.fe31_hecho = True
        self.be32_hecho = True

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN_APP if self.fe31_hecho else PLAN_APP.replace("Hecho", "En curso"), "utf-8")
        plan_be = self.tmp / "PLAN_BE.md"
        plan_be.write_text(PLAN_BACKEND if self.be32_hecho else PLAN_BACKEND.replace("Hecho", "En curso"), "utf-8")
        vm = self.tmp / "EscaneoViewModel.kt"
        vm.write_text(f"package x\n\ninternal const val CONSERVAR_FOTOS = {self.conservar}\n", "utf-8")
        monkeypatch.setattr(validate32, "ESCANEO_VM", vm)
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
        monkeypatch.setattr(comun, "http_post_multipart", self.api.http_post_multipart)
        monkeypatch.setattr(comun, "esperar_enter", self.esperar_enter)
        monkeypatch.setattr(comun, "reloj", self.reloj.reloj)
        monkeypatch.setattr(comun, "dormir", self.reloj.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setattr(comun, "cuenta_aws", lambda: f"arn:aws:iam::{comun.CUENTA}:user/validador")
        monkeypatch.setattr(
            comun,
            "terraform_outputs",
            lambda directorio=None: {"ecs_cluster": "cl", "ecs_servicios": {"embedding": "emb", "worker": "wrk"}},
        )
        monkeypatch.setattr(comun, "EmbeddingDev", EmbeddingFalso(self))
        monkeypatch.setattr(comun, "hora_bogota", lambda ahora=None: self.hora_bogota.astimezone(comun.ZONA_BOGOTA))
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def gradle(self, *args, timeout=0):
        self.gradle_ordenes.append(args)
        if "--version" in args:
            return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11\n", "")
        if "installDebug" in args:
            self.telefono.instalado_en = self.telefono.hora()
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        if "testDebugUnitTest" in args:
            for clase, casos in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{casos}" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
                    )
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        return comun.Resultado(0, "", "")

    # --- la persona en el teléfono (pasos guiados) ---------------------------------------------------------------

    def _vuelta(self, n: int) -> tuple[str, str]:
        sesion = f"scan-{12345 + n}"
        carpeta = (self.telefono.ahora() + timedelta(seconds=1)).strftime("%Y-%m-%d_%H-%M-%S")
        self.telefono.escribir("I", "EscaneoVM", sesion, "Escaneo iniciado (declinación -7.6°)")
        return sesion, carpeta

    def esperar_enter(self, instruccion: str) -> None:
        self.pasos.append(instruccion)
        t = self.telefono
        if "puntos conocidos" in instruccion:  # C1
            for i in range(self.puntos_c1):
                sesion, carpeta = self._vuelta(i)
                t.escribir("I", "Api", sesion, "POST /v1/localize -> 200 (812 ms) rid=r")
                nivel = "baja" if i == 3 else "alta"
                t.escribir(
                    "I",
                    "EscaneoVM",
                    sesion,
                    f"Resultado: ok nivel={nivel} confianza=0.78 cercano=sí referencias=2 correccion=-6.0 "
                    "fotos=5/4 (812 ms)",
                )
                if self.c1_deja_fotos and i == 0:
                    t.carpetas[carpeta] = ["envio_1.jpg", "escaneo_1.jpg"]
                else:
                    t.escribir("I", "EscaneoVM", sesion, f"Fotos del escaneo borradas (carpeta {carpeta}, 10 archivos)")
        elif "embedding apagado" in instruccion:  # C4
            sesion, carpeta = self._vuelta(99)
            t.escribir("I", "Api", sesion, f"POST /v1/localize -> {self.c4_estado} (95 ms) rid=r")
            if self.c4_estado == "503":
                t.escribir(
                    "W",
                    "EscaneoVM",
                    sesion,
                    "Localización falló (SERVICIO_NO_DISPONIBLE): HTTP 503 EmbeddingNoDisponible",
                )
                t.escribir("I", "EscaneoVM", sesion, f"Fotos del escaneo borradas (carpeta {carpeta}, 10 archivos)")
                t.escribir("W", "EscaneoVM", sesion, "Escaneo en ERROR: SERVICIO_NO_DISPONIBLE")
            else:
                t.escribir("I", "EscaneoVM", sesion, "Resultado: sin_coincidencias fotos=5 (900 ms)")
            if self.c4_crash:
                t.escribir("E", "CRASH", sesion, "java.lang.IllegalStateException")
                t.vivo = False
        else:
            raise AssertionError(instruccion)


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    return m


def _correr(m: Mundo, monkeypatch, entorno: str, *extra: str):
    m.instalar(monkeypatch)  # vuelve a escribir los PLAN y el .kt con las opciones del caso
    informe = m.tmp / "informe.json"
    codigo = validate32.main(["--entorno", entorno, "--informe", str(informe), *extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos, clave="comprobaciones"):
    return {c["id"]: c["estado"] for c in datos[clave]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


# --- piezas puras ----------------------------------------------------------------------------------------------


def test_lineas_log_y_resultados():
    texto = "\n".join(
        [
            "2026-10-26 10:00:01.000 I/EscaneoVM [main] [scan-1] Escaneo iniciado",
            "2026-10-26 10:00:20.000 I/EscaneoVM [main] [scan-1] Resultado: ok nivel=alta confianza=0.78 cercano=sí "
            "referencias=2 fotos=5/4 (812 ms)",
            "java.lang.RuntimeException: traza de una línea anterior",
            "2026-10-26 10:01:20.000 I/EscaneoVM [main] [scan-2] Resultado: sin_coincidencias fotos=5 (700 ms)",
            "2026-10-26 10:01:21.000 W/EscaneoVM [main] [scan-2] Resultado: ok (un W no cuenta)",
            "2026-10-26 09:59:59.000 I/EscaneoVM [main] [scan-0] Resultado: ok nivel=media",
        ]
    )
    lineas = validate32.lineas_log(texto, desde="2026-10-26 10:00:00")
    assert [ln.sesion for ln in lineas] == ["scan-1", "scan-1", "scan-2", "scan-2"]
    resultados = validate32.resultados_escaneo(lineas)
    assert [r["resultado"] for r in resultados] == ["ok", "sin_coincidencias"]
    assert resultados[0]["nivel"] == "alta" and resultados[0]["cercano"] == "sí" and resultados[0]["referencias"] == "2"
    assert validate32.resumen_resultados(resultados) == "2 resultados (alta 1, sin_coincidencias 1)"
    assert validate32.resumen_resultados([]) == "0 resultados"


@pytest.mark.parametrize(
    ("texto", "pasa"),
    [
        ("internal const val CONSERVAR_FOTOS = false\n", True),
        ("private const val CONSERVAR_FOTOS = false // privacidad\n", True),
        ("const val CONSERVAR_FOTOS=false\n", True),
        ("internal const val CONSERVAR_FOTOS = true\n", False),
        ("// const val CONSERVAR_FOTOS = false\nval otra = 1\n", False),
        ("internal const val CONSERVAR_FOTOS = false\nconst val CONSERVAR_FOTOS = true\n", False),
    ],
)
def test_comprobar_conservar(texto, pasa):
    if pasa:
        assert validate32.comprobar_conservar(texto) == "CONSERVAR_FOTOS = false"
    else:
        with pytest.raises(comun.Falla):
            validate32.comprobar_conservar(texto)


def test_comprobar_conservar_en_el_codigo_real():
    texto = validate32.ESCANEO_VM.read_text(encoding="utf-8")
    assert validate32.comprobar_conservar(texto) == "CONSERVAR_FOTOS = false"


def test_hora_de_carpeta_y_suma_procesadas():
    assert validate32.hora_de_carpeta("2026-10-26_14-03-12") == "2026-10-26 14:03:12"
    assert validate32.hora_de_carpeta("rec_0001") is None
    items = [
        {"nombre": "Campus", "conteo": {"procesada": 3}},
        {"nombre": "validacion_21_casa", "conteo": {"procesada": 56}},
        {"nombre": "Otro", "conteo": None},
        "no es un objeto",
    ]
    assert validate32.suma_procesadas(items) == 3


def test_cuerpo_multipart():
    partes = [
        comun.ParteMultipart("metadatos", b'{"rumbos": []}', "application/json"),
        comun.ParteMultipart("fotos", b"\xff\xd8\xff", "image/jpeg", "f.jpg"),
    ]
    cuerpo = comun.cuerpo_multipart(partes, "LIM")
    assert cuerpo == (
        b'--LIM\r\nContent-Disposition: form-data; name="metadatos"\r\nContent-Type: application/json\r\n\r\n'
        b'{"rumbos": []}\r\n'
        b'--LIM\r\nContent-Disposition: form-data; name="fotos"; filename="f.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        b"\xff\xd8\xff\r\n--LIM--\r\n"
    )


def test_http_post_multipart_envia_el_separador_y_devuelve_el_400(monkeypatch):
    vistas = []

    class Error400(comun.urllib.error.HTTPError):
        def __init__(self):
            super().__init__("https://a.com/v1/localize", 400, "Bad Request", {"X-Request-Id": "rid"}, None)

        def read(self):
            return b'{"error": {"codigo": "FOTOS_INVALIDAS"}}'

    def urlopen(peticion, timeout=0):
        vistas.append((peticion.get_method(), peticion.get_header("Content-type"), peticion.data))
        raise Error400()

    monkeypatch.setattr(comun.urllib.request, "urlopen", urlopen)
    r = comun.http_post_multipart(
        "https://a.com/v1/localize", [comun.ParteMultipart("metadatos", b"{}", "application/json")]
    )
    assert r.estado == 400 and comun.codigo_error(r) == "FOTOS_INVALIDAS"
    metodo, tipo, datos = vistas[0]
    assert metodo == "POST"
    limite = tipo.removeprefix("multipart/form-data; boundary=")
    assert limite.startswith("validacion-") and datos.startswith(f"--{limite}\r\n".encode())


# --- local ------------------------------------------------------------------------------------------------------


def test_local_pasa_con_jvm_y_estatico_sin_telefono(mundo, monkeypatch):
    codigo, datos = _correr(mundo, monkeypatch, "local")
    assert codigo == 0
    assert _estados(datos) == {
        "C1a": "pasa",
        "C2": "pasa",
        "C3a": "pasa",
        "C4a": "pasa",
        "C1b": "omitida",
        "C4b": "omitida",
        "C3b": "omitida",
    }
    assert [x["id"] for x in datos["precondiciones"]] == ["P1"]
    assert [x["id"] for x in datos["manuales"]] == ["C1c", "C4c"]
    assert "ConversionRumboTest 7/7" in _detalle(datos, "C2")
    assert _detalle(datos, "C3a").startswith("CONSERVAR_FOTOS = false; FotosEscaneoTest 6/6")
    # Una sola ejecución de Gradle con las seis clases; nunca instala ni toca el teléfono.
    pruebas = [o for o in mundo.gradle_ordenes if "testDebugUnitTest" in o]
    assert len(pruebas) == 1 and sum(1 for a in pruebas[0] if a.startswith("*.")) == 6
    assert not any("installDebug" in o for o in mundo.gradle_ordenes)
    assert mundo.telefono.ordenes == []


def test_local_conservar_true_falla_c3a(mundo, monkeypatch):
    mundo.conservar = "true"
    codigo, datos = _correr(mundo, monkeypatch, "local")
    assert codigo == 1
    assert _estados(datos)["C3a"] == "falla"
    assert "CONSERVAR_FOTOS = true" in _detalle(datos, "C3a")


def test_local_pocos_casos_falla(mundo, monkeypatch):
    mundo.casos["ConversionRumboTest"] = 3
    codigo, datos = _correr(mundo, monkeypatch, "local")
    assert codigo == 1
    assert "mínimo 5" in _detalle(datos, "C2")


# --- dev --------------------------------------------------------------------------------------------------------


def test_dev_feliz_enciende_c1_apaga_y_hace_c4(mundo, monkeypatch, capsys):
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 0, datos
    assert _estados(datos, "precondiciones") == {f"P{i}": "pasa" for i in range(1, 8)}
    assert set(_estados(datos).values()) == {"pasa"}
    assert "encendido por el validador" in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P7")
    assert "10 resultados (alta 9, baja 1)" in _detalle(datos, "C1b")
    assert "SERVICIO_NO_DISPONIBLE" in _detalle(datos, "C4b") and validate32.MENSAJE_C4 in _detalle(datos, "C4b")
    assert "11 sesiones [scan-…]" in _detalle(datos, "C3b") and "ninguna con .jpg" in _detalle(datos, "C3b")
    assert "dataset con 120 fotos procesadas" in _detalle(datos, "P6")
    # Encendió para C1, lo apagó antes de C4 y la limpieza lo vuelve a apagar (inofensivo).
    assert mundo.emb_ordenes == ["encender", "apagar", "apagar"]
    assert mundo.emb_creados == [("cl", "emb", "wrk")]
    # La sonda solo lleva metadatos (sin fotos).
    assert [p.nombre for p in mundo.api.sondas[0]] == ["metadatos"]
    assert len(mundo.pasos) == 2
    salida = capsys.readouterr()
    for secreto in (ADMIN[1], TOKEN):
        assert secreto not in salida.out and secreto not in salida.err
        assert secreto not in json.dumps(datos)
    assert "Biblioteca Central, Bloque 19" in salida.err  # imprime los lugares para C1


def test_dev_embedding_ya_encendido_publica_latido_y_c4_no_se_puede(mundo, monkeypatch):
    mundo.api.embedding = "ok"
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 3
    assert mundo.emb_ordenes == ["latido"]
    assert _estados(datos)["C1b"] == "pasa"
    assert _estados(datos)["C4b"] == "error"
    assert "no lo encendió este validador" in _detalle(datos, "C4b")


def test_dev_solo_c4_de_noche_sin_aws(mundo, monkeypatch):
    mundo.hora_bogota = datetime(2026, 10, 27, 3, 30, tzinfo=UTC)  # 22:30 en Bogotá
    codigo, datos = _correr(mundo, monkeypatch, "dev", "--solo", "C4")
    assert codigo == 0, datos
    assert _estados(datos, "precondiciones")["P7"] == "no evaluada"
    assert _estados(datos)["C4b"] == "pasa" and _estados(datos)["C1b"] == "omitida"
    assert mundo.emb_ordenes == [] and mundo.emb_creados == []
    assert len(mundo.pasos) == 1 and "embedding apagado" in mundo.pasos[0]


def test_dev_hora_limite_para_encender(mundo, monkeypatch):
    mundo.hora_bogota = datetime(2026, 10, 27, 1, 50, tzinfo=UTC)  # 20:50 en Bogotá
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 3
    assert "20:45" in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P7")
    assert mundo.emb_ordenes == []


def test_dev_be32_sin_hecho_bloquea(mundo, monkeypatch):
    mundo.be32_hecho = False
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 2
    assert _estados(datos, "precondiciones")["P6"] == "falla"
    assert _estados(datos, "precondiciones")["P7"] == "no evaluada"
    assert mundo.emb_ordenes == [] and mundo.pasos == []


def test_dev_fe31_sin_hecho_bloquea(mundo, monkeypatch):
    mundo.fe31_hecho = False
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 2
    assert "FE-3.1" in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P3")


@pytest.mark.parametrize(("sonda", "texto"), [((422, "VALIDACION"), "422 VALIDACION"), ((404, "NO_ENCONTRADO"), "404")])
def test_dev_sonda_de_localize_distinta_bloquea(mundo, monkeypatch, sonda, texto):
    mundo.api.sonda = sonda
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 2
    assert texto in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P6")


def test_dev_dataset_vacio_bloquea(mundo, monkeypatch):
    mundo.api.procesadas = 0
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 2
    assert "ninguna foto procesada" in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P6")


def test_dev_credenciales_malas_son_3(mundo, monkeypatch):
    mundo.api.login_estado = 401
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 3
    assert _estados(datos, "precondiciones")["P5"] == "falla"


def test_dev_menos_de_10_puntos_falla_c1b_y_apaga(mundo, monkeypatch):
    mundo.puntos_c1 = 7
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 1
    assert "solo 7 resultados" in _detalle(datos, "C1b")
    assert mundo.emb_ordenes[:2] == ["encender", "apagar"]


def test_dev_fotos_que_quedan_fallan_c3b(mundo, monkeypatch):
    mundo.c1_deja_fotos = True
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 1
    assert "quedan fotos de escaneo" in _detalle(datos, "C3b") and "2 .jpg" in _detalle(datos, "C3b")


def test_dev_c4_con_200_o_cierre_falla(mundo, monkeypatch):
    mundo.c4_estado = "200"
    codigo, datos = _correr(mundo, monkeypatch, "dev", "--solo", "C4")
    assert codigo == 1
    assert "embedding no estaba apagado" in _detalle(datos, "C4b")


def test_dev_c4_la_app_se_cierra(mundo, monkeypatch):
    mundo.c4_crash = True
    codigo, datos = _correr(mundo, monkeypatch, "dev", "--solo", "C4")
    assert codigo == 1
    assert "se cerró" in _detalle(datos, "C4b")


def test_dev_solo_c3_sin_escaneos_falla_y_no_instala(mundo, monkeypatch):
    mundo.telefono.instalado_en = "2026-10-26 09:00:00"
    codigo, datos = _correr(mundo, monkeypatch, "dev", "--solo", "C3")
    assert codigo == 1
    assert "ninguna sesión [scan-…]" in _detalle(datos, "C3b")
    assert not any("installDebug" in o for o in mundo.gradle_ordenes)
    assert [p for p in _estados(datos, "precondiciones") if _estados(datos, "precondiciones")[p] == "pasa"] == [
        "P1",
        "P2",
    ]


def test_dev_paso_guiado_sin_terminal_es_3(mundo, monkeypatch):
    def sin_terminal(instruccion):
        raise comun.ErrorConfiguracion("el paso guiado necesita una terminal: la entrada estándar está cerrada (EOF)")

    monkeypatch.setattr(comun, "esperar_enter", sin_terminal)
    informe = mundo.tmp / "informe.json"
    codigo = validate32.main(["--entorno", "dev", "--informe", str(informe), "--solo", "C1"])
    datos = json.loads(informe.read_text(encoding="utf-8"))
    assert codigo == 3
    assert _estados(datos)["C1b"] == "error"
    assert "apagar" in mundo.emb_ordenes  # la limpieza apaga lo que encendió


def test_dev_si_falla_la_jvm_no_hace_los_pasos_guiados(mundo, monkeypatch):
    mundo.casos["FotosEscaneoTest"] = 1
    codigo, datos = _correr(mundo, monkeypatch, "dev")
    assert codigo == 1
    assert _estados(datos)["C1b"] == "omitida" and "falló C3a" in _detalle(datos, "C1b")
    assert mundo.pasos == []
