"""Descarga la revisión fija de DINOv2 (ARCHITECTURE §5.3) durante el build (ADR-EMB-05).

Uso (desde project/, con `src/` en PYTHONPATH para leer modelo y revisión de `app.config`):

    PYTHONPATH=src python tools/descargar_modelo.py [DESTINO]

DESTINO por defecto: MODELO_DIR o /opt/modelo. Deja allí los archivos de ARCHIVOS_MODELO y un
`revision.json` que el servicio comprueba al arrancar. Es la única pieza que sale a internet.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

from app.config import ARCHIVO_REVISION, ARCHIVOS_MODELO, MODELO_ID, MODELO_REVISION


def descargar(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODELO_ID,
        revision=MODELO_REVISION,
        local_dir=destino,
        allow_patterns=list(ARCHIVOS_MODELO),
    )
    faltan = [nombre for nombre in ARCHIVOS_MODELO if not (destino / nombre).is_file()]
    if faltan:
        raise SystemExit(
            f"La revisión {MODELO_REVISION} de {MODELO_ID} no trae: {', '.join(faltan)}"
        )
    # Metadatos de descarga de huggingface_hub: no hacen falta en la imagen.
    shutil.rmtree(destino / ".cache", ignore_errors=True)
    registro = {"modelo": MODELO_ID, "revision": MODELO_REVISION, "archivos": list(ARCHIVOS_MODELO)}
    (destino / ARCHIVO_REVISION).write_text(json.dumps(registro, indent=2) + "\n", encoding="utf-8")
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "destino",
        nargs="?",
        type=Path,
        default=Path(os.environ.get("MODELO_DIR", "/opt/modelo")),
        help="Carpeta donde quedan los pesos (por defecto MODELO_DIR o /opt/modelo)",
    )
    args = parser.parse_args(argv)
    destino = descargar(args.destino)
    print(f"{MODELO_ID}@{MODELO_REVISION} → {destino}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
