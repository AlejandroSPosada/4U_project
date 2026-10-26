"""Validador de FE-2.2 — Panel con datos reales.

Documento: FRONTEND_KOTLIN/docs/validation/validation-2-2.md. Entornos: local (C1a y C2a, pruebas en la JVM; sin
teléfono ni backend) y dev (además C1b y C2b, con un dispositivo físico y la API de dev). En dev: inicia sesión como
admin por la API (P5) y comprueba GET /v1/admin/stats (P6). C1b borra el lugar de prueba `validacion-2-2-lugar` que
haya dejado una ejecución anterior y lo crea con POST /v1/admin/places (lo borra al terminar, también si algo falla),
instala el APK de depuración (conserva los datos), entra al Panel iniciando sesión por la interfaz, lee el «Resumen
rápido» con uiautomator y lo compara con GET /v1/admin/stats leído antes y después. C2b es un paso guiado: la persona
graba en el teléfono un recorrido corto `validacion-2-2` y elige «Guardar y subir después»; el validador compara
«Fotos pendientes de subir» del Panel con las fotos sin subir de los manifests del teléfono (run-as) y, al terminar,
borra del teléfono ese recorrido (solo si no se subió). Nunca imprime contraseñas ni tokens.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import comun

CLASES_C1A = ["RemoteAdminRepositoryTest", "TextosResumenTest"]
CLASES_C2A = ["PendientesPanelTest"]
MINIMO_CASOS = {"RemoteAdminRepositoryTest": 8, "TextosResumenTest": 4, "PendientesPanelTest": 4}
LUGAR_PRUEBA = "validacion-2-2-lugar"  # validation-2-2 §4
CATEGORIA_PRUEBA = "bloque"
POSICION_CAMPUS = (6.2006, -75.5783)  # aprox. EAFIT: si GET /v1/places no trae ningún lugar
DESPLAZAMIENTO_GRADOS = 0.0005  # el lugar de prueba queda ~55 m al norte del primer lugar
VIDEO_PRUEBA = "validacion-2-2"  # nombre del recorrido del paso guiado de C2b
DIR_RECOLECCION = "files/recoleccion"
PATRON_CARPETA = re.compile(r"^[A-Za-z0-9_-]+$")  # solo se borran carpetas con este nombre (sin «/» ni «..»)
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
LIMITE_LOGIN_S = 15  # desde el toque en «Iniciar sesión» hasta ver el Panel
LIMITE_RESUMEN_S = 30  # hasta ver el «Resumen rápido» cargado (con desplazamientos)
MAX_DESPLAZAMIENTOS = 4  # veces que baja el Panel buscando el «Resumen rápido»
LIMITE_PANEL_S = 10  # tras el Enter del paso guiado, hasta ver el Panel
LIMITE_C2_S = 30  # tras el Enter, hasta que el Panel y los manifests coincidan
ERRORES_LOGIN = ("Credenciales inválidas", "Sin conexión", "Algo salió mal")  # banners de Login (§5.5)
ERROR_RESUMEN = "No se pudo cargar el resumen."  # ResumenRapido con errorResumen (§5.5)
SIN_DATO = "—"  # TextosResumen.SIN_DATO
# content-desc de cada TileDato del «Resumen rápido» (§5.5): «<valor> <etiqueta en minúsculas>[. <detalle>]».
ETIQUETAS = {
    "fotos": "fotos en el dataset",
    "lugares": "lugares registrados",
    "alertas": "alertas activas",
    "video": "último video recolectado",
    "pendientes": "fotos pendientes de subir",
}
PATRON_CREADO_EN = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?Z$")  # backend §5.1: UTC con Z

INSTRUCCION_C2B = (
    "En el teléfono, desde el Panel: «Recolector de imágenes» (7.3) → marca el punto de inicio y el rumbo → escribe "
    f"el nombre «{VIDEO_PRUEBA}» → «Confirmar y comenzar» → en la recolección (7.4) elige «Cada 3 s» y deja que tome "
    "al menos 3 fotos → «Finalizar video» → en el Resumen de video (7.5) toca «Guardar y subir después» (NO «Subir y "
    "procesar»): vuelve al Panel. Con el Panel a la vista, pulsa Enter aquí."
)


@dataclass(frozen=True)
class Estadisticas:
    """Lo que importa de `GET /v1/admin/stats` (backend §5.5)."""

    total_fotos: int
    total_lugares: int
    alertas_activas: int
    ultimo_numero: int | None
    ultimo_creado_en: str | None

    def texto(self) -> str:
        video = (
            f"video {self.ultimo_numero} ({self.ultimo_creado_en})" if self.ultimo_numero is not None else "sin video"
        )
        return f"{self.total_fotos} fotos, {self.total_lugares} lugares, {self.alertas_activas} alertas, {video}"


@dataclass(frozen=True)
class Dato:
    """Un dato del «Resumen rápido» leído de su `content-desc`."""

    valor: str
    detalle: str | None


@dataclass(frozen=True)
class Recorrido:
    """Un recorrido de `files/recoleccion/` como lo cuenta la app (`ManifestRecorrido.recorrido`, §5.10)."""

    id: str
    nombre: str
    finalizado: bool
    fotos: int
    pendientes: int  # fotos sin `sync = subida`
    remoto: bool  # tiene `remote_video_id`: el backend ya lo conoce
    subida_estado: str


@dataclass
class Contexto:
    url: str = ""
    token: str = ""
    sdk: int = 0
    admin: tuple[str, str] | None = None
    nombre_admin: str = ""
    lugares_api: list | None = None
    telefono_listo: bool = False
    panel_abierto: bool = False
    gradle: comun.Resultado | None = None
    fallo_previo: str = ""  # la primera comprobación de la JVM que falló (entonces no se usan teléfono ni backend)


# --- piezas puras ----------------------------------------------------------------------------------------------


def saludo_esperado(nombre: str) -> str:
    """Lo que dibuja el Panel (7.2): «Hola, <lo que hay antes del primer espacio del nombre>» o «Hola» sin nombre."""
    primero = nombre.strip().split(" ")[0]
    return f"Hola, {primero}" if primero else "Hola"


def _entero(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0


def leer_estadisticas(cuerpo: object) -> Estadisticas:
    """El cuerpo de `GET /v1/admin/stats` según el contrato (backend §5.5); si no lo cumple → ValueError (motivo)."""
    if not isinstance(cuerpo, dict):
        raise ValueError("el cuerpo no es un objeto JSON")
    for clave in ("total_fotos", "total_lugares", "alertas_activas"):
        if not _entero(cuerpo.get(clave)):
            raise ValueError(f"{clave} = {cuerpo.get(clave)!r} (se espera un entero ≥ 0)")
    if "ultimo_video" not in cuerpo:
        raise ValueError("falta ultimo_video")
    video = cuerpo["ultimo_video"]
    numero = creado_en = None
    if video is not None:
        if not isinstance(video, dict) or not _entero(video.get("numero")):
            raise ValueError(f"ultimo_video = {video!r} (se espera null o {{numero, creado_en}})")
        creado_en = video.get("creado_en")
        if not isinstance(creado_en, str) or not PATRON_CREADO_EN.match(creado_en):
            raise ValueError(f"ultimo_video.creado_en = {creado_en!r} (se espera ISO-8601 en UTC con Z, backend §5.1)")
        numero = video["numero"]
    return Estadisticas(cuerpo["total_fotos"], cuerpo["total_lugares"], cuerpo["alertas_activas"], numero, creado_en)


def leer_dato(descripcion: str) -> tuple[str, Dato] | None:
    """`(clave de ETIQUETAS, Dato)` del `content-desc` de un dato del «Resumen rápido», o None si no es uno."""
    for clave, etiqueta in ETIQUETAS.items():
        m = re.fullmatch(r"(?P<valor>.+?) " + re.escape(etiqueta) + r"(?:\. (?P<detalle>.+))?", descripcion, re.DOTALL)
        if m:
            return clave, Dato(m.group("valor").strip(), m.group("detalle"))
    return None


def datos_resumen(nodos: list[comun.Nodo]) -> dict[str, Dato]:
    """Los datos del «Resumen rápido» visibles en la pantalla (por clave de ETIQUETAS)."""
    datos: dict[str, Dato] = {}
    for n in nodos:
        leido = leer_dato(n.descripcion)
        if leido is not None:
            datos.setdefault(leido[0], leido[1])
    return datos


def valor_numerico(texto: str) -> int | None:
    """«2.842», «2,842» o «2 842» → 2842; «—» → None. Sin cifras → comun.Falla."""
    if texto.strip() == SIN_DATO:
        return None
    cifras = re.sub(r"\D", "", texto)
    if not cifras:
        raise comun.Falla(f"el Panel muestra «{texto}», que no es un número")
    return int(cifras)


def hora_telefono(texto: str) -> datetime:
    """La salida de `adb shell date +%Y-%m-%dT%H:%M:%S%z` (p. ej. `2026-10-26T10:00:00-0500`) → datetime con zona."""
    try:
        return datetime.strptime(texto.strip(), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError as e:
        raise comun.Falla(f"no se pudo leer la hora del teléfono ({comun.resumir(texto, 60)!r})") from e


def fecha_esperada(creado_en: str, ahora: datetime) -> tuple[str, str]:
    """`(expresión regular, descripción)` del detalle que dibuja el Panel para `creado_en` (`TextosResumen.fecha`):
    «Hoy, HH:mm», «Ayer, HH:mm» o «d MMM, HH:mm» en la zona del teléfono (`ahora` trae su desfase). El mes no se
    compara: su abreviatura depende del idioma (`oct` u `oct.`)."""
    m = PATRON_CREADO_EN.match(creado_en)
    if not m:
        raise comun.Falla(f"ultimo_video.creado_en = {creado_en!r} no es UTC con Z (backend §5.1)")
    instante = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
    local = instante.astimezone(ahora.tzinfo)
    hora = local.strftime("%H:%M")
    if local.date() == ahora.date():
        return re.escape(f"Hoy, {hora}"), f"Hoy, {hora}"
    if local.date() == ahora.date() - timedelta(days=1):
        return re.escape(f"Ayer, {hora}"), f"Ayer, {hora}"
    return rf"{local.day} \S+, {re.escape(hora)}", f"{local.day} <mes>, {hora}"


def diferencias(datos: dict[str, Dato], s: Estadisticas, ahora: datetime) -> list[str]:
    """Lo que no coincide entre los cuatro datos del backend del Panel y `GET /v1/admin/stats` (vacío = todo igual)."""
    malas = []
    for clave, esperado in (("fotos", s.total_fotos), ("lugares", s.total_lugares), ("alertas", s.alertas_activas)):
        dato = datos[clave]
        if valor_numerico(dato.valor) != esperado:
            malas.append(f"{ETIQUETAS[clave]}: Panel «{dato.valor}», API {esperado}")
    video = datos["video"]
    if s.ultimo_numero is None:
        if valor_numerico(video.valor) is not None or video.detalle is not None:
            malas.append(
                f"último video: Panel «{video.valor}» «{video.detalle}», API ultimo_video = null (se espera «—»)"
            )
    else:
        assert s.ultimo_creado_en is not None
        patron, descripcion = fecha_esperada(s.ultimo_creado_en, ahora)
        if valor_numerico(video.valor) != s.ultimo_numero:
            malas.append(f"último video: Panel «{video.valor}», API numero {s.ultimo_numero}")
        if video.detalle is None or not re.fullmatch(patron, video.detalle):
            malas.append(
                f"fecha del último video: Panel «{video.detalle}», se espera «{descripcion}» "
                f"(creado_en {s.ultimo_creado_en}, teléfono {ahora.isoformat()})"
            )
    return malas


def _numero(valor: object) -> bool:
    if isinstance(valor, bool):
        return False
    if isinstance(valor, int | float):
        return True
    try:
        float(str(valor))
    except ValueError:
        return False
    return True


def leer_recorrido(carpeta: str, texto: str | None) -> Recorrido | None:
    """Un `manifest.json` de `files/recoleccion/<carpeta>/` como lo lee `AlmacenRecorridos.listar()` (§5.10), o None
    si la app lo saltaría (no existe, JSON roto, no es un objeto, una foto sin `id`, `file`, `lat` o `lng`)."""
    if not texto:
        return None
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        return None
    if not isinstance(datos, dict):
        return None
    fotos = datos.get("photos") if isinstance(datos.get("photos"), list) else []
    pendientes = 0
    for p in fotos:
        if not isinstance(p, dict) or p.get("id") is None or p.get("file") is None:
            return None
        if not _numero(p.get("lat")) or not _numero(p.get("lng")):
            return None
        if p.get("sync") != "subida":
            pendientes += 1
    nombre = datos.get("name") if isinstance(datos.get("name"), str) and datos["name"].strip() else carpeta
    return Recorrido(
        id=carpeta,
        nombre=str(nombre),
        finalizado=datos.get("estado") == "finalizado",
        fotos=len(fotos),
        pendientes=pendientes,
        remoto=bool(datos.get("remote_video_id")),
        subida_estado=str(datos.get("subida_estado") or "sin_subir"),
    )


def pendientes_de(recorridos: dict[str, Recorrido]) -> int:
    """«Fotos pendientes» con la regla de la app (`fotosPendientesDe`): fotos sin subir de los `finalizado`."""
    return sum(r.pendientes for r in recorridos.values() if r.finalizado)


def describir(recorridos: dict[str, Recorrido]) -> str:
    finalizados = [r for r in recorridos.values() if r.finalizado]
    return (
        f"{len(recorridos)} recorridos en el teléfono, {len(finalizados)} finalizados con "
        f"{pendientes_de(recorridos)} fotos sin subir"
    )


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-2.2",
        validacion="validation-2-2",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C2a", "C2b"],
        grupos={"C1": ["C1a", "C1b"], "C2": ["C2a", "C2b"]},
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

    def p3_fe21() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-2.1"):
            raise comun.Bloqueo("FE-2.1 no está «Hecho» en PLAN.md §3 (cola local de subida)")
        return "FE-2.1 Hecho"

    def p4_api() -> str:
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

    def p5_login_admin() -> str:
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

    def p6_be23() -> str:
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-2.3"):
            raise comun.Bloqueo("BE-2.3 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (GET /v1/admin/stats)")
        s = estadisticas(comun.Bloqueo)
        return f"BE-2.3 Hecho; GET /v1/admin/stats -> 200 ({s.texto()})"

    # --- API (nunca imprime el token) -------------------------------------------------------------------------

    def estadisticas(error: type[Exception] = comun.Falla) -> Estadisticas:
        try:
            r = comun.http_get(f"{ctx.url}/admin/stats", token=ctx.token)
        except comun.ErrorRed as e:
            raise error(f"BE-2.3: GET /v1/admin/stats sin respuesta ({e})") from e
        if r.estado != 200:
            raise error(f"BE-2.3: GET /v1/admin/stats respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        try:
            return leer_estadisticas(r.json())
        except ValueError as e:
            raise error(f"BE-2.3: GET /v1/admin/stats no cumple el contrato (backend §5.5): {e}") from e

    def lugares_publicos() -> list:
        r = comun.http_get(f"{ctx.url}/places")
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise comun.Falla(f"GET /v1/places respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return [i for i in cuerpo["items"] if isinstance(i, dict)]

    def borrar_lugar(lugar_id: str) -> None:
        r = comun.http_delete(f"{ctx.url}/admin/places/{quote(lugar_id)}", token=ctx.token)
        if r.estado != 204:
            raise comun.Falla(f"DELETE /v1/admin/places/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}")

    def borrar_restos_lugar() -> int:
        """Borra el lugar de prueba que haya dejado una ejecución anterior (solo el de nombre exacto)."""
        r = comun.http_get(f"{ctx.url}/admin/places?q={quote('validacion-2-2')}", token=ctx.token)
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict):
            raise comun.Falla(f"GET /v1/admin/places?q= respondió {r.estado} {comun.codigo_error(r) or ''}")
        restos = [
            str(i.get("id"))
            for i in cuerpo.get("items") or []
            if isinstance(i, dict) and str(i.get("nombre") or "").strip().casefold() == LUGAR_PRUEBA
        ]
        for lugar_id in restos:
            borrar_lugar(lugar_id)
        return len(restos)

    def crear_lugar_prueba() -> None:
        primero = (lugares_publicos() or [None])[0]
        if isinstance(primero, dict) and isinstance(primero.get("lat"), int | float):
            lat, lng = float(primero["lat"]) + DESPLAZAMIENTO_GRADOS, float(primero["lng"])
        else:
            lat, lng = POSICION_CAMPUS
        cuerpo = {
            "nombre": LUGAR_PRUEBA,
            "categoria": CATEGORIA_PRUEBA,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "alias": [],
            "descripcion": "Lugar de prueba de validate22.py (FE-2.2): se borra al terminar.",
        }
        r = comun.http_post_json(f"{ctx.url}/admin/places", cuerpo, token=ctx.token)
        datos = r.json()
        if r.estado != 201 or not isinstance(datos, dict) or not datos.get("id"):
            raise comun.Falla(
                f"POST /v1/admin/places ({LUGAR_PRUEBA}) respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        lugar_id = str(datos["id"])
        v.al_limpiar(f"borrar el lugar {LUGAR_PRUEBA}", lambda: borrar_lugar(lugar_id))
        comun.avisar(
            f"creado {LUGAR_PRUEBA} ({CATEGORIA_PRUEBA}, {cuerpo['lat']}, {cuerpo['lng']}); se borra al terminar"
        )

    # --- teléfono ----------------------------------------------------------------------------------------------

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

    def abrir_panel() -> None:
        """Una vez: abre la app en frío, inicia sesión por la interfaz (como validate12 C1) y espera el Panel."""
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

    def leer_resumen(limite_s: float = LIMITE_RESUMEN_S) -> dict[str, Dato]:
        """Los cinco datos del «Resumen rápido» ya cargados; baja el Panel hasta verlos (como mucho
        MAX_DESPLAZAMIENTOS veces). «No se pudo cargar el resumen.» → Falla."""
        fin = comun.reloj() + limite_s
        desplazamientos = 0
        while True:
            nodos = comun.volcar_pantalla()
            if comun.primero(nodos, contiene=ERROR_RESUMEN) is not None:
                raise comun.Falla(
                    f"el Panel dice «{ERROR_RESUMEN}» (GET /v1/admin/stats desde el teléfono: mira las líneas Api de "
                    "files/logs/app.log)"
                )
            datos = datos_resumen(nodos)
            completos = len(datos) == len(ETIQUETAS)
            if completos and datos["fotos"].valor != SIN_DATO and datos["pendientes"].valor != SIN_DATO:
                return datos
            if not completos and desplazamientos < MAX_DESPLAZAMIENTOS:
                comun.desplazar_hacia_abajo()
                desplazamientos += 1
                comun.dormir(0.5)
                continue
            if comun.reloj() >= fin:
                vistos = ", ".join(f"«{d.valor} {ETIQUETAS[k]}»" for k, d in datos.items()) or "ninguno"
                raise comun.Falla(
                    f"en {limite_s:.0f} s no se vio el «Resumen rápido» cargado (datos visibles: {vistos}); en "
                    f"pantalla: {comun.textos_visibles(nodos)}"
                )
            comun.dormir(1)

    def leer_hora_telefono() -> datetime:
        r = comun.adb("shell", "date", "+%Y-%m-%dT%H:%M:%S%z", timeout=30)
        return hora_telefono(r.salida)

    def recorridos_telefono() -> dict[str, Recorrido]:
        """Los recorridos legibles de `files/recoleccion/` (run-as), como los lista la app."""
        recorridos: dict[str, Recorrido] = {}
        for carpeta in comun.listar_archivos_app(DIR_RECOLECCION) or []:
            r = leer_recorrido(carpeta, comun.leer_archivo_app(f"{DIR_RECOLECCION}/{carpeta}/manifest.json"))
            if r is not None:
                recorridos[carpeta] = r
        return recorridos

    def borrar_recorrido(carpeta: str) -> None:
        """Cierra la app y borra `files/recoleccion/<carpeta>` del teléfono (lo mismo que «Descartar video» de 7.5)."""
        if not PATRON_CARPETA.match(carpeta):
            raise comun.Falla(f"nombre de carpeta inesperado: {carpeta!r} (no se borra)")
        comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
        r = comun.adb("shell", "run-as", comun.PAQUETE, "rm", "-rf", f"{DIR_RECOLECCION}/{carpeta}", timeout=60)
        if r.codigo != 0:
            raise comun.Falla(f"run-as rm -rf {DIR_RECOLECCION}/{carpeta} falló: {comun.resumir(r.texto, 200)}")

    def borrable(r: Recorrido) -> bool:
        """Un recorrido de prueba que se puede borrar del teléfono: se llama VIDEO_PRUEBA y el backend no lo conoce."""
        return r.nombre.strip() == VIDEO_PRUEBA and not r.remoto and r.subida_estado == "sin_subir"

    # --- comprobaciones ----------------------------------------------------------------------------------------

    def pruebas() -> comun.Resultado:
        if ctx.gradle is None:
            clases = [c for c in CLASES_C1A if v.incluida("C1a")] + [c for c in CLASES_C2A if v.incluida("C2a")]
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

    def c1b_backend() -> str:
        restos = borrar_restos_lugar()
        if restos:
            comun.avisar(f"borrado {restos} resto(s) de {LUGAR_PRUEBA} de una ejecución anterior")
        crear_lugar_prueba()
        antes = estadisticas()
        abrir_panel()  # entra en frío: el Panel carga GET /v1/admin/stats al abrirse
        datos = leer_resumen()
        ahora = leer_hora_telefono()
        despues = estadisticas()
        if antes != despues:
            raise comun.Falla(
                f"GET /v1/admin/stats cambió mientras se leía el Panel (antes: {antes.texto()}; después: "
                f"{despues.texto()}): ¿alguien sube videos o cambia lugares en dev? Repite"
            )
        if antes.total_lugares < 1:
            raise comun.Falla(f"total_lugares = 0 aunque se creó {LUGAR_PRUEBA}")
        malas = diferencias(datos, antes, ahora)
        if malas:
            raise comun.Falla("el Panel no coincide con GET /v1/admin/stats: " + "; ".join(malas))
        video = datos["video"]
        ultimo = (
            f"último video {video.valor} · «{video.detalle}»" if antes.ultimo_numero is not None else "sin video («—»)"
        )
        return (
            f"Panel = GET /v1/admin/stats (igual antes y después): {datos['fotos'].valor} fotos, "
            f"{datos['lugares'].valor} lugares (incluye {LUGAR_PRUEBA}), {datos['alertas'].valor} alertas, {ultimo}"
        )

    def c2b_pendientes() -> str:
        preparar_telefono()
        antes = recorridos_telefono()
        for carpeta, r in sorted(antes.items()):
            if borrable(r):
                borrar_recorrido(carpeta)  # resto de una ejecución anterior (cierra la app)
                ctx.panel_abierto = False
                comun.avisar(f"borrado del teléfono {carpeta} «{VIDEO_PRUEBA}», resto de una ejecución anterior")
        antes = recorridos_telefono()
        comun.avisar(f"antes del paso guiado: {describir(antes)}")
        abrir_panel()
        comun.esperar_enter(INSTRUCCION_C2B)
        despues = recorridos_telefono()
        nuevos = {c: r for c, r in despues.items() if c not in antes and r.nombre.strip() == VIDEO_PRUEBA}
        for carpeta, r in sorted(nuevos.items()):
            if borrable(r):
                v.al_limpiar(f"borrar del teléfono {carpeta} «{VIDEO_PRUEBA}»", lambda c=carpeta: borrar_recorrido(c))
            else:
                comun.avisar(
                    f"{carpeta} «{VIDEO_PRUEBA}» ya no es local (subida {r.subida_estado}): no se borra; si se subió, "
                    "hay que borrarlo del backend (validation-2-2 §4)"
                )
        if not nuevos:
            otros = [f"{c} «{r.nombre}»" for c, r in despues.items() if c not in antes]
            raise comun.Falla(
                f"no hay un recorrido nuevo «{VIDEO_PRUEBA}» en el teléfono (nuevos: {', '.join(otros) or 'ninguno'})"
            )
        listos = [r for r in nuevos.values() if r.finalizado and r.pendientes >= 1]
        if not listos:
            r = next(iter(nuevos.values()))
            raise comun.Falla(
                f"{r.id} «{VIDEO_PRUEBA}» está {'finalizado' if r.finalizado else 'en_curso'} con {r.pendientes} fotos "
                "sin subir: hacen falta ≥ 1 foto, «Finalizar video» y «Guardar y subir después»"
            )
        comun.esperar_nodo(
            lambda ns: (
                comun.primero(ns, dice="Resumen rápido")
                or comun.primero(ns, dice=saludo_esperado(ctx.nombre_admin))
                or next((n for n in ns if leer_dato(n.descripcion)), None)
            ),
            LIMITE_PANEL_S,
            "el Panel (¿se pulsó Enter con el Panel a la vista?)",
        )
        fin = comun.reloj() + LIMITE_C2_S
        while True:
            cuenta_antes = pendientes_de(recorridos_telefono())
            datos = leer_resumen(max(5.0, fin - comun.reloj()))
            cuenta_despues = pendientes_de(recorridos_telefono())
            panel = valor_numerico(datos["pendientes"].valor)
            if cuenta_antes == cuenta_despues == panel:
                break
            if comun.reloj() >= fin:
                raise comun.Falla(
                    f"«Fotos pendientes de subir» del Panel = «{datos['pendientes'].valor}», pero los manifests del "
                    f"teléfono dan {cuenta_antes} y {cuenta_despues} (antes y después de leer el Panel)"
                )
            comun.dormir(2)
        prueba = listos[0]
        return (
            f"«Fotos pendientes de subir» = {panel} = fotos sin subir de los recorridos finalizados del teléfono "
            f"(incluye {prueba.id} «{VIDEO_PRUEBA}», {prueba.pendientes} fotos; "
            f"antes de grabar: {pendientes_de(antes)})"
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = [
                ("P2", p2_dispositivo),
                ("P3", p3_fe21),
                ("P4", p4_api),
                ("P5", p5_login_admin),
                ("P6", p6_be23),
            ]
            if not v.alguna_incluida("C1b", "C2b"):
                for id_, _ in pasos:
                    v.precondicion_no_evaluada(id_, "C1b y C2b excluidas con --solo")
            else:
                for i, (id_, fn) in enumerate(pasos):
                    if not v.precondicion(id_, fn):
                        for siguiente, _ in pasos[i + 1 :]:
                            v.precondicion_no_evaluada(siguiente, f"{id_} no se cumple")
                        return

        local("C1a", CLASES_C1A)
        local("C2a", CLASES_C2A)
        for id_, fn in (("C1b", c1b_backend), ("C2b", c2b_pendientes)):
            if not dev:
                v.omitir(id_, "solo en dev (necesita el dispositivo y el backend)")
            elif ctx.fallo_previo and v.incluida(id_):
                v.omitir(id_, f"no se hace: falló {ctx.fallo_previo} (corrige y repite)")
            else:
                v.comprobacion(id_, fn)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
