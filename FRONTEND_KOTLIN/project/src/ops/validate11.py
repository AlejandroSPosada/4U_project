"""Validador de FE-1.1 — Cliente HTTP, conexión real y CI.

Documento: FRONTEND_KOTLIN/docs/validation/validation-1-1.md. Entornos: local (C2 y C4a) y dev (todo, con un
dispositivo físico). Solo lee: GET /v1/health y `terraform output -raw api_base_url`. En el teléfono instala el APK
de depuración (conserva los datos) y reinicia la app para leer su primera comprobación de conexión en app.log.
"""

from __future__ import annotations

import re
import sys
import time

import comun

CLASES_C2 = ["MapeoErroresApiTest", "MapeoDatosApiTest"]
ESPERA_C1A_S = 60
# Línea de RequestIdInterceptor en files/logs/app.log (ARCHITECTURE §5.10):
# "2026-10-25 17:03:44.123 I/Api [OkHttp …] [-] GET /v1/health -> 200 (85 ms) rid=<uuid>"
PATRON_SALUD = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3} I/Api .*GET /v1/health -> (\S+)(?: \S+)? \((\d+) ms\) rid=(\S+)"
)


class Contexto:
    def __init__(self) -> None:
        self.url_vigente: str | None = None
        self.origen_url: str | None = None


def lineas_salud(texto: str, desde: str) -> list[tuple[str, str, str]]:
    """`[(hora, resultado, rid)]` de las líneas de `GET /v1/health` con hora ≥ `desde` (`AAAA-MM-DD HH:MM:SS`)."""
    encontradas = []
    for linea in texto.splitlines():
        m = PATRON_SALUD.match(linea.strip())
        if m and m.group(1) >= desde:
            encontradas.append((m.group(1), m.group(2), m.group(4)))
    return encontradas


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-1.1",
        validacion="validation-1-1",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C2", "C4a", "C4b"],
        grupos={"C1": ["C1a"], "C4": ["C4a", "C4b"]},
    )
    ctx = Contexto()

    # --- precondiciones ----------------------------------------------------------------------------------------

    def p1_gradle() -> str:
        r = comun.gradle("--version", timeout=600)
        if r.codigo != 0:
            raise comun.ErrorConfiguracion(
                f"{' '.join(comun.comando_gradle())} --version falló: {comun.resumir(r.texto)}"
            )
        jvm = re.search(r"^JVM:\s+(.+)$", r.salida, re.MULTILINE)
        version = re.search(r"^Gradle (\S+)", r.salida, re.MULTILINE)
        return f"Gradle {version.group(1) if version else '?'}, JVM {jvm.group(1).strip() if jvm else '?'}"

    def p2_dispositivo() -> str:
        serial = comun.dispositivo_fisico()
        modelo = comun.adb("shell", "getprop", "ro.product.model", timeout=30).salida.strip()
        android = comun.adb("shell", "getprop", "ro.build.version.release", timeout=30).salida.strip()
        return f"{modelo or '?'} (Android {android or '?'}, serial {serial})"

    def p3_borde() -> str:
        url, origen = comun.url_api_vigente()
        ctx.url_vigente, ctx.origen_url = url, origen
        try:
            r = comun.http_get(f"{url}/health")
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"INF-1.4: el borde HTTPS no responde ({e})") from e
        return f"{origen}: HTTPS responde (HTTP {r.estado})"

    def p4_salud() -> str:
        r = comun.http_get(f"{ctx.url_vigente}/health")
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or cuerpo.get("estado") != "ok":
            raise comun.Bloqueo(f"BE-1.1: GET /v1/health respondió {r.estado} {comun.resumir(r.cuerpo, 120)}")
        return f"200 estado=ok, backend {cuerpo.get('version')} commit {cuerpo.get('commit')}"

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            if not v.precondicion("P2", p2_dispositivo):
                v.precondicion_no_evaluada("P3", "P2 no se cumple")
                v.precondicion_no_evaluada("P4", "P2 no se cumple")
                return
            if not v.precondicion("P3", p3_borde):
                v.precondicion_no_evaluada("P4", "P3 no se cumple")
                return
            if not v.precondicion("P4", p4_salud):
                return

        # --- comprobaciones automáticas ------------------------------------------------------------------------

        if dev:
            v.comprobacion("C1a", c1a_telefono_conectado)
        else:
            v.omitir("C1a", "solo en dev (necesita el dispositivo)")
        v.comprobacion("C2", c2_pruebas)
        v.comprobacion("C4a", c4a_api_config)
        if dev:
            v.comprobacion("C4b", c4b_salud_api_config)
        else:
            v.omitir("C4b", "solo en dev")

        # --- manuales ------------------------------------------------------------------------------------------

        v.manual(
            "C1b",
            "Con la app abierta en Inicio (la dejó así C1a), mira la barra inferior: «Conectado». Activa el modo "
            "avión y espera 20 s: «Sin conexión». Desactívalo y espera 20 s: «Conectado». Adjunta al PR las tres "
            "capturas o un video corto (validation-1-1 §3).",
        )
        v.manual(
            "C3",
            "En el PR que trae FE-1.1, el check «frontend / compilar y pruebas unitarias» (y «validadores») de "
            "frontend.yml en verde sobre el último commit del PR; enlaza la ejecución en el PR (validation-1-1 §3).",
        )

    def c1a_telefono_conectado() -> str:
        r = comun.gradle("installDebug", timeout=1800)
        if r.codigo != 0:
            raise comun.Falla(f"installDebug falló: {comun.resumir(r.texto[-600:], 300)}")
        hora = comun.adb("shell", "date", "+%Y-%m-%d_%H:%M:%S", timeout=30).salida.strip().replace("_", " ")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", hora):
            raise comun.Falla(f"no se pudo leer la hora del teléfono ({hora!r})")
        comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
        arranque = comun.adb("shell", "am", "start", "-W", "-n", comun.ACTIVIDAD, timeout=60)
        if arranque.codigo != 0 or "Error" in arranque.texto:
            raise comun.Falla(f"am start falló: {comun.resumir(arranque.texto, 200)}")
        comun.avisar(f"app abierta a las {hora}; esperando hasta {ESPERA_C1A_S} s su GET /v1/health en app.log")
        limite = time.monotonic() + ESPERA_C1A_S
        vistas: list[tuple[str, str, str]] = []
        while time.monotonic() < limite:
            texto = comun.leer_archivo_app(comun.LOG_APP) or ""
            vistas = lineas_salud(texto, hora)
            for _, resultado, rid in vistas:
                if resultado == "200":
                    return f"el teléfono llegó a GET /v1/health -> 200 (rid={rid})"
            time.sleep(3)
        if vistas:
            ultimos = ", ".join(f"{res} (rid={rid})" for _, res, rid in vistas[-3:])
            raise comun.Falla(f"el teléfono intentó GET /v1/health sin 200: {ultimos}; ¿tiene red? ¿ApiConfig?")
        raise comun.Falla(
            f"en {ESPERA_C1A_S} s no apareció GET /v1/health en {comun.LOG_APP} (¿diálogo de permisos sin responder?)"
        )

    def c2_pruebas() -> str:
        comun.borrar_resultados(CLASES_C2)
        argumentos = ["testDebugUnitTest"]
        for clase in CLASES_C2:
            argumentos += ["--tests", f"*.{clase}"]
        r = comun.gradle(*argumentos, timeout=1800)
        resultados = {c: comun.resultados_clase(c) for c in CLASES_C2}
        partes, malas = [], []
        for clase, res in resultados.items():
            if res is None:
                malas.append(f"{clase}: sin resultados")
                continue
            partes.append(f"{clase} {res.pruebas - res.fallos - res.errores}/{res.pruebas}")
            if not res.ok:
                malas.append(f"{clase}: {res.pruebas} casos, {res.fallos} fallos, {res.errores} errores")
        if r.codigo != 0 or malas:
            motivo = "; ".join(malas) or comun.resumir(r.texto[-600:], 300)
            raise comun.Falla(f"Gradle salió con {r.codigo}: {motivo}")
        return ", ".join(partes)

    def c4a_api_config() -> str:
        de_la_app = comun.normalizar_url(comun.url_api_config())
        if ctx.url_vigente is None:
            ctx.url_vigente, ctx.origen_url = comun.url_api_vigente()
        if not de_la_app.startswith("https://") or not de_la_app.endswith("/v1"):
            raise comun.Falla(f"ApiConfig.BASE_URL = {de_la_app} no es https://…/v1")
        if de_la_app != ctx.url_vigente:
            raise comun.Falla(f"ApiConfig.BASE_URL = {de_la_app}, pero {ctx.origen_url} da {ctx.url_vigente}")
        return f"ApiConfig.BASE_URL = {de_la_app} (= {ctx.origen_url})"

    def c4b_salud_api_config() -> str:
        url = comun.normalizar_url(comun.url_api_config())
        try:
            r = comun.http_get(f"{url}/health")
        except comun.ErrorRed as e:
            raise comun.Falla(f"GET {url}/health sin respuesta: {e}") from e
        if r.estado != 200:
            raise comun.Falla(f"GET {url}/health respondió {r.estado}")
        return f"GET <ApiConfig>/health -> 200 en {r.duracion_ms} ms"

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
