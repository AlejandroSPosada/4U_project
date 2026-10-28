"""Validador de FE-5.1 — Grafo y rutas (la «App 1» de la guía en tiempo real).

Documento: FRONTEND_KOTLIN/docs/validation/validation-5-1.md. Entornos: local (C1a, C1b, C2a, C3a y C4a: pruebas de la
JVM y comprobaciones estáticas de `assets/grafo.json`, sin teléfono ni red) y dev (además C3b: cada `lugar` del grafo
existe en `GET /v1/places`, ruta pública; y C4b: con el teléfono **en casa**, el mapa público del APK de depuración
abierto con un destino y una posición de prueba muestra la ruta y su primera instrucción, y un paso guiado —tocar otro
punto del mapa— la recalcula). No escribe nada en el backend, no usa `embedding` y en el teléfono no borra nada
(nunca `pm clear`).
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field

import comun

CLASES_C1A = ["LectorGrafoTest"]
CLASES_C2A = ["ProyeccionRutaTest", "InstruccionesTest"]
CLASES_C3A = ["EmparejamientoTest"]
CLASES_C4A = ["PlanificadorTest", "RutaEnMapaTest"]
CLASES_POR_COMPROBACION = {"C1a": CLASES_C1A, "C2a": CLASES_C2A, "C3a": CLASES_C3A, "C4a": CLASES_C4A}
MINIMO_CASOS = {
    "LectorGrafoTest": 6,
    "ProyeccionRutaTest": 7,
    "InstruccionesTest": 6,
    "EmparejamientoTest": 3,
    "PlanificadorTest": 5,
    "RutaEnMapaTest": 3,
}

DIR_APP = comun.PROYECTO / "app" / "src" / "main"
DIR_KOTLIN = DIR_APP / "java" / "com" / "example" / "myapplication"
DIR_ASSETS = DIR_APP / "assets"
GRAFO = DIR_ASSETS / "grafo.json"
APP_JS = DIR_ASSETS / "app.js"
MAIN_ACTIVITY = DIR_KOTLIN / "MainActivity.kt"
FORMATO_GRAFO = 1
TIPOS_NODO = ("cruce", "entrada")

# Paso en casa (C4b): la misma posición y destino que PlanificadorTest (ruta n0008 → n0002 → n0007, ~59,7 m).
DESTINO_PRUEBA = "bloque35"  # sin espacios: así pasa por `adb shell am start --es` sin comillas
POSICION_PRUEBA = (6.201434, -75.578427)  # sobre la arista n0008–n0014 del grafo
TITULO_ESPERADO = "Ruta a Bloque 35: 60 m por el camino"
PRIMERA_ESPERADA = "Camina 45 metros por el camino."
PREFIJO_AVISO = "Ruta a "
PREFIJO_DESTINO = "Ruta a Bloque 35: "
TEXTOS_SIN_RUTA = ("Destino: ", "No tengo un camino", "No encontré un camino", "Rutas desactivadas")
LIMITE_RUTA_S = 30  # arranque en frío + Leaflet desde unpkg.com + teselas
LIMITE_TOQUE_S = 15
PATRON_METROS = re.compile(r": (\d+) m por el camino$")

INSTRUCCION_C4B = (
    "En el teléfono se ve el mapa público con la ruta verde hasta Bloque 35 y, arriba, «"
    + TITULO_ESPERADO
    + "». Toca OTRO punto del mapa, a uno o dos dedos del punto azul (no pulses ▶), y espera a que el aviso de "
    "arriba cambie de distancia."
)
INSTRUCCION_C4C = (
    "Captura del mapa con la ruta y el aviso, tomada en el paso guiado de C4b antes de pulsar Enter "
    "(`adb exec-out screencap -p > c4c-mapa-ruta.png`), en validation/evidencia/fe-5-1/. Sin datos privados: el mapa "
    "muestra el campus y la posición de prueba, no la de la persona."
)


# --- piezas puras --------------------------------------------------------------------------------------------------


def normalizar(texto: str) -> str:
    """Como `EmparejarLugares.normalizar` de la app: minúsculas, sin tildes y solo letras y números."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", sin_tildes)


@dataclass
class ResumenGrafo:
    version: int
    nodos: int
    aristas: int
    entradas: int
    lugares: list[str]
    metros: float
    bloqueadas: int


def componentes(ids: list[str], aristas: list[tuple[str, str]]) -> list[set[str]]:
    """Componentes conexos (todas las aristas), el más grande primero."""
    vecinos: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in aristas:
        if a in vecinos and b in vecinos:
            vecinos[a].append(b)
            vecinos[b].append(a)
    visto: set[str] = set()
    resultado: list[set[str]] = []
    for inicio in ids:
        if inicio in visto:
            continue
        comp = {inicio}
        visto.add(inicio)
        pila = [inicio]
        while pila:
            for v in vecinos[pila.pop()]:
                if v not in visto:
                    visto.add(v)
                    comp.add(v)
                    pila.append(v)
        resultado.append(comp)
    return sorted(resultado, key=len, reverse=True)


def revisar_grafo(texto: str) -> ResumenGrafo:
    """Las reglas de `LectorGrafo` (ARCHITECTURE §5.7) sobre el texto de `grafo.json`; la primera falla → Falla."""
    try:
        g = json.loads(texto)
    except json.JSONDecodeError as e:
        raise comun.Falla(f"grafo.json no es JSON ({e.msg}, línea {e.lineno})") from e
    if not isinstance(g, dict):
        raise comun.Falla("grafo.json: la raíz no es un objeto")
    if g.get("formato") != FORMATO_GRAFO:
        raise comun.Falla(f"grafo.json: formato {g.get('formato')!r} (se espera {FORMATO_GRAFO})")
    version = g.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise comun.Falla("grafo.json: sin version entera")
    nodos, aristas = g.get("nodos"), g.get("aristas")
    if not isinstance(nodos, list) or not isinstance(aristas, list) or not nodos:
        raise comun.Falla("grafo.json: sin listas «nodos» (no vacía) y «aristas»")
    errores: list[str] = []
    ids: list[str] = []
    lugares: list[str] = []
    entradas = 0
    for i, n in enumerate(nodos):
        if not isinstance(n, dict) or not isinstance(n.get("id"), str) or not isinstance(n.get("tipo"), str):
            errores.append(f"nodo #{i} sin id o tipo")
            continue
        lat, lng = n.get("lat"), n.get("lng")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (lat, lng)):
            errores.append(f"nodo {n['id']} sin lat/lng numéricos")
        elif not (-90 <= lat <= 90 and -180 <= lng <= 180):
            errores.append(f"nodo {n['id']} con coordenadas fuera de rango")
        ids.append(n["id"])
        if n["tipo"] == "entrada":
            entradas += 1
            lugar = n.get("lugar")
            if not isinstance(lugar, str) or not lugar.strip():
                errores.append(f"entrada {n['id']} sin lugar")
            elif lugar not in lugares:
                lugares.append(lugar)
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    errores += [f"id de nodo repetido: {i}" for i in repetidos]
    pares: list[tuple[str, str]] = []
    ids_aristas: list[str] = []
    metros = 0.0
    bloqueadas = 0
    for i, a in enumerate(aristas):
        if not isinstance(a, dict) or not all(isinstance(a.get(k), str) for k in ("id", "a", "b")):
            errores.append(f"arista #{i} sin id, a o b")
            continue
        ids_aristas.append(a["id"])
        for extremo in (a["a"], a["b"]):
            if extremo not in ids:
                errores.append(f"arista {a['id']}: nodo inexistente {extremo}")
        if a["a"] == a["b"]:
            errores.append(f"arista {a['id']} une un nodo consigo mismo")
        m = a.get("metros")
        if not isinstance(m, (int, float)) or isinstance(m, bool) or m <= 0:
            errores.append(f"arista {a['id']} sin metros > 0")
        else:
            metros += float(m)
        if a.get("bloqueada") is True:
            bloqueadas += 1
        pares.append((a["a"], a["b"]))
    errores += [f"id de arista repetido: {i}" for i in sorted({i for i in ids_aristas if ids_aristas.count(i) > 1})]
    comps = componentes(list(dict.fromkeys(ids)), pares)
    if len(comps) > 1:
        fuera = sorted(set().union(*comps[1:]))
        errores.append(f"{len(comps)} componentes; fuera del principal: {', '.join(fuera[:10])}")
    if entradas == 0:
        errores.append("ninguna entrada")
    if errores:
        raise comun.Falla(f"grafo.json inválido: {'; '.join(errores[:6])}")
    return ResumenGrafo(version, len(nodos), len(aristas), entradas, lugares, metros, bloqueadas)


@dataclass
class Emparejamiento:
    exactos: list[str] = field(default_factory=list)
    normalizados: dict[str, str] = field(default_factory=dict)  # lugar del grafo → nombre en el backend
    faltan: list[str] = field(default_factory=list)


def emparejar(lugares_grafo: list[str], lugares_backend: list[dict]) -> Emparejamiento:
    """Como `EmparejarLugares.emparejar`: por `nombre` exacto o, si no, por `nombre` o un `alias` normalizado."""
    e = Emparejamiento()
    nombres = [str(lugar.get("nombre") or "") for lugar in lugares_backend]
    claves: list[tuple[str, set[str]]] = []
    for lugar in lugares_backend:
        alias = lugar.get("alias") if isinstance(lugar.get("alias"), list) else []
        textos = [str(lugar.get("nombre") or "")] + [str(a) for a in alias]
        claves.append((str(lugar.get("nombre") or ""), {normalizar(t) for t in textos if normalizar(t)}))
    for lg in lugares_grafo:
        if lg in nombres:
            e.exactos.append(lg)
            continue
        casa = next((nombre for nombre, cs in claves if normalizar(lg) in cs), None)
        if casa is None:
            e.faltan.append(lg)
        else:
            e.normalizados[lg] = casa
    return e


def aviso_en_pantalla(nodos: list[comun.Nodo]) -> tuple[str, str | None] | None:
    """El aviso de ruta del mapa (Compose, encima del `WebView`): `(título, detalle)`; `None` si no se ve. El detalle es
    el primer texto de la app después del título (la primera instrucción)."""
    de_la_app = comun.de_la_app(nodos)
    for i, n in enumerate(de_la_app):
        if n.texto.startswith(PREFIJO_AVISO) or n.texto.startswith(TEXTOS_SIN_RUTA):
            detalle = next((m.texto for m in de_la_app[i + 1 :] if m.texto.strip()), None)
            return n.texto, detalle
    return None


def comprobar_modo_prueba(archivos_kotlin: dict[str, str], main_activity: str, app_js: str) -> str:
    """Estática de C4a: los datos de prueba del mapa solo los fija `MainActivity` tras `rutaDePrueba` (que exige
    `FLAG_DEBUGGABLE`), y `app.js` tiene `onNativeRuta`, `onNativeInicio` y avisa con `listo`."""
    usos = [ruta for ruta, texto in archivos_kotlin.items() if "PruebaMapa.fijar(" in texto]
    if usos != ["MainActivity.kt"]:
        raise comun.Falla(f"PruebaMapa.fijar( debe estar solo en MainActivity.kt; está en: {usos or 'ninguno'}")
    if main_activity.count("PruebaMapa.fijar(") != 1:
        raise comun.Falla("MainActivity.kt llama más de una vez a PruebaMapa.fijar(")
    funcion = re.search(r"fun rutaDePrueba\(.*?\n    \}", main_activity, re.DOTALL)
    if not funcion or "FLAG_DEBUGGABLE" not in funcion.group(0):
        raise comun.Falla("MainActivity.rutaDePrueba no comprueba FLAG_DEBUGGABLE")
    if not re.search(r'if \(rutaPrueba == "mapa"\) \{\s*PruebaMapa\.fijar\(', main_activity):
        raise comun.Falla('PruebaMapa.fijar( no está dentro de `if (rutaPrueba == "mapa")`')
    for patron, que in (
        (r"window\.onNativeRuta\s*=\s*function", "window.onNativeRuta"),
        (r"window\.onNativeInicio\s*=\s*function", "window.onNativeInicio"),
        (r"bridgeCall\(\s*'listo'\s*\)", "bridgeCall('listo')"),
    ):
        if not re.search(patron, app_js):
            raise comun.Falla(f"app.js no tiene {que}")
    return "PruebaMapa solo en MainActivity (APK depurable, ruta mapa); app.js con onNativeRuta, onNativeInicio y listo"


def metros_del_aviso(titulo: str) -> int | None:
    m = PATRON_METROS.search(titulo)
    return int(m.group(1)) if m else None


@dataclass
class Contexto:
    url: str | None = None
    pasaron: set[str] = field(default_factory=set)
    resumen: ResumenGrafo | None = None
    telefono_listo: bool = False


def main(argv: list[str] | None = None) -> int:
    v = comun.Validador(
        lote="FE-5.1",
        validacion="validation-5-1",
        descripcion=__doc__ or "",
        comprobaciones=["C1a", "C1b", "C2a", "C3a", "C3b", "C4a", "C4b"],
        grupos={"C1": ["C1a", "C1b"], "C2": ["C2a"], "C3": ["C3a", "C3b"], "C4": ["C4a", "C4b"]},
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

    def p4_lotes() -> str:
        if not comun.lote_hecho(comun.PLAN_APP.read_text(encoding="utf-8"), "FE-3.1"):
            raise comun.Bloqueo("FE-3.1 no está «Hecho» en PLAN.md §3 (lugares públicos)")
        if not comun.lote_hecho(comun.PLAN_BACKEND.read_text(encoding="utf-8"), "BE-3.1"):
            raise comun.Bloqueo("BE-3.1 no está «Hecho» en BACKEND_FASTAPI/docs/PLAN.md §3 (GET /v1/places)")
        return "FE-3.1 y BE-3.1 Hecho"

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

    def c1b() -> str:
        if not GRAFO.is_file():
            raise comun.Falla("no existe app/src/main/assets/grafo.json")
        ctx.resumen = revisar_grafo(GRAFO.read_text(encoding="utf-8"))
        r = ctx.resumen
        ctx.pasaron.add("C1b")
        return (
            f"assets/grafo.json v{r.version}: {r.nodos} nodos, {r.aristas} aristas ({r.bloqueadas} bloqueadas), "
            f"{r.entradas} entradas con lugar ({len(r.lugares)} lugares), {r.metros:.0f} m, un solo componente"
        )

    def c2a() -> str:
        detalle = jvm("C2a")
        ctx.pasaron.add("C2a")
        return detalle

    def c3a() -> str:
        return jvm("C3a")

    def c4a() -> str:
        archivos = {
            str(p.relative_to(DIR_KOTLIN)).replace("\\", "/"): p.read_text(encoding="utf-8")
            for p in sorted(DIR_KOTLIN.rglob("*.kt"))
        }
        estatica = comprobar_modo_prueba(
            archivos, MAIN_ACTIVITY.read_text(encoding="utf-8"), APP_JS.read_text(encoding="utf-8")
        )
        detalle = jvm("C4a")
        ctx.pasaron.add("C4a")
        return f"{estatica}; {detalle}"

    # --- dev -----------------------------------------------------------------------------------------------------

    def c3b() -> str:
        if ctx.resumen is None:
            ctx.resumen = revisar_grafo(GRAFO.read_text(encoding="utf-8"))
        try:
            r = comun.http_get(f"{ctx.url}/places")
        except comun.ErrorRed as e:
            raise comun.Falla(f"GET /v1/places sin respuesta ({e})") from e
        cuerpo = r.json()
        if r.estado != 200 or not isinstance(cuerpo, dict) or not isinstance(cuerpo.get("items"), list):
            raise comun.Falla(f"GET /v1/places respondió {r.estado} {comun.codigo_error(r) or ''}".rstrip())
        items = [i for i in cuerpo["items"] if isinstance(i, dict)]
        e = emparejar(ctx.resumen.lugares, items)
        partes = [f"exactos: {', '.join(e.exactos) or 'ninguno'}"]
        if e.normalizados:
            partes.append("normalizados: " + ", ".join(f"{k} → {v}" for k, v in e.normalizados.items()))
        resumen = f"GET /v1/places -> {len(items)} lugares; {'; '.join(partes)}"
        if e.faltan:
            raise comun.Falla(
                f"{len(e.faltan)} de {len(ctx.resumen.lugares)} lugares del grafo no existen en GET /v1/places: "
                f"{', '.join(e.faltan)} ({resumen})"
            )
        return f"los {len(ctx.resumen.lugares)} lugares del grafo existen en el backend ({resumen})"

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

    def abrir_mapa_de_prueba() -> None:
        lat, lng = POSICION_PRUEBA
        comun.adb("shell", "am", "force-stop", comun.PAQUETE, timeout=30)
        r = comun.adb(
            "shell", "am", "start", "-W", "-n", comun.ACTIVIDAD,
            "--es", "ruta", "mapa",
            "--es", "destino_prueba", DESTINO_PRUEBA,
            "--es", "posicion_prueba", f"{lat},{lng}",
            timeout=60,
        )  # fmt: skip
        if r.codigo != 0 or "Error" in r.texto:
            raise comun.Falla(f"am start falló: {comun.resumir(r.texto, 200)}")

    def c4b() -> str:
        preparar_telefono()
        abrir_mapa_de_prueba()

        def con_ruta(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            aviso = aviso_en_pantalla(nodos)
            if aviso is None or not aviso[0].startswith(PREFIJO_AVISO):
                return None
            return next(n for n in nodos if n.texto == aviso[0])

        try:
            _, nodos = comun.esperar_nodo(con_ruta, LIMITE_RUTA_S, f"el aviso «{PREFIJO_AVISO}…» en el mapa")
        except comun.Falla as e:
            aviso = aviso_en_pantalla(comun.volcar_pantalla())
            if aviso is not None:
                raise comun.Falla(
                    f"el mapa muestra «{aviso[0]}» en vez de la ruta (¿sin internet para Leaflet? ¿grafo inválido?)"
                ) from e
            raise
        titulo, detalle = aviso_en_pantalla(nodos) or ("", None)
        if titulo != TITULO_ESPERADO or detalle != PRIMERA_ESPERADA:
            raise comun.Falla(
                f"el aviso dice «{titulo}» / «{detalle}»; se esperaba «{TITULO_ESPERADO}» / «{PRIMERA_ESPERADA}» "
                "(PlanificadorTest)"
            )
        comun.esperar_enter(INSTRUCCION_C4B)

        def cambiado(nodos: list[comun.Nodo]) -> comun.Nodo | None:
            aviso = aviso_en_pantalla(nodos)
            if aviso is None or not aviso[0].startswith(PREFIJO_DESTINO) or aviso[0] == TITULO_ESPERADO:
                return None
            return next(n for n in nodos if n.texto == aviso[0])

        _, nodos = comun.esperar_nodo(cambiado, LIMITE_TOQUE_S, "un aviso de ruta distinto tras tocar el mapa")
        nuevo, nueva_primera = aviso_en_pantalla(nodos) or ("", None)
        if not nueva_primera:
            raise comun.Falla(f"tras tocar, el aviso «{nuevo}» no trae la primera instrucción")
        return (
            f"con {DESTINO_PRUEBA} y {POSICION_PRUEBA[0]},{POSICION_PRUEBA[1]}: «{titulo}» / «{detalle}»; "
            f"tras tocar otro punto: «{nuevo}» / «{nueva_primera}»"
        )

    # --- cuerpo --------------------------------------------------------------------------------------------------

    def cuerpo(v: comun.Validador) -> None:
        dev = v.entorno == "dev"
        if not v.precondicion("P1", p1_gradle):
            return
        if dev:
            usa_telefono = v.incluida("C4b")
            usa_api = v.incluida("C3b")
            if usa_telefono:
                if not v.precondicion("P2", p2_dispositivo):
                    for p in ("P3", "P4"):
                        v.precondicion_no_evaluada(p, "falló P2")
                    return
            else:
                v.precondicion_no_evaluada("P2", "C4b no está incluida")
            if usa_api:
                if not v.precondicion("P3", p3_api):
                    v.precondicion_no_evaluada("P4", "falló P3")
                    return
                if not v.precondicion("P4", p4_lotes):
                    return
            else:
                v.precondicion_no_evaluada("P3", "C3b no está incluida")
                v.precondicion_no_evaluada("P4", "C3b no está incluida")

        v.comprobacion("C1a", c1a)
        v.comprobacion("C1b", c1b)
        v.comprobacion("C2a", c2a)
        v.comprobacion("C3a", c3a)
        v.comprobacion("C4a", c4a)
        if not dev:
            v.omitir("C3b", "solo en dev (GET /v1/places)")
            v.omitir("C4b", "solo en dev (teléfono en casa)")
        else:
            v.comprobacion("C3b", c3b)
            fallidas = [c for c in ("C1b", "C4a") if v.incluida(c) and c not in ctx.pasaron]
            if fallidas:
                v.omitir("C4b", f"no se hace: falló {' y '.join(fallidas)}")
            else:
                v.comprobacion("C4b", c4b)
        v.manual("C4c", INSTRUCCION_C4C)

    return v.correr(cuerpo, argv)


if __name__ == "__main__":
    sys.exit(main())
