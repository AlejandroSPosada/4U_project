"""Vectores dorados de pp-v1 (ARCHITECTURE §5.4, ADR-EMB-12): imágenes de referencia y vectores.

No va en la imagen (.dockerignore). Uso, desde project/:

    uv run python tools/dorados.py imagenes            # una vez: genera las cinco imágenes
    uv run python tools/dorados.py vectores --modelo .modelo [--hilos 1]
    uv run python tools/dorados.py comparar --modelo .modelo   # sin escribir nada

`imagenes` dibuja cinco escenas sintéticas (sin derechos de terceros) en tests/golden/. Los
archivos versionados son la referencia: volver a generarlos con otra versión de Pillow puede dar
otros bytes, así que no se regeneran salvo con una `version_vector` nueva.

`vectores` calcula cada vector con el mismo código del servicio (`preproceso` + `ModeloDinov2`,
imagen sola y lote de 1) y escribe tests/golden/esperados.json. Si ya existe y algún componente se
aleja más de la tolerancia, no lo sobrescribe: eso es un cambio de vectores y exige una
`version_vector` nueva (ADR-EMB-08), salvo `--forzar` al estrenar una versión.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

PROYECTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROYECTO / "src"))

from app import config  # noqa: E402
from app.preproceso import preprocesar  # noqa: E402

DIR_DORADOS = PROYECTO / "tests" / "golden"
ESPERADOS = DIR_DORADOS / "esperados.json"
TOLERANCIA = 1e-5
ORIENTACION_EXIF = 0x0112

TIPOS = {".jpg": "image/jpeg", ".png": "image/png"}


# --- Imágenes ------------------------------------------------------------------------------------


def _degradado(ancho: int, alto: int, arriba, abajo) -> Image.Image:
    t = np.linspace(0.0, 1.0, alto)[:, None, None]
    filas = (1 - t) * np.array(arriba) + t * np.array(abajo)
    return Image.fromarray(np.repeat(filas, ancho, axis=1).astype(np.uint8), "RGB")


def _con_grano(imagen: Image.Image, rng: np.random.Generator, fuerza: float) -> Image.Image:
    pixeles = np.asarray(imagen, dtype=np.float64)
    pixeles = pixeles + rng.normal(0.0, fuerza, pixeles.shape)
    return Image.fromarray(np.clip(pixeles, 0, 255).astype(np.uint8), imagen.mode)


def _escena_campus(
    ancho: int, alto: int, rng: np.random.Generator, grano: float = 2.5
) -> Image.Image:
    """Cielo, edificios con ventanas, árboles y un camino: algo parecido a una foto del campus."""
    imagen = _degradado(ancho, alto, (120, 170, 230), (225, 235, 245))
    dibujo = ImageDraw.Draw(imagen)
    horizonte = int(alto * 0.62)
    dibujo.rectangle([0, horizonte, ancho, alto], fill=(96, 140, 72))
    dibujo.polygon(
        [
            (ancho * 0.42, alto),
            (ancho * 0.58, alto),
            (ancho * 0.52, horizonte),
            (ancho * 0.48, horizonte),
        ],
        fill=(170, 160, 150),
    )
    x = int(ancho * 0.03)
    while x < ancho * 0.95:
        ancho_ed = int(rng.integers(ancho // 9, ancho // 5))
        alto_ed = int(rng.integers(alto // 6, alto // 2))
        color = tuple(int(c) for c in rng.integers(110, 220, 3))
        arriba = horizonte - alto_ed
        dibujo.rectangle([x, arriba, x + ancho_ed, horizonte], fill=color, outline=(60, 60, 60))
        for vy in range(arriba + 8, horizonte - 10, 16):
            for vx in range(x + 6, x + ancho_ed - 10, 14):
                dibujo.rectangle([vx, vy, vx + 7, vy + 9], fill=(40, 60, 90))
        x += ancho_ed + int(rng.integers(4, 30))
    for _ in range(7):
        cx = int(rng.integers(0, ancho))
        cy = horizonte + int(rng.integers(-5, alto // 6))
        r = int(rng.integers(alto // 20, alto // 9))
        dibujo.rectangle([cx - 3, cy, cx + 3, cy + r * 2], fill=(90, 60, 40))
        dibujo.ellipse(
            [cx - r, cy - r, cx + r, cy + r], fill=(40, 110 + int(rng.integers(0, 60)), 50)
        )
    dibujo.ellipse(
        [ancho * 0.82, alto * 0.06, ancho * 0.9, alto * 0.06 + ancho * 0.08], fill=(255, 240, 180)
    )
    suave = imagen.filter(ImageFilter.GaussianBlur(0.8))
    return _con_grano(suave, rng, grano) if grano else suave


def _guardar(imagen: Image.Image, ruta: Path, **opciones) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(ruta, **opciones)


def generar_imagenes(destino: Path = DIR_DORADOS) -> list[Path]:
    rng = np.random.default_rng(20261024)
    rutas = []

    # 1. JPEG apaisado 640 × 480 (se reduce: 341 × 256 → recorte).
    ruta = destino / "validacion-01-campus.jpg"
    _guardar(_escena_campus(640, 480, rng), ruta, format="JPEG", quality=85)
    rutas.append(ruta)

    # 2. JPEG vertical guardado girado con EXIF Orientation = 6: el servicio lo endereza (§5.3).
    vertical = _escena_campus(480, 640, rng)
    exif = Image.Exif()
    exif[ORIENTACION_EXIF] = 6
    ruta = destino / "validacion-02-vertical-exif.jpg"
    _guardar(
        vertical.transpose(Image.Transpose.ROTATE_90), ruta, format="JPEG", quality=85, exif=exif
    )
    rutas.append(ruta)

    # 3. PNG RGBA 320 × 240 con zonas transparentes: el alfa se descarta (cuentan los RGB de
    #    debajo). Sin grano, para que el PNG sea pequeño.
    base = _escena_campus(320, 240, rng, grano=0).convert("RGBA")
    alfa = Image.new("L", base.size, 255)
    ImageDraw.Draw(alfa).ellipse([40, 30, 190, 180], fill=0)
    ImageDraw.Draw(alfa).rectangle([230, 0, 320, 240], fill=96)
    base.putalpha(alfa)
    ruta = destino / "validacion-03-alfa.png"
    _guardar(base, ruta, format="PNG", optimize=True)
    rutas.append(ruta)

    # 4. PNG en gris 257 × 199 (lados impares; el menor se amplía a 256).
    yy, xx = np.mgrid[0:199, 0:257]
    anillos = 127.5 + 127.5 * np.sin(np.hypot(xx - 140, yy - 90) / 6.0)
    gris = Image.fromarray(anillos.astype(np.uint8), "L")
    ImageDraw.Draw(gris).rectangle([10, 120, 90, 190], fill=30)
    ruta = destino / "validacion-04-gris.png"
    _guardar(gris, ruta, format="PNG", optimize=True)
    rutas.append(ruta)

    # 5. JPEG pequeño 96 × 72 (cerca del mínimo de 64 px; se amplía unas 3,5 veces).
    ruta = destino / "validacion-05-pequena.jpg"
    _guardar(_escena_campus(96, 72, rng), ruta, format="JPEG", quality=85)
    rutas.append(ruta)
    return rutas


# --- Vectores ------------------------------------------------------------------------------------


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def imagenes_doradas(directorio: Path = DIR_DORADOS) -> list[Path]:
    return sorted(p for p in directorio.glob("validacion-*") if p.suffix in TIPOS)


def calcular(modelo_dir: Path, hilos: int) -> dict:
    from app.modelo import ModeloDinov2

    modelo = ModeloDinov2(modelo_dir, hilos)
    modelo.cargar()
    import PIL
    import torch
    import transformers

    entradas = []
    for ruta in imagenes_doradas():
        datos = ruta.read_bytes()
        tensor = preprocesar(datos)
        vector = modelo.inferir(tensor[None])[0]
        entradas.append(
            {
                "archivo": ruta.name,
                "tipo": TIPOS[ruta.suffix],
                "sha256": _sha256(datos),
                "sha256_preprocesado": _sha256(tensor.tobytes()),
                "vector": [float(x) for x in vector],
            }
        )
    return {
        "version_vector": config.VERSION_VECTOR,
        "modelo": config.MODELO_ID,
        "revision": config.MODELO_REVISION,
        "dim": config.DIM,
        "tolerancia": TOLERANCIA,
        "calculado": {
            "fecha": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "herramienta": "tools/dorados.py vectores",
            "hilos": hilos,
            "cpu": _cpu(),
            "capacidad_cpu_torch": torch.backends.cpu.get_cpu_capability(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "pillow": PIL.__version__,
        },
        "imagenes": entradas,
    }


def _cpu() -> str:
    try:
        for linea in Path("/proc/cpuinfo").read_text().splitlines():
            if linea.startswith("model name"):
                return linea.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or platform.machine()


def diferencias(nuevo: dict, previo: dict) -> dict[str, float]:
    """Diferencia máxima por componente de cada imagen común a los dos registros."""
    anteriores = {e["archivo"]: np.array(e["vector"], dtype=np.float32) for e in previo["imagenes"]}
    return {
        e["archivo"]: float(
            np.abs(np.array(e["vector"], dtype=np.float32) - anteriores[e["archivo"]]).max()
        )
        for e in nuevo["imagenes"]
        if e["archivo"] in anteriores
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="orden", required=True)
    sub.add_parser("imagenes", help="genera las cinco imágenes de referencia en tests/golden/")
    for nombre in ("vectores", "comparar"):
        p = sub.add_parser(nombre, help=f"{nombre} los vectores esperados con el modelo real")
        p.add_argument(
            "--modelo",
            type=Path,
            default=Path(os.environ.get("MODELO_DIR", PROYECTO / ".modelo")),
            help="carpeta con los pesos y revision.json (por defecto MODELO_DIR o .modelo)",
        )
        p.add_argument("--hilos", type=int, default=1)
        if nombre == "vectores":
            p.add_argument("--forzar", action="store_true", help="sobrescribe aunque cambien")
    args = parser.parse_args(argv)

    if args.orden == "imagenes":
        for ruta in generar_imagenes():
            print(f"{ruta.relative_to(PROYECTO)}  {ruta.stat().st_size} bytes")
        return 0

    nuevo = calcular(args.modelo, args.hilos)
    previo = json.loads(ESPERADOS.read_text(encoding="utf-8")) if ESPERADOS.exists() else None
    if previo is not None:
        for archivo, diferencia in diferencias(nuevo, previo).items():
            print(f"{archivo}: diferencia máxima {diferencia:.3e}")
        peor = max(diferencias(nuevo, previo).values(), default=0.0)
        if args.orden == "comparar":
            return 0 if peor <= TOLERANCIA else 1
        if peor > TOLERANCIA and not args.forzar:
            print(f"No se sobrescribe {ESPERADOS.name}: {peor:.3e} > {TOLERANCIA}", file=sys.stderr)
            return 1
    elif args.orden == "comparar":
        print(f"No existe {ESPERADOS}", file=sys.stderr)
        return 1
    ESPERADOS.write_text(json.dumps(nuevo, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{ESPERADOS.relative_to(PROYECTO)} escrito con {len(nuevo['imagenes'])} vectores")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
