"""Pruebas de validate12.py con un teléfono, Gradle, HTTP y AWS simulados.

El teléfono falso responde a las órdenes de adb que usa `comun` (uiautomator dump, input tap/text/keyevent/swipe,
pm grant, am, dumpsys, wm size) con pantallas de Inicio, Login y Panel parecidas a las reales, así se ejercitan de
verdad el volcado, el escape de `input text` y la búsqueda de nodos.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

import comun
import pytest
import validate12

URL = "https://api.example.com/v1"
ADMIN = ("admin@campus.edu.co", "Clave Segura$1'x")  # con espacio y caracteres del sh: se escapan
NOMBRE_ADMIN = "Alejandro Gómez"
PLAN = "| FE-1.1 | 1 | Hecho | [1-1](x) | `c5917bd` | 0.4.0 | | |\n| FE-1.2 | 1 | En curso | | | | | |\n"


class Reloj:
    def __init__(self) -> None:
        self.t = 1000.0

    def reloj(self) -> float:
        return self.t

    def dormir(self, s: float) -> None:
        self.t += s


def _nodo(texto="", desc="", clase="android.widget.TextView", limites=(0, 0, 10, 10), enabled=True, password=False):
    x1, y1, x2, y2 = limites
    return (
        f"<node text={quoteattr(texto)} content-desc={quoteattr(desc)} class={quoteattr(clase)} "
        f'bounds="[{x1},{y1}][{x2},{y2}]" enabled="{str(enabled).lower()}" password="{str(password).lower()}"/>'
    )


def _desescapar(texto: str) -> str:
    """Lo que hace el sh del teléfono (quita las `\\`) y después `input text` (`%s` → espacio)."""
    return re.sub(r"\\(.)", r"\1", texto).replace("%s", " ")


class Telefono:
    """Estado de la app en un teléfono falso."""

    def __init__(
        self,
        reloj: Reloj,
        *,
        miui_bloqueado=False,
        boton_tapado=False,
        retraso_login_s=1.0,
        desplazar_para_cerrar=1,
        user_abre_panel=False,
    ) -> None:
        self.reloj = reloj
        self.miui_bloqueado = miui_bloqueado
        self.boton_tapado = boton_tapado
        self.retraso_login_s = retraso_login_s
        self.desplazar_para_cerrar = desplazar_para_cerrar
        self.user_abre_panel = user_abre_panel
        self.usuarios: dict[str, str] = {}  # correo user → contraseña (los crea la tarea falsa)
        self.ordenes: list[tuple[str, ...]] = []
        self.textos_adb: list[str] = []
        self.pantalla: str | None = None
        self._reiniciar()

    def _reiniciar(self) -> None:
        self.campos = ["", ""]
        self.foco: int | None = None
        self.teclado = False
        self.desplazamientos = 0
        self.banner: str | None = None
        self.pendiente: tuple[float, str] | None = None

    # --- pantallas

    def _nodos(self) -> list[str]:
        if self.pendiente and self.reloj.t >= self.pendiente[0]:
            destino = self.pendiente[1]
            self.pendiente = None
            if destino == "panel":
                self.pantalla = "panel"
            else:
                self.banner = destino
        if self.pantalla == "inicio":
            return [
                _nodo(desc="Acceso administrador", clase="android.view.View", limites=(100, 2000, 980, 2100)),
                _nodo(texto="Acceso administrador", limites=(300, 2020, 800, 2080)),
                _nodo(texto="Conectado", limites=(100, 2200, 400, 2250)),
            ]
        if self.pantalla == "login":
            puede = bool(self.campos[0]) and bool(self.campos[1])
            nodos = [
                _nodo(texto="Campus Navi", limites=(200, 300, 880, 400)),
                _nodo(texto=self.campos[0], clase="android.widget.EditText", limites=(60, 900, 1020, 1060)),
                _nodo(
                    texto="•" * len(self.campos[1]),
                    clase="android.widget.EditText",
                    limites=(60, 1100, 1020, 1260),
                    password=True,
                ),
            ]
            if not (self.boton_tapado and self.teclado):
                nodos.append(_nodo(clase="android.widget.Button", limites=(60, 1330, 1020, 1500), enabled=puede))
                nodos.append(_nodo(texto="Iniciar sesión", limites=(300, 1380, 800, 1450)))
            if self.banner:
                nodos.append(_nodo(texto=self.banner, limites=(60, 1560, 1020, 1620)))
            return nodos
        if self.pantalla == "panel":
            nodos = [_nodo(texto=validate12.saludo_esperado(NOMBRE_ADMIN), limites=(100, 200, 900, 280))]
            if self.desplazamientos >= self.desplazar_para_cerrar:
                nodos.append(_nodo(texto="Cerrar sesión", limites=(60, 1900, 500, 1980)))
            return nodos
        return [_nodo(texto="Escritorio", limites=(0, 0, 1080, 2400))]

    def _xml(self) -> str:
        cuerpo = "".join(self._nodos())
        return f"<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">{cuerpo}</hierarchy>"

    def _tocar(self, x: int, y: int) -> None:
        if self.pantalla == "inicio" and 100 <= x <= 980 and 2000 <= y <= 2100:
            self.pantalla = "login"
            return
        if self.pantalla != "login":
            return
        if 900 <= y <= 1060:
            self.foco, self.teclado = 0, True
        elif 1100 <= y <= 1260:
            self.foco, self.teclado = 1, True
        elif 1330 <= y <= 1500 and not (self.boton_tapado and self.teclado):
            if not (self.campos[0] and self.campos[1]):
                return
            self.teclado, self.foco, self.banner = False, None, None
            correo, password = self.campos
            if (correo, password) == ADMIN:
                destino = "panel"
            elif self.usuarios.get(correo) == password:
                destino = "panel" if self.user_abre_panel else "Sin permisos"
            else:
                destino = "Credenciales inválidas"
            self.pendiente = (self.reloj.t + self.retraso_login_s, destino)

    # --- adb

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
        if orden[:2] == ("pm", "grant"):
            if self.miui_bloqueado:
                return comun.Resultado(
                    255,
                    "",
                    "Exception occurred while executing 'grant':\njava.lang.SecurityException: grantRuntimePermission: "
                    "Neither user 2000 nor current process has android.permission.GRANT_RUNTIME_PERMISSIONS.",
                )
            return ok
        if orden[0] == "input" and self.miui_bloqueado:
            return comun.Resultado(
                255, "", "java.lang.SecurityException: Injecting input events requires the caller to have INJECT_EVENTS"
            )
        if orden[:2] == ("am", "force-stop"):
            self.pantalla = None
            self._reiniciar()
            return ok
        if orden[:2] == ("am", "start"):
            self.pantalla = "inicio"
            self._reiniciar()
            return comun.Resultado(0, "Status: ok\n", "")
        if orden[:2] == ("input", "tap"):
            self._tocar(int(orden[2]), int(orden[3]))
            return ok
        if orden[:2] == ("input", "text"):
            self.textos_adb.append(orden[2])
            if self.foco is not None:
                self.campos[self.foco] += _desescapar(orden[2])
            return ok
        if orden[:2] == ("input", "keyevent") and orden[2] == comun.TECLA_ATRAS:
            if self.teclado:
                self.teclado = False
            elif self.pantalla == "login":
                self.pantalla = "inicio"
            return ok
        if orden[:2] == ("input", "swipe"):
            self.desplazamientos += 1
            return ok
        if orden[:2] == ("dumpsys", "input_method"):
            return comun.Resultado(0, f"  mInputShown={'true' if self.teclado else 'false'}\n", "")
        if orden[:2] == ("wm", "size"):
            return comun.Resultado(0, "Physical size: 1080x2400\n", "")
        return ok


class Mundo:
    """Gradle, HTTP, AWS y el teléfono falsos."""

    def __init__(self, tmp_path: Path, **opciones_telefono) -> None:
        self.tmp = tmp_path
        self.reloj = Reloj()
        self.telefono = Telefono(self.reloj, **opciones_telefono)
        self.casos = {validate12.CLASE_C3: 9, validate12.CLASE_C4: 6}
        self.login_estado = 200
        self.instalar_salida = "BUILD SUCCESSFUL"
        self.crear_falla = False
        self.tareas: list[list[str]] = []
        self.gradle_ordenes: list[tuple[str, ...]] = []

    def instalar(self, monkeypatch) -> None:
        plan = self.tmp / "PLAN.md"
        plan.write_text(PLAN, encoding="utf-8")
        monkeypatch.setattr(comun, "PLAN_APP", plan)
        monkeypatch.setattr(comun, "DIR_RESULTADOS_PRUEBAS", self.tmp)
        monkeypatch.setattr(comun, "gradle", self.gradle)
        monkeypatch.setattr(comun, "adb", self.telefono.adb)
        monkeypatch.setattr(comun, "dispositivo_fisico", lambda: "SERIAL1")
        monkeypatch.setattr(comun, "url_api_vigente", lambda: (URL, "terraform output api_base_url"))
        monkeypatch.setattr(comun, "url_api_config", lambda ruta=None: URL)
        monkeypatch.setattr(comun, "http_get", self.http_get)
        monkeypatch.setattr(comun, "http_post_json", self.http_post_json)
        monkeypatch.setattr(comun, "cuenta_aws", lambda: "arn:aws:iam::648617469176:root")
        monkeypatch.setattr(comun, "terraform_outputs", self.outputs)
        monkeypatch.setattr(comun, "tarea_cli", self.tarea_cli)
        monkeypatch.setattr(comun, "reloj", self.reloj.reloj)
        monkeypatch.setattr(comun, "dormir", self.reloj.dormir)
        monkeypatch.setattr(comun, "commit_actual", lambda: "abc1234")
        monkeypatch.setenv("VALIDACION_ADMIN_CORREO", ADMIN[0])
        monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", ADMIN[1])

    def gradle(self, *args, timeout=0):
        self.gradle_ordenes.append(args)
        if "--version" in args:
            return comun.Resultado(0, "Gradle 8.7\nJVM:          21.0.11\n", "")
        if "installDebug" in args:
            codigo = 1 if "FAILED" in self.instalar_salida else 0
            return comun.Resultado(codigo, self.instalar_salida, "")
        if "testDebugUnitTest" in args:
            for clase, casos in self.casos.items():
                if f"*.{clase}" in args:
                    (self.tmp / f"TEST-com.example.myapplication.x.{clase}.xml").write_text(
                        f'<testsuite tests="{casos}" failures="0" errors="0" skipped="0"/>', encoding="utf-8"
                    )
            return comun.Resultado(0, "BUILD SUCCESSFUL", "")
        return comun.Resultado(0, "", "")

    def http_get(self, url, timeout=15.0):
        return comun.RespuestaHttp(200, {}, json.dumps({"estado": "ok", "version": "0.1.0", "commit": "x"}), 40)

    def http_post_json(self, url, cuerpo, timeout=15.0):
        assert url == f"{URL}/auth/login"
        if self.login_estado != 200:
            codigo = {401: "CREDENCIALES_INVALIDAS", 404: "NO_ENCONTRADO"}.get(self.login_estado, "ERROR_INTERNO")
            return comun.RespuestaHttp(self.login_estado, {}, json.dumps({"error": {"codigo": codigo}}), 30)
        assert (cuerpo["identificador"], cuerpo["password"]) == ADMIN
        cuerpo_200 = {
            "token": "eyJ.token.secreto",
            "expira_en": "2026-10-26T12:00:00Z",
            "usuario": {"id": "u1", "nombre": NOMBRE_ADMIN, "correo": ADMIN[0], "rol": "admin"},
        }
        return comun.RespuestaHttp(200, {}, json.dumps(cuerpo_200), 900)

    def outputs(self, directorio=None):
        return {
            "ecs_cluster": "campus-locator-dev",
            "familias_tarea": {"migrate": "campus-locator-dev-migrate"},
            "subredes_tareas": ["subnet-1"],
            "sg_migrate": "sg-1",
        }

    def tarea_cli(self, outputs, argumentos, entorno=None, **kwargs):
        self.tareas.append(list(argumentos))
        self.reloj.t += 90
        if argumentos[0] == "crear-usuario":
            if self.crear_falla:
                return comun.ResultadoTarea(
                    "arn:t/1", "1", 1, "Essential container in task exited", ["comando_fallido"]
                )
            self.telefono.usuarios[comun.USUARIO_VALIDACION] = entorno["CREAR_USUARIO_PASSWORD"]
            return comun.ResultadoTarea("arn:t/1", "1", 0, "Essential container in task exited")
        if argumentos[0] == "desactivar-usuario":
            existia = self.telefono.usuarios.pop(comun.USUARIO_VALIDACION, None) is not None
            if existia:
                return comun.ResultadoTarea("arn:t/2", "2", 0, "")
            return comun.ResultadoTarea("arn:t/2", "2", 1, "", ["usuario_no_encontrado"])
        raise AssertionError(argumentos)


def _correr(tmp_path, entorno, argv_extra=()):
    informe = tmp_path / "informe.json"
    codigo = validate12.main(["--entorno", entorno, "--informe", str(informe), *argv_extra])
    return codigo, json.loads(informe.read_text(encoding="utf-8"))


def _estados(datos):
    return {c["id"]: c["estado"] for c in datos["comprobaciones"]}


def _detalle(datos, id_):
    return next(c["detalle"] for c in datos["comprobaciones"] + datos["precondiciones"] if c["id"] == id_)


def test_saludo_esperado():
    assert validate12.saludo_esperado("Alejandro Gómez") == "Hola, Alejandro"
    assert validate12.saludo_esperado("  Administrador ") == "Hola, Administrador"
    assert validate12.saludo_esperado("") == "Hola"


def test_dev_todo_bien_y_no_imprime_secretos(tmp_path, monkeypatch, capsys):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 0, datos
    assert [p["id"] for p in datos["precondiciones"]] == ["P1", "P2", "P3", "P4", "P5"]
    assert _estados(datos) == {"C1": "pasa", "C2": "pasa", "C3": "pasa", "C4": "pasa"}
    assert "Hola, Alejandro" in _detalle(datos, "C1")
    assert "Sin permisos" in _detalle(datos, "C2")
    # La cuenta user se crea y se desactiva al final; la app queda cerrada.
    assert [t[0] for t in m.tareas] == ["crear-usuario", "desactivar-usuario"]
    assert m.tareas[0] == [
        "crear-usuario",
        "--correo",
        comun.USUARIO_VALIDACION,
        "--nombre",
        "validacion-user",
        "--rol",
        "user",
    ]
    assert m.telefono.pantalla is None
    assert comun.USUARIO_VALIDACION not in m.telefono.usuarios
    # Permisos de Inicio concedidos (con ACTIVITY_RECOGNITION: SDK 34).
    concedidos = [o[4] for o in m.telefono.ordenes if o[:3] == ("shell", "pm", "grant")]
    assert concedidos == validate12.PERMISOS_INICIO + [validate12.PERMISO_ACTIVIDAD]
    # La contraseña del admin se escribió escapada para el sh del teléfono y nunca se imprimió.
    assert "Clave%sSegura\\$1\\'x" in m.telefono.textos_adb
    salida = capsys.readouterr()
    informe = json.dumps(datos, ensure_ascii=False)
    for secreto in (ADMIN[1], "eyJ.token.secreto", "validacion-pw-"):
        assert secreto not in salida.out
        assert secreto not in salida.err
        assert secreto not in informe


def test_local_solo_pruebas_en_la_jvm(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local")
    assert codigo == 0
    assert [p["id"] for p in datos["precondiciones"]] == ["P1"]
    assert _estados(datos) == {"C1": "omitida", "C2": "omitida", "C3": "pasa", "C4": "pasa"}
    assert m.telefono.ordenes == []
    assert m.tareas == []
    # Una sola ejecución de Gradle para las dos clases.
    pruebas = [o for o in m.gradle_ordenes if "testDebugUnitTest" in o]
    assert pruebas == [("testDebugUnitTest", "--tests", "*.SesionVencidaTest", "--tests", "*.RemoteAuthRepositoryTest")]


def test_miui_sin_depuracion_segura_es_3_con_mensaje_claro(tmp_path, monkeypatch):
    m = Mundo(tmp_path, miui_bloqueado=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 3
    assert _estados(datos)["C1"] == "error"
    assert "Depuración USB (Configuración de seguridad)" in _detalle(datos, "C1")
    # C2 creó la cuenta antes de fallar igual: la limpieza la desactiva.
    assert [t[0] for t in m.tareas] == ["crear-usuario", "desactivar-usuario"]


def test_install_restringido_en_miui_es_3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar_salida = "Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]"
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 3
    assert "Instalar vía USB" in _detalle(datos, "C1")


def test_boton_tapado_por_el_teclado_lo_cierra_con_atras(tmp_path, monkeypatch):
    m = Mundo(tmp_path, boton_tapado=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 0, datos
    assert ("shell", "input", "keyevent", comun.TECLA_ATRAS) in m.telefono.ordenes
    assert m.tareas == []  # sin C2 no se crea la cuenta user
    assert next(p for p in datos["precondiciones"] if p["id"] == "P3")["estado"] == "no evaluada"


@pytest.mark.parametrize(("estado", "codigo_esperado"), [(401, 3), (404, 2), (500, 2)])
def test_login_del_admin_en_p5(tmp_path, monkeypatch, estado, codigo_esperado):
    m = Mundo(tmp_path)
    m.login_estado = estado
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == codigo_esperado
    assert datos["comprobaciones"] == []
    assert m.tareas == []


def test_fe11_no_hecho_es_bloqueo(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    comun.PLAN_APP.write_text(PLAN.replace("| Hecho |", "| En curso |"), encoding="utf-8")
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 2
    assert "FE-1.1" in next(p["detalle"] for p in datos["precondiciones"] if p["id"] == "P4")


def test_crear_usuario_falla_c2_y_la_limpieza_lo_intenta_desactivar(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.crear_falla = True
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev")
    assert codigo == 1
    assert _estados(datos)["C2"] == "falla"
    assert "comando_fallido" in _detalle(datos, "C2")
    assert [t[0] for t in m.tareas] == ["crear-usuario", "desactivar-usuario"]


def test_user_que_abre_el_panel_falla_c2(tmp_path, monkeypatch):
    m = Mundo(tmp_path, user_abre_panel=True)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C2"])
    assert codigo == 1
    assert "abrió el Panel" in _detalle(datos, "C2")


def test_panel_sin_cerrar_sesion_falla_c1(tmp_path, monkeypatch):
    m = Mundo(tmp_path, desplazar_para_cerrar=99)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert "Cerrar sesión" in _detalle(datos, "C1")


def test_login_lento_falla_c1(tmp_path, monkeypatch):
    m = Mundo(tmp_path, retraso_login_s=30)
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "dev", ["--solo", "C1"])
    assert codigo == 1
    assert "15 s" in _detalle(datos, "C1")


def test_pocos_casos_fallan_c3(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.casos[validate12.CLASE_C3] = 3
    m.instalar(monkeypatch)
    codigo, datos = _correr(tmp_path, "local", ["--solo", "C3"])
    assert codigo == 1
    assert _estados(datos) == {"C1": "omitida", "C2": "omitida", "C3": "falla", "C4": "omitida"}
    assert "mínimo 4" in _detalle(datos, "C3")


def test_sin_limpieza_deja_la_cuenta(tmp_path, monkeypatch):
    m = Mundo(tmp_path)
    m.instalar(monkeypatch)
    codigo, _ = _correr(tmp_path, "dev", ["--solo", "C2", "--sin-limpieza"])
    assert codigo == 0
    assert [t[0] for t in m.tareas] == ["crear-usuario"]
