"""Validador de FE-3.1 — Lugares públicos y entrada al mapa.

Documento: FRONTEND_KOTLIN/docs/validation/validation-3-1.md. Entornos: local (C1a y C2a, pruebas en la JVM, y C2b,
comprobación estática del código; sin teléfono ni backend) y dev (además C1b, con un dispositivo físico y la API de
dev). En dev: inicia sesión como admin (POST /v1/auth/login), borra el lugar de prueba `validacion-3-1-lugar` que haya
dejado una ejecución anterior y lo crea con POST /v1/admin/places (lo borra al terminar, también si algo falla),
instala el APK de depuración (conserva los datos), abre la app y, tras un paso guiado (la persona abre Selección de
destino por voz o con TalkBack y pulsa Enter), lee la lista con uiautomator desplazándola hasta el final y la compara
con GET /v1/places. C2 (abrir el mapa desde Inicio por voz y con TalkBack, y volver con Atrás) es manual (C2c). Nunca
imprime contraseñas ni tokens.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import comun

CLASES_C1A = ["RemoteLugaresRepositoryTest"]
CLASES_C2A = ["ComandoParserTest", "ObservadorPrimerPlanoTest"]
MINIMO_CASOS = {"RemoteLugaresRepositoryTest": 6, "ComandoParserTest": 4, "ObservadorPrimerPlanoTest": 4}
LUGAR_PRUEBA = "validacion-3-1-lugar"  # validation-3-1 §4
CATEGORIA_PRUEBA = "bloque"
POSICION_CAMPUS = (6.2006, -75.5783)  # aprox. EAFIT: si GET /v1/places no trae ningún lugar
DESPLAZAMIENTO_GRADOS = 0.0002  # el lugar de prueba queda ~22 m al norte del primer lugar
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
LIMITE_INICIO_S = 30  # tras abrir la app, hasta ver Inicio («Acceso administrador»)
LIMITE_DESTINO_S = 20  # tras el Enter, hasta ver Selección de destino con filas
MAX_DESPLAZAMIENTOS = 40
INTENTOS_SIN_FILAS = 3  # desplazamientos sin ver ninguna fila antes de fallar
SIN_NOVEDAD_PARA_TERMINAR = 2  # desplazamientos seguidos sin filas nuevas = final de la lista
TITULO_DESTINO = "¿A dónde quieres ir?"  # EncabezadoPregunta (ARCHITECTURE §5.5)
FIN_FILA = ". Toca para elegir este destino."  # contentDescription de FilaLugar (§5.5)
ETIQUETAS_CATEGORIA = (  # CategoriaLugar.etiqueta (§5.6)
    "Biblioteca",
    "Cafetería",
    "Baño",
    "Bloque",
    "Auditorio",
    "Deportes",
    "Administración",
    "Entrada",
)
ERROR_CARGA = "No se pudo cargar la lista de lugares."  # estado de error de Destino (§5.5)
SIN_RESULTADOS = "No hay lugares con estos filtros"
DIR_KOTLIN = comun.PROYECTO / "app" / "src" / "main" / "java" / "com" / "example" / "myapplication"
MAIN_ACTIVITY = DIR_KOTLIN / "MainActivity.kt"
INICIO_SCREEN = DIR_KOTLIN / "ui" / "inicio" / "InicioScreen.kt"
INICIO_VIEWMODEL = DIR_KOTLIN / "ui" / "inicio" / "InicioViewModel.kt"
MAPA_PUBLICO = DIR_KOTLIN / "map" / "MapaPublicoScreen.kt"

INSTRUCCION_C1B = (
    "En el teléfono, en Inicio, abre Selección de destino: di «dos» (o, con TalkBack, la acción «Ir a un lugar» del "
    "botón principal y después desactiva TalkBack: con TalkBack activo adb puede no desplazar la lista). Espera a "
    f"ver «{TITULO_DESTINO}» y la lista de lugares, no toques el buscador ni los filtros, y pulsa Enter aquí."
)


@dataclass
class Contexto:
    url: str = ""
    token: str = ""
    sdk: int = 0
    lugares_api: list | None = None  # items de GET /v1/places en P5
    telefono_listo: bool = False
    gradle: comun.Resultado | None = None


# --- piezas puras ----------------------------------------------------------------------------------------------


def normalizar_nombre(texto: str) -> str:
    """Como `normalizar_nombre` del backend (backend §4.9): NFKD sin marcas combinantes, `casefold` y espacios
    reducidos a uno, sin espacios alrededor."""
    sin_marcas = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_marcas.casefold().split())


def nombre_de_fila(descripcion: str) -> str | None:
    """El nombre del lugar de una fila de la lista de Destino, desde su `content-desc` (`FilaLugar`, ARCHITECTURE §5.5):
    «{nombre}, {categoría}[, a {N} metros]. Toca para elegir este destino.». None si no es una fila."""
    if not descripcion.endswith(FIN_FILA):
        return None
    resto = re.sub(r", a \d+ metros$", "", descripcion[: -len(FIN_FILA)])
    for etiqueta in ETIQUETAS_CATEGORIA:
        sufijo = f", {etiqueta}"
        if resto.endswith(sufijo) and len(resto) > len(sufijo):
            return resto[: -len(sufijo)]
    return None


def filas_visibles(nodos: list[comun.Nodo]) -> list[str]:
    """Nombres de las filas de lugar visibles, de arriba abajo."""
    filas = [n for n in nodos if nombre_de_fila(n.descripcion) is not None]
    filas.sort(key=lambda n: (n.limites[1], n.limites[0]))
    return [nombre_de_fila(n.descripcion) or "" for n in filas]


def bloque_ruta(texto: str, ruta: str) -> str | None:
    """El texto de `composable("<ruta>")` hasta el siguiente `composable(` (o el final), o None si no está."""
    m = re.search(r'composable\(\s*"' + re.escape(ruta) + r'"', texto)
    if not m:
        return None
    siguiente = texto.find("composable(", m.end())
    return texto[m.start() : siguiente if siguiente >= 0 else len(texto)]


def comprobar_entrada_mapa(main: str, inicio_screen: str, inicio_vm: str, mapa: str) -> str:
    """C2b: Inicio abre la ruta `mapa` por la voz «mapa» y por la acción de TalkBack «Ver mapa», la ruta compone
    `MapaPublicoScreen` y el mapa pasa a su `PdrTracker` el ciclo de vida de su pantalla (ARCHITECTURE §4.5, §5.5,
    §5.8; ADR-FE-22). Si no → Falla."""
    inicio = bloque_ruta(main, "inicio")
    if inicio is None:
        raise comun.Falla("AppNav no registra la ruta inicio")
    m = re.search(r"onVerMapa\s*=\s*\{([^}]*)\}", inicio)
    if not m or 'navigate("mapa")' not in m.group(1):
        raise comun.Falla('la ruta inicio no pasa a InicioScreen un onVerMapa que navegue a "mapa"')
    ruta_mapa = bloque_ruta(main, "mapa")
    if ruta_mapa is None or "MapaPublicoScreen(" not in ruta_mapa:
        raise comun.Falla("AppNav no registra la ruta mapa con MapaPublicoScreen")
    if not re.search(r'CustomAccessibilityAction\(\s*"Ver mapa"\s*\)\s*\{\s*onVerMapa\(\)', inicio_screen):
        raise comun.Falla("el orbe de Inicio no tiene la acción de TalkBack «Ver mapa» que llama a onVerMapa")
    if not re.search(r"InicioEvento\.VerMapa\s*->\s*onVerMapa\(\)", inicio_screen):
        raise comun.Falla("InicioScreen no lleva el evento InicioEvento.VerMapa a onVerMapa")
    if not re.search(r"Comando\.VER_MAPA\s*->\s*navegar\(\s*InicioEvento\.VerMapa\s*\)", inicio_vm):
        raise comun.Falla("InicioViewModel no navega con el comando de voz «mapa» (Comando.VER_MAPA)")
    if not re.search(r"PdrTracker\([^)]*cicloDeVida\s*=", mapa) or "LocalLifecycleOwner.current.lifecycle" not in mapa:
        raise comun.Falla("MapaPublicoScreen no pasa a PdrTracker el ciclo de vida de su pantalla (ADR-FE-22)")
    return (
        'ruta inicio: onVerMapa → navigate("mapa"); voz «mapa» (Comando.VER_MAPA) y acción de TalkBack «Ver mapa» → '
        "InicioEvento.VerMapa; ruta mapa → MapaPublicoScreen con el ciclo de vida de su pantalla"
    )


def instruccion_c2(contexto: str) -> str:
    prefijo = f"[{contexto}] " if contexto else ""
    return (
        f"{prefijo}Con la app abierta desde el lanzador (Inicio), di «mapa»: se abre el mapa público; pulsa Atrás: "
        "vuelve a Inicio. Activa TalkBack; en el botón principal de Inicio abre las acciones (menú de TalkBack → "
        "Acciones) y elige «Ver mapa»: se abre el mapa; toca un punto del mapa como inicio y pulsa ▶ (la posición "
        "empieza en el punto tocado); Atrás vuelve a Inicio. Ya en Inicio, `dumpsys sensorservice` sin conexiones "
        "activas de la app y las líneas Pdr de app.log. Evidencia: video corto con audio (grabadora de pantalla), "
        "c2-sensores-inicio.txt y c2-app-log.txt en docs/validation/evidencia/fe-3-1/ (el video, citado en el PR si "
        "muestra algo privado); procedimiento en validation-3-1 §3"
    )


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-3.1",
        validacion="validation-3-1",
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

    def p3_fe11() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-1.1"):
            raise comun.Bloqueo("FE-1.1 no está «Hecho» en PLAN.md §3")
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
        return f"FE-1.1 Hecho; ApiConfig = {origen}; GET /v1/health -> 200"

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

    def p5_be31() -> str:
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.1"):
            raise comun.Bloqueo("BE-3.1 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3")
        ctx.lugares_api = lugares_publicos()
        return f"BE-3.1 Hecho; GET /v1/places -> 200 ({len(ctx.lugares_api)} lugares)"

    # --- API de lugares (nunca imprime el token) ---------------------------------------------------------------

    def lugares_publicos() -> list:
        try:
            r = comun.http_get(f"{ctx.url}/places")
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"BE-3.1: GET /v1/places sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise comun.Bloqueo(f"BE-3.1: GET /v1/places respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        return [i for i in cuerpo["items"] if isinstance(i, dict)]

    def borrar_lugar(lugar_id: str) -> None:
        r = comun.http_delete(f"{ctx.url}/admin/places/{quote(lugar_id)}", token=ctx.token)
        if r.estado != 204:
            raise comun.Falla(f"DELETE /v1/admin/places/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}")

    def borrar_restos() -> int:
        """Borra el lugar de prueba que haya dejado una ejecución anterior (solo el de nombre exacto, sin distinguir
        mayúsculas ni tildes como el backend)."""
        r = comun.http_get(f"{ctx.url}/admin/places?q={quote('validacion-3-1')}", token=ctx.token)
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict):
            raise comun.Falla(f"GET /v1/admin/places?q= respondió {r.estado} {comun.codigo_error(r) or ''}")
        restos = [
            str(i.get("id"))
            for i in cuerpo.get("items") or []
            if isinstance(i, dict) and normalizar_nombre(str(i.get("nombre") or "")) == normalizar_nombre(LUGAR_PRUEBA)
        ]
        for lugar_id in restos:
            borrar_lugar(lugar_id)
        return len(restos)

    def crear_lugar_prueba() -> tuple[float, float]:
        primero = (ctx.lugares_api or [None])[0]
        if isinstance(primero, dict) and isinstance(primero.get("lat"), int | float):
            lat = float(primero["lat"]) + DESPLAZAMIENTO_GRADOS
            lng = float(primero["lng"])
        else:
            lat, lng = POSICION_CAMPUS
        cuerpo = {
            "nombre": LUGAR_PRUEBA,
            "categoria": CATEGORIA_PRUEBA,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "alias": [],
            "descripcion": "Lugar de prueba de validate31.py (FE-3.1): se borra al terminar.",
        }
        r = comun.http_post_json(f"{ctx.url}/admin/places", cuerpo, token=ctx.token)
        datos = r.json()
        if r.estado != 201 or not isinstance(datos, dict) or not datos.get("id"):
            raise comun.Falla(
                f"POST /v1/admin/places ({LUGAR_PRUEBA}) respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        lugar_id = str(datos["id"])
        v.al_limpiar(f"borrar el lugar {LUGAR_PRUEBA}", lambda: borrar_lugar(lugar_id))
        return cuerpo["lat"], cuerpo["lng"]

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

    def esperar_destino() -> list[comun.Nodo]:
        """Tras el Enter: hasta `LIMITE_DESTINO_S` a que se vea Selección de destino con alguna fila. Con el título pero
        sin filas al final del plazo, sigue (las filas pueden estar más abajo). Error de carga o lista vacía → Falla."""
        fin = comun.reloj() + LIMITE_DESTINO_S
        titulo_visto = False
        while True:
            nodos = comun.volcar_pantalla()
            if comun.primero(nodos, contiene=ERROR_CARGA) is not None:
                raise comun.Falla(
                    "Selección de destino mostró «Sin conexión: No se pudo cargar la lista de lugares.» "
                    "(GET /v1/places desde el teléfono; mira las líneas Api de files/logs/app.log)"
                )
            if comun.primero(nodos, contiene=SIN_RESULTADOS) is not None:
                raise comun.Falla(f"Selección de destino dice «{SIN_RESULTADOS}»: ¿se tocó el buscador o un filtro?")
            titulo_visto = titulo_visto or comun.primero(nodos, dice=TITULO_DESTINO) is not None
            if titulo_visto and filas_visibles(nodos):
                return nodos
            if comun.reloj() >= fin:
                if titulo_visto:
                    return nodos
                raise comun.Falla(
                    f"en {LIMITE_DESTINO_S} s no se vio Selección de destino («{TITULO_DESTINO}»); en pantalla: "
                    f"{comun.textos_visibles(nodos)}"
                )
            comun.dormir(1)

    def leer_lista(nodos: list[comun.Nodo]) -> tuple[list[str], int]:
        """Nombres de todas las filas de la lista, desplazándola hacia abajo hasta que dos desplazamientos seguidos no
        traen filas nuevas. Devuelve los nombres (en orden de aparición) y cuántas veces desplazó."""
        vistos: list[str] = []
        sin_novedad = 0
        desplazamientos = 0
        while True:
            nuevos = [n for n in filas_visibles(nodos) if n not in vistos]
            vistos += nuevos
            if nuevos:
                sin_novedad = 0
            elif vistos:
                sin_novedad += 1
            elif desplazamientos >= INTENTOS_SIN_FILAS:
                raise comun.Falla(
                    f"Selección de destino no muestra ninguna fila de lugar tras {desplazamientos} desplazamientos; en "
                    f"pantalla: {comun.textos_visibles(nodos)}"
                )
            if sin_novedad >= SIN_NOVEDAD_PARA_TERMINAR:
                return vistos, desplazamientos
            if desplazamientos >= MAX_DESPLAZAMIENTOS:
                raise comun.Falla(
                    f"la lista no terminó tras {MAX_DESPLAZAMIENTOS} desplazamientos ({len(vistos)} filas leídas)"
                )
            comun.desplazar_hacia_abajo()
            desplazamientos += 1
            comun.dormir(0.5)
            nodos = comun.volcar_pantalla()

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

    def c1b_lista() -> str:
        preparar_telefono()
        restos = borrar_restos()
        if restos:
            comun.avisar(f"borrado {restos} resto(s) de {LUGAR_PRUEBA} de una ejecución anterior")
        lat, lng = crear_lugar_prueba()
        comun.avisar(f"creado {LUGAR_PRUEBA} ({CATEGORIA_PRUEBA}, {lat}, {lng}); se borra al terminar")
        comun.abrir_app()
        comun.esperar_nodo(
            lambda ns: comun.primero(ns, dice="Acceso administrador"),
            LIMITE_INICIO_S,
            "Inicio («Acceso administrador»)",
        )
        comun.esperar_enter(INSTRUCCION_C1B)
        en_app, desplazamientos = leer_lista(esperar_destino())
        en_api = [str(i.get("nombre") or "") for i in lugares_publicos()]
        faltan = [n for n in en_api if n not in en_app]
        sobran = [n for n in en_app if n not in en_api]
        if faltan or sobran:
            partes = []
            if faltan:
                partes.append(f"faltan {len(faltan)} ({', '.join(f'«{n}»' for n in faltan[:5])})")
            if sobran:
                partes.append(f"sobran {len(sobran)} ({', '.join(f'«{n}»' for n in sobran[:5])})")
            raise comun.Falla(
                f"la lista de Destino ({len(en_app)}) no es la de GET /v1/places ({len(en_api)}): {'; '.join(partes)}"
            )
        if LUGAR_PRUEBA not in en_app:
            raise comun.Falla(f"la lista no incluye {LUGAR_PRUEBA}")
        return (
            f"{len(en_app)} lugares en Selección de destino = GET /v1/places (incluye «{LUGAR_PRUEBA}»; "
            f"{desplazamientos} desplazamientos)"
        )

    def leer(ruta: Path) -> str:
        try:
            return ruta.read_text(encoding="utf-8")
        except OSError as e:
            raise comun.Falla(f"no se pudo leer {ruta.name}: {e}") from e

    def c2b_entrada_mapa() -> str:
        return comprobar_entrada_mapa(
            leer(MAIN_ACTIVITY), leer(INICIO_SCREEN), leer(INICIO_VIEWMODEL), leer(MAPA_PUBLICO)
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = [("P2", p2_dispositivo), ("P3", p3_fe11), ("P4", p4_login_admin), ("P5", p5_be31)]
            if not v.incluida("C1b"):
                for id_, _ in pasos:
                    v.precondicion_no_evaluada(id_, "C1b excluida con --solo")
            else:
                for i, (id_, fn) in enumerate(pasos):
                    if not v.precondicion(id_, fn):
                        for siguiente, _ in pasos[i + 1 :]:
                            v.precondicion_no_evaluada(siguiente, f"{id_} no se cumple")
                        return

        v.comprobacion("C1a", lambda: pruebas_clases(CLASES_C1A))
        if dev:
            v.comprobacion("C1b", c1b_lista)
        else:
            v.omitir("C1b", "solo en dev (necesita el dispositivo y el backend)")
        v.comprobacion("C2a", lambda: pruebas_clases(CLASES_C2A))
        v.comprobacion("C2b", c2b_entrada_mapa)
        if ctx.telefono_listo:
            contexto = "APK de este commit instalado por C1b"
        else:
            contexto = "antes, instalar el APK de este commit (installDebug, validation-3-1 §5)"
        v.manual("C2c", instruccion_c2(contexto))

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
