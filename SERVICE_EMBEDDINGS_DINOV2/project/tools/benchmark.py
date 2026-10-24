"""Latencia por tamaño de lote en CPU (EMB-3.1; ARCHITECTURE §4.4, formato de salida en §5.9).

Se implementa en EMB-3.1. Existe desde EMB-1.1 porque la imagen lo incluye en /srv/tools/ (§5.5).
"""

from __future__ import annotations

import sys


def main() -> int:
    print("benchmark.py: pendiente de EMB-3.1", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
