"""Pipeline de preprocesamiento pp-v1 (ARCHITECTURE §5.3): función pura bytes → tensor.

Devuelve un array de NumPy (3, 224, 224) float32 sin depender de PyTorch; `modelo.inferir` lo
convierte. Los pasos y sus constantes son contrato: cambiar cualquiera exige una `version_vector`
nueva (ADR-EMB-08). Lo que la tabla de §5.3 no detalla se hace igual que el procesador publicado
con el modelo (`preprocessor_config.json`, `BitImageProcessorPil` de transformers), y lo fijan los
vectores dorados (§5.4):
- el lado largo se escala con truncado: `int(256 * largo / corto)`;
- el recorte central empieza en `(lado - 224) // 2`;
- la escala a [0, 1] multiplica en float64 por 1/255 y baja a float32; la normalización
  `(x - media) / desviación` se hace en float32.

Además de lo que hace ese procesador, aplica la orientación EXIF (paso 1 de §5.3).
"""

from __future__ import annotations

import io
import warnings
from collections.abc import Sequence

import numpy as np
from PIL import Image, ImageOps

LADO_REDIMENSION_PX = 256
LADO_RECORTE_PX = 224
ESCALA = 1.0 / 255.0
MEDIA = np.array([0.485, 0.456, 0.406], dtype=np.float32)
DESVIACION = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# Formatos que se intentan decodificar, sea cual sea el tipo declarado (image/jpeg o image/png).
FORMATOS = ("JPEG", "PNG")

# Pillow avisa (DecompressionBombWarning) por encima de Image.MAX_IMAGE_PIXELS (~89,5 MP) y falla
# por encima del doble. Aquí los dos casos se rechazan como IMAGEN_INVALIDA (§5.6), así que el
# aviso no aporta nada y no debe salir por stderr fuera del log JSON.
warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)


class ImagenInvalida(ValueError):
    """La imagen no se puede usar (§5.6 `IMAGEN_INVALIDA`); `indice` es su posición en el lote."""

    def __init__(self, motivo: str, indice: int | None = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.indice = indice


def tamano_redimensionado(ancho: int, alto: int) -> tuple[int, int]:
    """(ancho, alto) con el lado menor a 256 px y el mayor truncado, manteniendo la proporción."""
    if ancho <= alto:
        return LADO_REDIMENSION_PX, int(LADO_REDIMENSION_PX * alto / ancho)
    return int(LADO_REDIMENSION_PX * ancho / alto), LADO_REDIMENSION_PX


def caja_recorte(ancho: int, alto: int) -> tuple[int, int, int, int]:
    """Caja (izquierda, arriba, derecha, abajo) del recorte central de 224 × 224 px."""
    izquierda = (ancho - LADO_RECORTE_PX) // 2
    arriba = (alto - LADO_RECORTE_PX) // 2
    return izquierda, arriba, izquierda + LADO_RECORTE_PX, arriba + LADO_RECORTE_PX


def decodificar(datos: bytes, lado_min_px: int, proporcion_max: int) -> Image.Image:
    """Paso 1: Pillow, orientación EXIF aplicada y RGB (descarta alfa).

    Rechaza con `ImagenInvalida` lo que no es un JPEG o PNG decodificable, lo que supera
    `Image.MAX_IMAGE_PIXELS`, lo que mide menos de `lado_min_px` de lado y aquello cuyo lado largo
    pasa de `proporcion_max` veces el corto (§5.6, §5.7). Los tamaños se comprueban con la
    cabecera, antes de decodificar. Sin el límite de proporción, una imagen de 64 × 1 000 000 px
    obligaría a la redimensión a crear un intermedio de varios GB (el lado menor sube a 256).
    """
    try:
        imagen = Image.open(io.BytesIO(datos), formats=FORMATOS)
    except Image.DecompressionBombError as error:
        raise ImagenInvalida(f"tiene demasiados píxeles ({error})") from error
    except MemoryError:
        raise
    except Exception as error:
        raise ImagenInvalida("no se pudo decodificar como JPEG ni como PNG") from error

    ancho, alto = imagen.size
    if ancho * alto > Image.MAX_IMAGE_PIXELS:
        raise ImagenInvalida(
            f"tiene {ancho * alto / 1e6:.1f} MP; el máximo es {Image.MAX_IMAGE_PIXELS / 1e6:.1f} MP"
        )
    if min(ancho, alto) < lado_min_px:
        raise ImagenInvalida(f"mide {ancho} × {alto} px; el mínimo es {lado_min_px} px de lado")
    if max(ancho, alto) > proporcion_max * min(ancho, alto):
        raise ImagenInvalida(
            f"mide {ancho} × {alto} px; el lado largo no puede pasar de {proporcion_max} veces "
            "el corto"
        )

    try:
        imagen.load()
        imagen = ImageOps.exif_transpose(imagen)
        return imagen.convert("RGB")
    except MemoryError:
        raise
    except Exception as error:
        raise ImagenInvalida(f"no se pudo decodificar ({type(error).__name__})") from error


def a_tensor(imagen: Image.Image) -> np.ndarray:
    """Pasos 2 a 4 sobre una imagen RGB: redimensión, recorte central y normalización."""
    redimensionada = imagen.resize(
        tamano_redimensionado(*imagen.size), Image.Resampling.BICUBIC, reducing_gap=None
    )
    recortada = redimensionada.crop(caja_recorte(*redimensionada.size))
    pixeles = np.asarray(recortada, dtype=np.uint8)  # (224, 224, 3)
    escalada = (pixeles.astype(np.float64) * ESCALA).astype(np.float32)
    normalizada = (escalada - MEDIA) / DESVIACION
    return np.ascontiguousarray(normalizada.transpose(2, 0, 1), dtype=np.float32)


def preprocesar(datos: bytes, lado_min_px: int = 64, proporcion_max: int = 32) -> np.ndarray:
    """Bytes de una imagen JPEG o PNG → array (3, 224, 224) float32 listo para el modelo."""
    return a_tensor(decodificar(datos, lado_min_px, proporcion_max))


def preprocesar_lote(
    imagenes: Sequence[bytes], lado_min_px: int = 64, proporcion_max: int = 32
) -> np.ndarray:
    """Lote de imágenes → array (n, 3, 224, 224); la primera que falla se informa con su índice."""
    tensores = []
    for indice, datos in enumerate(imagenes):
        try:
            tensores.append(preprocesar(datos, lado_min_px, proporcion_max))
        except ImagenInvalida as error:
            error.indice = indice
            raise
    return np.stack(tensores)
