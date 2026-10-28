"""Validador de FE-4.1 — Videos e imágenes contra el backend (7.11–7.14).

Documento: FRONTEND_KOTLIN/docs/validation/validation-4-1.md. Entornos: local (C1a, C2a y C3a: comprobaciones
estáticas y pruebas en la JVM; sin teléfono ni backend) y dev (además C1b, C3b y C2b, con un dispositivo físico y la
API de dev; no necesita `embedding`). En dev: crea por la API de recolección dos videos de prueba,
`validacion-4-1-a` y `validacion-4-1-b`, con 3 JPEG sintéticos cada uno; inicia sesión por la interfaz del teléfono;
compara los contadores de 7.13 («N videos», «M sin subir en este teléfono») y de 7.11 («N imágenes») con la API y con
los manifests del teléfono (C1b); en dos pasos guiados, la persona renombra `validacion-4-1-a` en 7.14 (el script lo
busca en GET /v1/admin/videos/{id}: C3b) y elimina `validacion-4-1-b` (el script comprueba que la app volvió sola a
7.13 sin él, que el backend ya no lo tiene y que la Galería, buscando `validacion-4-1`, solo muestra las fotos del otro:
C2b). Al empezar y al terminar (también si algo falla) borra con DELETE /v1/admin/videos/{id} **solo** los videos cuyo
`nombre` y `ref_cliente` empiezan por `validacion-4-1` (más los que creó, por su id); nunca otros videos ni imágenes
sueltas. Nunca imprime contraseñas, tokens ni URLs prefirmadas; nunca usa `pm clear`.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote

import comun

CLASES_C1A = ["VideoRepositoryCompuestoTest"]
CLASES_C2A = ["TextosVideosTest"]
CLASES_C3A = ["RemoteVideoRepositoryTest"]
MINIMO_CASOS = {"VideoRepositoryCompuestoTest": 8, "TextosVideosTest": 4, "RemoteVideoRepositoryTest": 10}

DIR_APP = comun.PROYECTO / "app" / "src" / "main"
DIR_KOTLIN = DIR_APP / "java" / "com" / "example" / "myapplication"
DIR_ASSETS = DIR_APP / "assets"
JS_DETALLE = DIR_ASSETS / "video_detalle.js"
# Lo que ya no debe existir en el código (C1: «EdicionesLocales ya no existe»; los videos de assets ya no se muestran).
PROHIBIDOS = ("EdicionesLocales", "AssetsVideoRepository", "FuenteRecorridos")
# Las Factory de 7.11–7.14 deben crear los repositorios del backend (ARCHITECTURE §5.6).
FACTORIES = {
    "ui/admin/imagenes/GaleriaViewModel.kt": ("RemoteVideoRepository()", "VideoRepositoryCompuesto.deLaApp()"),
    "ui/admin/videos/VideosViewModel.kt": ("VideoRepositoryCompuesto.deLaApp()",),
    "ui/admin/videos/VideoDetalleViewModel.kt": ("VideoRepositoryCompuesto.deLaApp()",),
    "data/repository/VideoRepository.kt": ("servidor = RemoteVideoRepository()",),
}

PREFIJO = "validacion-4-1"  # lo que se busca con ?q= y lo único que se borra (nombre **y** ref_cliente)
VIDEO_A = "validacion-4-1-a"  # se renombra en C3b
VIDEO_B = "validacion-4-1-b"  # se elimina en C2b
RENOMBRADO = "validacion-4-1-renombrado"
FOTOS_POR_VIDEO = 3
LADO_FOTOS = (640, 480)
# Fuera del campus (como los validadores del backend): no se mezclan con las fotos reales en el mapa ni en 7.3.
POSICION_PRUEBA = (1.0, -100.0)
# Fechas del recorrido en el pasado: «Usar mi última posición» (7.3) nunca elige un video de prueba.
INICIADO_EN = "2026-01-01T00:00:00Z"
FINALIZADO_EN = "2026-01-01T00:05:00Z"
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
DIR_RECOLECCION = "files/recoleccion"
LIMITE_LOGIN_S = 15
LIMITE_LISTA_S = 30  # 7.13 pide todas las páginas de GET /v1/admin/videos
LIMITE_FILTRO_S = 15  # tras escribir en un buscador (espera de 400 ms + la petición)
LIMITE_RENOMBRAR_S = 20
LIMITE_VUELTA_S = 30  # tras el Enter de C2b, hasta ver 7.13
MAX_DESPLAZAMIENTOS = 4
TECLA_FIN = "123"  # KEYCODE_MOVE_END
TECLA_BORRAR = "67"  # KEYCODE_DEL
# Textos de la app (ARCHITECTURE §5.5 y TextosVideos): cambiarlos exige cambiarlos aquí.
ACCESO_VIDEOS = "Videos"  # tarjeta del Panel
ACCESO_IMAGENES = "Imágenes"  # tarjeta del Panel
TITULO_LISTA = "Videos de recolección"
TITULO_GALERIA = "Imágenes del dataset"
PATRON_TOTAL_VIDEOS = re.compile(r"^(\d+) videos?$")
PATRON_SIN_SUBIR = re.compile(r"^(\d+) sin subir en este teléfono$")
PATRON_TOTAL_IMAGENES = re.compile(r"^([\d.,\s  ]+) imágenes$|^(1) imagen$")
PREFIJO_FILA = "Video "  # content-desc de una fila de 7.13: «Video <nombre>, …»
ERROR_ELIMINAR = "No se pudo eliminar el video"
ERROR_RENOMBRAR = "No se pudo renombrar"
ERRORES_LOGIN = ("Credenciales inválidas", "Sin conexión", "Algo salió mal")

INSTRUCCION_C3B = (
    f"En el teléfono, en la lista de videos (7.13, con «{PREFIJO}» en el buscador), toca «{VIDEO_A}». En su detalle "
    f"(7.14) toca «Renombrar», escribe {RENOMBRADO} y «Guardar». Espera a que el nombre nuevo salga arriba y pulsa "
    "Enter aquí."
)
INSTRUCCION_C2B = (
    f"En el teléfono, en la lista de videos (7.13, con «{PREFIJO}» en el buscador), abre «{VIDEO_B}». Toca «Eliminar "
    f"video», escribe {VIDEO_B} y confirma. La app vuelve sola a la lista cuando el servidor confirma el borrado: "
    "espera a verla (sin tocar nada más) y pulsa Enter aquí."
)
INSTRUCCION_C2C = (
    "Evidencia para el PR (validation-4-1 §3): tras C2b, una captura (`adb exec-out screencap -p`) de 7.13 con "
    f"«{PREFIJO}» en el buscador (solo «{RENOMBRADO}») y otra de la Galería con la misma búsqueda (sus "
    f"{FOTOS_POR_VIDEO} fotos), sin datos privados (nombres de prueba; nada de la cámara)."
)


@dataclass
class VideoPrueba:
    nombre: str
    ref_cliente: str
    id: str = ""
    imagenes: list[str] = field(default_factory=list)


@dataclass
class Contexto:
    url: str = ""
    token: str = ""
    nombre_admin: str = ""
    admin: tuple[str, str] | None = None
    sdk: int = 0
    telefono_listo: bool = False
    panel_abierto: bool = False
    datos_listos: bool = False
    gradle: comun.Resultado | None = None
    fallo_previo: str | None = None
    videos: dict[str, VideoPrueba] = field(default_factory=dict)
    creados: list[str] = field(default_factory=list)  # ids que creó esta ejecución (los borra la limpieza)
    renombrado: bool = False


# --- piezas puras ----------------------------------------------------------------------------------------------


def quitar_comentarios_kotlin(texto: str, cadenas: bool = True) -> str:
    """Kotlin (o JS) sin comentarios `//` y `/* */`, respetando cadenas `"…"`, `'…'` y `\"\"\"…\"\"\"`: las palabras de
    un KDoc no cuentan como uso. Con `cadenas=False` también vacía el contenido de las cadenas (queda `""`)."""
    salida: list[str] = []
    i, n = 0, len(texto)
    while i < n:
        if texto.startswith('"""', i):
            fin = texto.find('"""', i + 3)
            fin = n if fin < 0 else fin + 3
            salida.append(texto[i:fin] if cadenas else '""')
            i = fin
        elif texto[i] in "\"'`":
            cierre = texto[i]
            j = i + 1
            while j < n and texto[j] != cierre and texto[j] != "\n":
                j += 2 if texto[j] == "\\" else 1
            salida.append(texto[i : j + 1] if cadenas else cierre * 2)
            i = j + 1
        elif texto.startswith("//", i):
            fin = texto.find("\n", i)
            i = n if fin < 0 else fin
        elif texto.startswith("/*", i):
            fin = texto.find("*/", i + 2)
            i = n if fin < 0 else fin + 2
            salida.append(" ")
        else:
            salida.append(texto[i])
            i += 1
    return "".join(salida)


def usos_prohibidos(archivos: dict[str, str]) -> list[str]:
    """`ruta: nombre` de cada uso (fuera de comentarios y cadenas) de un nombre de `PROHIBIDOS` en los archivos."""
    encontrados = []
    for ruta, texto in sorted(archivos.items()):
        codigo = quitar_comentarios_kotlin(texto, cadenas=False)
        for nombre in PROHIBIDOS:
            if re.search(rf"\b{nombre}\b", codigo):
                encontrados.append(f"{ruta}: {nombre}")
    return encontrados


def cuerpo_funcion_js(texto: str, nombre: str) -> str | None:
    """El cuerpo (entre llaves) de `function <nombre>(…) {…}` sin comentarios, o None si no está."""
    codigo = quitar_comentarios_kotlin(texto)
    m = re.search(rf"\bfunction\s+{re.escape(nombre)}\s*\([^)]*\)\s*\{{", codigo)
    if not m:
        return None
    profundidad, i = 1, m.end()
    while i < len(codigo) and profundidad:
        profundidad += {"{": 1, "}": -1}.get(codigo[i], 0)
        i += 1
    return codigo[m.end() : i - 1]


def comprobar_js_eliminar(texto: str) -> str:
    """C2a (estática): `eliminarVideo()` de `video_detalle.js` llama al puente y **no** sale sola (ni `setTimeout` ni
    `salir`): la app vuelve a la lista cuando el servidor confirmó (FE-4.1). Devuelve un detalle o lanza Falla."""
    cuerpo = cuerpo_funcion_js(texto, "eliminarVideo")
    if cuerpo is None:
        raise comun.Falla("video_detalle.js no tiene «function eliminarVideo()»")
    if "call('eliminarVideo')" not in cuerpo.replace('"', "'"):
        raise comun.Falla("eliminarVideo() de video_detalle.js no llama al puente (call('eliminarVideo'))")
    if "setTimeout" in cuerpo or "salir" in cuerpo:
        raise comun.Falla(
            "eliminarVideo() de video_detalle.js sale sola de la pantalla (setTimeout/salir) sin esperar al servidor"
        )
    return "video_detalle.js: eliminarVideo() llama al puente y no sale sola"


def es_de_prueba(item: dict) -> bool:
    """¿Un `VideoResumen` es de esta validación? `nombre` **y** `ref_cliente` empiezan por `PREFIJO` (backend §5.5)."""
    return str(item.get("nombre") or "").startswith(PREFIJO) and str(item.get("ref_cliente") or "").startswith(PREFIJO)


def valor_entero(texto: str) -> int | None:
    """«2.842», «2,842», «2 842» o «2842» → 2842; otra cosa → None."""
    limpio = re.sub(r"[.,\s  ]", "", texto)
    return int(limpio) if limpio.isdigit() else None


def total_en_pantalla(nodos: list[comun.Nodo], patron: re.Pattern[str]) -> int | None:
    for n in nodos:
        m = patron.match(n.texto.strip())
        if m:
            return valor_entero(next(g for g in m.groups() if g is not None))
    return None


def filas_videos(nodos: list[comun.Nodo]) -> list[str]:
    """Las `content-desc` de las filas de 7.13 visibles («Video <nombre>, …»), de arriba abajo."""
    return [n.descripcion for n in nodos if n.descripcion.startswith(PREFIJO_FILA)]


def hay_fila(filas: list[str], nombre: str) -> bool:
    return any(f.startswith(f"{PREFIJO_FILA}{nombre},") for f in filas)


def sin_subir_en_manifests(manifests: list[str]) -> int:
    """Recorridos que 7.13 debe mostrar como locales: `estado = finalizado` sin `remote_video_id` (manifests legibles
    con fotos válidas, como `AlmacenRecorridos.listar`)."""
    n = 0
    for texto in manifests:
        try:
            m = json.loads(texto)
        except ValueError:
            continue
        if not isinstance(m, dict) or m.get("estado") != "finalizado" or m.get("remote_video_id"):
            continue
        fotos = m.get("photos") or []
        if not isinstance(fotos, list) or any(
            not isinstance(f, dict) or not all(k in f for k in ("id", "file", "lat", "lng")) for f in fotos
        ):
            continue
        n += 1
    return n


def saludo_esperado(nombre: str) -> str:
    primero = nombre.strip().split(" ")[0]
    return f"Hola, {primero}" if primero else "Hola"


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-4.1",
        validacion="validation-4-1",
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

    def p5_fe21() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-2.1"):
            raise comun.Bloqueo("FE-2.1 no está «Hecho» en PLAN.md §3 (subida de recorridos)")
        return "FE-2.1 Hecho"

    def p6_be41() -> str:
        plan = comun.PLAN_BACKEND.read_text(encoding="utf-8")
        for lote in ("BE-2.1", "BE-4.1"):
            if not comun.lote_hecho(plan, lote):
                raise comun.Bloqueo(f"{lote} no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3")
        videos = pagina("/admin/videos?por_pagina=1", comun.Bloqueo)
        imagenes = pagina("/admin/images?por_pagina=1", comun.Bloqueo)
        r = comun.http_post_json(f"{ctx.url}/collect/videos", {}, token=ctx.token)
        if r.estado != 422 or comun.codigo_error(r) != "VALIDACION":
            raise comun.Bloqueo(
                f"BE-2.1: POST /v1/collect/videos {{}} respondió {r.estado} {comun.codigo_error(r) or ''}"
            )
        return (
            f"BE-2.1 y BE-4.1 Hecho; GET /v1/admin/videos -> 200 (total {videos['total']}); "
            f"GET /v1/admin/images -> 200 (total {imagenes['total']}); POST /v1/collect/videos {{}} -> 422 VALIDACION"
        )

    # --- API (nunca imprime el token ni las URLs prefirmadas) ---------------------------------------------------

    def pagina(ruta: str, error: type[Exception] = comun.Falla) -> dict:
        try:
            r = comun.http_get(f"{ctx.url}{ruta}", token=ctx.token)
        except comun.ErrorRed as e:
            raise error(f"GET /v1{ruta.split('?')[0]} sin respuesta ({e})") from e
        cuerpo = r.json()
        if (
            r.estado != 200
            or not isinstance(cuerpo, dict)
            or not isinstance(cuerpo.get("items"), list)
            or not isinstance(cuerpo.get("total"), int)
        ):
            raise error(
                f"BE-4.1: GET /v1{ruta.split('?')[0]} respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        return cuerpo

    def total_videos(q: str | None = None) -> int:
        return int(pagina(f"/admin/videos?por_pagina=1{f'&q={quote(q)}' if q else ''}")["total"])

    def total_imagenes(q: str | None = None, video_id: str | None = None) -> int:
        extra = (f"&q={quote(q)}" if q else "") + (f"&video_id={quote(video_id)}" if video_id else "")
        return int(pagina(f"/admin/images?por_pagina=1{extra}")["total"])

    def detalle_video(video_id: str) -> dict | None:
        r = comun.http_get(f"{ctx.url}/admin/videos/{quote(video_id)}", token=ctx.token)
        if r.estado == 404:
            return None
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict):
            raise comun.Falla(
                f"GET /v1/admin/videos/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        return cuerpo

    def borrar_video(video_id: str) -> None:
        r = comun.http_delete(f"{ctx.url}/admin/videos/{quote(video_id)}", token=ctx.token)
        if r.estado not in (202, 404):
            raise comun.Falla(
                f"DELETE /v1/admin/videos/{{id}} respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )

    def borrar_restos() -> int:
        """Borra los videos de prueba: los de `?q=validacion-4-1` con `nombre` y `ref_cliente` del prefijo y los que
        creó esta ejecución si su `ref_cliente` es del prefijo (por si la persona los renombró a otra cosa)."""
        borrados: set[str] = set()
        for numero in range(1, 21):
            items = pagina(f"/admin/videos?q={quote(PREFIJO)}&por_pagina=100&pagina={numero}")["items"]
            for item in items:
                if isinstance(item, dict) and es_de_prueba(item) and item.get("id"):
                    borrar_video(str(item["id"]))
                    borrados.add(str(item["id"]))
            if len(items) < 100:
                break
        for video_id in ctx.creados:
            if video_id in borrados:
                continue
            d = detalle_video(video_id)
            if d is not None and str(d.get("ref_cliente") or "").startswith(PREFIJO):
                borrar_video(video_id)
                borrados.add(video_id)
        return len(borrados)

    def crear_video(nombre: str, semilla: int) -> VideoPrueba:
        ref = f"{nombre}-{v.sello}"
        cuerpo = {
            "ref_cliente": ref,
            "nombre": nombre,
            "iniciado_en": INICIADO_EN,
            "finalizado_en": FINALIZADO_EN,
            "duracion_s": 300,
            "distancia_m": 12.5,
            "pasos": 17,
            "inicio": {"lat": POSICION_PRUEBA[0], "lng": POSICION_PRUEBA[1], "rumbo": 0.0},
            "total_fotos": FOTOS_POR_VIDEO,
            "dispositivo": "validate41.py",
        }
        r = comun.http_post_json(f"{ctx.url}/collect/videos", cuerpo, token=ctx.token)
        datos = r.json()
        if r.estado not in (200, 201) or not isinstance(datos, dict) or not datos.get("id"):
            raise comun.Falla(
                f"POST /v1/collect/videos ({nombre}) respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip()
            )
        video = VideoPrueba(nombre, ref, str(datos["id"]))
        ctx.creados.append(video.id)
        fotos = {
            orden: comun.jpeg_sintetico(*LADO_FOTOS, semilla=semilla * 10 + orden)
            for orden in range(1, FOTOS_POR_VIDEO + 1)
        }
        imagenes = [
            {
                "orden": orden,
                "lat": POSICION_PRUEBA[0] + orden * 0.0001,
                "lng": POSICION_PRUEBA[1],
                "rumbo": float((orden * 90) % 360),
                "capturada_en": f"2026-01-01T00:0{orden}:00Z",
                "bytes": len(datos_foto),
            }
            for orden, datos_foto in fotos.items()
        ]
        r = comun.http_post_json(f"{ctx.url}/collect/videos/{video.id}/images", {"imagenes": imagenes}, token=ctx.token)
        registradas = (r.json() or {}).get("imagenes") if isinstance(r.json(), dict) else None
        if r.estado != 200 or not isinstance(registradas, list):
            raise comun.Falla(f"POST /v1/collect/videos/{{id}}/images ({nombre}) respondió {r.estado}")
        for reg in registradas:
            orden = reg.get("orden")
            video.imagenes.append(str(reg.get("id")))
            subida = reg.get("subida")
            if not isinstance(subida, dict):
                continue  # ya estaba subida
            put = comun.http_put_bytes(str(subida.get("url")), fotos[orden], dict(subida.get("encabezados") or {}))
            if put.estado != 200:
                raise comun.Falla(f"PUT a S3 de la foto {orden} de {nombre} respondió {put.estado}")
        r = comun.http_post_json(f"{ctx.url}/collect/videos/{video.id}/complete", {}, token=ctx.token)
        conteo = (r.json() or {}).get("conteo") if isinstance(r.json(), dict) else None
        if r.estado != 200 or not isinstance(conteo, dict) or conteo.get("pendiente_subida") != 0:
            raise comun.Falla(
                f"POST /v1/collect/videos/{{id}}/complete ({nombre}) respondió {r.estado}, conteo {conteo}"
            )
        return video

    def preparar_datos() -> None:
        """Una vez: registra la limpieza, borra los restos de una ejecución anterior y crea los dos videos."""
        if ctx.datos_listos:
            return
        v.al_limpiar(f"borrar los videos de prueba ({PREFIJO}-*)", borrar_restos)
        restos = borrar_restos()
        if restos:
            comun.avisar(f"borrado(s) {restos} video(s) de prueba de una ejecución anterior")
        for semilla, nombre in enumerate((VIDEO_A, VIDEO_B), start=1):
            ctx.videos[nombre] = crear_video(nombre, semilla)
        comun.avisar(f"creados {VIDEO_A} y {VIDEO_B} ({FOTOS_POR_VIDEO} fotos cada uno) por la API de recolección")
        ctx.datos_listos = True

    # --- teléfono ----------------------------------------------------------------------------------------------

    def preparar_telefono() -> None:
        """Una vez: `installDebug` (conserva los datos) y `pm grant` de los permisos de Inicio (como validate34)."""
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

    def cerrar_teclado() -> None:
        if comun.teclado_visible():
            comun.tecla(comun.TECLA_ATRAS)
            comun.dormir(1)

    def tocar_en_panel(texto: str) -> None:
        """Toca la tarjeta del Panel que dice `texto` (bajando hasta `MAX_DESPLAZAMIENTOS` veces)."""
        for intento in range(MAX_DESPLAZAMIENTOS + 1):
            nodos = comun.volcar_pantalla()
            nodo = comun.primero(nodos, dice=texto)
            if nodo is not None:
                comun.tocar(nodo)
                return
            if intento < MAX_DESPLAZAMIENTOS:
                comun.desplazar_hacia_abajo()
                comun.dormir(0.5)
        raise comun.Falla(f"no se ve «{texto}» en el Panel; en pantalla: {comun.textos_visibles(nodos)}")

    def volver_al_panel() -> None:
        """Atrás (cerrando antes el teclado) hasta ver el saludo del Panel; como mucho 4 veces."""
        saludo = saludo_esperado(ctx.nombre_admin)
        cerrar_teclado()
        for _ in range(4):
            nodos = comun.volcar_pantalla()
            if comun.primero(nodos, dice=saludo) is not None:
                return
            comun.tecla(comun.TECLA_ATRAS)
            comun.dormir(1)
        nodos = comun.volcar_pantalla()
        if comun.primero(nodos, dice=saludo) is None:
            raise comun.Falla(f"no se volvió al Panel con Atrás; en pantalla: {comun.textos_visibles(nodos)}")

    def asegurar_busqueda(texto: str) -> None:
        """El primer campo de la pantalla queda con `texto` (si tenía otra cosa, se borra) y el teclado cerrado."""
        campos = comun.campos_texto(comun.volcar_pantalla())
        if not campos:
            raise comun.Falla("no se ve el buscador de la pantalla")
        if campos[0].texto == texto:
            return
        comun.tocar(campos[0])
        comun.dormir(0.5)
        if campos[0].texto:
            comun.tecla(TECLA_FIN)
            for _ in range(len(campos[0].texto)):
                comun.tecla(TECLA_BORRAR)
        comun.escribir_texto(texto)
        comun.dormir(1)
        cerrar_teclado()

    def esperar(que: str, limite_s: float, listo: Callable[[list[comun.Nodo]], bool]) -> list[comun.Nodo]:
        fin = comun.reloj() + limite_s
        while True:
            nodos = comun.volcar_pantalla()
            if listo(nodos):
                return nodos
            if comun.reloj() >= fin:
                raise comun.Falla(f"en {limite_s:.0f} s no se vio {que}; en pantalla: {comun.textos_visibles(nodos)}")
            comun.dormir(1)

    def en_lista(nodos: list[comun.Nodo]) -> bool:
        return (
            comun.primero(nodos, dice=TITULO_LISTA) is not None
            and total_en_pantalla(nodos, PATRON_TOTAL_VIDEOS) is not None
        )

    def en_galeria(nodos: list[comun.Nodo]) -> bool:
        return (
            comun.primero(nodos, dice=TITULO_GALERIA) is not None
            and total_en_pantalla(nodos, PATRON_TOTAL_IMAGENES) is not None
        )

    def recorridos_sin_subir() -> int | None:
        carpetas = comun.listar_archivos_app(DIR_RECOLECCION)
        if carpetas is None:
            return None
        manifests = [
            t for c in carpetas if (t := comun.leer_archivo_app(f"{DIR_RECOLECCION}/{c}/manifest.json")) is not None
        ]
        return sin_subir_en_manifests(manifests)

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
        return f"{', '.join(partes)} (mínimos {', '.join(str(MINIMO_CASOS[c]) for c in clases)})"

    def estatica_c1() -> str:
        archivos = {
            str(p.relative_to(DIR_KOTLIN)): p.read_text(encoding="utf-8") for p in sorted(DIR_KOTLIN.rglob("*.kt"))
        }
        usos = usos_prohibidos(archivos)
        if usos:
            raise comun.Falla(f"siguen en el código: {'; '.join(usos[:5])}")
        if (DIR_ASSETS / "videos").exists():
            raise comun.Falla("sigue app/src/main/assets/videos/ (los videos empaquetados ya no se muestran)")
        for ruta, esperados in FACTORIES.items():
            codigo = quitar_comentarios_kotlin(archivos.get(ruta, ""))
            faltan = [e for e in esperados if e not in codigo]
            if faltan:
                raise comun.Falla(f"{ruta} no crea {', '.join(faltan)}")
        return f"sin {', '.join(PROHIBIDOS)} ni assets/videos; las Factory de 7.11–7.14 usan el backend"

    def local(id_: str, fn: Callable[[], str]) -> None:
        def envuelta() -> str:
            try:
                return fn()
            except Exception:
                ctx.fallo_previo = ctx.fallo_previo or id_
                raise

        v.comprobacion(id_, envuelta)

    def c1a() -> str:
        return f"{estatica_c1()}; {pruebas_clases(CLASES_C1A)}"

    def c2a() -> str:
        return f"{comprobar_js_eliminar(JS_DETALLE.read_text(encoding='utf-8'))}; {pruebas_clases(CLASES_C2A)}"

    def c3a() -> str:
        return pruebas_clases(CLASES_C3A)

    def c1b_contadores() -> str:
        preparar_datos()
        abrir_panel()
        esperado_locales = recorridos_sin_subir()
        antes = total_videos()
        tocar_en_panel(ACCESO_VIDEOS)
        nodos = esperar("la lista de videos (7.13) con «N videos»", LIMITE_LISTA_S, en_lista)
        despues = total_videos()
        en_pantalla = total_en_pantalla(nodos, PATRON_TOTAL_VIDEOS)
        if en_pantalla not in (antes, despues):
            raise comun.Falla(f"7.13 dice «{en_pantalla} videos», pero GET /v1/admin/videos da total {despues}")
        locales = total_en_pantalla(nodos, PATRON_SIN_SUBIR) or 0
        if esperado_locales is not None and locales != esperado_locales:
            raise comun.Falla(
                f"7.13 dice «{locales} sin subir en este teléfono», pero hay {esperado_locales} recorridos finalizados "
                "sin remote_video_id en files/recoleccion"
            )
        asegurar_busqueda(PREFIJO)
        total_q = total_videos(PREFIJO)

        def con_los_dos(ns: list[comun.Nodo]) -> bool:
            filas = filas_videos(ns)
            return (
                hay_fila(filas, VIDEO_A)
                and hay_fila(filas, VIDEO_B)
                and total_en_pantalla(ns, PATRON_TOTAL_VIDEOS) == total_q
            )

        esperar(
            f"«{VIDEO_A}», «{VIDEO_B}» y «{total_q} videos» con «{PREFIJO}» en el buscador",
            LIMITE_FILTRO_S,
            con_los_dos,
        )
        volver_al_panel()
        imagenes_antes = total_imagenes()
        tocar_en_panel(ACCESO_IMAGENES)
        nodos = esperar("la Galería (7.11) con «N imágenes»", LIMITE_LISTA_S, en_galeria)
        imagenes_despues = total_imagenes()
        en_galeria_total = total_en_pantalla(nodos, PATRON_TOTAL_IMAGENES)
        if en_galeria_total not in (imagenes_antes, imagenes_despues):
            raise comun.Falla(
                f"la Galería dice «{en_galeria_total} imágenes», pero GET /v1/admin/images da total {imagenes_despues}"
            )
        volver_al_panel()
        locales_texto = (
            f"«{locales} sin subir en este teléfono» = manifests"
            if esperado_locales is not None
            else f"«{locales} sin subir» (sin comprobar: run-as no listó files/recoleccion)"
        )
        return (
            f"7.13 «{en_pantalla} videos» = GET /v1/admin/videos (total); {locales_texto}; con «{PREFIJO}»: "
            f"{VIDEO_A} y {VIDEO_B} ({total_q} = total con q); "
            f"7.11 «{en_galeria_total} imágenes» = GET /v1/admin/images"
        )

    def abrir_lista_filtrada() -> None:
        """Deja 7.13 abierta y con `PREFIJO` en el buscador (para los pasos guiados)."""
        if not en_lista(comun.volcar_pantalla()):
            volver_al_panel()
            tocar_en_panel(ACCESO_VIDEOS)
            esperar("la lista de videos (7.13)", LIMITE_LISTA_S, en_lista)
        asegurar_busqueda(PREFIJO)

    def c3b_renombrar() -> str:
        preparar_datos()
        abrir_panel()
        video = ctx.videos[VIDEO_A]
        abrir_lista_filtrada()
        comun.esperar_enter(INSTRUCCION_C3B)
        fin = comun.reloj() + LIMITE_RENOMBRAR_S
        nombre = ""
        while True:
            d = detalle_video(video.id)
            nombre = str((d or {}).get("nombre") or "")
            if nombre == RENOMBRADO:
                break
            nodos = comun.volcar_pantalla()
            error = comun.primero(nodos, contiene=ERROR_RENOMBRAR)
            if error is not None:
                raise comun.Falla(f"la app mostró «{error.texto or error.descripcion}» al renombrar")
            if comun.reloj() >= fin:
                raise comun.Falla(
                    f"en {LIMITE_RENOMBRAR_S} s GET /v1/admin/videos/{{id}} sigue con nombre «{nombre}», "
                    f"no «{RENOMBRADO}»"
                )
            comun.dormir(1)
        ctx.renombrado = True
        return f"«{VIDEO_A}» renombrado en 7.14: GET /v1/admin/videos/{{id}} da nombre «{RENOMBRADO}»"

    def c2b_eliminar() -> str:
        preparar_datos()
        abrir_panel()
        video = ctx.videos[VIDEO_B]
        otro = RENOMBRADO if ctx.renombrado else VIDEO_A
        abrir_lista_filtrada()
        comun.esperar_enter(INSTRUCCION_C2B)

        def vuelta(ns: list[comun.Nodo]) -> bool:
            error = comun.primero(ns, dice=ERROR_ELIMINAR)
            if error is not None:
                mensaje = next((n.texto for n in ns if "se pudo eliminar el video" in n.texto and n != error), "")
                raise comun.Falla(f"la app mostró «{ERROR_ELIMINAR}»: «{mensaje}»")
            return en_lista(ns)

        esperar("la lista de videos (7.13) tras eliminar", LIMITE_VUELTA_S, vuelta)
        if detalle_video(video.id) is not None:
            raise comun.Falla(
                f"GET /v1/admin/videos/{{id}} de «{VIDEO_B}» sigue respondiendo 200: la app no lo eliminó"
            )
        asegurar_busqueda(PREFIJO)
        total_q = total_videos(PREFIJO)

        def sin_b(ns: list[comun.Nodo]) -> bool:
            filas = filas_videos(ns)
            return (
                not hay_fila(filas, VIDEO_B)
                and hay_fila(filas, otro)
                and total_en_pantalla(ns, PATRON_TOTAL_VIDEOS) == total_q
            )

        esperar(f"7.13 sin «{VIDEO_B}» (con «{otro}» y «{total_q} video»)", LIMITE_FILTRO_S, sin_b)
        volver_al_panel()
        tocar_en_panel(ACCESO_IMAGENES)
        esperar("la Galería (7.11)", LIMITE_LISTA_S, en_galeria)
        asegurar_busqueda(PREFIJO)
        imagenes_q = total_imagenes(PREFIJO)
        if total_imagenes(video_id=video.id) != 0:
            raise comun.Falla(f"GET /v1/admin/images?video_id=<{VIDEO_B}> sigue dando fotos")

        def galeria_sin_b(ns: list[comun.Nodo]) -> bool:
            if any(f"video {VIDEO_B}" in n.descripcion for n in ns):
                return False
            return total_en_pantalla(ns, PATRON_TOTAL_IMAGENES) == imagenes_q

        esperar(
            f"la Galería con «{PREFIJO}»: «{imagenes_q} imágenes» y ninguna de «{VIDEO_B}»",
            LIMITE_FILTRO_S,
            galeria_sin_b,
        )
        volver_al_panel()
        return (
            f"«{VIDEO_B}» eliminado en 7.14: la app volvió sola a 7.13, que ya no lo lista (sí «{otro}»; "
            f"{total_q} = total con q); GET /v1/admin/videos/{{id}} -> 404; la Galería con «{PREFIJO}» muestra "
            f"{imagenes_q} imágenes (= GET /v1/admin/images?q=) y ninguna de «{VIDEO_B}», sin reiniciar la app"
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        telefono = ("C1b", "C3b", "C2b")
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = [
                ("P2", p2_dispositivo),
                ("P3", p3_api),
                ("P4", p4_login_admin),
                ("P5", p5_fe21),
                ("P6", p6_be41),
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

        local("C1a", c1a)
        local("C2a", c2a)
        local("C3a", c3a)

        def en_telefono(id_: str, fn: Callable[[], str]) -> None:
            if not dev:
                v.omitir(id_, "solo en dev (necesita el dispositivo y el backend)")
            elif not v.incluida(id_):
                v.comprobacion(id_, fn)  # el Validador la marca omitida (--solo)
            elif ctx.fallo_previo:
                v.omitir(id_, f"no se hace: falló {ctx.fallo_previo} (corrige y repite)")
            else:
                v.comprobacion(id_, fn)

        en_telefono("C1b", c1b_contadores)
        en_telefono("C3b", c3b_renombrar)
        en_telefono("C2b", c2b_eliminar)
        v.manual("C2c", INSTRUCCION_C2C)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
