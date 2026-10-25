"""Validador de EMB-2.1 — Vectorización por lotes (docs/validation/validation-2-1.md).

    EMBEDDING_IMAGEN=<ecr_embedding_url>:<sha> \
        uv run --group ops python src/ops/validate21.py --entorno local

Solo `local`: arranca la imagen con `docker run` y llama a POST /v1/embed en localhost:8080. Cierra
el lote con EMBEDDING_IMAGEN = la imagen que embedding.yml publicó para el commit que se cierra.
Las imágenes sintéticas se generan en memoria con semilla fija; no escribe nada en disco salvo el
informe.
"""

from __future__ import annotations

import hashlib
import io
import json
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from itertools import count

import httpx
import numpy as np
from PIL import Image

from comun import (
    DIR_PROYECTO,
    PLAZO_ARRANQUE_S,
    PUERTO,
    URL_LOCAL,
    VERSION_VECTOR,
    ErrorConfiguracion,
    Falla,
    Lote,
    Paso,
    PrecondicionNoCumplida,
    borrar_contenedores,
    docker,
    ejecutar,
    en_marcha,
    entornos,
    imagen_local,
    logs_contenedor,
    puerto_ocupado,
)

CONTENEDOR_LOCAL = "validacion-emb21"
LOCAL = entornos("local")
DIR_DORADOS = DIR_PROYECTO / "tests" / "golden"
DIM = 384
LOTE_MAX = 8
TOLERANCIA = 1e-5
BYTES_MAX_IMAGEN = 4 * 1024 * 1024  # §5.7
BYTES_MAX_PETICION = 16 * 1024 * 1024
COLA_MAX_IMAGENES = 40
RETRY_AFTER_S = "5"
TIEMPO_PETICION_S = 300
MARGEN_C4_MS = 500
MARGEN_SUBIDA_S = 0.1  # C4: lo que puede tardar la alta en subir y entrar en la cola
INTENTOS = 3

_numero = count(1)


# --- Imágenes de prueba (en memoria, semilla fija) ------------------------------------------------


def sintetica(semilla: int, ancho: int = 640, alto: int = 480) -> bytes:
    """JPEG de `ancho` × `alto`: ruido de baja resolución ampliado (parece una foto borrosa)."""
    rng = np.random.default_rng(semilla)
    pixeles = rng.integers(0, 256, (alto // 16, ancho // 16, 3), dtype=np.uint8)
    imagen = Image.fromarray(pixeles).resize((ancho, alto), Image.Resampling.BICUBIC)
    salida = io.BytesIO()
    imagen.save(salida, "JPEG", quality=90)
    return salida.getvalue()


def ruido_png(lado: int, semilla: int) -> bytes:
    """PNG de ruido puro (no se comprime): ~3 bytes por píxel."""
    pixeles = np.random.default_rng(semilla).integers(0, 256, (lado, lado, 3), dtype=np.uint8)
    salida = io.BytesIO()
    Image.fromarray(pixeles).save(salida, "PNG", compress_level=1)
    return salida.getvalue()


def gif(semilla: int = 7) -> bytes:
    salida = io.BytesIO()
    Image.open(io.BytesIO(sintetica(semilla, 128, 96))).save(salida, "GIF")
    return salida.getvalue()


def jpeg_truncado(semilla: int = 3) -> bytes:
    datos = sintetica(semilla)
    return datos[: len(datos) // 2]


def doradas() -> list[dict]:
    """Entradas de tests/golden/esperados.json con sus bytes; `Falla` si no coinciden."""
    try:
        esperados = json.loads((DIR_DORADOS / "esperados.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Falla(f"no se pudo leer tests/golden/esperados.json: {error}") from error
    if esperados.get("version_vector") != VERSION_VECTOR:
        raise Falla(f"esperados.json es de {esperados.get('version_vector')}, no {VERSION_VECTOR}")
    entradas = []
    for entrada in esperados["imagenes"]:
        datos = (DIR_DORADOS / entrada["archivo"]).read_bytes()
        if hashlib.sha256(datos).hexdigest() != entrada["sha256"]:
            raise Falla(
                f"{entrada['archivo']} no es la imagen con la que se calcularon los dorados"
            )
        entradas.append({**entrada, "datos": datos})
    if len(entradas) != 5:
        raise Falla(f"tests/golden/ tiene {len(entradas)} imágenes de referencia, no 5")
    return entradas


# --- HTTP ----------------------------------------------------------------------------------------

Imagen = tuple[bytes, str]  # (bytes, tipo)


@dataclass
class Envio:
    respuesta: httpx.Response
    enviado: float  # time.monotonic() justo antes de enviar
    prioridad: str

    @property
    def cuerpo(self) -> dict:
        try:
            return self.respuesta.json()
        except ValueError as error:
            raise Falla(f"respuesta no JSON ({self.respuesta.status_code})") from error

    @property
    def codigo_error(self) -> str | None:
        return (self.cuerpo.get("error") or {}).get("codigo")

    def tiempo(self, nombre: str) -> float:
        return self.cuerpo["tiempos_ms"][nombre] / 1000

    @property
    def salida_de_cola(self) -> float:
        """Instante (reloj del validador) en que el servicio la tomó: envío + tiempos_ms.cola."""
        return self.enviado + self.tiempo("cola")


def cliente() -> httpx.Client:
    return httpx.Client(base_url=URL_LOCAL, timeout=TIEMPO_PETICION_S)


def enviar(c: httpx.Client, imagenes: Sequence[Imagen], prioridad: str | None = None) -> Envio:
    n = next(_numero)
    encabezados = {"X-Request-Id": f"validacion-emb21-{n}"}
    if prioridad is not None:
        encabezados["X-Prioridad"] = prioridad
    archivos = [
        ("imagenes", (f"validacion-emb21-{n}-{i}", datos, tipo))
        for i, (datos, tipo) in enumerate(imagenes)
    ]
    enviado = time.monotonic()
    try:
        respuesta = c.post("/v1/embed", files=archivos, headers=encabezados)
    except httpx.HTTPError as error:
        raise Falla(f"POST /v1/embed falló: {type(error).__name__}: {error}") from error
    return Envio(respuesta, enviado, prioridad or "baja")


def a_la_vez(
    c: httpx.Client,
    peticiones: Sequence[Sequence[Imagen]],
    al_soltar: Callable[[], None] | None = None,
) -> list[Envio]:
    """Envía las peticiones `baja` en paralelo, soltándolas a la vez con una barrera."""
    barrera = threading.Barrier(len(peticiones), action=al_soltar)

    def una(imagenes):
        barrera.wait(timeout=30)
        return enviar(c, imagenes)

    with ThreadPoolExecutor(len(peticiones)) as hilos:
        return list(hilos.map(una, peticiones))


def vectores_ok(envio: Envio, n: int) -> np.ndarray:
    """Exige 200 con el contrato de §5.2 y devuelve la matriz (n, 384) float32."""
    if envio.respuesta.status_code != 200:
        raise Falla(f"respondió {envio.respuesta.status_code}: {_error(envio)}")
    cuerpo = envio.cuerpo
    if cuerpo.get("version_vector") != VERSION_VECTOR or cuerpo.get("dim") != DIM:
        raise Falla(f"version_vector={cuerpo.get('version_vector')}, dim={cuerpo.get('dim')}")
    vectores = np.array(cuerpo.get("vectores"), dtype=np.float32)
    if vectores.shape != (n, DIM):
        raise Falla(f"vectores con forma {vectores.shape}, se esperaba ({n}, {DIM})")
    return vectores


def _error(envio: Envio) -> str:
    try:
        error = envio.respuesta.json().get("error") or {}
        return f"{error.get('codigo')} {error.get('detalle')} «{error.get('mensaje')}»"
    except ValueError:
        return envio.respuesta.text[:200]


def exigir_error(envio: Envio, estado: int, codigo: str, detalle=...) -> None:
    if envio.respuesta.status_code != estado or envio.codigo_error != codigo:
        raise Falla(
            f"se esperaba {estado} {codigo}; "
            f"respondió {envio.respuesta.status_code} {_error(envio)}"
        )
    if detalle is not ... and envio.cuerpo["error"].get("detalle") != detalle:
        raise Falla(f"detalle={envio.cuerpo['error'].get('detalle')}, se esperaba {detalle}")


# --- Precondiciones ------------------------------------------------------------------------------


def p1_docker(ctx) -> str:
    info = docker("info", "--format", "{{.ServerVersion}}", timeout=60)
    if info.returncode != 0:
        raise ErrorConfiguracion("Docker no responde (docker info); ¿está arrancado?")
    ctx.limpiar_restos()
    if puerto_ocupado(PUERTO):
        raise ErrorConfiguracion(f"el puerto {PUERTO} está ocupado en esta máquina")
    return f"Docker {info.stdout.strip()}; puerto {PUERTO} libre"


def p2_imagen(ctx) -> str:
    imagen = imagen_local()
    ctx.datos["imagen"] = imagen
    return f"{imagen} (linux/amd64)"


def p3_servicio_listo(ctx) -> str:
    imagen = ctx.datos["imagen"]
    salida = docker(
        "run", "-d", "--name", CONTENEDOR_LOCAL, "-p", f"{PUERTO}:{PUERTO}",
        "-e", "TORCH_NUM_THREADS=1", imagen, timeout=300,
    )  # fmt: skip
    if salida.returncode != 0:
        raise ErrorConfiguracion(f"docker run falló: {salida.stderr.strip()[-300:]}")
    inicio = time.monotonic()
    with cliente() as c:
        while True:
            transcurrido = time.monotonic() - inicio
            try:
                listo = c.get("/health/ready", timeout=5)
                if listo.status_code == 200 and listo.json() == {"estado": "listo"}:
                    break
            except httpx.HTTPError:
                pass  # aún no escucha
            if not en_marcha(CONTENEDOR_LOCAL):
                raise PrecondicionNoCumplida(
                    f"EMB-1.1: el contenedor terminó antes de estar listo: "
                    f"{logs_contenedor(CONTENEDOR_LOCAL)}"
                )
            if transcurrido > PLAZO_ARRANQUE_S:
                raise PrecondicionNoCumplida(
                    f"EMB-1.1: /health/ready no respondió 200 en {PLAZO_ARRANQUE_S} s"
                )
            time.sleep(2)
        info = c.get("/v1/info", headers={"X-Request-Id": "validacion-emb21-info"}).json()
    if info.get("version_vector") != VERSION_VECTOR or info.get("lote_max") != LOTE_MAX:
        raise PrecondicionNoCumplida(
            f"EMB-1.1: /v1/info da version_vector={info.get('version_vector')!r}, "
            f"lote_max={info.get('lote_max')!r}"
        )
    return (
        f"listo a los {transcurrido:.0f} s; commit={info.get('commit')}, "
        f"version_vector={info['version_vector']}, lote_max={info['lote_max']}"
    )


# --- Comprobaciones ------------------------------------------------------------------------------


def c1_dorados(ctx) -> str:
    diferencias = {}
    with cliente() as c:
        for entrada in doradas():
            try:
                vector = vectores_ok(enviar(c, [(entrada["datos"], entrada["tipo"])]), 1)[0]
            except Falla as error:
                raise Falla(f"{entrada['archivo']}: {error}") from error
            esperado = np.array(entrada["vector"], dtype=np.float32)
            diferencias[entrada["archivo"]] = float(np.abs(vector - esperado).max())
    peor = max(diferencias, key=diferencias.get)
    if diferencias[peor] > TOLERANCIA:
        fuera = {k: f"{v:.2e}" for k, v in diferencias.items() if v > TOLERANCIA}
        raise Falla(f"fuera de {TOLERANCIA}: {fuera}")
    return f"5/5 dentro de {TOLERANCIA}; diferencia máxima {diferencias[peor]:.2e} ({peor})"


def c2_independencia_del_lote(ctx) -> str:
    imagenes = [(e["datos"], e["tipo"]) for e in doradas()]
    imagenes += [(sintetica(100 + i), "image/jpeg") for i in range(3)]
    with cliente() as c:
        lote = vectores_ok(enviar(c, imagenes), len(imagenes))
        solas = np.concatenate([vectores_ok(enviar(c, [imagen]), 1) for imagen in imagenes])
    diferencia = float(np.abs(lote - solas).max())
    if diferencia > TOLERANCIA:
        raise Falla(f"lote de 8 frente a solas: diferencia máxima {diferencia:.2e} > {TOLERANCIA}")
    return f"lote de 8 frente a cada imagen sola: diferencia máxima {diferencia:.2e}"


def c3_imagen_corrupta(ctx) -> str:
    buenas = [(sintetica(200 + i), "image/jpeg") for i in range(3)]
    imagenes = [buenas[0], buenas[1], (jpeg_truncado(), "image/jpeg"), buenas[2]]
    with cliente() as c:
        envio = enviar(c, imagenes)
    exigir_error(envio, 400, "IMAGEN_INVALIDA", {"indice": 2})
    return f"400 IMAGEN_INVALIDA, detalle.indice = 2 («{envio.cuerpo['error']['mensaje']}»)"


@dataclass
class IntentoC4:
    valido: bool
    detalle: str
    falla: str | None = None


def _intento_c4(c: httpx.Client, espera_s: float, margen_s: float, ronda: int) -> IntentoC4:
    bajas = [
        [(sintetica(1000 * ronda + 10 * p + i), "image/jpeg") for i in range(8)] for p in range(4)
    ]
    alta = [(sintetica(1000 * ronda + 99), "image/jpeg")]
    resultado: dict[str, list[Envio]] = {}
    soltadas = threading.Event()

    def lanzar_bajas():
        resultado["bajas"] = a_la_vez(c, bajas, al_soltar=soltadas.set)

    hilo = threading.Thread(target=lanzar_bajas)
    hilo.start()
    if not soltadas.wait(30):
        return IntentoC4(True, "", "no se pudieron lanzar las 4 peticiones baja")
    time.sleep(espera_s)
    envio_alta = enviar(c, alta, "alta")
    hilo.join(TIEMPO_PETICION_S)
    envios = resultado.get("bajas", [])
    for envio in [*envios, envio_alta]:
        if envio.respuesta.status_code != 200:
            return IntentoC4(
                True, "", f"una petición respondió {envio.respuesta.status_code}: {_error(envio)}"
            )
    if len(envios) != 4:
        return IntentoC4(True, "", "no respondieron las 4 peticiones baja")

    # Una baja que sale de la cola mientras la alta todavía sube no estaba esperando: se descuentan
    # las que salen en los primeros `margen_s` tras el envío de la alta.
    t_alta = envio_alta.enviado + margen_s
    esperando = [e for e in envios if e.salida_de_cola > t_alta]
    previas = [e for e in envios if e.salida_de_cola <= envio_alta.salida_de_cola]
    if len(esperando) < 2:
        return IntentoC4(
            False,
            f"solo {len(esperando)} baja seguían esperando al enviar la alta "
            f"(espera {espera_s:.2f} s)",
        )
    # (b) La alta sale de la cola antes que todas las baja que esperaban.
    primera_baja = min(e.salida_de_cola for e in esperando)
    if envio_alta.salida_de_cola >= primera_baja:
        return IntentoC4(
            True,
            "",
            f"(b) la alta salió de la cola "
            f"{1000 * (envio_alta.salida_de_cola - primera_baja):.0f} ms después de una baja "
            "que esperaba",
        )
    # (c) Solo esperó el lote en curso.
    en_curso = max(previas, key=lambda e: e.salida_de_cola, default=None)
    limite_ms = (en_curso.tiempo("inferencia") * 1000 if en_curso else 0) + MARGEN_C4_MS
    cola_alta_ms = envio_alta.tiempo("cola") * 1000
    if cola_alta_ms > limite_ms:
        return IntentoC4(
            True, "", f"(c) la alta esperó {cola_alta_ms:.0f} ms en cola > {limite_ms:.0f} ms"
        )
    return IntentoC4(
        True,
        f"{len(esperando)} baja esperaban; la alta salió de la cola "
        f"{1000 * (primera_baja - envio_alta.salida_de_cola):.0f} ms antes que ellas y esperó "
        f"{cola_alta_ms:.0f} ms (límite: lote en curso {limite_ms - MARGEN_C4_MS:.0f} ms "
        f"+ {MARGEN_C4_MS})",
    )


def c4_prioridad(ctx) -> str:
    with cliente() as c:
        # Duración de un lote de 8 en esta máquina: la alta sale a mitad del primero.
        medida = enviar(c, [(sintetica(900 + i), "image/jpeg") for i in range(8)])
        vectores_ok(medida, 8)
        lote_s = medida.tiempo("inferencia")
        espera_s = min(max(lote_s / 2, 0.05), 1.0)
        margen_s = min(MARGEN_SUBIDA_S, lote_s / 4)
        notas = []
        for ronda in range(1, INTENTOS + 1):
            intento = _intento_c4(c, espera_s, margen_s, ronda)
            if intento.falla:
                raise Falla(intento.falla)
            if intento.valido:
                previos = f" (tras {'; '.join(notas)})" if notas else ""
                return (
                    f"lote de 8 = {lote_s * 1000:.0f} ms, alta a {espera_s:.2f} s: "
                    f"{intento.detalle}{previos}"
                )
            notas.append(intento.detalle)
            espera_s = max(espera_s / 2, 0.01)
    raise Falla(f"ningún intento válido en {INTENTOS}: {'; '.join(notas)}")


def c5a_limites_de_tamano(ctx) -> str:
    grande = ruido_png(1300, 1)
    medianas = [ruido_png(1100, 10 + i) for i in range(5)]
    if len(grande) <= BYTES_MAX_IMAGEN or not all(len(m) < BYTES_MAX_IMAGEN for m in medianas):
        raise Falla("las imágenes de prueba no tienen el tamaño previsto")
    if sum(len(m) for m in medianas) <= BYTES_MAX_PETICION:
        raise Falla("las 5 imágenes de prueba no superan 16 MB")
    pequenas = [(sintetica(300 + i, 128, 96), "image/jpeg") for i in range(9)]
    casos = {
        "9 partes": pequenas,
        f"1 parte de {len(grande) / 2**20:.1f} MB": [(grande, "image/png")],
        f"5 partes, {sum(map(len, medianas)) / 2**20:.1f} MB": [(m, "image/png") for m in medianas],
    }
    with cliente() as c:
        for nombre, imagenes in casos.items():
            envio = enviar(c, imagenes)
            try:
                exigir_error(envio, 413, "LOTE_DEMASIADO_GRANDE")
            except Falla as error:
                raise Falla(f"{nombre}: {error}") from error
    return "413 LOTE_DEMASIADO_GRANDE en: " + ", ".join(casos)


def c5b_tipo_no_soportado(ctx) -> str:
    with cliente() as c:
        envio = enviar(c, [(gif(), "image/gif")])
    exigir_error(envio, 415, "TIPO_NO_SOPORTADO")
    return "415 TIPO_NO_SOPORTADO con image/gif"


def c5c_saturado(ctx) -> str:
    peticiones = [
        [(sintetica(5000 + 10 * p + i), "image/jpeg") for i in range(8)] for p in range(8)
    ]
    notas = []
    with cliente() as c:
        for intento in range(1, INTENTOS + 1):
            envios = a_la_vez(c, peticiones)
            estados = [e.respuesta.status_code for e in envios]
            saturadas = [e for e in envios if e.respuesta.status_code == 503]
            otras = [e for e in envios if e.respuesta.status_code not in (200, 503)]
            if otras:
                raise Falla(f"respuestas inesperadas: {[_error(e) for e in otras]}")
            for envio in saturadas:
                exigir_error(envio, 503, "SATURADO")
                if envio.respuesta.headers.get("Retry-After") != RETRY_AFTER_S:
                    raise Falla(
                        f"Retry-After={envio.respuesta.headers.get('Retry-After')!r}, "
                        f"se esperaba {RETRY_AFTER_S}"
                    )
            for envio in envios:
                if envio.respuesta.status_code == 200:
                    vectores_ok(envio, 8)
            if saturadas:
                return (
                    f"{len(saturadas)} × 503 SATURADO con Retry-After: {RETRY_AFTER_S} y "
                    f"{estados.count(200)} × 200 (intento {intento})"
                )
            notas.append(f"intento {intento}: 8 × 200")
    raise Falla(
        f"la cola nunca se saturó con 64 imágenes frente a {COLA_MAX_IMAGENES}: {'; '.join(notas)}"
    )


# --- Limpieza (§4 de la validación) -------------------------------------------------------------


def limpiar(ctx) -> None:
    borrar_contenedores(CONTENEDOR_LOCAL)


LOTE = Lote(
    lote="EMB-2.1",
    validacion="validation-2-1",
    entornos=LOCAL,
    descripcion="Vectorización por lotes (POST /v1/embed).",
    precondiciones=[
        Paso("P1", LOCAL, p1_docker),
        Paso("P2", LOCAL, p2_imagen),
        Paso("P3", LOCAL, p3_servicio_listo),
    ],
    comprobaciones=[
        Paso("C1", LOCAL, c1_dorados),
        Paso("C2", LOCAL, c2_independencia_del_lote),
        Paso("C3", LOCAL, c3_imagen_corrupta),
        Paso("C4", LOCAL, c4_prioridad),
        Paso("C5a", LOCAL, c5a_limites_de_tamano),
        Paso("C5b", LOCAL, c5b_tipo_no_soportado),
        Paso("C5c", LOCAL, c5c_saturado),
    ],
    limpiar=limpiar,
)


if __name__ == "__main__":
    raise SystemExit(ejecutar(LOTE))
