"""Variantes de preprocesamiento y extracción que EMB-3.2 compara con pp-v1 (ARCHITECTURE §4.5).

Ninguna se despliega: si una gana, se abre EMB-5.1 con `version_vector` nueva (ADR-EMB-08). Se
calculan en este proceso con los pesos de `project/.modelo/` (o `MODELO_DIR`) y los vecinos se
buscan por fuerza bruta sobre el dataset vectorizado con la misma variante.

Para añadir una: una función `bytes → array (3, H, W)` float32 normalizado (H y W múltiplos de 14)
y la extracción (`cls` o `media_parches`), y una entrada en `VARIANTES`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.preproceso import DESVIACION, ESCALA, MEDIA, decodificar, preprocesar
from evaluacion.conjunto import CoberturaPunto, Conjunto, Foto
from evaluacion.fuentes import FuenteDataset, indexar, preparar_foto
from evaluacion.metricas import consultar, metricas_variante

PARCHE_PX = 14
LADO_MAYOR_MAX_PX = 64 * PARCHE_PX  # sin-recorte: tope de 896 px (fotos muy apaisadas)
DIRECTORIO_MODELO = Path(__file__).resolve().parents[2] / ".modelo"


def _normalizar(imagen: Image.Image) -> np.ndarray:
    """Escala y normalización de pp-v1 (§5.3, paso 4) sobre una imagen RGB ya del tamaño final."""
    pixeles = np.asarray(imagen, dtype=np.uint8)
    escalada = (pixeles.astype(np.float64) * ESCALA).astype(np.float32)
    normalizada = (escalada - MEDIA) / DESVIACION
    return np.ascontiguousarray(normalizada.transpose(2, 0, 1), dtype=np.float32)


def sin_recorte(datos: bytes) -> np.ndarray:
    """Lado menor a 224 y el mayor proporcional, truncado a múltiplo de 14 (tope 896): no se
    pierde el tercio de altura de las fotos verticales (ADR-EMB-04)."""
    imagen = decodificar(datos, 64, 32)
    corto, largo = min(imagen.size), max(imagen.size)
    lado_largo = min(LADO_MAYOR_MAX_PX, max(224, (224 * largo // corto) // PARCHE_PX * PARCHE_PX))
    tamano = (lado_largo, 224) if imagen.width >= imagen.height else (224, lado_largo)
    return _normalizar(imagen.resize(tamano, Image.Resampling.BICUBIC, reducing_gap=None))


def resolucion_448(datos: bytes) -> np.ndarray:
    """Como pp-v1 al doble: lado menor a 512 y recorte central de 448 (32 × 32 parches)."""
    imagen = decodificar(datos, 64, 32)
    corto = min(imagen.size)
    if imagen.width <= imagen.height:
        tamano = (512, int(512 * imagen.height / corto))
    else:
        tamano = (int(512 * imagen.width / corto), 512)
    grande = imagen.resize(tamano, Image.Resampling.BICUBIC, reducing_gap=None)
    izquierda, arriba = (grande.width - 448) // 2, (grande.height - 448) // 2
    return _normalizar(grande.crop((izquierda, arriba, izquierda + 448, arriba + 448)))


@dataclass(frozen=True)
class Variante:
    nombre: str
    descripcion: str
    preprocesar: Callable[[bytes], np.ndarray]
    extraccion: str  # "cls" (pooler_output, como pp-v1) | "media_parches"


VARIANTES: dict[str, Variante] = {
    v.nombre: v
    for v in (
        Variante("pp-v1", "referencia, igual que el servicio (§5.3)", preprocesar, "cls"),
        Variante("sin-recorte", "lado menor 224 sin recorte central", sin_recorte, "cls"),
        Variante("res-448", "lado menor 512 y recorte central 448", resolucion_448, "cls"),
        Variante("media-parches", "pp-v1, media de los tokens de parches", preprocesar,
                 "media_parches"),
    )
}  # fmt: skip


class ExtractorDinov2:
    """`Dinov2Model` de la revisión fijada (comprueba `revision.json` como el servicio)."""

    def __init__(self, directorio: Path | None = None, hilos: int = 1) -> None:
        self.directorio = Path(directorio or os.environ.get("MODELO_DIR") or DIRECTORIO_MODELO)
        self.hilos = hilos
        self._red = None

    def cargar(self) -> ExtractorDinov2:
        if self._red is None:
            from transformers import Dinov2Model

            from app.modelo import fijar_hilos, verificar_revision

            verificar_revision(self.directorio)
            fijar_hilos(self.hilos)
            red = Dinov2Model.from_pretrained(
                self.directorio, local_files_only=True, use_safetensors=True
            )
            self._red = red.float().eval()
        return self

    def vector(self, tensor: np.ndarray, extraccion: str) -> np.ndarray:
        import torch

        self.cargar()
        with torch.inference_mode():
            salida = self._red(pixel_values=torch.from_numpy(np.ascontiguousarray(tensor)[None]))
        if extraccion == "cls":
            v = salida.pooler_output[0]
        elif extraccion == "media_parches":
            v = salida.last_hidden_state[0, 1:].mean(dim=0)  # ya con la layernorm final
        else:
            raise ValueError(f"extracción desconocida: {extraccion}")
        v = v.double().numpy()
        return (v / np.linalg.norm(v)).astype(np.float32)


def vectorizador(variante: Variante, extractor) -> Callable[[bytes], np.ndarray]:
    return lambda datos: extractor.vector(variante.preprocesar(datos), variante.extraccion)


def comparar(
    conjunto: Conjunto,
    cobertura: Sequence[CoberturaPunto],
    fuente: FuenteDataset,
    variantes: Sequence[Variante],
    extractor,
    leer: Callable[[Foto], bytes],
    progreso: Callable[[str], None] | None = None,
) -> list[dict]:
    """Recall a 15 m de cada variante, con el dataset vectorizado aquí y fuerza bruta."""
    filas = []
    for variante in variantes:
        if progreso:
            progreso(f"variante {variante.nombre}: vectorizando el dataset")
        vectorizar = vectorizador(variante, extractor)
        # El dataset, reducido como lo envía el worker (lado mayor 1024, backend §5.10).
        buscador = indexar(fuente, lambda datos, v=vectorizar: v(preparar_foto(datos)))
        buscador.vectorizar = vectorizar  # las consultas ya llegan preparadas (`leer`)
        resultados = consultar(conjunto, cobertura, buscador, leer)
        # pp-v1 calculada aquí se llama pp-v1-local: la de referencia es la del backend (HNSW).
        nombre = f"{variante.nombre}-local" if variante.nombre == "pp-v1" else variante.nombre
        fila = metricas_variante(nombre, resultados)
        fila["descripcion"] = variante.descripcion
        fila["vecinos"] = "fuerza_bruta_local"
        filas.append(fila)
    return filas
