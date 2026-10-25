"""`uv run python tools/evaluacion <orden>` desde `project/` (órdenes en cli.py, §5.9)."""

import sys
from pathlib import Path

_PROYECTO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(_PROYECTO / "tools"), str(_PROYECTO / "src")]

from evaluacion.cli import main  # noqa: E402

raise SystemExit(main())
