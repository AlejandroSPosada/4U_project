"""Pruebas de las ayudas de comun.py que añadió FE-1.2: PLAN, input text, uiautomator, AWS, tareas sueltas y POST."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import comun
import pytest


def test_lote_hecho_lee_la_tabla_de_estado_del_plan_real():
    texto = comun.PLAN_APP.read_text(encoding="utf-8")
    assert comun.lote_hecho(texto, "FE-1.1")
    assert not comun.lote_hecho(texto, "FE-9.9")  # no existe
    # La fila de §2.1 de FE-1.1 (`| FE-1.1 | Cliente HTTP… | — | …`) tampoco se confunde con la de §3.
    assert not comun.lote_hecho("| FE-1.1 | Cliente HTTP, conexión real y CI | — | BE-1.1, INF-1.4 |", "FE-1.1")
    # Una fila de §2.1 (tercera celda = «Para construir») no cuenta aunque diga «Hecho» en otra celda.
    assert not comun.lote_hecho("| FE-9.9 | Nombre | — | Hecho |", "FE-9.9")
    assert comun.lote_hecho("| FE-9.9 | 1 | Hecho | x |", "FE-9.9")


def _como_sh_e_input(escapado: str) -> str:
    """Lo que hacen el sh del teléfono (quita las `\\`) y `input text` (`%s` → espacio)."""
    return re.sub(r"\\(.)", r"\1", escapado).replace("%s", " ")


@pytest.mark.parametrize(
    ("texto", "escapado"),
    [
        ("admin@campus.edu.co", "admin@campus.edu.co"),
        ("validacion+user@campus.edu.co", "validacion+user@campus.edu.co"),
        ("validacion-pw-1b4e28ba-2fa1-11d2-883f-0016d3cca427", "validacion-pw-1b4e28ba-2fa1-11d2-883f-0016d3cca427"),
        ("dos palabras", "dos%spalabras"),
        ("a$b'c\"d\\e", "a\\$b\\'c\\\"d\\\\e"),
        (";&|<>()*?~#!`{}[]^", "\\;\\&\\|\\<\\>\\(\\)\\*\\?\\~\\#\\!\\`\\{\\}\\[\\]\\^"),
        ("100% s", "100\\%%ss"),
    ],
)
def test_escapar_input_text(texto, escapado):
    assert comun.escapar_input_text(texto) == escapado
    assert _como_sh_e_input(escapado) == texto


@pytest.mark.skipif(shutil.which("sh") is None, reason="sin sh en esta máquina")
@pytest.mark.parametrize("texto", ["Clave Segura$1'x", 'a"b\\c;d&e|f', "(x)<y>*?~#!`", "100% s"])
def test_escapar_input_text_con_un_sh_de_verdad(texto):
    escapado = comun.escapar_input_text(texto)
    # Como lo recibe `input` tras el sh del teléfono (adb une los argumentos con espacios y los pasa a `sh -c`).
    r = subprocess.run(["sh", "-c", f"printf '%s' {escapado}"], capture_output=True, text=True, check=True)
    assert r.stdout.replace("%s", " ") == texto


@pytest.mark.parametrize("texto", ["", "con %s dentro", "contraseña"])
def test_escapar_input_text_rechaza_lo_que_no_se_puede_escribir(texto):
    with pytest.raises(comun.ErrorConfiguracion) as e:
        comun.escapar_input_text(texto)
    assert texto not in str(e.value) or texto == ""


XML_LOGIN = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
    '<node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">'
    '<node text="Campus Navi" content-desc="" class="android.widget.TextView" bounds="[200,300][880,400]" '
    'enabled="true"/>'
    '<node text="admin@campus.edu.co" class="android.widget.EditText" bounds="[60,900][1020,1060]" enabled="true"/>'
    '<node text="secreta" class="android.widget.EditText" bounds="[60,1100][1020,1260]" password="true"/>'
    '<node text="" content-desc="" class="android.widget.Button" bounds="[60,1330][1020,1500]" enabled="false">'
    '<node text="Iniciar sesión" class="android.widget.TextView" bounds="[300,1380][800,1450]" enabled="true"/>'
    "</node></node></hierarchy>"
)


def test_parsear_ui_y_textos_visibles_sin_campos():
    nodos = comun.parsear_ui(XML_LOGIN[XML_LOGIN.find("<hierarchy") :])
    campos = comun.campos_texto(nodos)
    assert [c.limites for c in campos] == [(60, 900, 1020, 1060), (60, 1100, 1020, 1260)]
    assert campos[1].contrasena
    boton = comun.primero(nodos, dice="Iniciar sesión")
    assert boton is not None and boton.centro == (550, 1415)
    texto = comun.textos_visibles(nodos)
    assert "Campus Navi" in texto and "Iniciar sesión" in texto
    assert "secreta" not in texto and "admin@campus" not in texto


def test_volcar_pantalla_reintenta_y_borra_el_archivo(monkeypatch):
    ordenes = []
    respuestas = iter(["ERROR: could not get idle state.", XML_LOGIN])

    def adb(*args, timeout=0):
        ordenes.append(args)
        return comun.Resultado(0, next(respuestas), "")

    monkeypatch.setattr(comun, "adb", adb)
    monkeypatch.setattr(comun, "dormir", lambda s: None)
    nodos = comun.volcar_pantalla()
    assert len(comun.campos_texto(nodos)) == 2
    assert len(ordenes) == 2
    assert ordenes[0][0] == "exec-out" and f"rm -f {comun.RUTA_UI}" in ordenes[0][1]


def test_volcar_pantalla_explica_la_pantalla_que_no_para(monkeypatch):
    monkeypatch.setattr(comun, "adb", lambda *a, timeout=0: comun.Resultado(0, "ERROR: could not get idle state.", ""))
    monkeypatch.setattr(comun, "dormir", lambda s: None)
    with pytest.raises(comun.Falla) as e:
        comun.volcar_pantalla()
    assert "could not get idle state" in str(e.value)


def test_exigir_adb_permitido_reconoce_miui():
    r = comun.Resultado(255, "", "java.lang.SecurityException: Injecting to another application requires INJECT_EVENTS")
    with pytest.raises(comun.ErrorConfiguracion) as e:
        comun.exigir_adb_permitido(r, "tocar")
    assert "Depuración USB (Configuración de seguridad)" in str(e.value)
    comun.exigir_adb_permitido(comun.Resultado(0, "", ""), "tocar")  # sin error


def test_escribir_texto_no_copia_la_salida_de_adb(monkeypatch):
    monkeypatch.setattr(comun, "adb", lambda *a, timeout=0: comun.Resultado(1, "eco: secreta", "otra cosa secreta"))
    with pytest.raises(comun.Falla) as e:
        comun.escribir_texto("secreta")
    assert "secreta" not in str(e.value)


# --- AWS ---------------------------------------------------------------------------------------------------------


def _aws_falso(respuestas):
    """`comun.aws` falso: devuelve la primera respuesta cuya clave (tupla de argumentos iniciales) coincide."""
    llamadas = []

    def aws(*args, timeout=0):
        llamadas.append(args)
        for clave, resultado in respuestas:
            if args[: len(clave)] == clave:
                return resultado(args) if callable(resultado) else resultado
        raise AssertionError(args)

    return aws, llamadas


def test_aws_json_clasifica_los_errores(monkeypatch):
    aws, _ = _aws_falso(
        [
            (("a",), comun.Resultado(254, "", "An error occurred (AccessDeniedException) when calling X: no")),
            (("b",), comun.Resultado(254, "", "An error occurred (ResourceNotFoundException) when calling X: v=1")),
            (("c",), comun.Resultado(255, "", "Unable to locate credentials. You can configure credentials")),
            (("d",), comun.Resultado(0, '{"x": 1}', "")),
        ]
    )
    monkeypatch.setattr(comun, "aws", aws)
    with pytest.raises(comun.ErrorConfiguracion):
        comun.aws_json("a", accion="a")
    with pytest.raises(comun.ErrorAws) as e:
        comun.aws_json("b", accion="b", mostrar_error=False)
    assert e.value.codigo == "ResourceNotFoundException"
    assert "v=1" not in str(e.value)
    with pytest.raises(comun.ErrorConfiguracion):
        comun.aws_json("c", accion="c")
    assert comun.aws_json("d", accion="d") == {"x": 1}


def test_cuenta_aws_exige_la_del_proyecto(monkeypatch):
    aws, _ = _aws_falso([(("sts",), comun.Resultado(0, '{"Account": "111111111111", "Arn": "arn:x"}', ""))])
    monkeypatch.setattr(comun, "aws", aws)
    with pytest.raises(comun.ErrorConfiguracion):
        comun.cuenta_aws()


def test_credenciales_admin(monkeypatch):
    monkeypatch.setenv("VALIDACION_ADMIN_CORREO", "a@b.co")
    monkeypatch.setenv("VALIDACION_ADMIN_PASSWORD", "p")
    assert comun.credenciales_admin("local") == ("a@b.co", "p")
    monkeypatch.delenv("VALIDACION_ADMIN_PASSWORD")
    with pytest.raises(comun.ErrorConfiguracion):
        comun.credenciales_admin("local")
    secreto = json.dumps(json.dumps({"correo": "admin@campus.edu.co", "password": "Xy12"}))
    aws, llamadas = _aws_falso([(("secretsmanager", "get-secret-value"), comun.Resultado(0, secreto, ""))])
    monkeypatch.setattr(comun, "aws", aws)
    assert comun.credenciales_admin("dev") == ("admin@campus.edu.co", "Xy12")
    assert comun.SECRETO_ADMIN in llamadas[0]


def test_secreto_inexistente_es_bloqueo(monkeypatch):
    aws, _ = _aws_falso(
        [(("secretsmanager",), comun.Resultado(254, "", "An error occurred (ResourceNotFoundException) when x"))]
    )
    monkeypatch.setattr(comun, "aws", aws)
    with pytest.raises(comun.Bloqueo):
        comun.leer_secreto(comun.SECRETO_ADMIN)


OUTPUTS = {
    "ecs_cluster": "campus-locator-dev",
    "familias_tarea": {"migrate": "campus-locator-dev-migrate"},
    "subredes_tareas": ["subnet-1"],
    "sg_migrate": "sg-1",
}


def _mundo_ecs(codigo_contenedor, mensajes_log=None):
    overrides = {}

    def run_task(args):
        ruta = args[args.index("--overrides") + 1].removeprefix("file://")
        overrides.update(json.loads(Path(ruta).read_text(encoding="utf-8")))
        return comun.Resultado(0, json.dumps({"arn": "arn:aws:ecs:us-east-1:1:task/c/abc123", "fallos": []}), "")

    respuestas = [
        (("ecs", "run-task"), run_task),
        (("ecs", "wait"), comun.Resultado(0, "", "")),
        (("ecs", "describe-tasks"), comun.Resultado(0, json.dumps({"codigo": codigo_contenedor, "motivo": "x"}), "")),
        (("logs", "get-log-events"), comun.Resultado(0, json.dumps(mensajes_log or []), "")),
    ]
    return respuestas, overrides


def test_crear_usuario_pasa_la_contrasena_por_archivo_y_no_por_argumentos(monkeypatch):
    respuestas, overrides = _mundo_ecs(0)
    aws, llamadas = _aws_falso(respuestas)
    monkeypatch.setattr(comun, "aws", aws)
    password = comun.crear_usuario_validacion(OUTPUTS)
    assert password.startswith("validacion-pw-")
    contenedor = overrides["containerOverrides"][0]
    assert contenedor["name"] == "app"
    assert contenedor["command"] == [
        "python",
        "-m",
        "app.cli",
        "crear-usuario",
        "--correo",
        comun.USUARIO_VALIDACION,
        "--nombre",
        "validacion-user",
        "--rol",
        "user",
    ]
    assert contenedor["environment"] == [{"name": "CREAR_USUARIO_PASSWORD", "value": password}]
    lanzar = llamadas[0]
    assert all(password not in a for a in lanzar)
    red = json.loads(lanzar[lanzar.index("--network-configuration") + 1])
    assert red == {
        "awsvpcConfiguration": {"subnets": ["subnet-1"], "securityGroups": ["sg-1"], "assignPublicIp": "ENABLED"}
    }
    assert lanzar[lanzar.index("--task-definition") + 1] == "campus-locator-dev-migrate"
    # La consulta de describe-tasks no trae los overrides (llevan la contraseña).
    describe = next(a for a in llamadas if a[:2] == ("ecs", "describe-tasks"))
    assert "overrides" not in describe[describe.index("--query") + 1]


def test_desactivar_usuario_tolera_que_no_exista_y_explica_otros_fallos(monkeypatch):
    log = [json.dumps({"evento": "usuario_no_encontrado"}), "texto suelto"]
    respuestas, _ = _mundo_ecs(1, log)
    monkeypatch.setattr(comun, "aws", _aws_falso(respuestas)[0])
    monkeypatch.setattr(comun, "dormir", lambda s: None)
    assert "no existía" in comun.desactivar_usuario_validacion(OUTPUTS)
    with pytest.raises(comun.Falla) as e:
        comun.desactivar_usuario_validacion(OUTPUTS, tolerar_inexistente=False)
    assert "usuario_no_encontrado" in str(e.value)


def test_salidas_tarea_sin_outputs_es_bloqueo():
    with pytest.raises(comun.Bloqueo):
        comun.salidas_tarea({"ecs_cluster": "c"})


# --- POST con reintento de 429 de API Gateway --------------------------------------------------------------------


def test_http_post_json_reintenta_el_429_de_api_gateway(monkeypatch):
    recibidos = []
    respuestas = iter([(429, b'{"message":"Too Many Requests"}'), (200, b'{"token":"t"}')])

    class Manejador(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 — nombre de http.server
            recibidos.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            estado, cuerpo = next(respuestas)
            self.send_response(estado)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def log_message(self, *args):
            pass

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    monkeypatch.setattr(comun, "dormir", lambda s: None)
    try:
        r = comun.http_post_json(f"http://127.0.0.1:{servidor.server_port}/v1/auth/login", {"identificador": "a"})
    finally:
        servidor.shutdown()
    assert r.estado == 200
    assert recibidos == [{"identificador": "a"}, {"identificador": "a"}]
