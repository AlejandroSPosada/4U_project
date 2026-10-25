"""Latencia de `POST /v1/embed` por tamaño de lote en CPU (EMB-3.1).

Diseño en ARCHITECTURE §4.4 y ADR-EMB-13; argumentos, salida y códigos en §5.9.

Arranca el servicio como subproceso con el comando de la imagen (uvicorn, un proceso) pero solo en
127.0.0.1, espera a que `GET /health/ready` responda 200 y envía **en serie** lotes de imágenes
sintéticas (JPEG de 1024 × 768 px, calidad 85, como las fotos de `/v1/localize`). Cada petición se
mide desde el cliente: de empezar a enviarla a tener la respuesta completa. Las primeras de cada
lote se descartan como calentamiento.

    python tools/benchmark.py --salida json   # dentro de la imagen (/srv); así lo lanza validate31
    docker run --rm --cpus 2 --memory 4g -e TORCH_NUM_THREADS=2 <imagen> python tools/benchmark.py

Va dentro de la imagen (§5.5) y solo usa la biblioteca estándar, NumPy, Pillow y el paquete `app`.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

PREFIJO_JSON = "BENCHMARK_JSON "
LOTES = (1, 4, 5, 8)
REPETICIONES = {1: 40, 4: 30, 5: 60, 8: 30}
REPETICIONES_OTRO_LOTE = 30
CALENTAMIENTO = 3
ANCHO_PX, ALTO_PX, CALIDAD_JPEG = 1024, 768, 85
PUERTO = 8080
PLAZO_ARRANQUE_S = 300
TIEMPO_PETICION_S = 120
REPETICIONES_PREPROCESO = 5
LOTE_MAX = 8  # §5.7
FRONTERA = "benchmark-emb31-6f1d0c2a9b"
CGROUP = Path("/sys/fs/cgroup")


class ErrorBenchmark(Exception):
    """El servicio no quedó listo o una petición falló (código 1)."""


# --- Registro: JSON por línea en stderr, como el servicio (§5.7) --------------------------------


def registrar(evento: str, nivel: str = "INFO", **campos: Any) -> None:
    linea = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "nivel": nivel,
        "evento": evento,
        **campos,
    }
    print(json.dumps(linea, ensure_ascii=False), file=sys.stderr, flush=True)


# --- Datos de prueba ----------------------------------------------------------------------------


def imagen_sintetica(
    semilla: int, ancho: int = ANCHO_PX, alto: int = ALTO_PX, calidad: int = CALIDAD_JPEG
) -> bytes:
    """JPEG con semilla fija que se parece a una foto: fondo suave, bloques y algo de ruido."""
    rng = np.random.default_rng(semilla)
    fondo = (rng.random((max(alto // 64, 2), max(ancho // 64, 2), 3)) * 255).astype(np.uint8)
    imagen = Image.fromarray(fondo).resize((ancho, alto), Image.Resampling.BICUBIC)
    dibujo = ImageDraw.Draw(imagen)
    for _ in range(40):
        x0, y0 = int(rng.integers(0, ancho)), int(rng.integers(0, alto))
        x1, y1 = x0 + int(rng.integers(20, 300)), y0 + int(rng.integers(20, 300))
        dibujo.rectangle((x0, y0, x1, y1), fill=tuple(int(c) for c in rng.integers(0, 256, 3)))
    ruido = rng.normal(0, 6, (alto, ancho, 3))
    pixeles = np.clip(np.asarray(imagen, dtype=np.float32) + ruido, 0, 255).astype(np.uint8)
    salida = io.BytesIO()
    Image.fromarray(pixeles).save(salida, "JPEG", quality=calidad)
    return salida.getvalue()


def cuerpo_multipart(imagenes: Sequence[bytes]) -> tuple[bytes, str]:
    """Cuerpo `multipart/form-data` con una parte `imagenes` (`image/jpeg`) por imagen (§5.2)."""
    partes = []
    for indice, datos in enumerate(imagenes):
        encabezado = (
            f"--{FRONTERA}\r\n"
            'Content-Disposition: form-data; name="imagenes"; '
            f'filename="benchmark-{indice}.jpg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        )
        partes.append(encabezado.encode("ascii") + datos + b"\r\n")
    partes.append(f"--{FRONTERA}--\r\n".encode("ascii"))
    return b"".join(partes), f"multipart/form-data; boundary={FRONTERA}"


# --- Estadística --------------------------------------------------------------------------------


def percentil(valores: Sequence[float], p: float) -> float:
    """Percentil por rango más cercano: el valor en la posición ⌈p/100 · n⌉ de los ordenados."""
    if not valores:
        raise ValueError("sin valores")
    ordenados = sorted(valores)
    return ordenados[max(1, math.ceil(p / 100 * len(ordenados))) - 1]


@dataclass(frozen=True)
class Medida:
    total_ms: float
    cola_ms: float
    inferencia_ms: float


def resumen(lote: int, medidas: Sequence[Medida]) -> dict[str, int]:
    totales = [m.total_ms for m in medidas]
    inferencias = [m.inferencia_ms for m in medidas]
    return {
        "lote": lote,
        "repeticiones": len(medidas),
        "p50_ms": round(percentil(totales, 50)),
        "p95_ms": round(percentil(totales, 95)),
        "max_ms": round(max(totales)),
        "inferencia_p50_ms": round(percentil(inferencias, 50)),
        "inferencia_p95_ms": round(percentil(inferencias, 95)),
        "cola_max_ms": round(max(m.cola_ms for m in medidas)),
    }


# --- Cliente HTTP (una conexión persistente, sin proxies) -----------------------------------------


class Cliente:
    def __init__(self, url: str, timeout: float = TIEMPO_PETICION_S) -> None:
        partes = urllib.parse.urlsplit(url)
        if partes.scheme != "http" or not partes.hostname:
            raise ErrorBenchmark(f"--url debe ser http://anfitrion:puerto, no {url!r}")
        self.anfitrion = partes.hostname
        self.puerto = partes.port or 80
        self.timeout = timeout
        self._conexion: http.client.HTTPConnection | None = None

    def pedir(
        self, metodo: str, ruta: str, cuerpo: bytes | None = None, encabezados: dict | None = None
    ) -> tuple[int, bytes]:
        if self._conexion is None:
            self._conexion = http.client.HTTPConnection(
                self.anfitrion, self.puerto, timeout=self.timeout
            )
        try:
            self._conexion.request(metodo, ruta, body=cuerpo, headers=encabezados or {})
            respuesta = self._conexion.getresponse()
            return respuesta.status, respuesta.read()
        except (OSError, http.client.HTTPException):
            self.cerrar()
            raise

    def cerrar(self) -> None:
        if self._conexion is not None:
            self._conexion.close()
            self._conexion = None


def _resumir(datos: bytes, maximo: int = 300) -> str:
    texto = " ".join(datos.decode("utf-8", errors="replace").split())
    return texto if len(texto) <= maximo else texto[:maximo] + "…"


def esperar_listo(cliente: Cliente, servidor: Servidor | None, plazo_s: float) -> float:
    """Segundos hasta `GET /health/ready` = 200; `ErrorBenchmark` si el servidor muere o vence."""
    inicio = time.monotonic()
    while True:
        if servidor is not None and servidor.terminado() is not None:
            raise ErrorBenchmark(
                f"el servicio terminó con código {servidor.terminado()} antes de quedar listo "
                "(ver carga_del_modelo_fallida en el log)"
            )
        try:
            estado, _ = cliente.pedir("GET", "/health/ready")
            if estado == 200:
                return time.monotonic() - inicio
        except (OSError, http.client.HTTPException):
            pass  # aún no escucha
        if time.monotonic() - inicio > plazo_s:
            raise ErrorBenchmark(f"/health/ready no respondió 200 en {plazo_s:.0f} s")
        time.sleep(1)


def info(cliente: Cliente) -> dict[str, Any]:
    estado, datos = cliente.pedir("GET", "/v1/info")
    if estado != 200:
        raise ErrorBenchmark(f"GET /v1/info respondió {estado}: {_resumir(datos)}")
    return json.loads(datos)


def medir_lote(
    cliente: Cliente,
    lote: int,
    cuerpo: bytes,
    tipo: str,
    repeticiones: int,
    calentamiento: int,
    prioridad: str,
) -> list[Medida]:
    """Envía el mismo lote `calentamiento + repeticiones` veces, en serie; mide las últimas."""
    medidas = []
    for n in range(calentamiento + repeticiones):
        encabezados = {
            "Content-Type": tipo,
            "X-Prioridad": prioridad,
            "X-Request-Id": f"benchmark-l{lote}-{n}",
        }
        inicio = time.perf_counter()
        estado, datos = cliente.pedir("POST", "/v1/embed", cuerpo, encabezados)
        total_ms = (time.perf_counter() - inicio) * 1000
        if estado != 200:
            raise ErrorBenchmark(
                f"lote {lote}: POST /v1/embed respondió {estado}: {_resumir(datos)}"
            )
        respuesta = json.loads(datos)
        if len(respuesta.get("vectores", [])) != lote:
            raise ErrorBenchmark(f"lote {lote}: la respuesta no trae {lote} vectores")
        if n >= calentamiento:
            tiempos = respuesta["tiempos_ms"]
            medidas.append(Medida(total_ms, float(tiempos["cola"]), float(tiempos["inferencia"])))
    return medidas


# --- Servidor como subproceso ---------------------------------------------------------------------


def directorio_app() -> Path:
    """Carpeta que contiene el paquete `app`: /srv en la imagen, project/src en el repositorio."""
    base = Path(__file__).resolve().parent.parent
    for candidato in (base, base / "src"):
        if (candidato / "app" / "main.py").is_file():
            return candidato
    raise ErrorBenchmark(f"no se encuentra el paquete app junto a {base}")


def puerto_ocupado(puerto: int, anfitrion: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((anfitrion, puerto), timeout=1):
            return True
    except OSError:
        return False


class Servidor:
    """`uvicorn app.main:app` en 127.0.0.1 con TORCH_NUM_THREADS = hilos; sus logs van a stderr."""

    def __init__(self, puerto: int, hilos: int) -> None:
        self.puerto = puerto
        self.hilos = hilos
        self.proceso: subprocess.Popen | None = None

    def arrancar(self) -> None:
        if puerto_ocupado(self.puerto):
            raise ErrorBenchmark(
                f"el puerto {self.puerto} ya está en uso: no se mediría este servicio"
            )
        comando = [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--app-dir", str(directorio_app()),
            "--host", "127.0.0.1", "--port", str(self.puerto),
            "--workers", "1", "--no-server-header",
        ]  # fmt: skip
        entorno = {**os.environ, "TORCH_NUM_THREADS": str(self.hilos)}
        self.proceso = subprocess.Popen(comando, env=entorno, stdout=2, stderr=2)

    def terminado(self) -> int | None:
        return None if self.proceso is None else self.proceso.poll()

    def memoria_mb(self) -> dict[str, int] | None:
        """VmRSS y VmHWM (pico) del proceso, en MiB, de /proc (solo Linux)."""
        if self.proceso is None:
            return None
        try:
            texto = Path(f"/proc/{self.proceso.pid}/status").read_text(encoding="utf-8")
        except OSError:
            return None
        valores = {}
        for linea in texto.splitlines():
            clave, _, resto = linea.partition(":")
            if clave in ("VmRSS", "VmHWM") and resto.split():
                valores[clave] = round(int(resto.split()[0]) / 1024)
        return valores or None

    def detener(self) -> None:
        if self.proceso is None or self.proceso.poll() is not None:
            return
        self.proceso.terminate()
        try:
            self.proceso.wait(30)
        except subprocess.TimeoutExpired:
            self.proceso.kill()
            self.proceso.wait(10)


# --- Entorno de la medida -------------------------------------------------------------------------


def _numero(valor: float) -> int | float:
    return int(valor) if float(valor).is_integer() else round(float(valor), 2)


def limites_ecs(uri: str | None) -> tuple[int | float, int] | None:
    """`Limits` de la tarea (metadatos de ECS v4: CPU en vCPU y Memory en MiB), o None."""
    if not uri:
        return None
    sin_proxy = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with sin_proxy.open(uri.rstrip("/") + "/task", timeout=3) as respuesta:
            limites = json.load(respuesta).get("Limits") or {}
        cpu, memoria = float(limites["CPU"]), int(limites["Memory"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if cpu >= 128:  # por si viniera en unidades de CPU (1024 = 1 vCPU)
        cpu /= 1024
    return _numero(cpu), memoria


def limites_cgroup(raiz: Path = CGROUP) -> tuple[int | float | None, int | None]:
    """vCPU y MiB del contenedor según su cgroup (v2 o v1); None donde no hay límite."""
    cpu = memoria = None
    try:
        if (raiz / "cpu.max").is_file():  # cgroup v2
            cuota, periodo = (raiz / "cpu.max").read_text().split()[:2]
            if cuota != "max":
                cpu = int(cuota) / int(periodo)
            limite = (raiz / "memory.max").read_text().strip()
            if limite != "max":
                memoria = int(limite) // 2**20
        elif (raiz / "cpu" / "cpu.cfs_quota_us").is_file():  # cgroup v1
            cuota_v1 = int((raiz / "cpu" / "cpu.cfs_quota_us").read_text())
            if cuota_v1 > 0:
                cpu = cuota_v1 / int((raiz / "cpu" / "cpu.cfs_period_us").read_text())
            limite_v1 = int((raiz / "memory" / "memory.limit_in_bytes").read_text())
            if limite_v1 < 2**60:
                memoria = limite_v1 // 2**20
    except (OSError, ValueError):
        pass
    return (None if cpu is None else _numero(cpu)), memoria


def limites() -> tuple[int | float | None, int | None, str]:
    """(vCPU, MiB, de dónde salen): metadatos de ECS, cgroup o la máquina entera."""
    ecs = limites_ecs(os.environ.get("ECS_CONTAINER_METADATA_URI_V4"))
    if ecs is not None:
        return ecs[0], ecs[1], "ecs"
    cpu, memoria = limites_cgroup()
    if cpu is not None or memoria is not None:
        return cpu if cpu is not None else os.cpu_count(), memoria, "cgroup"
    return os.cpu_count(), None, "sistema"


def modelo_cpu() -> str | None:
    try:
        for linea in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if linea.startswith("model name"):
                return linea.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def capacidad_cpu_torch() -> str | None:
    """Ruta SIMD que usa PyTorch (AVX2, AVX512…). Se llama con el servidor ya detenido."""
    try:
        import torch

        return torch.backends.cpu.get_cpu_capability()
    except Exception:
        return None


def medir_preproceso(imagenes: Sequence[bytes]) -> float | None:
    """p50 en ms de pp-v1 (decodificar + redimensionar + recortar) por imagen, en este proceso."""
    directorio = str(directorio_app())
    if directorio not in sys.path:
        sys.path.insert(0, directorio)
    try:
        from app.preproceso import preprocesar
    except ImportError:
        return None
    tiempos = []
    for _ in range(REPETICIONES_PREPROCESO):
        for datos in imagenes:
            inicio = time.perf_counter()
            preprocesar(datos)
            tiempos.append((time.perf_counter() - inicio) * 1000)
    return round(percentil(tiempos, 50), 1)


# --- Medida completa ------------------------------------------------------------------------------


def _lista_enteros(texto: str) -> list[int]:
    try:
        valores = [int(v) for v in texto.split(",") if v.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"se esperan enteros separados por comas: {texto}"
        ) from error
    if not valores or any(v < 1 for v in valores):
        raise argparse.ArgumentTypeError(f"se esperan enteros ≥ 1: {texto}")
    return valores


def argumentos(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Latencia de POST /v1/embed por tamaño de lote (EMB-3.1, ARCHITECTURE §5.9).",
        epilog="Salida: 0 medido · 1 el servicio no quedó listo o una petición falló · 2 uso",
    )
    parser.add_argument("--salida", choices=("texto", "json"), default="texto")
    parser.add_argument("--lotes", type=_lista_enteros, default=list(LOTES), help="p. ej. 1,5,8")
    parser.add_argument(
        "--repeticiones",
        type=_lista_enteros,
        help="una cifra para todos los lotes o una por lote (por defecto 1:40, 4:30, 5:60, 8:30)",
    )
    parser.add_argument("--calentamiento", type=int, default=CALENTAMIENTO)
    parser.add_argument(
        "--hilos",
        type=int,
        default=int(os.environ.get("TORCH_NUM_THREADS") or 1),
        help="TORCH_NUM_THREADS del servicio que arranca (por defecto, la variable o 1)",
    )
    parser.add_argument("--prioridad", choices=("alta", "baja"), default="alta")
    parser.add_argument("--puerto", type=int, default=PUERTO)
    parser.add_argument("--plazo-arranque", type=float, default=PLAZO_ARRANQUE_S)
    parser.add_argument(
        "--url", help="medir un servicio ya en marcha (no arranca otro; sin memoria ni hilos)"
    )
    args = parser.parse_args(argv)
    if any(lote > LOTE_MAX for lote in args.lotes):
        parser.error(f"--lotes: el máximo es {LOTE_MAX} (LOTE_MAX, §5.7)")
    if args.repeticiones is None:
        args.repeticiones = [REPETICIONES.get(lote, REPETICIONES_OTRO_LOTE) for lote in args.lotes]
    elif len(args.repeticiones) == 1:
        args.repeticiones = args.repeticiones * len(args.lotes)
    elif len(args.repeticiones) != len(args.lotes):
        parser.error("--repeticiones: una cifra o tantas como --lotes")
    if args.calentamiento < 0 or args.hilos < 1:
        parser.error("--calentamiento ≥ 0 y --hilos ≥ 1")
    return args


def medir(args: argparse.Namespace) -> dict[str, Any]:
    imagenes = [imagen_sintetica(semilla) for semilla in range(max(args.lotes))]
    cuerpos = {lote: cuerpo_multipart(imagenes[:lote]) for lote in args.lotes}
    vcpu, memoria_mb, origen = limites()
    registrar(
        "benchmark_inicio",
        lotes=args.lotes,
        repeticiones=args.repeticiones,
        hilos=None if args.url else args.hilos,
        vcpu=vcpu,
        memoria_mb=memoria_mb,
    )
    servidor = None if args.url else Servidor(args.puerto, args.hilos)
    cliente = Cliente(args.url or f"http://127.0.0.1:{args.puerto}")
    try:
        if servidor is not None:
            servidor.arrancar()
        arranque_s = esperar_listo(cliente, servidor, args.plazo_arranque)
        datos_info = info(cliente)
        reposo = servidor.memoria_mb() if servidor else None
        registrar(
            "benchmark_listo", arranque_s=round(arranque_s, 1), commit=datos_info.get("commit")
        )
        resultados = []
        for lote, repeticiones in zip(args.lotes, args.repeticiones, strict=True):
            cuerpo, tipo = cuerpos[lote]
            medidas = medir_lote(
                cliente, lote, cuerpo, tipo, repeticiones, args.calentamiento, args.prioridad
            )
            resultados.append(resumen(lote, medidas))
            registrar("benchmark_lote", **resultados[-1])
        final = servidor.memoria_mb() if servidor else None
    finally:
        cliente.cerrar()
        if servidor is not None:
            servidor.detener()
    return {
        "version_vector": datos_info.get("version_vector"),
        "commit": datos_info.get("commit"),
        "hilos": None if args.url else args.hilos,
        "vcpu": vcpu,
        "memoria_mb": memoria_mb,
        "limites_de": origen,
        "cpu": modelo_cpu(),
        "capacidad_cpu_torch": capacidad_cpu_torch(),
        "imagen": {
            "ancho": ANCHO_PX,
            "alto": ALTO_PX,
            "calidad_jpeg": CALIDAD_JPEG,
            "bytes_media": round(sum(map(len, imagenes)) / len(imagenes)),
        },
        "prioridad": args.prioridad,
        "calentamiento": args.calentamiento,
        "arranque_s": None if args.url else round(arranque_s, 1),
        "memoria_proceso_mb": None
        if servidor is None
        else {
            "reposo": (reposo or {}).get("VmRSS"),
            "final": (final or {}).get("VmRSS"),
            "pico": (final or {}).get("VmHWM"),
        },
        "preproceso_ms_por_imagen": medir_preproceso(imagenes[:5]),
        "resultados": resultados,
    }


def tabla(resultado: dict[str, Any]) -> str:
    memoria = resultado["memoria_proceso_mb"] or {}
    limite = resultado["memoria_mb"]
    lineas = [
        f"POST /v1/embed · {resultado['version_vector']} · commit {resultado['commit']} · "
        f"hilos {resultado['hilos']} · {resultado['vcpu']} vCPU / "
        f"{f'{limite} MiB' if limite else 'memoria sin límite'} ({resultado['limites_de']})",
        f"CPU: {resultado['cpu']} ({resultado['capacidad_cpu_torch']}) · listo en "
        f"{resultado['arranque_s']} s · memoria del proceso: reposo {memoria.get('reposo')} MiB, "
        f"pico {memoria.get('pico')} MiB",
        f"imágenes {resultado['imagen']['ancho']} × {resultado['imagen']['alto']} JPEG "
        f"q{resultado['imagen']['calidad_jpeg']} ({resultado['imagen']['bytes_media'] // 1024} KiB "
        f"de media) · pp-v1 {resultado['preproceso_ms_por_imagen']} ms por imagen (p50) · "
        f"prioridad {resultado['prioridad']}",
        f"{'lote':>4} {'rep':>4} {'p50_ms':>7} {'p95_ms':>7} {'max_ms':>7} "
        f"{'inf_p50':>8} {'inf_p95':>8}",
    ]
    for r in resultado["resultados"]:
        lineas.append(
            f"{r['lote']:>4} {r['repeticiones']:>4} {r['p50_ms']:>7} {r['p95_ms']:>7} "
            f"{r['max_ms']:>7} {r['inferencia_p50_ms']:>8} {r['inferencia_p95_ms']:>8}"
        )
    return "\n".join(lineas)


def main(argv: Sequence[str] | None = None) -> int:
    args = argumentos(argv)
    try:
        resultado = medir(args)
    except ErrorBenchmark as error:
        registrar("benchmark_fallido", nivel="ERROR", motivo=str(error))
        return 1
    if args.salida == "json":
        texto = json.dumps(resultado, ensure_ascii=False, separators=(",", ":"))
        print(PREFIJO_JSON + texto, flush=True)
    else:
        print(tabla(resultado), flush=True)
    return 0


def _terminar(signum: int, _frame) -> None:
    # En la tarea suelta este proceso es el PID 1: sin manejador, ignoraría SIGTERM (stop-task).
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _terminar)
    raise SystemExit(main())
