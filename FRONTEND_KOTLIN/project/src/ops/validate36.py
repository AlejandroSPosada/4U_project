"""Validador de FE-3.6 — Alertas públicas.

Documento: FRONTEND_KOTLIN/docs/validation/validation-3-6.md. Entornos: local (C1a, C3a y C4a: pruebas de la JVM y una
comprobación estática del modo de prueba, sin teléfono ni red) y dev (además, con el teléfono **en casa**: C1b y C1c
—una alerta creada en el backend llega a la caché del teléfono en la siguiente sincronización y al borrarla
desaparece—, C2b —en modo avión, el mapa abierto con la ubicación de prueba de «Ubicarme» anuncia la alerta de la
caché—, C4b —la vista 6.3 con la ubicación de prueba muestra la alerta después de la ubicación— y C5a —«Caminar con el
mapa» abre el mapa con el seguimiento empezado en esa posición, sin tocarlo—). Crea y borra por la API las alertas
`validacion-3-6-c1` y `validacion-3-6-c2` (solo esas, por mensaje exacto); no usa `embedding` y en el teléfono no
borra nada (nunca `pm clear`). La manual C5 (TalkBack) queda para la persona.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

import comun

CLASES_C1A = ["CacheAlertasPublicasTest"]
CLASES_C3A = ["DetectarAlertasCercanasTest"]
CLASES_C4A = ["AlertasEnResultadoTest"]
CLASES_POR_COMPROBACION = {"C1a": CLASES_C1A, "C3a": CLASES_C3A, "C4a": CLASES_C4A}
MINIMO_CASOS = {"CacheAlertasPublicasTest": 5, "DetectarAlertasCercanasTest": 5, "AlertasEnResultadoTest": 3}

DIR_APP = comun.PROYECTO / "app" / "src" / "main"
DIR_KOTLIN = DIR_APP / "java" / "com" / "example" / "myapplication"
APP_JS = DIR_APP / "assets" / "app.js"
MAIN_ACTIVITY = DIR_KOTLIN / "MainActivity.kt"
MAPA_PUBLICO = DIR_KOTLIN / "map" / "MapaPublicoScreen.kt"

PREFIJO_PRUEBA = "validacion-3-6"  # el `q` de la limpieza
MENSAJE_C1 = "validacion-3-6-c1"  # normal: se crea y se borra (C1b, C1c)
MENSAJE_C2 = "validacion-3-6-c2"  # alta: se queda hasta la limpieza (C2b, C4b, C5a)
MENSAJES_PRUEBA = (MENSAJE_C1, MENSAJE_C2)  # lo único que se borra (mensaje normalizado exacto)
RADIO_PRUEBA = 15
# La ubicación de prueba (`--es ubicacion_prueba`, ADR-FE-42) es la que usaba FE-5.1 con el grafo v180; con el v209
# sigue dentro del grafo (sobre la arista a0044). Las alertas van ~6 m al norte: con radio 15 m y la incertidumbre de
# 5 m de PruebaUbicacion, alcanzan de sobra.
POSICION_PRUEBA = (6.201434, -75.578427)
POSICION_ALERTAS = (6.201484, -75.578427)

CACHE = "files/alertas/publicas.json"
TAG_ALERTAS = "AlertasPublicas"
TAG_MAPA = "MapaPublico"
TAG_RESULTADO = "ResultadoVM"
TAG_PDR = "Pdr"
PATRON_LINEA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3} ([DIWE])/(\S+) \[[^\]]*\] \[([^\]]*)\] (.*)$")
PATRON_SINCRONIZADA = re.compile(
    r"^Alertas públicas sincronizadas \(([^)]*)\): (completa|diferencias desde (\S+)), (\d+) recibidas, "
    r"(\d+) eliminadas, (\d+) en caché \(generado_en (\S+)\)$"
)
PATRON_NO_SINCRONIZO = re.compile(r"^Alertas públicas: no se pudo sincronizar")
PATRON_ANUNCIADA = re.compile(
    r"^Alerta anunciada \((resultado|mapa)\): (\S+) a (\d+) m \(radio (\d+) m, incertidumbre (\d+) m, (\S+)\)$"
)
INICIO_UBICARME = "Inicio desde Ubicarme"
PATRON_SENSORES = re.compile(r"sensores registrados \((iniciar|primer plano)")
RESULTADO_ALTA = "Resultado: alta"

# Textos de la app (ARCHITECTURE §5.5, «Resultado de ubicación», y §5.9, mapa público).
TITULO_SIN_LUGARES = "No hay lugares conocidos cerca"  # 6.3 con la ubicación de prueba (sin referencias)
TITULO_ALERTAS = "Alertas cercanas"
BOTON_MAPA = "Caminar con el mapa"
PREFIJO_ALERTA = "Alerta: "

LIMITE_SINCRONIZACION_S = 45
LIMITE_ALERTA_S = 30
LIMITE_RESULTADO_S = 20
PAUSA_LOG_S = 2
MAX_DESPLAZAMIENTOS = 3
COMPROBACIONES_TELEFONO = ("C1b", "C1c", "C2b", "C4b", "C5a")

INSTRUCCION_C2B_AVION = (
    "Activa el MODO AVIÓN en el teléfono (con el cable USB puesto: adb sigue funcionando) y comprueba que el Wi-Fi "
    "también quedó apagado. No abras la app: la abre el script."
)
INSTRUCCION_C2B_RED = (
    "Debiste oír «"
    + MENSAJE_C2
    + ".» y ver arriba del mapa «"
    + PREFIJO_ALERTA
    + MENSAJE_C2
    + ".». Ahora DESACTIVA el "
    "modo avión y espera a que vuelva la conexión (datos móviles o Wi-Fi)."
)
INSTRUCCION_C5 = (
    "Con TalkBack activo (si sale su tutorial, termínalo o sal de él): en Inicio, abre las acciones del botón "
    "principal con el gesto de TalkBack 17 que muestre su ayuda (menú de TalkBack → «Acciones») y elige «Ver mapa»; "
    "anota en ARCHITECTURE §4.5 el gesto que funcionó. Haz Ubicarme (o abre la app con la ruta de prueba `resultado` "
    "y `ubicacion_prueba`) y, en el Resultado, «Caminar con el mapa» con doble toque: el seguimiento empieza sin "
    "tocar el mapa y se oye «Sigo tus pasos desde tu última ubicación.». Atrás vuelve a Inicio; ahí, `adb shell "
    "dumpsys sensorservice` sin conexiones activas de com.example.myapplication. Evidencia en "
    "validation/evidencia/fe-3-6/: c5-video.mp4 (sin audio, screenrecord), c5-sensores-inicio.txt y c5-app-log.txt "
    "(líneas Pdr y MapaPublico)."
)


# --- piezas puras --------------------------------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    """Como `normalizar_nombre` del backend (la regla de `q` de las alertas): NFKD sin marcas, `casefold`, espacios a
    uno (como validate33)."""
    sin_marcas = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_marcas.casefold().split())


def alertas_de_prueba(items: list) -> list[dict]:
    """Las alertas cuyo mensaje normalizado es exactamente uno de `MENSAJES_PRUEBA`; nunca otras."""
    buscados = {normalizar(m) for m in MENSAJES_PRUEBA}
    return [i for i in items if isinstance(i, dict) and normalizar(str(i.get("mensaje") or "")) in buscados]


@dataclass
class LineaLog:
    hora: str
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


@dataclass
class Sincronizacion:
    motivo: str
    completa: bool
    desde: str | None
    recibidas: int
    eliminadas: int
    total: int
    generado_en: str


def sincronizaciones(lineas: list[LineaLog]) -> list[Sincronizacion]:
    """Las líneas «Alertas públicas sincronizadas (…)» (`I/AlertasPublicas`), en orden."""
    salida = []
    for linea in lineas:
        m = PATRON_SINCRONIZADA.match(linea.texto) if linea.tag == TAG_ALERTAS and linea.nivel == "I" else None
        if m:
            salida.append(
                Sincronizacion(
                    motivo=m.group(1),
                    completa=m.group(2) == "completa",
                    desde=m.group(3),
                    recibidas=int(m.group(4)),
                    eliminadas=int(m.group(5)),
                    total=int(m.group(6)),
                    generado_en=m.group(7),
                )
            )
    return salida


def fallos_sincronizacion(lineas: list[LineaLog]) -> list[str]:
    return [linea.texto for linea in lineas if linea.tag == TAG_ALERTAS and PATRON_NO_SINCRONIZO.match(linea.texto)]


@dataclass
class Anuncio:
    donde: str
    id: str
    distancia_m: int
    radio_m: int
    incertidumbre_m: int
    prioridad: str


def anuncios(lineas: list[LineaLog]) -> list[Anuncio]:
    """Las líneas «Alerta anunciada (resultado|mapa): <id> …» (`I/AlertasPublicas`)."""
    salida = []
    for linea in lineas:
        m = PATRON_ANUNCIADA.match(linea.texto) if linea.tag == TAG_ALERTAS and linea.nivel == "I" else None
        if m:
            salida.append(
                Anuncio(m.group(1), m.group(2), int(m.group(3)), int(m.group(4)), int(m.group(5)), m.group(6))
            )
    return salida


def leer_cache(texto: str | None) -> tuple[dict[str, dict], str | None]:
    """`files/alertas/publicas.json` (ARCHITECTURE §5.6): `({id: alerta}, generado_en)`; sin archivo → `({}, None)`."""
    if not texto:
        return {}, None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        raise comun.Falla(f"{CACHE} no es JSON ({e.msg})") from e
    if not isinstance(datos, dict) or not isinstance(datos.get("alertas"), list):
        raise comun.Falla(f"{CACHE} no tiene la forma de la versión 1 (sin «alertas»)")
    alertas = {str(a.get("id")): a for a in datos["alertas"] if isinstance(a, dict)}
    generado = datos.get("generado_en")
    return alertas, generado if isinstance(generado, str) else None


def comprobar_modo_prueba(archivos_kotlin: dict[str, str], main_activity: str, mapa: str, app_js: str) -> str:
    """Estática de C4a (ADR-FE-41 y ADR-FE-42): la ubicación de prueba solo la registra `MainActivity` tras una ruta
    de prueba (que exige `FLAG_DEBUGGABLE`), `resultado` es ruta de prueba, la 6.3 lleva al mapa, y el mapa empieza
    desde «Ubicarme» con `onNativeRastreoIniciado` (que existe en `app.js`)."""
    usos = [ruta for ruta, texto in archivos_kotlin.items() if "PruebaUbicacion.resultado(" in texto]
    if usos != ["MainActivity.kt"]:
        raise comun.Falla(
            f"PruebaUbicacion.resultado( debe estar solo en MainActivity.kt; está en: {usos or 'ninguno'}"
        )
    if main_activity.count("PruebaUbicacion.resultado(") != 1:
        raise comun.Falla("MainActivity.kt llama más de una vez a PruebaUbicacion.resultado(")
    if not re.search(r"if \(rutaPrueba != null\) \{\s*PruebaUbicacion\.resultado\(", main_activity):
        raise comun.Falla("PruebaUbicacion.resultado( no está dentro de `if (rutaPrueba != null)`")
    funcion = re.search(r"fun rutaDePrueba\(.*?\n    \}", main_activity, re.DOTALL)
    if not funcion or "FLAG_DEBUGGABLE" not in funcion.group(0):
        raise comun.Falla("MainActivity.rutaDePrueba no comprueba FLAG_DEBUGGABLE")
    rutas = re.search(r"RUTAS_DE_PRUEBA = setOf\(([^)]*)\)", main_activity)
    if not rutas or '"resultado"' not in rutas.group(1):
        raise comun.Falla('RUTAS_DE_PRUEBA no incluye "resultado"')
    if not re.search(r'onVerMapa = \{ nav\.navigate\("mapa"\)', main_activity):
        raise comun.Falla('la ruta `resultado` no conecta onVerMapa con nav.navigate("mapa")')
    if "SesionDeNavegacion.ubicacionVigente()" not in mapa or "onNativeRastreoIniciado(" not in mapa:
        raise comun.Falla("MapaPublicoScreen no empieza desde la ubicación vigente con onNativeRastreoIniciado")
    if not re.search(r"window\.onNativeRastreoIniciado\s*=\s*function", app_js):
        raise comun.Falla("app.js no tiene window.onNativeRastreoIniciado")
    return (
        "ubicación de prueba solo en MainActivity (APK depurable, rutas resultado y mapa); 6.3 → mapa; el mapa empieza "
        "desde Ubicarme (onNativeRastreoIniciado)"
    )


def ordenados_de_arriba_abajo(*nodos: comun.Nodo) -> bool:
    ys = [n.limites[1] for n in nodos]
    return ys == sorted(ys) and len(set(ys)) == len(ys)


@dataclass
class Contexto:
    url: str | None = None
    token: str = ""
    pasaron: set[str] = field(default_factory=set)
    telefono_listo: bool = False
    datos_listos: bool = False
    ids: dict[str, str] = field(default_factory=dict)  # mensaje → id de la alerta de prueba
    borradas: set[str] = field(default_factory=set)
    sincronizado: bool = False
    en_resultado: bool = False


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-3.6",
        validacion="validation-3-6",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C1c", "C2b", "C3a", "C4a", "C4b", "C5a"],
        grupos={"C1": ["C1a", "C1b", "C1c"], "C2": ["C2b"], "C3": ["C3a"], "C4": ["C4a", "C4b"], "C5": ["C5a"]},
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
        sdk = comun.adb("shell", "getprop", "ro.build.version.sdk", timeout=30).salida.strip()
        return f"{modelo or '?'} (Android {android or '?'}, SDK {sdk or '?'}, serial {serial})"

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

    def p4_login_admin() -> str:
        correo, password = comun.credenciales_admin(v.entorno)
        try:
            r = comun.http_post_json(f"{ctx.url}/auth/login", {"identificador": correo, "password": password})
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"INF-1.4: POST /v1/auth/login sin respuesta ({e})") from e
        if r.estado == 401:
            raise comun.ErrorConfiguracion(
                f"las credenciales del admin no sirven (401 {comun.codigo_error(r)}): revisa VALIDACION_ADMIN_* o "
                f"{comun.SECRETO_ADMIN}"
            )
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not cuerpo.get("token"):
            raise comun.Bloqueo(
                f"BE-1.3: POST /v1/auth/login respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        usuario = cuerpo.get("usuario") if isinstance(cuerpo.get("usuario"), dict) else {}
        if usuario.get("rol") != "admin":
            raise comun.ErrorConfiguracion(f"la cuenta {correo} no tiene rol admin (rol {usuario.get('rol')!r})")
        ctx.token = str(cuerpo["token"])
        return f"200: {correo}, rol admin"

    def p5_lotes() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-3.1"):
            raise comun.Bloqueo("FE-3.1 no está «Hecho» en PLAN.md §3 (mapa público desde Inicio)")
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.3"):
            raise comun.Bloqueo("BE-3.3 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (alertas)")
        foto = foto_publica(error=comun.Bloqueo)
        if foto.get("completo") is not True or not isinstance(foto.get("alertas"), list):
            raise comun.Bloqueo(f"BE-3.3: GET /v1/alerts sin «completo = true» ni «alertas»: {sorted(foto)}")
        return f"FE-3.1 y BE-3.3 Hecho; GET /v1/alerts -> 200 ({len(foto['alertas'])} activas)"

    # --- API de alertas (nunca imprime el token) ---------------------------------------------------------------

    def foto_publica(desde: str | None = None, error: type[Exception] = comun.Falla) -> dict:
        ruta = f"/alerts?desde={quote(desde)}" if desde else "/alerts"
        try:
            r = comun.http_get(f"{ctx.url}{ruta}")
        except comun.ErrorRed as e:
            raise error(f"GET /v1/alerts sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("generado_en"), str):
            raise error(f"GET /v1/alerts respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return cuerpo

    def lista_admin() -> list[dict]:
        try:
            r = comun.http_get(f"{ctx.url}/admin/alerts?q={quote(PREFIJO_PRUEBA)}", token=ctx.token)
        except comun.ErrorRed as e:
            raise comun.Falla(f"GET /v1/admin/alerts sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise comun.Falla(f"GET /v1/admin/alerts respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return [i for i in cuerpo["items"] if isinstance(i, dict)]

    def borrar_alerta(alerta_id: str) -> None:
        r = comun.http_delete(f"{ctx.url}/admin/alerts/{quote(alerta_id)}", token=ctx.token)
        if r.estado != 204:
            raise comun.Falla(f"DELETE /v1/admin/alerts/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}")
        ctx.borradas.add(alerta_id)

    def crear_alerta(mensaje: str, prioridad: str) -> str:
        """Por `sincronizar` (un `upsert` con un UUID nuevo, como validate33); su DELETE va a la limpieza."""
        alerta_id = str(uuid.uuid4())
        lat, lng = POSICION_ALERTAS
        alerta = {"id": alerta_id, "lat": lat, "lng": lng, "mensaje": mensaje, "tipo": "otro",
                  "prioridad": prioridad, "radio_m": RADIO_PRUEBA, "activa": True}  # fmt: skip
        v.al_limpiar(f"borrar la alerta {mensaje}", lambda: borrar_alerta(alerta_id))
        try:
            r = comun.http_post_json(
                f"{ctx.url}/admin/alerts/sincronizar",
                {"cambios": [{"op": "upsert", "alerta": alerta}]},
                token=ctx.token,
            )
        except comun.ErrorRed as e:
            raise comun.Falla(f"POST /v1/admin/alerts/sincronizar sin respuesta ({e})") from e
        cuerpo = r.json()
        resultados = cuerpo.get("resultados") if isinstance(cuerpo, dict) else None
        if r.estado != 200 or not isinstance(resultados, list) or [x.get("estado") for x in resultados] != ["ok"]:
            raise comun.Falla(
                f"crear {mensaje}: POST /v1/admin/alerts/sincronizar respondió {r.estado} "
                f"{comun.codigo_error(r) or ''} {resultados or ''}".rstrip()
            )
        ctx.ids[mensaje] = alerta_id
        return alerta_id

    # --- teléfono ----------------------------------------------------------------------------------------------

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
        ctx.telefono_listo = True

    def preparar_datos() -> None:
        """Una vez: instala, borra los restos `validacion-3-6-c1|c2`, crea c1 (normal) y c2 (alta) y registra que, tras
        borrarlas, la caché del teléfono se ponga al día (la siguiente sincronización las quita)."""
        if ctx.datos_listos:
            return
        preparar_telefono()
        v.al_limpiar("poner al día la caché del teléfono", sincronizar_al_limpiar)
        restos = alertas_de_prueba(lista_admin())
        for alerta in restos:
            borrar_alerta(str(alerta.get("id")))
        if restos:
            comun.avisar(f"· borrados {len(restos)} restos {PREFIJO_PRUEBA}-… de una ejecución anterior")
        crear_alerta(MENSAJE_C1, "normal")
        crear_alerta(MENSAJE_C2, "alta")
        ctx.datos_listos = True

    def hora_telefono() -> str:
        r = comun.adb("shell", "date", "+%Y-%m-%d_%H:%M:%S", timeout=30)
        hora = r.salida.strip().replace("_", " ")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", hora):
            raise comun.Falla(f"adb shell date no dio la hora del teléfono: {comun.resumir(r.texto, 120)}")
        return hora

    def log_desde(hora: str) -> list[LineaLog]:
        return lineas_log(comun.leer_archivo_app(comun.LOG_APP) or "", hora)

    def abrir(ruta: str, ubicacion: tuple[float, float] | None = None) -> None:
        """Arranque en frío con una ruta de prueba (APK de depuración): el proceso nuevo sincroniza la caché."""
        comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
        extras = ["--es", "ruta", ruta]
        if ubicacion is not None:
            extras += ["--es", "ubicacion_prueba", f"{ubicacion[0]},{ubicacion[1]}"]
        r = comun.adb("shell", "am", "start", "-W", "-n", comun.ACTIVIDAD, *extras, timeout=60)
        if r.codigo != 0 or "Error" in r.texto:
            raise comun.Falla(f"am start falló: {comun.resumir(r.texto, 200)}")

    def esperar_log(hora: str, encontrar, limite_s: float, que: str):
        """Lee app.log cada `PAUSA_LOG_S` hasta que `encontrar(lineas)` dé algo distinto de None."""
        fin = comun.reloj() + limite_s
        while True:
            lineas = log_desde(hora)
            hallado = encontrar(lineas)
            if hallado is not None:
                return hallado, lineas
            if comun.reloj() >= fin:
                fallos = fallos_sincronizacion(lineas)
                extra = f"; en app.log: «{fallos[-1]}»" if fallos else ""
                raise comun.Falla(f"en {limite_s:.0f} s no apareció {que} en app.log{extra}")
            comun.dormir(PAUSA_LOG_S)

    def sincronizar_telefono() -> Sincronizacion:
        hora = hora_telefono()
        # Una sincronización anterior pudo quedar en el mismo segundo: se espera una más que las que ya había.
        previas = len(sincronizaciones(log_desde(hora)))
        abrir("mapa")
        sinc, _ = esperar_log(
            hora,
            lambda ls: s[-1] if len(s := sincronizaciones(ls)) > previas else None,
            LIMITE_SINCRONIZACION_S,
            "«Alertas públicas sincronizadas (…)» (¿el teléfono tiene internet de verdad?)",
        )
        ctx.sincronizado = True
        return sinc

    def sincronizar_al_limpiar() -> None:
        if not ctx.datos_listos:
            return
        try:
            sincronizar_telefono()
        except comun.Falla as e:
            comun.avisar(f"· la caché del teléfono se pone al día en la próxima sincronización ({e})")

    def cache_telefono() -> tuple[dict[str, dict], str | None]:
        return leer_cache(comun.leer_archivo_app(CACHE))

    def describir(s: Sincronizacion) -> str:
        tipo = "completa" if s.completa else f"diferencias desde {s.desde}"
        return f"{tipo}, {s.recibidas} recibidas, {s.eliminadas} eliminadas, {s.total} en caché"

    def c1b() -> str:
        preparar_datos()
        s = sincronizar_telefono()
        alertas, generado = cache_telefono()
        faltan = [m for m in MENSAJES_PRUEBA if ctx.ids[m] not in alertas]
        if faltan:
            raise comun.Falla(
                f"tras la sincronización ({describir(s)}) la caché del teléfono no tiene {', '.join(faltan)} "
                f"({len(alertas)} alertas en {CACHE})"
            )
        for m in MENSAJES_PRUEBA:
            a = alertas[ctx.ids[m]]
            if a.get("mensaje") != m or a.get("radio") != RADIO_PRUEBA:
                raise comun.Falla(f"en la caché, {m} tiene mensaje {a.get('mensaje')!r} y radio {a.get('radio')!r}")
        if not generado:
            raise comun.Falla(f"{CACHE} no guarda generado_en (lo necesita la sincronización por diferencias)")
        ctx.pasaron.add("C1b")
        return f"{MENSAJE_C1} y {MENSAJE_C2} en la caché del teléfono tras la sincronización ({describir(s)})"

    def c1c() -> str:
        preparar_datos()
        if not ctx.sincronizado:
            sincronizar_telefono()
        antes, generado_antes = cache_telefono()
        if ctx.ids[MENSAJE_C1] not in antes or not generado_antes:
            raise comun.Falla(f"antes de borrar, la caché del teléfono no tiene {MENSAJE_C1} (¿falló C1b?)")
        borrar_alerta(ctx.ids[MENSAJE_C1])
        s = sincronizar_telefono()
        if s.completa or s.eliminadas < 1:
            raise comun.Falla(f"la sincronización tras borrar no fue por diferencias con eliminadas ({describir(s)})")
        despues, _ = cache_telefono()
        if ctx.ids[MENSAJE_C1] in despues:
            raise comun.Falla(f"tras borrar y sincronizar ({describir(s)}), {MENSAJE_C1} sigue en la caché")
        if ctx.ids[MENSAJE_C2] not in despues:
            raise comun.Falla(f"tras sincronizar ({describir(s)}), {MENSAJE_C2} desapareció de la caché")
        foto = foto_publica(generado_antes)
        if ctx.ids[MENSAJE_C1] not in (foto.get("eliminadas") or []):
            raise comun.Falla(f"GET /v1/alerts?desde={generado_antes} no trae {MENSAJE_C1} en «eliminadas»")
        ctx.pasaron.add("C1c")
        return (
            f"borrada en el backend ({MENSAJE_C1} en «eliminadas» de GET /v1/alerts?desde=), la sincronización "
            f"siguiente ({describir(s)}) la quitó de la caché; {MENSAJE_C2} sigue"
        )

    def modo_avion() -> bool:
        r = comun.adb("shell", "settings", "get", "global", "airplane_mode_on", timeout=30)
        return r.salida.strip() == "1"

    def asegurar_c2_en_cache() -> None:
        preparar_datos()
        alertas, _ = cache_telefono()
        if ctx.ids[MENSAJE_C2] not in alertas:
            sincronizar_telefono()
            alertas, _ = cache_telefono()
            if ctx.ids[MENSAJE_C2] not in alertas:
                raise comun.Falla(f"{MENSAJE_C2} no llegó a la caché del teléfono (falla C1)")

    def esperar_aviso_alerta() -> comun.Nodo:
        texto = f"{PREFIJO_ALERTA}{MENSAJE_C2}"

        def aviso(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            return next((n for n in nodos if n.texto.startswith(texto)), None)

        nodo, _ = comun.esperar_nodo(aviso, LIMITE_ALERTA_S, f"el aviso «{texto}.» sobre el mapa")
        return nodo

    def c2b() -> str:
        asegurar_c2_en_cache()
        comun.esperar_enter(INSTRUCCION_C2B_AVION)
        if not modo_avion():
            raise comun.Falla("el modo avión no está activado (settings global airplane_mode_on ≠ 1)")
        hora = hora_telefono()
        abrir("mapa", POSICION_PRUEBA)

        def anunciada(lineas: list[LineaLog]) -> Anuncio | None:
            return next((a for a in anuncios(lineas) if a.donde == "mapa" and a.id == ctx.ids[MENSAJE_C2]), None)

        anuncio, lineas = esperar_log(hora, anunciada, LIMITE_ALERTA_S, f"«Alerta anunciada (mapa): <{MENSAJE_C2}>»")
        if not any(ln.tag == TAG_MAPA and ln.texto.startswith(INICIO_UBICARME) for ln in lineas):
            raise comun.Falla(
                f"el mapa no dejó «{INICIO_UBICARME} …» en app.log: no empezó desde la ubicación de prueba"
            )
        hechas = sincronizaciones(lineas)
        if hechas:
            raise comun.Falla(f"hubo una sincronización correcta en modo avión ({describir(hechas[-1])}): ¿hay red?")
        if "C1c" in ctx.pasaron and any(a.id == ctx.ids.get(MENSAJE_C1) for a in anuncios(lineas)):
            raise comun.Falla(f"se anunció {MENSAJE_C1}, que ya se había borrado (la caché no se puso al día)")
        esperar_aviso_alerta()
        sin_red = fallos_sincronizacion(lineas)
        comun.esperar_enter(INSTRUCCION_C2B_RED)
        if modo_avion():
            comun.avisar("· el teléfono sigue en modo avión: desactívalo (C4b y C5a no lo necesitan, la limpieza sí)")
        return (
            f"en modo avión, el mapa empezó desde la ubicación de prueba y anunció {MENSAJE_C2} desde la caché "
            f"(a {anuncio.distancia_m} m, radio {anuncio.radio_m} m, incertidumbre {anuncio.incertidumbre_m} m, "
            f"{anuncio.prioridad}); sin sincronizar ({len(sin_red)} intentos fallidos)"
        )

    def abrir_resultado() -> tuple[str, list[comun.Nodo]]:
        hora = hora_telefono()
        abrir("resultado", POSICION_PRUEBA)
        _, nodos = comun.esperar_nodo(
            lambda ns: comun.primero(ns, dice=TITULO_SIN_LUGARES), LIMITE_RESULTADO_S, f"«{TITULO_SIN_LUGARES}» (6.3)"
        )
        ctx.en_resultado = True
        return hora, nodos

    def c4b() -> str:
        asegurar_c2_en_cache()
        hora, nodos = abrir_resultado()
        texto_alerta = f"{MENSAJE_C2}."

        def completa(ns: list[comun.Nodo]) -> comun.Nodo | None:
            return comun.primero(ns, dice=texto_alerta) if comun.primero(ns, dice=TITULO_ALERTAS) else None

        try:  # las alertas llegan al leer la caché del disco, un instante después del título
            nodo, nodos = comun.esperar_nodo(completa, 5, f"«{TITULO_ALERTAS}» con «{texto_alerta}»")
        except comun.Falla:
            nodo = None
        for _ in range(MAX_DESPLAZAMIENTOS):
            if nodo is not None:
                break
            comun.desplazar_hacia_abajo()
            comun.dormir(0.5)
            nodos = comun.volcar_pantalla()
            nodo = completa(nodos)
        if nodo is None:
            raise comun.Falla(
                f"la 6.3 no muestra «{TITULO_ALERTAS}» con «{texto_alerta}»; en pantalla: "
                f"{comun.textos_visibles(nodos)}"
            )
        titulo = comun.primero(nodos, dice=TITULO_SIN_LUGARES)
        encabezado = comun.primero(nodos, dice=TITULO_ALERTAS)
        orden = "debajo de la ubicación"
        if titulo is not None and encabezado is not None:
            if not ordenados_de_arriba_abajo(titulo, encabezado, nodo):
                raise comun.Falla("en la 6.3 la alerta no está debajo de la ubicación")
        else:
            orden = "tras desplazar"

        def anunciada(lineas: list[LineaLog]) -> Anuncio | None:
            return next((a for a in anuncios(lineas) if a.donde == "resultado" and a.id == ctx.ids[MENSAJE_C2]), None)

        anuncio, lineas = esperar_log(hora, anunciada, 10, f"«Alerta anunciada (resultado): <{MENSAJE_C2}>»")
        if not any(ln.tag == TAG_RESULTADO and ln.texto.startswith(RESULTADO_ALTA) for ln in lineas):
            raise comun.Falla(
                f"falta «{RESULTADO_ALTA}» (ResultadoVM) en app.log: la 6.3 no leyó la ubicación de prueba"
            )
        return (
            f"6.3 con la ubicación de prueba: «{TITULO_SIN_LUGARES}» y, {orden}, «{TITULO_ALERTAS}» con "
            f"«{texto_alerta}» "
            f"(a {anuncio.distancia_m} m, incertidumbre {anuncio.incertidumbre_m} m)"
        )

    def c5a() -> str:
        asegurar_c2_en_cache()
        if not ctx.en_resultado:
            abrir_resultado()
        boton = None
        nodos = comun.volcar_pantalla()
        for _ in range(MAX_DESPLAZAMIENTOS + 1):
            boton = comun.primero(nodos, dice=BOTON_MAPA)
            if boton is not None:
                break
            comun.desplazar_hacia_abajo()
            comun.dormir(0.5)
            nodos = comun.volcar_pantalla()
        if boton is None:
            raise comun.Falla(f"la 6.3 no ofrece «{BOTON_MAPA}»; en pantalla: {comun.textos_visibles(nodos)}")
        hora = hora_telefono()
        comun.tocar(boton)
        ctx.en_resultado = False

        def listo(lineas: list[LineaLog]) -> Anuncio | None:
            inicio = any(ln.tag == TAG_MAPA and ln.texto.startswith(INICIO_UBICARME) for ln in lineas)
            sensores = any(ln.tag == TAG_PDR and PATRON_SENSORES.search(ln.texto) for ln in lineas)
            alerta = next((a for a in anuncios(lineas) if a.donde == "mapa" and a.id == ctx.ids[MENSAJE_C2]), None)
            return alerta if inicio and sensores else None

        anuncio, _ = esperar_log(
            hora, listo, LIMITE_ALERTA_S,
            f"«{INICIO_UBICARME} …», «sensores registrados …» (Pdr) y «Alerta anunciada (mapa): <{MENSAJE_C2}>»",
        )  # fmt: skip
        esperar_aviso_alerta()
        return (
            f"«{BOTON_MAPA}» abrió el mapa con el seguimiento empezado en la ubicación de prueba sin tocarlo (Pdr: "
            f"sensores registrados) y anunció {MENSAJE_C2} (a {anuncio.distancia_m} m)"
        )

    # --- comprobaciones de la JVM (una sola ejecución de Gradle) ------------------------------------------------

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

    def c3a() -> str:
        detalle = jvm("C3a")
        ctx.pasaron.add("C3a")
        return detalle

    def c4a() -> str:
        archivos = {
            str(p.relative_to(DIR_KOTLIN)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in sorted(DIR_KOTLIN.rglob("*.kt"))
        }
        estatica = comprobar_modo_prueba(
            archivos,
            MAIN_ACTIVITY.read_text(encoding="utf-8"),
            MAPA_PUBLICO.read_text(encoding="utf-8"),
            APP_JS.read_text(encoding="utf-8"),
        )
        detalle = jvm("C4a")
        ctx.pasaron.add("C4a")
        return f"{estatica}; {detalle}"

    # --- cuerpo --------------------------------------------------------------------------------------------------

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        usa_telefono = dev and v.alguna_incluida(*COMPROBACIONES_TELEFONO)
        if dev:
            if usa_telefono:
                pasos = (("P2", p2_dispositivo), ("P3", p3_api), ("P4", p4_login_admin), ("P5", p5_lotes))
                for i, (id_, fn) in enumerate(pasos):
                    if not v.precondicion(id_, fn):
                        for siguiente, _ in pasos[i + 1 :]:
                            v.precondicion_no_evaluada(siguiente, f"falló {id_}")
                        return
            else:
                for id_ in ("P2", "P3", "P4", "P5"):
                    v.precondicion_no_evaluada(id_, "ninguna comprobación con teléfono está incluida")

        v.comprobacion("C1a", c1a)
        v.comprobacion("C3a", c3a)
        v.comprobacion("C4a", c4a)
        if not dev:
            for id_ in COMPROBACIONES_TELEFONO:
                v.omitir(id_, "solo en dev (teléfono en casa)")
        else:
            fallidas = [c for c in ("C1a", "C3a", "C4a") if v.incluida(c) and c not in ctx.pasaron]
            if fallidas:
                for id_ in COMPROBACIONES_TELEFONO:
                    v.omitir(id_, f"no se hace: falló {' y '.join(fallidas)}")
            else:
                v.comprobacion("C1b", c1b)
                if v.incluida("C1b") and "C1b" not in ctx.pasaron:
                    for id_ in ("C1c", "C2b", "C4b", "C5a"):
                        v.omitir(id_, "no se hace: falló C1b")
                else:
                    v.comprobacion("C1c", c1c)
                    v.comprobacion("C2b", c2b)
                    v.comprobacion("C4b", c4b)
                    v.comprobacion("C5a", c5a)
        v.manual("C5", INSTRUCCION_C5)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
