"""Carga de DINOv2 desde MODELO_DIR, inferencia por lotes y normalización L2 (§5.3, §5.4).

PyTorch y transformers se importan dentro de las funciones: así `app.main` arranca y responde
`/health` antes de pagar su importación, y las variables de OpenMP se fijan antes de cargarlas.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.config import ARCHIVO_REVISION, DIM, MODELO_ID, MODELO_REVISION

if TYPE_CHECKING:
    import torch

LADO_ENTRADA_PX = 224
LOTES_CALENTAMIENTO = (1, 8)


class ErrorModelo(RuntimeError):
    """El modelo de la imagen no se puede usar (falta, revisión distinta o no cargado)."""


def fijar_hilos(hilos: int) -> None:
    """Aplica TORCH_NUM_THREADS a OpenMP/MKL y a PyTorch (§5.5).

    OpenMP lee sus variables al cargarse, por eso se fijan antes del primer `import torch`.
    """
    for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[variable] = str(hilos)
    import torch

    torch.set_num_threads(hilos)
    # Solo se puede fijar una vez por proceso (las pruebas cargan varias veces).
    with contextlib.suppress(RuntimeError):
        torch.set_num_interop_threads(1)


def verificar_revision(directorio: Path) -> dict[str, object]:
    """Comprueba que los pesos de `directorio` son la revisión fijada en §5.3."""
    ruta = directorio / ARCHIVO_REVISION
    try:
        registro = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ErrorModelo(f"No existe {ruta}: los pesos no los descargó el build") from error
    except json.JSONDecodeError as error:
        raise ErrorModelo(f"{ruta} no es JSON válido") from error
    esperado = {"modelo": MODELO_ID, "revision": MODELO_REVISION}
    encontrado = {clave: registro.get(clave) for clave in esperado}
    if encontrado != esperado:
        raise ErrorModelo(f"Los pesos de {directorio} son {encontrado}; se esperaba {esperado}")
    return registro


class ModeloDinov2:
    """Un único modelo en float32 y modo evaluación; una inferencia a la vez (ADR-EMB-07)."""

    def __init__(self, directorio: Path, hilos: int) -> None:
        self.directorio = Path(directorio)
        self.hilos = hilos
        self._red = None

    @property
    def cargado(self) -> bool:
        return self._red is not None

    def cargar(self) -> None:
        verificar_revision(self.directorio)
        fijar_hilos(self.hilos)
        from transformers import Dinov2Model
        from transformers.utils import logging as registro_transformers

        # Sin barras de progreso ni manejador propio: sus avisos salen por el log JSON del servicio.
        registro_transformers.disable_progress_bar()
        registro_transformers.disable_default_handler()
        registro_transformers.enable_propagation()

        red = Dinov2Model.from_pretrained(
            self.directorio, local_files_only=True, use_safetensors=True
        )
        red = red.float().eval()
        if red.config.hidden_size != DIM:
            raise ErrorModelo(f"El modelo produce {red.config.hidden_size} dimensiones, no {DIM}")
        self._red = red

    def calentar(self) -> None:
        """Dos inferencias (lote 1 y lote 8): la primera petición real no paga el arranque."""
        import torch

        for tamano in LOTES_CALENTAMIENTO:
            self.inferir(torch.zeros((tamano, 3, LADO_ENTRADA_PX, LADO_ENTRADA_PX)))

    def inferir(self, lote: torch.Tensor) -> np.ndarray:
        """Tensor (n, 3, 224, 224) ya preprocesado → matriz (n, DIM) float32 con norma L2 = 1.

        Descriptor: token CLS de la última capa tras la layernorm final (`pooler_output`, §5.3).
        """
        if self._red is None:
            raise ErrorModelo("El modelo no está cargado")
        import torch

        with torch.inference_mode():
            salida = self._red(pixel_values=lote.to(torch.float32))
            vectores = torch.nn.functional.normalize(salida.pooler_output, p=2.0, dim=1)
        return vectores.to(torch.float32).numpy()
