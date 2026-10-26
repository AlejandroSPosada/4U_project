"""Validador de FE-3.4 — Lugares de administración (7.6, 7.7).

Documento: FRONTEND_KOTLIN/docs/validation/validation-3-4.md. Entornos: local (C1a, C2a y C3a, pruebas en la JVM; sin
teléfono ni backend) y dev (además C1b, C2b, C1c y C3b, con un dispositivo físico y la API de dev). En dev: inicia
sesión como admin por la API y por la interfaz del teléfono, borra los lugares de prueba `validacion-3-4-*` que haya
dejado una ejecución anterior y, en tres pasos guiados, la persona: crea en 7.7 `validacion-3-4-lugar` eligiendo el
punto en el mapa (el script lee «Punto: …» del formulario, toca «Guardar» y lo busca en GET /v1/places: C1b; con esa
coordenada, GET /v1/places?lat=&lng= lo da primero con distancia_m < 1: C2b); abre Selección de destino por voz (el
script escribe `validacion-3-4` en el buscador y busca la fila: C1c); y escribe en 7.7 un nombre que ya existe (el
script crea `validacion-3-4-dup` por la API, toca «Guardar» y espera el 409 bajo el nombre: C3b). Al terminar borra
los lugares de prueba (también si algo falla) y cierra la app. Nunca imprime contraseñas ni tokens.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

import comun

CLASES_C1A = ["RemoteLugaresAdminRepositoryTest"]
CLASES_C2A = ["FormularioLugarTest"]
CLASES_C3A = ["ErroresLugarTest"]
MINIMO_CASOS = {"RemoteLugaresAdminRepositoryTest": 8, "FormularioLugarTest": 8, "ErroresLugarTest": 4}
PREFIJO_PRUEBA = "validacion-3-4"  # validation-3-4 §4: lo que se busca con ?q= al limpiar
LUGAR_PRUEBA = "validacion-3-4-lugar"  # lo crea la persona en 7.7 (C1b)
CATEGORIA_PRUEBA = "bloque"
ETIQUETA_CATEGORIA = "Bloque"  # CategoriaLugar.BLOQUE.etiqueta (ARCHITECTURE §5.6)
ALIAS_PRUEBA = "validacion"
LUGAR_DUPLICADO = "validacion-3-4-dup"  # lo crea el script por la API (C3b)
NOMBRE_DUPLICADO_ESCRITO = "VALIDACIÓN-3-4-DUP"  # lo que escribe la persona: mismo nombre normalizado
NOMBRES_PRUEBA = (LUGAR_PRUEBA, LUGAR_DUPLICADO)  # lo único que borra la limpieza (nombre normalizado exacto)
POSICION_CAMPUS = (6.2006, -75.5783)  # aprox. EAFIT: donde va validacion-3-4-dup
BUSQUEDA_DESTINO = "validacion-3-4"  # lo que escribe el script en el buscador de Destino (C1c)
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
LIMITE_LOGIN_S = 15  # desde el toque en «Iniciar sesión» hasta ver el Panel
LIMITE_GUARDAR_S = 20  # tras tocar «Guardar», hasta volver a 7.6 (C1b) o ver el 409 (C3b)
LIMITE_DESTINO_S = 20  # tras el Enter de C1c, hasta ver Selección de destino
MAX_DESPLAZAMIENTOS = 4  # veces que baja Destino buscando el buscador o la fila
DISTANCIA_MAXIMA_M = 1.0  # C2 (PLAN §2.2)
# Textos de la app (ARCHITECTURE §5.5, «Lugares de administración»): cambiarlos exige cambiarlos aquí.
PREFIJO_PUNTO = "Punto: "  # pie fijo de 7.7 (FormularioLugar.textoPunto)
PATRON_PUNTO = re.compile(r"^Punto: (-?\d{1,3}\.\d{6}), (-?\d{1,3}\.\d{6})$")
BOTON_GUARDAR = "Guardar"
VISTA_LISTA = "Vista de lista"  # content-desc del selector Lista/Mapa de 7.6
ERROR_DUPLICADO = "Ya existe un lugar con ese nombre"  # ErroresLugarMapeo.NOMBRE_DUPLICADO (comienzo)
ERRORES_FORMULARIO = (  # mensajes de 7.7 que indican que no se guardó (FormularioLugar, ErroresLugarMapeo)
    ERROR_DUPLICADO,
    "Sin conexión.",
    "Algo salió mal.",
    "Escribe un nombre",
    "Máximo 80 caracteres.",
    "Elige una categoría.",
    "Toca el mapa para elegir",
    "Este lugar ya no existe",
    "Revisa los datos",
)
ERRORES_LOGIN = ("Credenciales inválidas", "Sin conexión", "Algo salió mal")  # banners de Login (§5.5)
TITULO_DESTINO = "¿A dónde quieres ir?"  # EncabezadoPregunta (§5.5)
FIN_FILA_DESTINO = ". Toca para elegir este destino."  # contentDescription de FilaLugar (§5.5)
ERROR_CARGA_DESTINO = "No se pudo cargar la lista de lugares."

INSTRUCCION_C1B = (
    "En el teléfono, en el Panel, toca «Lugares» → «Nuevo lugar». Nombre: validacion-3-4-lugar; alias: validacion; "
    "categoría: Bloque. Toca el mapa en un punto libre (lejos de los otros lugares) y comprueba que el pie dice "
    "«Punto: …» con números. NO pulses «Guardar» (lo pulsa el script): cierra el teclado si tapa algo y pulsa Enter "
    "aquí."
)
INSTRUCCION_C1C = (
    "En el teléfono, vuelve a Inicio (Atrás hasta el Panel y «Volver al modo público»). En Inicio di «dos»: se abre "
    f"Selección de destino («{TITULO_DESTINO}»). No toques nada más (el script escribe en el buscador) y pulsa Enter "
    "aquí."
)
INSTRUCCION_C3B = (
    f"En el teléfono, en el Panel, toca «Lugares» → «Nuevo lugar». Nombre: {NOMBRE_DUPLICADO_ESCRITO} (con "
    "mayúsculas y tilde), cualquier categoría, y toca el mapa en cualquier punto. NO pulses «Guardar» (lo pulsa el "
    "script): cierra el teclado si tapa algo y pulsa Enter aquí."
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
    punto: tuple[str, str] | None = None  # «Punto: lat, lng» de C1b, tal como lo mostró el formulario


# --- piezas puras ----------------------------------------------------------------------------------------------


def normalizar_nombre(texto: str) -> str:
    """Como `normalizar_nombre` del backend (backend §4.9; igual que en validate31): NFKD sin marcas combinantes,
    `casefold` y espacios reducidos a uno."""
    sin_marcas = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sin_marcas.casefold().split())


def saludo_esperado(nombre: str) -> str:
    """Lo que dibuja el Panel (7.2): «Hola, <lo que hay antes del primer espacio del nombre>» o «Hola» sin nombre
    (como validate22)."""
    primero = nombre.strip().split(" ")[0]
    return f"Hola, {primero}" if primero else "Hola"


def punto_del_formulario(nodos: list[comun.Nodo]) -> tuple[str, str] | None:
    """`(lat, lng)` como texto del pie «Punto: lat, lng» de 7.7, o None si no se ve o no hay punto elegido."""
    for n in nodos:
        m = PATRON_PUNTO.match(n.texto.strip())
        if m:
            return m.group(1), m.group(2)
    return None


def en_formulario(nodos: list[comun.Nodo]) -> bool:
    """¿Se ve 7.7? (su pie «Punto: …», con o sin punto elegido)."""
    return any(n.texto.startswith(PREFIJO_PUNTO) for n in nodos)


def error_del_formulario(nodos: list[comun.Nodo]) -> str | None:
    """El primer mensaje de error de 7.7 que se ve (texto completo), o None."""
    for n in nodos:
        for fragmento in ERRORES_FORMULARIO:
            if fragmento in n.texto:
                return n.texto
    return None


def nombre_de_fila_destino(descripcion: str) -> str | None:
    """El nombre y la categoría de una fila de Destino: «{nombre}, {categoría}» desde su `content-desc` (`FilaLugar`,
    ARCHITECTURE §5.5: «{nombre}, {categoría}[, a {N} metros]. Toca para elegir este destino.»). None si no es fila."""
    if not descripcion.endswith(FIN_FILA_DESTINO):
        return None
    return re.sub(r", a \d+ metros$", "", descripcion[: -len(FIN_FILA_DESTINO)])


def lugares_de_prueba(items: list) -> list[dict]:
    """Los lugares cuyo nombre normalizado es exactamente uno de `NOMBRES_PRUEBA` (nunca otros)."""
    nombres = {normalizar_nombre(n) for n in NOMBRES_PRUEBA}
    return [i for i in items if isinstance(i, dict) and normalizar_nombre(str(i.get("nombre") or "")) in nombres]


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-3.4",
        validacion="validation-3-4",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C1c", "C2a", "C2b", "C3a", "C3b"],
        grupos={"C1": ["C1a", "C1b", "C1c"], "C2": ["C2a", "C2b"], "C3": ["C3a", "C3b"]},
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

    def p6_be31() -> str:
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.1"):
            raise comun.Bloqueo("BE-3.1 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (lugares)")
        admin = lista_admin(error=comun.Bloqueo)
        publicos = lugares_publicos(error=comun.Bloqueo)
        return f"BE-3.1 Hecho; GET /v1/admin/places -> 200 ({len(admin)}); GET /v1/places -> 200 ({len(publicos)})"

    # --- API de lugares (nunca imprime el token) ---------------------------------------------------------------

    def lista(ruta: str, token: str | None, error: type[Exception]) -> list[dict]:
        try:
            r = comun.http_get(f"{ctx.url}{ruta}", token=token)
        except comun.ErrorRed as e:
            raise error(f"BE-3.1: GET /v1{ruta.split('?')[0]} sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise error(
                f"BE-3.1: GET /v1{ruta.split('?')[0]} respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        return [i for i in cuerpo["items"] if isinstance(i, dict)]

    def lista_admin(q: str | None = None, error: type[Exception] = comun.Falla) -> list[dict]:
        return lista(f"/admin/places?q={quote(q)}" if q else "/admin/places", ctx.token, error)

    def lugares_publicos(lat: str | None = None, lng: str | None = None, error: type[Exception] = comun.Falla):
        ruta = f"/places?lat={quote(lat)}&lng={quote(lng)}" if lat is not None and lng is not None else "/places"
        return lista(ruta, None, error)

    def borrar_lugar(lugar_id: str) -> None:
        r = comun.http_delete(f"{ctx.url}/admin/places/{quote(lugar_id)}", token=ctx.token)
        if r.estado != 204:
            raise comun.Falla(f"DELETE /v1/admin/places/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}")

    def borrar_restos() -> int:
        """Borra los lugares de prueba (solo los de nombre normalizado exacto de `NOMBRES_PRUEBA`)."""
        restos = lugares_de_prueba(lista_admin(PREFIJO_PRUEBA))
        for lugar in restos:
            borrar_lugar(str(lugar.get("id")))
        return len(restos)

    def preparar_datos() -> None:
        """Una vez: borra los restos de una ejecución anterior y registra la misma limpieza para el final."""
        if ctx.limpieza_registrada:
            return
        restos = borrar_restos()
        if restos:
            comun.avisar(f"borrado(s) {restos} lugar(es) de prueba de una ejecución anterior")
        v.al_limpiar(f"borrar los lugares de prueba ({', '.join(NOMBRES_PRUEBA)})", borrar_restos)
        ctx.limpieza_registrada = True

    def crear_duplicado() -> None:
        cuerpo = {
            "nombre": LUGAR_DUPLICADO,
            "categoria": CATEGORIA_PRUEBA,
            "lat": POSICION_CAMPUS[0],
            "lng": POSICION_CAMPUS[1],
            "alias": [],
            "descripcion": "Lugar de prueba de validate34.py (FE-3.4, C3): se borra al terminar.",
        }
        r = comun.http_post_json(f"{ctx.url}/admin/places", cuerpo, token=ctx.token)
        if r.estado != 201:
            raise comun.Falla(
                f"POST /v1/admin/places ({LUGAR_DUPLICADO}) respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        comun.avisar(f"creado {LUGAR_DUPLICADO} por la API; se borra al terminar")

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

    def sin_teclado(nodos: list[comun.Nodo], hay: Callable[[list[comun.Nodo]], bool]) -> list[comun.Nodo]:
        """Si `hay(nodos)` es falso y el teclado está abierto, lo cierra con Atrás (solo entonces) y vuelve a volcar."""
        if not hay(nodos) and comun.teclado_visible():
            comun.tecla(comun.TECLA_ATRAS)
            comun.dormir(1)
            return comun.volcar_pantalla()
        return nodos

    def formulario_listo(que: str) -> tuple[list[comun.Nodo], tuple[str, str]]:
        """Tras el Enter: 7.7 a la vista con un punto elegido y «Guardar». Devuelve los nodos y el punto."""
        nodos = comun.volcar_pantalla()
        nodos = sin_teclado(nodos, lambda ns: en_formulario(ns) and comun.primero(ns, dice=BOTON_GUARDAR) is not None)
        if not en_formulario(nodos):
            raise comun.Falla(
                f"no se ve el formulario de lugar (7.7) para {que}; en pantalla: {comun.textos_visibles(nodos)}"
            )
        punto = punto_del_formulario(nodos)
        if punto is None:
            raise comun.Falla(
                f"el formulario dice «{comun.primero(nodos, contiene=PREFIJO_PUNTO).texto}»: falta tocar el mapa"
            )
        if comun.primero(nodos, dice=BOTON_GUARDAR) is None:
            raise comun.Falla(
                f"no se ve «{BOTON_GUARDAR}» en el formulario; en pantalla: {comun.textos_visibles(nodos)}"
            )
        return nodos, punto

    def nombre_escrito(nodos: list[comun.Nodo]) -> str:
        campos = comun.campos_texto(nodos)
        if not campos:
            raise comun.Falla("no se ve el campo Nombre del formulario (¿quedó fuera de la pantalla?)")
        return campos[0].texto

    def guardar_y_esperar(
        nodos: list[comun.Nodo], que_se_espera: str, listo: Callable[[list[comun.Nodo]], bool]
    ) -> list[comun.Nodo]:
        """Toca «Guardar» y vuelca cada ~1 s hasta `listo(nodos)` o `LIMITE_GUARDAR_S`."""
        boton = comun.primero(nodos, dice=BOTON_GUARDAR)
        assert boton is not None
        comun.tocar(boton)
        fin = comun.reloj() + LIMITE_GUARDAR_S
        while True:
            comun.dormir(1)
            nodos = comun.volcar_pantalla()
            resultado = listo(nodos)
            if resultado:
                return nodos
            if comun.reloj() >= fin:
                raise comun.Falla(
                    f"en {LIMITE_GUARDAR_S} s tras «{BOTON_GUARDAR}» no se vio {que_se_espera}; en pantalla: "
                    f"{comun.textos_visibles(nodos)}"
                )

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

    def c1b_crear() -> str:
        preparar_datos()
        abrir_panel()
        comun.esperar_enter(INSTRUCCION_C1B)
        nodos, punto = formulario_listo("C1b")
        escrito = nombre_escrito(nodos)
        if escrito.strip() != LUGAR_PRUEBA:
            raise comun.Falla(f"el nombre del formulario es «{escrito}», no «{LUGAR_PRUEBA}» (no se guardó nada)")
        comun.avisar(f"el formulario muestra «{PREFIJO_PUNTO}{punto[0]}, {punto[1]}»; se toca «{BOTON_GUARDAR}»")

        def vuelto(ns: list[comun.Nodo]) -> bool:
            error = error_del_formulario(ns)
            if error is not None and en_formulario(ns):
                raise comun.Falla(f"el formulario no guardó: «{error}»")
            return not en_formulario(ns) and comun.primero(ns, dice=VISTA_LISTA) is not None

        guardar_y_esperar(nodos, "la lista de lugares (7.6)", vuelto)
        encontrados = [i for i in lugares_publicos() if str(i.get("nombre") or "") == LUGAR_PRUEBA]
        if len(encontrados) != 1:
            raise comun.Falla(f"GET /v1/places tiene {len(encontrados)} lugares «{LUGAR_PRUEBA}» (se esperaba 1)")
        lugar = encontrados[0]
        if lugar.get("categoria") != CATEGORIA_PRUEBA:
            raise comun.Falla(f"«{LUGAR_PRUEBA}» tiene categoria = {lugar.get('categoria')!r}, no {CATEGORIA_PRUEBA!r}")
        alias = [str(a) for a in lugar.get("alias") or []]
        if alias != [ALIAS_PRUEBA]:
            raise comun.Falla(f"«{LUGAR_PRUEBA}» tiene alias {alias}, no [{ALIAS_PRUEBA!r}]")
        ctx.punto = punto
        return (
            f"«{LUGAR_PRUEBA}» creado en 7.7 aparece una vez en GET /v1/places (categoria {CATEGORIA_PRUEBA}, alias "
            f"[{ALIAS_PRUEBA}], {lugar.get('lat')}, {lugar.get('lng')}); 7.6 a la vista tras «{BOTON_GUARDAR}»"
        )

    def c2b_posicion() -> str:
        assert ctx.punto is not None
        lat, lng = ctx.punto
        items = lugares_publicos(lat, lng)
        if not items:
            raise comun.Falla(f"GET /v1/places?lat={lat}&lng={lng} no devolvió lugares")
        primero = items[0]
        distancia = primero.get("distancia_m")
        if str(primero.get("nombre") or "") != LUGAR_PRUEBA:
            raise comun.Falla(
                f"GET /v1/places?lat={lat}&lng={lng} da primero «{primero.get('nombre')}» (a {distancia} m), no "
                f"«{LUGAR_PRUEBA}»: la posición guardada no es la del formulario"
            )
        if not isinstance(distancia, int | float) or distancia >= DISTANCIA_MAXIMA_M:
            raise comun.Falla(
                f"«{LUGAR_PRUEBA}» está a {distancia} m de «{PREFIJO_PUNTO}{lat}, {lng}» (máximo {DISTANCIA_MAXIMA_M})"
            )
        return (
            f"GET /v1/places?lat={lat}&lng={lng} (el punto del formulario) da primero «{LUGAR_PRUEBA}» con "
            f"distancia_m = {distancia} (< {DISTANCIA_MAXIMA_M:g}); guardado en {primero.get('lat')}, "
            f"{primero.get('lng')}"
        )

    def c1c_destino() -> str:
        preparar_telefono()
        comun.esperar_enter(INSTRUCCION_C1C)
        ctx.panel_abierto = False  # la persona salió del Panel

        def destino(ns: list[comun.Nodo]) -> comun.Nodo | None:
            if comun.primero(ns, contiene=ERROR_CARGA_DESTINO) is not None:
                raise comun.Falla(
                    "Selección de destino no pudo cargar la lista (GET /v1/places desde el teléfono; mira las líneas "
                    "Api de files/logs/app.log)"
                )
            return comun.primero(ns, dice=TITULO_DESTINO)

        _, nodos = comun.esperar_nodo(destino, LIMITE_DESTINO_S, f"Selección de destino («{TITULO_DESTINO}»)")
        for _ in range(MAX_DESPLAZAMIENTOS):
            if comun.campos_texto(nodos):
                break
            comun.desplazar_hacia_abajo()
            comun.dormir(0.5)
            nodos = comun.volcar_pantalla()
        campos = comun.campos_texto(nodos)
        if not campos:
            raise comun.Falla(
                f"no se ve el buscador de Selección de destino; en pantalla: {comun.textos_visibles(nodos)}"
            )
        comun.tocar(campos[0])
        comun.dormir(0.5)
        comun.escribir_texto(BUSQUEDA_DESTINO)
        comun.dormir(1)
        if comun.teclado_visible():
            comun.tecla(comun.TECLA_ATRAS)
            comun.dormir(1)
        esperado = f"{LUGAR_PRUEBA}, {ETIQUETA_CATEGORIA}"
        filas: list[str] = []
        for intento in range(MAX_DESPLAZAMIENTOS + 1):
            nodos = comun.volcar_pantalla()
            filas = [f for f in (nombre_de_fila_destino(n.descripcion) for n in nodos) if f is not None]
            if esperado in filas:
                return (
                    f"Selección de destino, con «{BUSQUEDA_DESTINO}» en el buscador, muestra la fila «{esperado}»"
                    + (f" ({intento} desplazamientos)" if intento else "")
                )
            if intento < MAX_DESPLAZAMIENTOS:
                comun.desplazar_hacia_abajo()
                comun.dormir(0.5)
        raise comun.Falla(
            f"Selección de destino no muestra «{esperado}» tras buscar «{BUSQUEDA_DESTINO}» (filas: "
            f"{', '.join(f'«{f}»' for f in filas) or 'ninguna'}; en pantalla: {comun.textos_visibles(nodos)})"
        )

    def c3b_duplicado() -> str:
        preparar_datos()
        crear_duplicado()
        ctx.panel_abierto = False  # vuelve a entrar en frío (tras C1c la app está en el flujo público)
        abrir_panel()
        comun.esperar_enter(INSTRUCCION_C3B)
        nodos, _ = formulario_listo("C3b")
        escrito = nombre_escrito(nodos)
        if normalizar_nombre(escrito) != normalizar_nombre(LUGAR_DUPLICADO):
            raise comun.Falla(
                f"el nombre del formulario es «{escrito}»: hace falta uno igual a «{LUGAR_DUPLICADO}» sin mayúsculas "
                "ni tildes (no se guardó nada)"
            )

        def con_error(ns: list[comun.Nodo]) -> bool:
            if not en_formulario(ns) and comun.primero(ns, dice=VISTA_LISTA) is not None:
                raise comun.Falla(f"el formulario se cerró como si hubiera guardado «{escrito}» (se esperaba el 409)")
            return en_formulario(ns) and comun.primero(ns, contiene=ERROR_DUPLICADO) is not None

        nodos = guardar_y_esperar(nodos, f"«{ERROR_DUPLICADO}…» en el formulario", con_error)
        mensaje = comun.primero(nodos, contiene=ERROR_DUPLICADO)
        assert mensaje is not None
        iguales = [
            i for i in lista_admin(PREFIJO_PRUEBA) if normalizar_nombre(str(i.get("nombre") or "")) == LUGAR_DUPLICADO
        ]
        if len(iguales) != 1:
            raise comun.Falla(f"GET /v1/admin/places tiene {len(iguales)} lugares «{LUGAR_DUPLICADO}» (se esperaba 1)")
        return (
            f"«{escrito}» → 409: el formulario muestra «{mensaje.texto}» y no se cierra; GET /v1/admin/places sigue "
            f"con un solo «{LUGAR_DUPLICADO}»"
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        telefono = ("C1b", "C2b", "C1c", "C3b")
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = [
                ("P2", p2_dispositivo),
                ("P3", p3_api),
                ("P4", p4_login_admin),
                ("P5", p5_fe12),
                ("P6", p6_be31),
            ]
            if not v.alguna_incluida(*telefono):
                for id_, _ in pasos:
                    v.precondicion_no_evaluada(id_, "C1b, C1c, C2b y C3b excluidas con --solo")
            else:
                for i, (id_, fn) in enumerate(pasos):
                    if not v.precondicion(id_, fn):
                        for siguiente, _ in pasos[i + 1 :]:
                            v.precondicion_no_evaluada(siguiente, f"{id_} no se cumple")
                        return

        local("C1a", CLASES_C1A)
        local("C2a", CLASES_C2A)
        local("C3a", CLASES_C3A)

        def en_telefono(id_: str, fn: Callable[[], str], requiere_c1b: bool = False) -> None:
            if not dev:
                v.omitir(id_, "solo en dev (necesita el dispositivo y el backend)")
            elif not v.incluida(id_):
                v.comprobacion(id_, fn)  # el Validador la marca omitida (--solo)
            elif ctx.fallo_previo:
                v.omitir(id_, f"no se hace: falló {ctx.fallo_previo} (corrige y repite)")
            elif requiere_c1b and not v.incluida("C1b"):
                v.omitir(id_, "necesita C1b (el lugar creado en el formulario): inclúyela en --solo")
            elif requiere_c1b and ctx.punto is None:
                v.omitir(id_, "no se hace: C1b no creó el lugar")
            else:
                v.comprobacion(id_, fn)

        en_telefono("C1b", c1b_crear)
        en_telefono("C2b", c2b_posicion, requiere_c1b=True)
        en_telefono("C1c", c1c_destino, requiere_c1b=True)
        en_telefono("C3b", c3b_duplicado)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
