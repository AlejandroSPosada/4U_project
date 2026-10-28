"""Validador de FE-3.2 — Ubicación real y Resultado (6.3).

Documento: FRONTEND_KOTLIN/docs/validation/validation-3-2.md. Entornos: local (C1a, C2, C3a y C4a: pruebas en la JVM
y una comprobación estática; sin teléfono ni backend) y dev (además, con un dispositivo físico y la API de dev: C1b,
paso guiado con `embedding` encendido —lo enciende si hace falta y lo apaga al terminar si lo encendió—; C4b, paso
guiado con `embedding` apagado; y C3b, que no quedan fotos de escaneo en el teléfono). C1 (los 10 puntos del campus) y
C4 (el mensaje hablado) dejan además evidencia manual (C1c y C4c). Las precondiciones de otros lotes (FE-3.1 y BE-3.2
«Hecho», la sonda de POST /v1/localize y un dataset con fotos procesadas) dan código 2. Nunca imprime contraseñas ni
tokens, ni posiciones de la persona (app.log no las tiene).
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field

import comun

CLASES_C1A = ["RemoteLocalizacionRepositoryTest", "DescribirUbicacionTest", "SesionDeNavegacionTest"]
CLASES_C2 = ["ConversionRumboTest"]
CLASES_C3A = ["FotosEscaneoTest"]
CLASES_C4A = ["ErrorEscaneoTest"]
MINIMO_CASOS = {
    "RemoteLocalizacionRepositoryTest": 8,
    "DescribirUbicacionTest": 8,
    "SesionDeNavegacionTest": 4,
    "ConversionRumboTest": 5,
    "FotosEscaneoTest": 4,
    "ErrorEscaneoTest": 5,
}
DIR_KOTLIN = comun.PROYECTO / "app" / "src" / "main" / "java" / "com" / "example" / "myapplication"
ESCANEO_VM = DIR_KOTLIN / "ui" / "ubicacion" / "EscaneoViewModel.kt"
PATRON_CONSERVAR = re.compile(
    r"^\s*(?:(?:private|internal)\s+)?const\s+val\s+CONSERVAR_FOTOS\s*=\s*(true|false)\b", re.MULTILINE
)
DIR_FOTOS = "files/camera/photos"  # crearCarpetaEscaneo (ARCHITECTURE §5.2)
PATRON_CARPETA = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})$")
# Una línea de files/logs/app.log (AppLog, ARCHITECTURE §3.2): «AAAA-MM-DD HH:MM:SS.mmm N/Tag [hilo] [sesión] texto».
PATRON_LINEA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d{3} ([DIWE])/(\S+) \[[^\]]*\] \[([^\]]*)\] (.*)$")
PATRON_RESULTADO = re.compile(r"^Resultado: (ok|sin_coincidencias)\b(.*)$")  # EscaneoVM (ARCHITECTURE §5.2)
PATRON_LOCALIZE = re.compile(r"POST /v1/localize -> (\S+)")  # RequestIdInterceptor (§5.10)
PATRON_INSTALACION = re.compile(r"lastUpdateTime=(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
ERROR_C4 = "Escaneo en ERROR: SERVICIO_NO_DISPONIBLE"
MENSAJE_C4 = "El servicio de ubicación no está disponible en este momento"  # ErrorEscaneo (ARCHITECTURE §5.10)
PERMISOS_INICIO = ["android.permission.CAMERA", "android.permission.RECORD_AUDIO"]
PERMISO_ACTIVIDAD = "android.permission.ACTIVITY_RECOGNITION"  # Permisos.INICIALES desde Android 10 (SDK 29)
LIMITE_INICIO_S = 30
HORA_LIMITE_C1 = (20, 45)  # Bogotá: después no se enciende embedding (hasta 10 min + 60 de C1 antes de las 22:00)
MINIMO_PUNTOS_C1 = 10
LIMITE_APAGADO_S = 300  # C4b: espera a que /v1/health/ready diga no_disponible tras apagarlo el validador
PAUSA_APAGADO_S = 15
MAX_PAGINAS_VIDEOS = 20

INSTRUCCION_C1B = (
    f"En el campus, en cada uno de {MINIMO_PUNTOS_C1} puntos conocidos con dataset (junto a lugares de la lista de "
    "arriba): desde Inicio di «uno» (si no escucha, toca el botón principal y dilo), da la vuelta completa y escucha "
    "el Resultado; anota para C1c el punto, el lugar esperado, lo que dijo la app, la confianza y si pidió volver a "
    "ubicarse; vuelve con «Volver al inicio». Graba en video con audio al menos dos puntos. Cuando termines los "
    f"{MINIMO_PUNTOS_C1}, pulsa Enter aquí."
)
INSTRUCCION_C4B = (
    "Con embedding apagado: en el teléfono, desde Inicio di «uno» (si no escucha, toca el botón principal y dilo) y "
    f"da la vuelta completa grabando la pantalla con audio. Tras «Analizando…» la app debe decir «{MENSAJE_C4}» y "
    "seguir abierta. Después pulsa Enter aquí."
)


@dataclass
class LineaLog:
    hora: str  # «AAAA-MM-DD HH:MM:SS», hora del teléfono
    nivel: str
    tag: str
    sesion: str
    texto: str


@dataclass
class Contexto:
    url: str = ""
    token: str = ""
    sdk: int = 0
    cluster: str = ""
    servicios: dict = field(default_factory=dict)
    embedding: comun.EmbeddingDev | None = None
    encendido_por_mi: bool = False
    apagado_por_mi: bool = False
    telefono_listo: bool = False
    gradle: comun.Resultado | None = None
    fallo_previo: str = ""  # la primera automática local que falló (entonces no se hacen los pasos guiados)
    resultados_c1: list[dict] = field(default_factory=list)


# --- piezas puras ----------------------------------------------------------------------------------------------


def lineas_log(texto: str, desde: str = "") -> list[LineaLog]:
    """Las líneas de app.log (sin las de una traza) con hora ≥ `desde` («AAAA-MM-DD HH:MM:SS»; vacío = todas)."""
    salida = []
    for linea in texto.splitlines():
        m = PATRON_LINEA.match(linea)
        if m and m.group(1) >= desde:
            salida.append(LineaLog(*m.groups()))
    return salida


def resultados_escaneo(lineas: list[LineaLog]) -> list[dict]:
    """Las líneas `Resultado: …` de EscaneoVM (una por `200` de POST /v1/localize) como diccionarios:
    `hora`, `resultado` y los pares `clave=valor` que traigan (`nivel`, `confianza`, `cercano`, `referencias`…)."""
    salida = []
    for linea in lineas:
        if linea.tag != "EscaneoVM" or linea.nivel != "I":
            continue
        m = PATRON_RESULTADO.match(linea.texto)
        if not m:
            continue
        datos = {"hora": linea.hora, "resultado": m.group(1)}
        datos.update(dict(re.findall(r"(\w+)=(\S+)", m.group(2))))
        salida.append(datos)
    return salida


def resumen_resultados(resultados: list[dict]) -> str:
    """«10 resultados (alta 6, media 2, baja 1, sin_coincidencias 1)»."""
    cuentas: dict[str, int] = {}
    for r in resultados:
        clave = r.get("nivel", "?") if r["resultado"] == "ok" else "sin_coincidencias"
        cuentas[clave] = cuentas.get(clave, 0) + 1
    orden = ["alta", "media", "baja", "sin_coincidencias"]
    partes = [f"{k} {cuentas[k]}" for k in orden + sorted(set(cuentas) - set(orden)) if k in cuentas]
    return f"{len(resultados)} resultados ({', '.join(partes)})" if partes else "0 resultados"


def hora_de_carpeta(nombre: str) -> str | None:
    """`2026-10-26_14-03-12` → «2026-10-26 14:03:12»; None si no es una carpeta de escaneo."""
    m = PATRON_CARPETA.match(nombre)
    return f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}" if m else None


def comprobar_conservar(texto: str) -> str:
    """C3a (estático): EscaneoViewModel.kt declara `CONSERVAR_FOTOS = false` (una sola vez). Si no → Falla."""
    valores = PATRON_CONSERVAR.findall(texto)
    if not valores:
        raise comun.Falla("EscaneoViewModel.kt no declara const val CONSERVAR_FOTOS")
    if len(valores) > 1:
        raise comun.Falla(f"EscaneoViewModel.kt declara CONSERVAR_FOTOS {len(valores)} veces")
    if valores[0] != "false":
        raise comun.Falla("EscaneoViewModel.kt declara CONSERVAR_FOTOS = true (las fotos de escaneo se conservarían)")
    return "CONSERVAR_FOTOS = false"


def suma_procesadas(items: list) -> int:
    """Fotos `procesada` de los videos de una página de GET /v1/admin/videos, sin los de prueba (`validacion…`)."""
    total = 0
    for v in items:
        if not isinstance(v, dict) or str(v.get("nombre") or "").startswith("validacion"):
            continue
        conteo = v.get("conteo") if isinstance(v.get("conteo"), dict) else {}
        n = conteo.get("procesada")
        total += n if isinstance(n, int) else 0
    return total


def instruccion_c1(contexto: str) -> str:
    prefijo = f"[{contexto}] " if contexto else ""
    return (
        f"{prefijo}Tabla de los {MINIMO_PUNTOS_C1} puntos (punto, lugar esperado, lo que dijo la app, nivel de "
        "confianza, si pidió volver a ubicarse) y video con audio de al menos dos; en cada punto la app dice el lugar "
        "correcto o, con confianza baja, lo dice y ofrece «Volver a ubicarme». Evidencia en "
        "docs/validation/evidencia/fe-3-2/ (un video que muestre algo privado se cita en el PR); procedimiento en "
        "validation-3-2 §3"
    )


def instruccion_c4(contexto: str) -> str:
    prefijo = f"[{contexto}] " if contexto else ""
    return (
        f"{prefijo}Con embedding apagado, Inicio → «uno» → vuelta completa: tras «Analizando…» la app dice "
        f"«{MENSAJE_C4}» y no se cierra. Evidencia: video con audio (c4-video.mp4, citado en el PR si muestra algo "
        "privado); procedimiento en validation-3-2 §3"
    )


# --- validador ---------------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-3.2",
        validacion="validation-3-2",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C2", "C3a", "C3b", "C4a", "C4b"],
        grupos={"C1": ["C1a", "C1b"], "C3": ["C3a", "C3b"], "C4": ["C4a", "C4b"]},
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

    def p3_fe31() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-3.1"):
            raise comun.Bloqueo("FE-3.1 no está «Hecho» en PLAN.md §3")
        return "FE-3.1 Hecho"

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

    def p6_be32() -> str:
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.2"):
            raise comun.Bloqueo("BE-3.2 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3")
        # Sonda: solo `metadatos`, sin fotos → 400 FOTOS_INVALIDAS (backend §5.3: se rechaza antes de procesar nada).
        metadatos = json.dumps({"rumbos": [], "origen": "escaneo", "app_version": "validacion-3-2"}).encode()
        parte = comun.ParteMultipart("metadatos", metadatos, "application/json")
        try:
            r = comun.http_post_multipart(f"{ctx.url}/localize", [parte])
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"BE-3.2: POST /v1/localize sin respuesta ({e})") from e
        if r.estado != 400 or comun.codigo_error(r) != "FOTOS_INVALIDAS":
            codigo = f"{r.estado} {comun.codigo_error(r) or ''}".rstrip()
            raise comun.Bloqueo(
                f"BE-3.2: POST /v1/localize sin fotos respondió {codigo} (se esperaba 400 FOTOS_INVALIDAS)"
            )
        procesadas = dataset_procesado()
        if procesadas < 1:
            raise comun.Bloqueo("BE-3.2: el dataset no tiene ninguna foto procesada (GET /v1/admin/videos)")
        return (
            f"BE-3.2 Hecho; POST /v1/localize sin fotos -> 400 FOTOS_INVALIDAS; dataset con {procesadas} fotos "
            "procesadas"
        )

    def dataset_procesado() -> int:
        """Suma de `conteo.procesada` de GET /v1/admin/videos (BE-2.1), sin los videos de prueba."""
        total = 0
        for pagina in range(1, MAX_PAGINAS_VIDEOS + 1):
            r = comun.http_get(f"{ctx.url}/admin/videos?por_pagina=100&pagina={pagina}", token=ctx.token)
            cuerpo = r.json()
            if r.estado != 200 or not isinstance(cuerpo, dict):
                raise comun.Bloqueo(f"BE-2.1: GET /v1/admin/videos respondió {r.estado} {comun.codigo_error(r) or ''}")
            items = cuerpo.get("items") or []
            total += suma_procesadas(items)
            if total > 0 or len(items) < 100:
                return total
        return total

    def p7_embedding() -> str:
        arn = comun.cuenta_aws()
        outputs = comun.terraform_outputs()
        faltan = [k for k in ("ecs_cluster", "ecs_servicios") if not outputs.get(k)]
        if faltan:
            raise comun.Bloqueo(f"INF-1.3: faltan los outputs {', '.join(faltan)}")
        ctx.cluster = str(outputs["ecs_cluster"])
        servicios = outputs["ecs_servicios"]
        ctx.servicios = servicios if isinstance(servicios, dict) else {}
        ctx.embedding = comun.EmbeddingDev(ctx.cluster, *nombres_servicios())
        cuenta = arn.rsplit(":", 1)[-1]
        if salud_lista().get("embedding") == "ok":
            ctx.embedding.latido()
            return f"cuenta {comun.CUENTA} ({cuenta}); embedding ya estaba encendido (latido publicado)"
        ahora = comun.hora_bogota()
        if (ahora.hour, ahora.minute) >= HORA_LIMITE_C1:
            raise comun.ErrorConfiguracion(
                f"son las {ahora:%H:%M} en Bogotá: después de las {HORA_LIMITE_C1[0]}:{HORA_LIMITE_C1[1]:02d} no se "
                "enciende embedding para C1 (60 min antes de que se apague a las 22:00). Repite mañana, o corre solo "
                "C4 de noche (--solo C4)"
            )
        ctx.embedding.comprobar_inf21()
        # Antes de encender: la limpieza lo apaga aunque el encendido falle a medias (infra §5.11).
        ctx.encendido_por_mi = True
        v.al_limpiar("apagar embedding (lo encendió el validador)", ctx.embedding.apagar)
        comun.avisar("encendiendo embedding (3–6 min; infra §5.10)")
        segundos = ctx.embedding.encender(lambda: salud_lista().get("embedding") == "ok")
        return f"cuenta {comun.CUENTA} ({cuenta}); embedding encendido por el validador en {segundos:.0f} s"

    def nombres_servicios() -> tuple[str, str]:
        return str(ctx.servicios.get("embedding") or "embedding"), str(ctx.servicios.get("worker") or "worker")

    def salud_lista() -> dict:
        try:
            r = comun.http_get(f"{ctx.url}/health/ready")
        except comun.ErrorRed as e:
            raise comun.Bloqueo(f"BE-1.1: GET /v1/health/ready sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict):
            raise comun.Bloqueo(f"BE-1.2: GET /v1/health/ready respondió {r.estado} {comun.codigo_error(r) or ''}")
        return cuerpo

    # --- teléfono ----------------------------------------------------------------------------------------------

    def preparar_telefono() -> None:
        """Una vez: `installDebug` (conserva los datos) y `pm grant` de los permisos de Inicio (como validate31)."""
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

    def hora_telefono() -> str:
        r = comun.adb("shell", "date", "+%Y-%m-%d_%H:%M:%S", timeout=30)
        hora = r.salida.strip().replace("_", " ")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", hora):
            raise comun.Falla(f"adb shell date no dio la hora del teléfono: {comun.resumir(r.texto, 120)}")
        return hora

    def abrir_en_inicio() -> str:
        """Abre la app en Inicio (arranque en frío) y devuelve la hora del teléfono justo antes."""
        desde = hora_telefono()
        comun.abrir_app()
        comun.esperar_nodo(
            lambda ns: comun.primero(ns, dice="Acceso administrador"),
            LIMITE_INICIO_S,
            "Inicio («Acceso administrador»)",
        )
        return desde

    def leer_log(desde: str) -> list[LineaLog]:
        return lineas_log(comun.leer_archivo_app(comun.LOG_APP) or "", desde)

    def app_viva() -> bool:
        return bool(comun.adb("shell", "pidof", comun.PAQUETE, timeout=30).salida.strip())

    # --- comprobaciones ----------------------------------------------------------------------------------------

    def pruebas() -> comun.Resultado:
        if ctx.gradle is None:
            clases = (
                [c for c in CLASES_C1A if v.incluida("C1a")]
                + [c for c in CLASES_C2 if v.incluida("C2")]
                + [c for c in CLASES_C3A if v.incluida("C3a")]
                + [c for c in CLASES_C4A if v.incluida("C4a")]
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

    def local(id_: str, fn) -> None:
        """Una comprobación que corre también en local; si falla, se anota para no hacer los pasos guiados."""

        def envuelta() -> str:
            try:
                return fn()
            except Exception:
                ctx.fallo_previo = ctx.fallo_previo or id_
                raise

        v.comprobacion(id_, envuelta)

    def c3a_conservar() -> str:
        try:
            texto = ESCANEO_VM.read_text(encoding="utf-8")
        except OSError as e:
            raise comun.Falla(f"no se pudo leer {ESCANEO_VM.name}: {e}") from e
        estatico = comprobar_conservar(texto)
        return f"{estatico}; {pruebas_clases(CLASES_C3A)}"

    def c1b_campus() -> str:
        preparar_telefono()
        lugares = lugares_publicos()
        comun.avisar(f"lugares de GET /v1/places ({len(lugares)}): {', '.join(lugares) or '—'}")
        comun.avisar(f"embedding: {salud_lista().get('embedding')}")
        desde = abrir_en_inicio()
        comun.esperar_enter(INSTRUCCION_C1B)
        lineas = leer_log(desde)
        resultados = resultados_escaneo(lineas)
        ctx.resultados_c1 = resultados
        for r in resultados:
            comun.avisar(
                f"{r['hora']} {r['resultado']} nivel={r.get('nivel', '-')} confianza={r.get('confianza', '-')} "
                f"cercano={r.get('cercano', '-')} referencias={r.get('referencias', '-')}"
            )
        errores = [ln.texto for ln in lineas if ln.tag == "EscaneoVM" and ln.texto.startswith("Escaneo en ERROR")]
        if ctx.encendido_por_mi and ctx.embedding is not None:
            ctx.embedding.apagar()
            ctx.apagado_por_mi = True
            comun.avisar("embedding apagado (lo encendió el validador)")
        extra = f"; {len(errores)} errores ({', '.join(e.split(': ', 1)[-1] for e in errores[:5])})" if errores else ""
        if len(resultados) < MINIMO_PUNTOS_C1:
            raise comun.Falla(
                f"solo {resumen_resultados(resultados)} de POST /v1/localize en app.log desde las {desde} "
                f"(mínimo {MINIMO_PUNTOS_C1}){extra}"
            )
        return f"{resumen_resultados(resultados)} desde las {desde}{extra}"

    def lugares_publicos() -> list[str]:
        try:
            r = comun.http_get(f"{ctx.url}/places")
        except comun.ErrorRed as e:
            raise comun.Falla(f"GET /v1/places sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict):
            raise comun.Falla(f"GET /v1/places respondió {r.estado}")
        return [str(i.get("nombre")) for i in cuerpo.get("items") or [] if isinstance(i, dict)]

    def esperar_embedding_apagado() -> str:
        fin = comun.reloj() + (LIMITE_APAGADO_S if ctx.apagado_por_mi else 0)
        while True:
            estado = salud_lista().get("embedding")
            if estado != "ok":
                return str(estado)
            if comun.reloj() >= fin:
                if ctx.apagado_por_mi:
                    raise comun.Falla(f"embedding sigue encendido {LIMITE_APAGADO_S} s después de apagarlo")
                raise comun.ErrorConfiguracion(
                    "embedding está encendido (no lo encendió este validador): repite con --solo C4 cuando se "
                    "apague solo (45 min sin uso o a las 22:00 de Bogotá) o, si nadie más lo usa, apágalo con "
                    "embedding.py apagar (infra §5.11)"
                )
            comun.dormir(PAUSA_APAGADO_S)

    def c4b_no_disponible() -> str:
        estado = esperar_embedding_apagado()
        preparar_telefono()
        desde = abrir_en_inicio()
        comun.esperar_enter(INSTRUCCION_C4B)
        lineas = leer_log(desde)
        codigos = []
        for ln in lineas:
            m = PATRON_LOCALIZE.search(ln.texto) if ln.tag == "Api" else None
            if m:
                codigos.append(m.group(1))
        if not codigos:
            raise comun.Falla(
                f"app.log no tiene ninguna línea «POST /v1/localize» desde las {desde}: ¿se completó la vuelta?"
            )
        if "200" in codigos:
            raise comun.Falla(f"POST /v1/localize respondió 200 ({', '.join(codigos)}): embedding no estaba apagado")
        if not any(ln.tag == "EscaneoVM" and ln.texto.startswith(ERROR_C4) for ln in lineas):
            raise comun.Falla(f"app.log no tiene «{ERROR_C4}» desde las {desde} (POST /v1/localize -> {codigos[-1]})")
        if any(ln.tag == "CRASH" for ln in lineas) or not app_viva():
            raise comun.Falla("la app se cerró (línea CRASH en app.log o sin proceso)")
        return (
            f"embedding {estado}; POST /v1/localize -> {codigos[-1]}; {ERROR_C4.split(': ', 1)[1]} "
            f"(«{MENSAJE_C4}»); la app sigue abierta"
        )

    def hora_instalacion() -> str:
        r = comun.adb("shell", "dumpsys", "package", comun.PAQUETE, timeout=60)
        m = PATRON_INSTALACION.search(r.salida)
        if not m:
            raise comun.Falla(f"{comun.PAQUETE} no está instalada (dumpsys package sin lastUpdateTime)")
        return m.group(1)

    def c3b_sin_fotos() -> str:
        instalacion = hora_instalacion()
        lineas = leer_log(instalacion)
        sesiones = sorted({ln.sesion for ln in lineas if ln.tag == "EscaneoVM" and ln.sesion.startswith("scan-")})
        if not sesiones:
            raise comun.Falla(
                f"app.log no tiene ninguna sesión [scan-…] desde la instalación ({instalacion}): haz una vuelta (C1 o "
                "C4) y repite con --solo C3"
            )
        borrados = sum(
            1 for ln in lineas if ln.tag == "EscaneoVM" and ln.texto.startswith("Fotos del escaneo borradas")
        )
        carpetas = comun.listar_archivos_app(DIR_FOTOS) or []
        posteriores = [c for c in carpetas if (hora_de_carpeta(c) or "") >= instalacion]
        con_fotos = []
        for nombre in posteriores:
            jpg = [a for a in comun.listar_archivos_app(f"{DIR_FOTOS}/{nombre}") or [] if a.lower().endswith(".jpg")]
            if jpg:
                con_fotos.append(f"{nombre} ({len(jpg)} .jpg)")
        if con_fotos:
            raise comun.Falla(f"quedan fotos de escaneo en el teléfono: {', '.join(con_fotos[:5])}")
        return (
            f"{len(sesiones)} sesiones [scan-…] desde la instalación ({instalacion}), {borrados} borrados registrados; "
            f"{len(posteriores)} carpetas de escaneo posteriores, ninguna con .jpg"
        )

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            pasos = []
            if v.alguna_incluida("C1b", "C3b", "C4b"):
                pasos.append(("P2", p2_dispositivo, ""))
            else:
                v.precondicion_no_evaluada("P2", "C1b, C3b y C4b excluidas con --solo")
            if v.alguna_incluida("C1b", "C4b"):
                pasos += [("P3", p3_fe31, ""), ("P4", p4_api, ""), ("P5", p5_login_admin, ""), ("P6", p6_be32, "")]
            else:
                for id_ in ("P3", "P4", "P5", "P6"):
                    v.precondicion_no_evaluada(id_, "C1b y C4b excluidas con --solo")
            if v.incluida("C1b"):
                pasos.append(("P7", p7_embedding, ""))
            else:
                v.precondicion_no_evaluada("P7", "C1b excluida con --solo (embedding solo hace falta encendido en C1)")
            for i, (id_, fn, _) in enumerate(pasos):
                if not v.precondicion(id_, fn):
                    for siguiente, _, _ in pasos[i + 1 :]:
                        v.precondicion_no_evaluada(siguiente, f"{id_} no se cumple")
                    return

        local("C1a", lambda: pruebas_clases(CLASES_C1A))
        local("C2", lambda: pruebas_clases(CLASES_C2))
        local("C3a", c3a_conservar)
        local("C4a", lambda: pruebas_clases(CLASES_C4A))
        guiadas = [("C1b", c1b_campus), ("C4b", c4b_no_disponible), ("C3b", c3b_sin_fotos)]
        for id_, fn in guiadas:
            if not dev:
                v.omitir(id_, "solo en dev (necesita el dispositivo y el backend)")
            elif ctx.fallo_previo and v.incluida(id_):
                v.omitir(id_, f"no se hace: falló {ctx.fallo_previo} (corrige y repite)")
            else:
                v.comprobacion(id_, fn)
        if ctx.telefono_listo:
            contexto = "APK de este commit instalado por el validador"
        else:
            contexto = "antes, instalar el APK de este commit (installDebug, validation-3-2 §5)"
        v.manual("C1c", instruccion_c1(contexto))
        v.manual("C4c", instruccion_c4(contexto))

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
