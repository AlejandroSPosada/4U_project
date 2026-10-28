"""Validador de FE-5.3 — Guía por voz con pasos y fotos (vistas 6.5 y 6.6; la «App 2» de la guía en tiempo real).

Documento: FRONTEND_KOTLIN/docs/validation/validation-5-3.md. Entornos: local (C1a, C2a y C3a: pruebas de la JVM —avance
sobre la ruta, avisos, desvío y recálculo, regla de mezcla, cliente de `POST /v1/localize/frame`— y comprobaciones
estáticas del modo de prueba, sin teléfono ni red) y dev (además, con el teléfono **en casa**: C1b, la guía abierta en
el APK de depuración con el destino y la posición de prueba de FE-5.1 y el modo de simulación «camina» la ruta y dice
cada aviso hasta la llegada (6.6), leído en `app.log`; y C2b, en esa misma caminata la app llama de verdad a
`POST /v1/localize/frame` con fotos de la cámara —en casa responde `sin_coincidencias`— y la guía sigue sin caerse).
No escribe nada en el backend salvo lo que deja cada foto de la app (una fila anónima de `eventos_localizacion`, backend
§5.3), no enciende ni apaga `embedding` y en el teléfono no borra nada (nunca `pm clear`).
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

import comun

CLASES_C1A = ["TrazadoRutaTest", "AnunciadorTest", "GuiaNavegacionTest", "AlertasEnRutaTest"]
CLASES_C2A = ["ReglaMezclaTest", "RemoteFrameRepositoryTest", "ComandoGuiaTest"]
CLASES_C3A = ["ColaVozTest"]
CLASES_POR_COMPROBACION = {"C1a": CLASES_C1A, "C2a": CLASES_C2A, "C3a": CLASES_C3A}
MINIMO_CASOS = {
    "TrazadoRutaTest": 4,
    "AnunciadorTest": 5,
    "GuiaNavegacionTest": 6,
    "AlertasEnRutaTest": 2,
    "ReglaMezclaTest": 6,
    "RemoteFrameRepositoryTest": 4,
    "ComandoGuiaTest": 2,
    "ColaVozTest": 2,
}

DIR_KOTLIN = comun.PROYECTO / "app" / "src" / "main" / "java" / "com" / "example" / "myapplication"
MAIN_ACTIVITY = DIR_KOTLIN / "MainActivity.kt"
PARAMETROS_GUIA = DIR_KOTLIN / "domain" / "guia" / "ParametrosGuia.kt"
CAMPUS_API = DIR_KOTLIN / "data" / "remote" / "CampusApi.kt"
RESULTADO_SCREEN = DIR_KOTLIN / "ui" / "ubicacion" / "ResultadoUbicacionScreen.kt"

# Decisión del usuario del 2026-10-28 (cómo llevar el teléfono): lo que la guía dice al empezar.
COMO_LLEVAR = "Lleva el teléfono en la mano, frente al pecho, con la cámara hacia adelante."

# La caminata en casa (C1b y C2b): la ruta de prueba de FE-5.1 (PlanificadorTest, validate51.py: 28,7 m con el grafo
# versión 209) recorrida por el modo de simulación con un paso de 0,7 m cada 500 ms (~21 s).
DESTINO_PRUEBA = "bloque35"
POSICION_PRUEBA = (6.201434, -75.578707)
SIMULAR_PASOS = "0.7,500"
LIMITE_LLEGADA_S = 120
LIMITE_INICIO_S = 30
PERMISO_CAMARA = "android.permission.CAMERA"
APP_LOG = "files/logs/app.log"

# Lo que dice la guía en esa ruta (líneas `Guia` de app.log; el destino sale como `<destino>`).
INICIO_ESPERADO = f"{COMO_LLEVAR} Vamos a <destino>, a 29 metros por el camino. Camina 14 metros por el camino."
PREVIO_GIRO = re.compile(r"^En \d+ metros?, gira a la izquierda\.$")
MANIOBRA_ESPERADA = "Gira a la izquierda y sigue recto 14 metros."
PREVIO_LLEGADA = re.compile(r"^En \d+ metros?, llegas a <destino>\.$")
LLEGADA_ESPERADA = "Has llegado a <destino>."
PATRON_INICIO = re.compile(r"^Guía iniciada: ruta (\d+) m, (\d+) instrucciones.*simulación")

# Una línea de files/logs/app.log (AppLog, ARCHITECTURE §3.2): «AAAA-MM-DD HH:MM:SS.mmm N/Tag [hilo] [sesión] texto».
PATRON_LINEA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3} ([DIWE])/(\S+) \[[^\]]*\] \[([^\]]*)\] (.*)$")
PATRON_FRAME_API = re.compile(r"POST /v1/localize/frame -> (\S+)")  # RequestIdInterceptor (§5.10)

INSTRUCCION_C1B = (
    "Sostén el teléfono desbloqueado con la cámara trasera hacia una zona iluminada de la casa (no la tapes ni la "
    "pongas boca abajo: una foto oscura o borrosa no se envía) durante unos 40 s, con el volumen alto. Al pulsar Enter "
    "se abre la guía en modo de simulación y «camina» sola la ruta de prueba hasta la Llegada."
)
INSTRUCCION_C3C = (
    "Capturas de 6.5 durante la simulación (instrucción en grande, «Faltan N m», estado de las fotos) y de 6.6 "
    "(«Has llegado a bloque 35.»), tomadas con `adb exec-out screencap -p` durante C1b, en "
    "validation/evidencia/fe-5-3/. Sin datos privados: la vista previa de la cámara de 6.5 muestra la casa; "
    "recórtala o tápala antes de versionar."
)
INSTRUCCION_C4C = (
    "Día de campo (criterio de la meta 3, PLAN §2.2 FE-5.3): en el campus, con `embedding` encendido, al menos 5 "
    "recorridos de 50 a 150 m dentro del grafo desde «Ubicarme» → 6.3 → «Guiarme»: llegar a ≤ 5 m de la entrada del "
    "destino, cada giro anunciado antes del cruce, desvío detectado y recalculado, y posición a ≤ ~10 m de la real; "
    "anotar dónde llegó tarde un aviso, dónde se desvió la posición y dónde falló la foto (para ajustar "
    "ParametrosGuia)."
)


# --- piezas puras --------------------------------------------------------------------------------------------------


@dataclass
class LineaLog:
    hora: str  # «AAAA-MM-DD HH:MM:SS», hora del teléfono
    nivel: str
    tag: str
    sesion: str
    texto: str


def lineas_log(texto: str, desde: str = "") -> list[LineaLog]:
    """Las líneas de app.log (sin las de una traza) con hora ≥ `desde` («AAAA-MM-DD HH:MM:SS»; vacío = todas)."""
    salida = []
    for linea in texto.splitlines():
        m = PATRON_LINEA.match(linea)
        if m and m.group(1) >= desde:
            salida.append(LineaLog(*m.groups()))
    return salida


def ultima_guia(lineas: list[LineaLog]) -> list[LineaLog]:
    """Las líneas desde la última «Guía iniciada…» (de cualquier tag: también `Api`); vacía si no hay ninguna."""
    inicio = max(
        (i for i, linea in enumerate(lineas) if linea.tag == "Guia" and linea.texto.startswith("Guía iniciada")),
        default=None,
    )
    return [] if inicio is None else lineas[inicio:]


# Avisos de la guía que dependen de la red o de embedding (los mira C2b, no C1b).
AVISOS_DE_RED = ("Sin conexión:", "El servicio de fotos no está disponible")


def dichos(lineas: list[LineaLog]) -> list[str]:
    """Lo que dijo la guía, en orden: el texto de las líneas `Voz…:` y la de `Llegada:` (tag `Guia`), sin los avisos
    de red ([AVISOS_DE_RED])."""
    salida = []
    for linea in lineas:
        if linea.tag != "Guia":
            continue
        m = re.match(r"^Voz(?: \(ya\))?: (.*)$", linea.texto)
        if m:
            if not m.group(1).startswith(AVISOS_DE_RED):
                salida.append(m.group(1))
        elif linea.texto.startswith("Llegada: "):
            salida.append(linea.texto.removeprefix("Llegada: "))
    return salida


def revisar_secuencia(lineas: list[LineaLog]) -> str:
    """C1b: la guía de la caminata simulada dijo, en orden, el inicio, el aviso previo del giro, el giro, el aviso de
    la llegada y la llegada (ARCHITECTURE §5.7, «Guía por voz»), y la 6.6 se abrió. Falla con lo que faltó."""
    if not lineas:
        raise comun.Falla("app.log no tiene «Guía iniciada…» desde el arranque: ¿se abrió la 6.5?")
    m = PATRON_INICIO.match(lineas[0].texto)
    if not m:
        raise comun.Falla(f"la guía no arrancó en modo de simulación: «{lineas[0].texto}»")
    if any(linea.tag == "CRASH" for linea in lineas):
        raise comun.Falla("la app se cerró (línea CRASH en app.log)")
    d = dichos(lineas)
    esperado = [INICIO_ESPERADO, PREVIO_GIRO, MANIOBRA_ESPERADA, PREVIO_LLEGADA, LLEGADA_ESPERADA]

    def coincide(e: str | re.Pattern[str], x: str) -> bool:
        return e.match(x) is not None if isinstance(e, re.Pattern) else e == x

    if len(d) != len(esperado) or not all(coincide(e, x) for e, x in zip(esperado, d, strict=True)):
        raise comun.Falla(
            f"la guía dijo {d!r}; se esperaba inicio, «En N metros, gira a la izquierda.», «{MANIOBRA_ESPERADA}», "
            f"«En N metros, llegas a <destino>.» y «{LLEGADA_ESPERADA}»"
        )
    if not any(linea.tag == "Guia" and linea.texto.startswith("Llegada mostrada") for linea in lineas):
        raise comun.Falla("app.log no tiene «Llegada mostrada (6.6)»")
    return f"ruta {m.group(1)} m, {m.group(2)} instrucciones; dijo: " + " | ".join(d)


@dataclass
class Fotos:
    pedidas: int = 0  # «Enviando foto…»
    no_enviadas: list[str] = field(default_factory=list)  # «Foto no enviada: oscura|borrosa»
    codigos: list[str] = field(default_factory=list)  # POST /v1/localize/frame -> <código>
    respuestas: list[str] = field(default_factory=list)  # «Foto: ok …» / «Foto: sin_coincidencias …»
    decisiones: list[str] = field(default_factory=list)  # «Foto aceptada (…)» / «Foto descartada (…)»
    fallos: list[str] = field(default_factory=list)  # «Foto falló (…)»
    corregidas: int = 0  # «Posición corregida por la foto»


def fotos_de(lineas: list[LineaLog]) -> Fotos:
    f = Fotos()
    for linea in lineas:
        t = linea.texto
        if linea.tag == "Api":
            m = PATRON_FRAME_API.search(t)
            if m:
                f.codigos.append(m.group(1))
            continue
        if linea.tag != "Guia":
            continue
        if t.startswith("Enviando foto a POST /v1/localize/frame"):
            f.pedidas += 1
        elif t.startswith("Foto no enviada: "):
            f.no_enviadas.append(t.removeprefix("Foto no enviada: "))
        elif t.startswith("Foto: "):
            f.respuestas.append(t.removeprefix("Foto: "))
        elif t.startswith(("Foto aceptada", "Foto descartada")):
            f.decisiones.append(t.removeprefix("Foto "))
        elif t.startswith("Foto falló"):
            f.fallos.append(t.removeprefix("Foto falló "))
        elif t.startswith("Posición corregida"):
            f.corregidas += 1
    return f


def revisar_fotos(f: Fotos) -> str:
    """C2b: al menos una foto llegó al backend con `200` y cada respuesta tuvo su decisión (aceptada o descartada)."""
    ok = [c for c in f.codigos if c == "200"]
    if not ok:
        if f.no_enviadas and not f.codigos:
            raise comun.Falla(
                f"ninguna foto se envió: {len(f.no_enviadas)} descartadas por calidad ({', '.join(f.no_enviadas)}); "
                "apunta la cámara a una zona iluminada y repite con --solo C1b,C2b"
            )
        raise comun.Falla(
            f"ninguna respuesta 200 de POST /v1/localize/frame (códigos {f.codigos or 'ninguno'}, fallos "
            f"{f.fallos or 'ninguno'}): ¿embedding apagado (503)? ¿sin red?"
        )
    if len(f.decisiones) < len(f.respuestas) or not f.respuestas:
        raise comun.Falla(f"{len(f.respuestas)} respuestas y solo {len(f.decisiones)} decisiones en app.log")
    return (
        f"{f.pedidas} fotos enviadas, POST /v1/localize/frame -> {', '.join(f.codigos)}; respuestas: "
        f"{'; '.join(f.respuestas)}; decisiones: {', '.join(f.decisiones)}"
        + (f"; no enviadas por calidad: {', '.join(f.no_enviadas)}" if f.no_enviadas else "")
        + (f"; posición corregida {f.corregidas} veces" if f.corregidas else "")
    )


def comprobar_estatica(archivos_kotlin: dict[str, str], main_activity: str) -> str:
    """Estática de C3a: los datos de prueba de la guía (`PruebaGuia.fijar(`) solo los fija `MainActivity` tras
    `rutaDePrueba` (que exige `FLAG_DEBUGGABLE`) con la ruta `navegacion`; las rutas `navegacion` y `llegada` están
    registradas; la 6.3 tiene «Guiarme»; `CampusApi` declara `localize/frame`; y la guía dice cómo llevar el teléfono
    con el texto de la decisión del usuario."""
    usos = [ruta for ruta, texto in archivos_kotlin.items() if "PruebaGuia.fijar(" in texto]
    if usos != ["MainActivity.kt"]:
        raise comun.Falla(f"PruebaGuia.fijar( debe estar solo en MainActivity.kt; está en: {usos or 'ninguno'}")
    funcion = re.search(r"fun rutaDePrueba\(.*?\n    \}", main_activity, re.DOTALL)
    if not funcion or "FLAG_DEBUGGABLE" not in funcion.group(0):
        raise comun.Falla("MainActivity.rutaDePrueba no comprueba FLAG_DEBUGGABLE")
    if not re.search(r'if \(rutaPrueba == "navegacion"\) \{\s*PruebaGuia\.fijar\(', main_activity):
        raise comun.Falla('PruebaGuia.fijar( no está dentro de `if (rutaPrueba == "navegacion")`')
    if not re.search(r'RUTAS_DE_PRUEBA = setOf\([^)]*"navegacion"', main_activity):
        raise comun.Falla('"navegacion" no está en MainActivity.RUTAS_DE_PRUEBA')
    for ruta in ("navegacion", "llegada"):
        if f'composable("{ruta}")' not in main_activity:
            raise comun.Falla(f'AppNav no registra la ruta "{ruta}"')
    resultado = archivos_kotlin.get("ui/ubicacion/ResultadoUbicacionScreen.kt", "")
    if 'BotonPrincipal("Guiarme"' not in resultado:
        raise comun.Falla("la 6.3 no tiene el botón «Guiarme»")
    if '@POST("localize/frame")' not in archivos_kotlin.get("data/remote/CampusApi.kt", ""):
        raise comun.Falla('CampusApi no declara @POST("localize/frame")')
    parametros = archivos_kotlin.get("domain/guia/ParametrosGuia.kt", "")
    if f'"{COMO_LLEVAR}"' not in parametros:
        raise comun.Falla(f"COMO_LLEVAR_EL_TELEFONO no es «{COMO_LLEVAR}» (decisión del usuario del 2026-10-28)")
    return (
        "PruebaGuia solo en MainActivity (APK depurable, ruta navegacion); rutas navegacion y llegada; «Guiarme» en "
        '6.3; @POST("localize/frame"); cómo llevar el teléfono = decisión del usuario'
    )


@dataclass
class Contexto:
    url: str | None = None
    pasaron: set[str] = field(default_factory=set)
    telefono_listo: bool = False
    lineas: list[LineaLog] | None = None


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-5.3",
        validacion="validation-5-3",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C2a", "C3a", "C1b", "C2b"],
        grupos={"C1": ["C1a", "C1b"], "C2": ["C2a", "C2b"], "C3": ["C3a"]},
    )
    ctx = Contexto()
    gradle_resultado: dict[str, object] = {}

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

    def p3_api() -> str:
        url, origen = comun.url_api_vigente()
        ctx.url = url
        de_la_app = comun.normalizar_url(comun.url_api_config())
        if de_la_app != url:
            raise comun.Bloqueo(f"FE-1.1: ApiConfig.BASE_URL = {de_la_app}, pero {origen} da {url}")
        try:
            r = comun.http_get(f"{url}/health")
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"INF-1.4: GET /v1/health sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or cuerpo.get("estado") != "ok":
            raise comun.Bloqueo(f"BE-1.1: GET /v1/health respondió {r.estado}")
        return f"ApiConfig = {origen}; GET /v1/health -> 200"

    def p4_lotes() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-5.1"):
            raise comun.Bloqueo("FE-5.1 no está «Hecho» en PLAN.md §3 (grafo y rutas)")
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-5.1"):
            raise comun.Bloqueo("BE-5.1 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (POST /v1/localize/frame)")
        return "FE-5.1 y BE-5.1 Hecho"

    # --- JVM (una sola ejecución de Gradle) ------------------------------------------------------------------------

    def clases_incluidas() -> list[str]:
        return [c for id_, clases in CLASES_POR_COMPROBACION.items() if v.incluida(id_) for c in clases]

    def correr_gradle() -> None:
        if gradle_resultado:
            return
        clases = clases_incluidas()
        comun.borrar_resultados(clases)
        argumentos = ["testDebugUnitTest"]
        for clase in clases:
            argumentos += ["--tests", f"*.{clase}"]
        gradle_resultado["r"] = comun.gradle(*argumentos, timeout=1800)

    def jvm(id_: str) -> str:
        correr_gradle()
        r = gradle_resultado["r"]
        assert isinstance(r, comun.Resultado)
        partes = []
        for clase in CLASES_POR_COMPROBACION[id_]:
            res = comun.resultados_clase(clase)
            if res is None:
                raise comun.Falla(
                    f"{clase}: sin resultados; Gradle salió con {r.codigo}: {comun.resumir(r.texto[-600:], 300)}"
                )
            if not res.ok or res.omitidas or res.pruebas < MINIMO_CASOS[clase]:
                raise comun.Falla(
                    f"{clase}: {res.pruebas} casos (mínimo {MINIMO_CASOS[clase]}), {res.fallos} fallos, "
                    f"{res.errores} errores, {res.omitidas} omitidos"
                )
            partes.append(f"{clase} {res.pruebas}/{res.pruebas}")
        if r.codigo != 0:
            raise comun.Falla(f"Gradle salió con {r.codigo}: {comun.resumir(r.texto[-600:], 300)}")
        minimos = ", ".join(str(MINIMO_CASOS[c]) for c in CLASES_POR_COMPROBACION[id_])
        return f"{', '.join(partes)} (mínimos {minimos})"

    def c1a() -> str:
        detalle = jvm("C1a")
        ctx.pasaron.add("C1a")
        return detalle

    def c2a() -> str:
        detalle = jvm("C2a")
        ctx.pasaron.add("C2a")
        return detalle

    def c3a() -> str:
        archivos = {
            str(p.relative_to(DIR_KOTLIN)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in sorted(DIR_KOTLIN.rglob("*.kt"))
        }
        estatica = comprobar_estatica(archivos, MAIN_ACTIVITY.read_text(encoding="utf-8"))
        detalle = jvm("C3a")
        ctx.pasaron.add("C3a")
        return f"{estatica}; {detalle}"

    # --- dev: la caminata simulada en casa (C1b y C2b) ---------------------------------------------------------

    def preparar_telefono() -> None:
        if ctx.telefono_listo:
            return
        v.al_limpiar("cerrar la app (am force-stop)", lambda: comun.adb("shell", "am", "force-stop", comun.PAQUETE))
        r = comun.gradle("installDebug", timeout=1800)
        if "INSTALL_FAILED_USER_RESTRICTED" in r.texto:
            raise comun.ErrorConfiguracion(
                "installDebug: INSTALL_FAILED_USER_RESTRICTED — en MIUI/HyperOS activa «Instalar vía USB» en Opciones "
                "de desarrollador y acepta el diálogo de instalación en el teléfono"
            )
        if r.codigo != 0:
            raise comun.Falla(f"installDebug falló: {comun.resumir(r.texto[-600:], 300)}")
        g = comun.adb("shell", "pm", "grant", comun.PAQUETE, PERMISO_CAMARA, timeout=30)
        comun.exigir_adb_permitido(g, "conceder CAMERA (pm grant)")
        if g.codigo != 0:
            raise comun.Falla(f"pm grant {PERMISO_CAMARA} falló: {comun.resumir(g.texto, 200)}")
        ctx.telefono_listo = True

    def hora_telefono() -> str:
        r = comun.adb("shell", "date", "+%Y-%m-%d_%H:%M:%S", timeout=30)
        hora = r.salida.strip().replace("_", " ")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", hora):
            raise comun.Falla(f"adb shell date no dio la hora del teléfono: {comun.resumir(r.texto, 120)}")
        return hora

    def caminar() -> list[LineaLog]:
        """Abre la 6.5 de prueba con la simulación, espera la 6.6 y devuelve las líneas de app.log de esa guía."""
        if ctx.lineas is not None:
            return ctx.lineas
        preparar_telefono()
        comun.esperar_enter(INSTRUCCION_C1B)
        lat, lng = POSICION_PRUEBA
        comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
        desde = hora_telefono()
        r = comun.adb(
            "shell", "am", "start", "-W", "-n", comun.ACTIVIDAD,
            "--es", "ruta", "navegacion",
            "--es", "destino_prueba", DESTINO_PRUEBA,
            "--es", "posicion_prueba", f"{lat},{lng}",
            "--es", "simular_pasos", SIMULAR_PASOS,
            timeout=60,
        )  # fmt: skip
        if r.codigo != 0 or "Error" in r.texto:
            raise comun.Falla(f"am start falló: {comun.resumir(r.texto, 200)}")
        comun.esperar_nodo(
            lambda ns: comun.primero(ns, dice="Repetir instrucción"),
            LIMITE_INICIO_S,
            "la vista 6.5 («Repetir instrucción»)",
        )
        comun.esperar_nodo(
            lambda ns: comun.primero(ns, dice="Ir a otro lugar"), LIMITE_LLEGADA_S, "la vista 6.6 («Ir a otro lugar»)"
        )
        comun.dormir(2)  # la última línea (Llegada mostrada) se escribe al abrir la 6.6
        texto = comun.leer_archivo_app(APP_LOG)
        if texto is None:
            raise comun.Falla(f"no se pudo leer {APP_LOG} (run-as)")
        ctx.lineas = ultima_guia(lineas_log(texto, desde))
        return ctx.lineas

    def c1b() -> str:
        return revisar_secuencia(caminar())

    def c2b() -> str:
        lineas = caminar()
        if not lineas:
            raise comun.Falla("app.log no tiene «Guía iniciada…»: la caminata no empezó")
        return revisar_fotos(fotos_de(lineas))

    # --- cuerpo --------------------------------------------------------------------------------------------------

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        telefono = dev and v.alguna_incluida("C1b", "C2b")
        if telefono:
            if not v.precondicion("P2", p2_dispositivo):
                for p in ("P3", "P4"):
                    v.precondicion_no_evaluada(p, "falló P2")
                return
            if not v.precondicion("P3", p3_api):
                v.precondicion_no_evaluada("P4", "falló P3")
                return
            if not v.precondicion("P4", p4_lotes):
                return
        elif dev:
            for p in ("P2", "P3", "P4"):
                v.precondicion_no_evaluada(p, "C1b y C2b no están incluidas")

        v.comprobacion("C1a", c1a)
        v.comprobacion("C2a", c2a)
        v.comprobacion("C3a", c3a)
        if not dev:
            v.omitir("C1b", "solo en dev (teléfono en casa)")
            v.omitir("C2b", "solo en dev (teléfono en casa, POST /v1/localize/frame)")
        else:
            fallidas = [c for c in ("C1a", "C3a") if v.incluida(c) and c not in ctx.pasaron]
            if fallidas:
                v.omitir("C1b", f"no se hace: falló {' y '.join(fallidas)}")
                v.omitir("C2b", f"no se hace: falló {' y '.join(fallidas)}")
            else:
                v.comprobacion("C1b", c1b)
                v.comprobacion("C2b", c2b)
        v.manual("C3c", INSTRUCCION_C3C)
        v.manual("C4c", INSTRUCCION_C4C)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
