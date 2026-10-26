"""Validador de FE-3.3 — Alertas de administración sincronizadas (7.8–7.10).

Documento: FRONTEND_KOTLIN/docs/validation/validation-3-3.md. Entornos: local (C1a, C2a y C3a, pruebas en la JVM; sin
teléfono ni backend) y dev (además C1b, C2b y C3b, con un dispositivo físico y la API de dev). En dev: inicia sesión
como admin por la API y por la interfaz del teléfono, borra las alertas `validacion-3-3-c1|c2|c3` y el recorrido local
`validacion-3-3` que haya dejado una ejecución anterior y, en tres pasos guiados, la persona: graba un recorrido corto
con «Agregar alerta aquí» (`validacion-3-3-c1`) y sincroniza en 7.8 (el script la busca en GET /v1/admin/alerts, a
≤ 30 m de la primera foto del recorrido: C1b); crea y borra `validacion-3-3-c2` en 7.8 antes de sincronizar (ni la
alerta ni un *tombstone* en GET /v1/alerts?desde=, y app.log sin errores: C2b); y abre la Lista de alertas (7.10),
donde el script busca `validacion-3-3`, ve las filas y abre `validacion-3-3-c3`, que creó por la API (C3b). Al terminar
borra las alertas y el recorrido de prueba (también si algo falla) y cierra la app. Nunca imprime contraseñas ni tokens.
"""

from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote

import comun

CLASES_C1A = ["RemoteAlertasRepositoryTest", "AlmacenAlertasTest"]
CLASES_C2A = ["ReglasAlertasTest"]
CLASES_C3A = ["FormularioAlertaTest"]
MINIMO_CASOS = {
    "RemoteAlertasRepositoryTest": 8,
    "AlmacenAlertasTest": 3,
    "ReglasAlertasTest": 6,
    "FormularioAlertaTest": 7,
}
PREFIJO_PRUEBA = "validacion-3-3"  # el `q` de la limpieza y lo que se busca en 7.10
MENSAJE_C1 = "validacion-3-3-c1"  # la crea la persona en 7.4 («Agregar alerta aquí»)
MENSAJE_C2 = "validacion-3-3-c2"  # la crea y la borra la persona en 7.8 antes de sincronizar
MENSAJE_C3 = "validacion-3-3-c3"  # la crea el script por la API (sincronizar con un `upsert`)
MENSAJES_PRUEBA = (MENSAJE_C1, MENSAJE_C2, MENSAJE_C3)  # lo único que borra la limpieza (mensaje normalizado exacto)
VIDEO_PRUEBA = "validacion-3-3"  # nombre del recorrido de C1b (7.3)
DIR_RECOLECCION = "files/recoleccion"
PATRON_CARPETA = re.compile(r"^[A-Za-z0-9_-]+$")  # solo se borran carpetas con este nombre (sin «/» ni «..»)
POSICION_CAMPUS = (6.2006, -75.5783)  # aprox. EAFIT: donde va validacion-3-3-c3
DISTANCIA_MAXIMA_C1_M = 30.0  # validation-3-3 §2, C1
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
LIMITE_LOGIN_S = 15  # desde el toque en «Iniciar sesión» hasta ver el Panel
LIMITE_LISTA_S = 20  # C3b: hasta ver la lista 7.10 y sus filas
LIMITE_FORMULARIO_S = 10  # C3b: tras tocar la fila, hasta ver «Editar alerta»
# Textos y registros de la app (ARCHITECTURE §5.5 y §5.10, «Alertas»): cambiarlos exige cambiarlos aquí.
BUSCADOR_LISTA = "Buscar por mensaje…"  # placeholder del buscador de 7.10
TITULO_EDITAR = "Editar alerta"  # título de la hoja 7.9 al editar
PATRON_FILA = re.compile(  # content-desc de una fila de 7.10 (descripcionFilaAlerta)
    r"^(.*), (Agua|Mobiliario|Escalones|Obra|Vehículos|Otro|Alerta), prioridad (normal|alta), (activa|inactiva)"
    r"(, sin sincronizar)?\. Toca para editar\.$"
)
PATRON_LINEA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3} ([DIWE])/(\S+) \[[^\]]*\] \[([^\]]*)\] (.*)$")
PATRON_SINCRONIZADAS = re.compile(r"^Alertas sincronizadas: (\d+) enviadas, (\d+) aplicadas, (\d+) rechazadas$")
TAG_ALERTAS = "Alertas"  # RemoteAlertasRepository.TAG
ERRORES_LOGIN = ("Credenciales inválidas", "Sin conexión", "Algo salió mal")  # banners de Login (§5.5)

INSTRUCCION_C1B = (
    "En el teléfono, desde el Panel: «Recolector de imágenes» (7.3) → marca el punto de inicio y el rumbo → nombre "
    f"«{VIDEO_PRUEBA}» → «Confirmar y comenzar». En la recolección (7.4) elige «Cada 3 s» y, quieto, deja que tome "
    f"al menos 2 fotos; toca «Agregar alerta aquí», escribe {MENSAJE_C1} y «Guardar». «Finalizar video» → en el "
    "Resumen (7.5) «Guardar y subir después» (NO «Subir y procesar»). En el Panel abre «Mapa y alertas» (7.8): mira "
    "que esté el marcador de la alerta y pulsa «Guardar / Sincronizar» (sale «Sincronizado: …»). Con el editor a la "
    "vista, pulsa Enter aquí."
)
INSTRUCCION_C2B = (
    f"En el editor de mapa (7.8): «Nueva alerta», toca el mapa, mensaje {MENSAJE_C2} y «Guardar». Toca su marcador → "
    "«Eliminar» (confirma). Después pulsa «Guardar / Sincronizar» (sale «Sincronizado: …»). Con el editor a la vista, "
    "pulsa Enter aquí."
)
INSTRUCCION_C3B = (
    "En el editor de mapa (7.8) toca «Ver lista»: se abre la Lista de alertas (7.10). No toques nada más (el script "
    "escribe en el buscador y abre una alerta) y pulsa Enter aquí."
)
INSTRUCCION_C3C = (
    "Evidencia para el PR (validation-3-3 §3): capturas de 7.10 buscando «validacion-3-3» (con validacion-3-3-c1 y "
    "validacion-3-3-c3) y del formulario 7.9 abierto con validacion-3-3-c3 (C3b lo abre y lo cierra sin guardar)."
)


@dataclass
class Contexto:
    url: str = ""
    token: str = ""
    nombre_admin: str = ""
    admin: tuple[str, str] | None = None
    sdk: int = 0
    telefono_listo: bool = False
    panel_abierto: bool = False
    limpieza_registrada: bool = False
    gradle: comun.Resultado | None = None
    fallo_previo: str | None = None
    borradas: set[str] = field(default_factory=set)  # ids que borró el propio validador (no son «rastro» de C2)
    c1_creada: bool = False


@dataclass(frozen=True)
class Recorrido:
    id: str
    nombre: str
    finalizado: bool
    fotos: int
    primera: tuple[float, float] | None  # lat, lng de la primera foto (la de menor id)
    remoto: bool
    subida_estado: str


@dataclass(frozen=True)
class LineaLog:
    hora: str  # «AAAA-MM-DD HH:MM:SS», hora del teléfono
    nivel: str
    tag: str
    sesion: str
    texto: str


# --- piezas puras ----------------------------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    """Como `normalizar_nombre` del backend (backend §4.9, la regla de `q` de las alertas, §4.11): NFKD sin marcas
    combinantes, `casefold` y espacios reducidos a uno."""
    sin_marcas = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_marcas.casefold().split())


def saludo_esperado(nombre: str) -> str:
    """«Hola, <primer nombre>» o «Hola» (como validate22 y validate34)."""
    primero = nombre.strip().split(" ")[0]
    return f"Hola, {primero}" if primero else "Hola"


def alertas_de_prueba(items: list, mensaje: str | None = None) -> list[dict]:
    """Las alertas cuyo mensaje normalizado es exactamente uno de `MENSAJES_PRUEBA` (o [mensaje]); nunca otras."""
    buscados = {normalizar(mensaje)} if mensaje else {normalizar(m) for m in MENSAJES_PRUEBA}
    return [i for i in items if isinstance(i, dict) and normalizar(str(i.get("mensaje") or "")) in buscados]


def distancia_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine con R = 6 371 000 m (la de `CalibracionPaso.distanciaEntre`, ARCHITECTURE §5.7)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _numero(v: object) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def leer_recorrido(carpeta: str, texto: str | None) -> Recorrido | None:
    """Un `manifest.json` de `files/recoleccion/<carpeta>/` (§5.6 y §5.10), o None si no se puede leer."""
    if not texto:
        return None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    fotos = [p for p in datos.get("photos") or [] if isinstance(p, dict)]
    con_posicion = sorted(
        (p for p in fotos if _numero(p.get("lat")) and _numero(p.get("lng")) and p.get("id") is not None),
        key=lambda p: str(p["id"]),
    )
    primera = (float(con_posicion[0]["lat"]), float(con_posicion[0]["lng"])) if con_posicion else None
    nombre = datos.get("name") if isinstance(datos.get("name"), str) and datos["name"].strip() else carpeta
    return Recorrido(
        id=carpeta,
        nombre=str(nombre),
        finalizado=datos.get("estado") == "finalizado",
        fotos=len(fotos),
        primera=primera,
        remoto=bool(datos.get("remote_video_id")),
        subida_estado=str(datos.get("subida_estado") or "sin_subir"),
    )


def borrable(r: Recorrido) -> bool:
    """Un recorrido de prueba que se puede borrar del teléfono: se llama VIDEO_PRUEBA y el backend no lo conoce."""
    return r.nombre.strip() == VIDEO_PRUEBA and not r.remoto and r.subida_estado == "sin_subir"


def lineas_log(texto: str, desde: str = "") -> list[LineaLog]:
    """Las líneas de app.log (sin las de una traza) con hora ≥ `desde` («AAAA-MM-DD HH:MM:SS»; vacío = todas)."""
    salida = []
    for linea in texto.splitlines():
        m = PATRON_LINEA.match(linea)
        if m and m.group(1) >= desde:
            salida.append(LineaLog(*m.groups()))
    return salida


def sincronizaciones(lineas: list[LineaLog]) -> list[tuple[int, int, int]]:
    """`(enviadas, aplicadas, rechazadas)` de cada «Alertas sincronizadas: …» (`I/Alertas`)."""
    salida = []
    for linea in lineas:
        m = PATRON_SINCRONIZADAS.match(linea.texto) if linea.tag == TAG_ALERTAS and linea.nivel == "I" else None
        if m:
            salida.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return salida


def errores_log(lineas: list[LineaLog]) -> list[LineaLog]:
    """Las líneas de nivel E o con tag CRASH."""
    return [linea for linea in lineas if linea.nivel == "E" or linea.tag == "CRASH"]


def mensaje_de_fila(descripcion: str) -> str | None:
    """El mensaje de una fila de 7.10 desde su `content-desc` (`descripcionFilaAlerta`, §5.5), o None si no es fila."""
    m = PATRON_FILA.match(descripcion)
    return m.group(1) if m else None


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-3.3",
        validacion="validation-3-3",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C2a", "C2b", "C3a", "C3b"],
        grupos={"C1": ["C1a", "C1b"], "C2": ["C2a", "C2b"], "C3": ["C3a", "C3b"]},
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
        sdk = comun.adb("shell", "getprop", "ro.build.version.sdk", timeout=30).salida.strip()
        ctx.sdk = int(sdk) if sdk.isdigit() else 0
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
        ctx.admin = (correo, password)
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
        ctx.nombre_admin = str(usuario.get("nombre") or "")
        return f"200: {correo}, rol admin"

    def p5_fe12() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-1.2"):
            raise comun.Bloqueo("FE-1.2 no está «Hecho» en PLAN.md §3 (login de admin en la app)")
        return "FE-1.2 Hecho"

    def p6_be33() -> str:
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.3"):
            raise comun.Bloqueo("BE-3.3 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (alertas)")
        admin = lista_admin(error=comun.Bloqueo)
        # Sonda sin rastro: `eliminar` de un id que el servidor no conoce → `ok`, sin tombstone ni auditoría (§4.11).
        resultados = sincronizar([{"op": "eliminar", "id": str(uuid.uuid4())}], error=comun.Bloqueo)
        if [r.get("estado") for r in resultados] != ["ok"]:
            raise comun.Bloqueo(f"BE-3.3: la sonda de sincronizar respondió {resultados}")
        return (
            f"BE-3.3 Hecho; GET /v1/admin/alerts -> 200 ({len(admin)}); POST /v1/admin/alerts/sincronizar (sonda "
            "eliminar de un id desconocido) -> 200 ok"
        )

    # --- API de alertas (nunca imprime el token) ---------------------------------------------------------------

    def lista_admin(q: str | None = None, error: type[Exception] = comun.Falla) -> list[dict]:
        ruta = f"/admin/alerts?q={quote(q)}" if q else "/admin/alerts"
        try:
            r = comun.http_get(f"{ctx.url}{ruta}", token=ctx.token)
        except comun.ErrorRed as e:
            raise error(f"BE-3.3: GET /v1/admin/alerts sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise error(f"BE-3.3: GET /v1/admin/alerts respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return [i for i in cuerpo["items"] if isinstance(i, dict)]

    def foto_publica(desde: str | None = None) -> dict:
        ruta = f"/alerts?desde={quote(desde)}" if desde else "/alerts"
        try:
            r = comun.http_get(f"{ctx.url}{ruta}")
        except comun.ErrorRed as e:
            raise comun.Falla(f"GET /v1/alerts sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("generado_en"), str):
            raise comun.Falla(f"GET /v1/alerts respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return cuerpo

    def sincronizar(cambios: list[dict], error: type[Exception] = comun.Falla) -> list[dict]:
        try:
            r = comun.http_post_json(f"{ctx.url}/admin/alerts/sincronizar", {"cambios": cambios}, token=ctx.token)
        except comun.ErrorRed as e:
            raise error(f"BE-3.3: POST /v1/admin/alerts/sincronizar sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("resultados"), list):
            raise error(
                f"BE-3.3: POST /v1/admin/alerts/sincronizar respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        return [x for x in cuerpo["resultados"] if isinstance(x, dict)]

    def borrar_restos() -> int:
        """Borra las alertas de prueba (solo las de mensaje normalizado exacto de `MENSAJES_PRUEBA`)."""
        restos = alertas_de_prueba(lista_admin(PREFIJO_PRUEBA))
        for alerta in restos:
            alerta_id = str(alerta.get("id"))
            r = comun.http_delete(f"{ctx.url}/admin/alerts/{quote(alerta_id)}", token=ctx.token)
            if r.estado != 204:
                raise comun.Falla(f"DELETE /v1/admin/alerts/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}")
            ctx.borradas.add(alerta_id)
        return len(restos)

    # --- teléfono ----------------------------------------------------------------------------------------------

    def recorridos_telefono() -> dict[str, Recorrido]:
        salida = {}
        for carpeta in comun.listar_archivos_app(DIR_RECOLECCION) or []:
            r = leer_recorrido(carpeta, comun.leer_archivo_app(f"{DIR_RECOLECCION}/{carpeta}/manifest.json"))
            if r is not None:
                salida[carpeta] = r
        return salida

    def borrar_recorridos_prueba() -> int:
        """Cierra la app y borra del teléfono los recorridos `validacion-3-3` que el backend no conoce (validate22)."""
        borrados = 0
        for r in recorridos_telefono().values():
            if not borrable(r) or not PATRON_CARPETA.match(r.id):
                continue
            comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
            b = comun.adb("shell", "run-as", comun.PAQUETE, "rm", "-rf", f"{DIR_RECOLECCION}/{r.id}", timeout=60)
            if b.codigo != 0:
                raise comun.Falla(f"run-as rm -rf {DIR_RECOLECCION}/{r.id} falló: {comun.resumir(b.texto, 200)}")
            borrados += 1
            ctx.panel_abierto = False
        return borrados

    def preparar_telefono() -> None:
        """Una vez: `installDebug` (conserva los datos) y `pm grant` de los permisos de Inicio (como validate12)."""
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
        permisos = PERMISOS_INICIO + ([PERMISO_ACTIVIDAD] if ctx.sdk >= 29 else [])
        for permiso in permisos:
            g = comun.adb("shell", "pm", "grant", comun.PAQUETE, permiso, timeout=30)
            comun.exigir_adb_permitido(g, f"conceder {permiso.rsplit('.', 1)[-1]} (pm grant)")
            if g.codigo != 0:
                raise comun.Falla(f"pm grant {permiso} falló: {comun.resumir(g.texto, 200)}")
        ctx.telefono_listo = True

    def preparar_datos() -> None:
        """Una vez: instala, borra los restos (alertas y recorrido) y registra la misma limpieza para el final."""
        if ctx.limpieza_registrada:
            return
        preparar_telefono()
        restos = borrar_restos()
        locales = borrar_recorridos_prueba()
        if restos or locales:
            comun.avisar(f"borrados de una ejecución anterior: {restos} alerta(s) y {locales} recorrido(s) de prueba")
        v.al_limpiar(f"borrar el recorrido de prueba «{VIDEO_PRUEBA}» del teléfono", borrar_recorridos_prueba)
        v.al_limpiar(f"borrar las alertas de prueba ({', '.join(MENSAJES_PRUEBA)})", borrar_restos)
        ctx.limpieza_registrada = True

    def abrir_panel() -> None:
        """Abre la app en frío, inicia sesión por la interfaz (como validate12 C1) y espera el Panel."""
        if ctx.panel_abierto:
            return
        preparar_telefono()
        assert ctx.admin is not None
        comun.abrir_login()
        comun.enviar_credenciales(*ctx.admin)
        saludo = saludo_esperado(ctx.nombre_admin)

        def panel(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            for titulo in ERRORES_LOGIN:
                if comun.primero(nodos, contiene=titulo) is not None:
                    raise comun.Falla(f"Login mostró «{titulo}» en vez del Panel")
            return comun.primero(nodos, dice=saludo)

        comun.esperar_nodo(panel, LIMITE_LOGIN_S, f"«{saludo}» (Panel)")
        ctx.panel_abierto = True

    def hora_telefono() -> str:
        r = comun.adb("shell", "date", "+%Y-%m-%d_%H:%M:%S", timeout=30)
        hora = r.salida.strip().replace("_", " ")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", hora):
            raise comun.Falla(f"adb shell date no dio la hora del teléfono: {comun.resumir(r.texto, 120)}")
        return hora

    def log_desde(hora: str) -> list[LineaLog]:
        return lineas_log(comun.leer_archivo_app(comun.LOG_APP) or "", hora)

    def sincronizo(lineas: list[LineaLog], que: str) -> tuple[int, int, int]:
        """La última «Alertas sincronizadas: …» de [lineas]; sin ninguna → falla."""
        hechas = sincronizaciones(lineas)
        if not hechas:
            raise comun.Falla(
                f"no hay «Alertas sincronizadas: …» (tag {TAG_ALERTAS}) en app.log tras {que}: ¿se pulsó «Guardar / "
                "Sincronizar» con conexión? (mira las líneas Api de files/logs/app.log)"
            )
        return hechas[-1]

    # --- comprobaciones ----------------------------------------------------------------------------------------

    def pruebas() -> comun.Resultado:
        if ctx.gradle is None:
            clases = (
                [c for c in CLASES_C1A if v.incluida("C1a")]
                + [c for c in CLASES_C2A if v.incluida("C2a")]
                + [c for c in CLASES_C3A if v.incluida("C3a")]
            )
            comun.borrar_resultados(clases)
            argumentos = ["testDebugUnitTest"]
            for clase in clases:
                argumentos += ["--tests", f"*.{clase}"]
            ctx.gradle = comun.gradle(*argumentos, timeout=1800)
        return ctx.gradle

    def pruebas_clases(clases: list[str]) -> str:
        r = pruebas()
        partes = []
        for clase in clases:
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
        minimos = ", ".join(str(MINIMO_CASOS[c]) for c in clases)
        return f"{', '.join(partes)} (mínimos {minimos})"

    def local(id_: str, clases: list[str]) -> None:
        """Una comprobación de la JVM; si falla, se anota para no usar el teléfono ni el backend."""

        def envuelta() -> str:
            try:
                return pruebas_clases(clases)
            except Exception:
                ctx.fallo_previo = ctx.fallo_previo or id_
                raise

        v.comprobacion(id_, envuelta)

    def c1b_recoleccion() -> str:
        preparar_datos()
        abrir_panel()
        antes = set(recorridos_telefono())
        hora = hora_telefono()
        comun.esperar_enter(INSTRUCCION_C1B)
        nuevos = [
            r for c, r in sorted(recorridos_telefono().items()) if c not in antes and r.nombre.strip() == VIDEO_PRUEBA
        ]
        if not nuevos:
            raise comun.Falla(
                f"no hay un recorrido nuevo «{VIDEO_PRUEBA}» en {DIR_RECOLECCION} (¿otro nombre, o se descartó en 7.5?)"
            )
        video = nuevos[-1]
        if video.primera is None:
            raise comun.Falla(f"el recorrido {video.id} no tiene fotos: deja que tome al menos una antes de finalizar")
        enviadas, aplicadas, rechazadas = sincronizo(log_desde(hora), "el paso guiado")
        iguales = alertas_de_prueba(lista_admin(MENSAJE_C1), MENSAJE_C1)
        if len(iguales) != 1:
            raise comun.Falla(
                f"GET /v1/admin/alerts?q={MENSAJE_C1} tiene {len(iguales)} alertas «{MENSAJE_C1}» (se esperaba 1; "
                f"app.log: {enviadas} enviadas, {aplicadas} aplicadas, {rechazadas} rechazadas)"
            )
        alerta = iguales[0]
        if alerta.get("activa") is not True:
            raise comun.Falla(f"«{MENSAJE_C1}» llegó con activa = {alerta.get('activa')!r}")
        lat, lng = float(alerta.get("lat")), float(alerta.get("lng"))
        d = distancia_m(lat, lng, *video.primera)
        if d > DISTANCIA_MAXIMA_C1_M:
            raise comun.Falla(
                f"«{MENSAJE_C1}» está a {d:.1f} m de la primera foto de {video.id} (máximo {DISTANCIA_MAXIMA_C1_M:g} m)"
            )
        ctx.c1_creada = True
        return (
            f"«{MENSAJE_C1}» creada en 7.4 durante {video.id} ({video.fotos} fotos) está en GET /v1/admin/alerts, "
            f"activa, a {d:.1f} m de la primera foto (máximo {DISTANCIA_MAXIMA_C1_M:g}); app.log: {enviadas} enviadas, "
            f"{aplicadas} aplicadas, {rechazadas} rechazadas"
        )

    def c2b_sin_rastro() -> str:
        preparar_datos()
        abrir_panel()
        desde = str(foto_publica()["generado_en"])
        hora = hora_telefono()
        comun.esperar_enter(INSTRUCCION_C2B)
        lineas = log_desde(hora)
        errores = errores_log(lineas)
        if errores:
            e = errores[0]
            raise comun.Falla(
                f"app.log tiene {len(errores)} línea(s) de error desde {hora}; la primera: {e.nivel}/{e.tag} "
                f"{comun.resumir(e.texto, 160)}"
            )
        enviadas, aplicadas, rechazadas = sincronizo(lineas, "el paso guiado")
        if rechazadas or aplicadas != enviadas:
            raise comun.Falla(
                f"la sincronización de app.log no salió limpia: {enviadas} enviadas, {aplicadas} aplicadas, "
                f"{rechazadas} rechazadas"
            )
        if alertas_de_prueba(lista_admin(MENSAJE_C2), MENSAJE_C2):
            raise comun.Falla(f"GET /v1/admin/alerts tiene «{MENSAJE_C2}»: se creó en el servidor")
        dif = foto_publica(desde)
        con_mensaje = alertas_de_prueba(dif.get("alertas") or [], MENSAJE_C2)
        if con_mensaje:
            raise comun.Falla(f"GET /v1/alerts?desde={desde} trae «{MENSAJE_C2}» (activa o no): pasó por el servidor")
        ajenas = sorted(str(i) for i in dif.get("eliminadas") or [] if str(i) not in ctx.borradas)
        if ajenas:
            raise comun.Falla(
                f"GET /v1/alerts?desde={desde} trae {len(ajenas)} borrada(s) que no borró el validador: un "
                f"*tombstone* de «{MENSAJE_C2}» (se envió un upsert antes del eliminar) u otro admin borrando a la vez"
            )
        completo = " (la respuesta vino completa: sin diferencias que revisar)" if dif.get("completo") else ""
        return (
            f"crear y borrar «{MENSAJE_C2}» antes de sincronizar: app.log sin errores ({enviadas} enviadas = "
            f"{aplicadas} aplicadas, 0 rechazadas); no está en GET /v1/admin/alerts ni en "
            f"GET /v1/alerts?desde={desde}, sin borradas ajenas{completo}"
        )

    def c3b_lista() -> str:
        preparar_datos()
        alerta_id = str(uuid.uuid4())
        resultado = sincronizar(
            [
                {
                    "op": "upsert",
                    "alerta": {
                        "id": alerta_id,
                        "lat": POSICION_CAMPUS[0],
                        "lng": POSICION_CAMPUS[1],
                        "mensaje": MENSAJE_C3,
                        "tipo": "obra",
                        "prioridad": "normal",
                        "radio_m": 15,
                        "activa": True,
                    },
                }
            ]
        )
        if [r.get("estado") for r in resultado] != ["ok"]:
            raise comun.Falla(f"no se pudo crear «{MENSAJE_C3}» por la API: {resultado}")
        comun.avisar(f"creada {MENSAJE_C3} por la API; se borra al terminar")
        abrir_panel()
        comun.esperar_enter(INSTRUCCION_C3B)

        def buscador(ns: list[comun.Nodo]) -> comun.Nodo | None:
            campos = comun.campos_texto(ns)
            return campos[0] if campos and comun.primero(ns, contiene=BUSCADOR_LISTA) is not None else None

        campo, _ = comun.esperar_nodo(buscador, LIMITE_LISTA_S, f"la Lista de alertas (7.10, «{BUSCADOR_LISTA}»)")
        comun.tocar(campo)
        comun.dormir(0.5)
        comun.escribir_texto(PREFIJO_PRUEBA)
        comun.dormir(1)
        if comun.teclado_visible():
            comun.tecla(comun.TECLA_ATRAS)
            comun.dormir(1)
        esperados = [MENSAJE_C3] + ([MENSAJE_C1] if ctx.c1_creada else [])

        def filas(ns: list[comun.Nodo]) -> comun.Nodo | None:
            mensajes = {mensaje_de_fila(n.descripcion): n for n in ns}
            return mensajes.get(MENSAJE_C3) if all(m in mensajes for m in esperados) else None

        fila, nodos = comun.esperar_nodo(filas, LIMITE_LISTA_S, f"las filas {', '.join(esperados)} en 7.10")
        vistas = sorted(m for m in (mensaje_de_fila(n.descripcion) for n in nodos) if m)
        comun.tocar(fila)

        def editar(ns: list[comun.Nodo]) -> comun.Nodo | None:
            if comun.primero(ns, dice=TITULO_EDITAR) is None:
                return None
            return next((c for c in comun.campos_texto(ns) if c.texto.strip() == MENSAJE_C3), None)

        comun.esperar_nodo(editar, LIMITE_FORMULARIO_S, f"«{TITULO_EDITAR}» con el mensaje {MENSAJE_C3}")
        comun.tecla(comun.TECLA_ATRAS)  # cierra la hoja sin guardar
        comun.dormir(1)
        guardada = alertas_de_prueba(lista_admin(MENSAJE_C3), MENSAJE_C3)
        if len(guardada) != 1 or guardada[0].get("version") != 1:
            raise comun.Falla(f"tras abrir y cerrar sin guardar, «{MENSAJE_C3}» en el servidor es {guardada}")
        return (
            f"7.10 con «{PREFIJO_PRUEBA}» en el buscador muestra {', '.join(vistas)}; tocar «{MENSAJE_C3}» (creada "
            f"solo en el backend) abre «{TITULO_EDITAR}» con su mensaje; cerrada sin guardar, sigue en la versión 1"
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        telefono = ("C1b", "C2b", "C3b")
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = [
                ("P2", p2_dispositivo),
                ("P3", p3_api),
                ("P4", p4_login_admin),
                ("P5", p5_fe12),
                ("P6", p6_be33),
            ]
            if not v.alguna_incluida(*telefono):
                for id_, _ in pasos:
                    v.precondicion_no_evaluada(id_, "C1b, C2b y C3b excluidas con --solo")
            else:
                for i, (id_, fn) in enumerate(pasos):
                    if not v.precondicion(id_, fn):
                        for siguiente, _ in pasos[i + 1 :]:
                            v.precondicion_no_evaluada(siguiente, f"{id_} no se cumple")
                        return

        local("C1a", CLASES_C1A)
        local("C2a", CLASES_C2A)
        local("C3a", CLASES_C3A)

        for id_, fn in (("C1b", c1b_recoleccion), ("C2b", c2b_sin_rastro), ("C3b", c3b_lista)):
            if not dev:
                v.omitir(id_, "solo en dev (necesita el dispositivo y el backend)")
            elif not v.incluida(id_):
                v.comprobacion(id_, fn)  # el Validador la marca omitida (--solo)
            elif ctx.fallo_previo:
                v.omitir(id_, f"no se hace: falló {ctx.fallo_previo} (corrige y repite)")
            else:
                v.comprobacion(id_, fn)
        v.manual("C3c", INSTRUCCION_C3C)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
