"""Preprocesamiento pp-v1 (§5.3) y rechazos de IMAGEN_INVALIDA (§5.6): función pura, sin modelo."""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from app import preproceso
from app.preproceso import (
    DESVIACION,
    MEDIA,
    ImagenInvalida,
    caja_recorte,
    preprocesar,
    preprocesar_lote,
    tamano_redimensionado,
)


def codificar(imagen: Image.Image, formato: str = "PNG", **opciones) -> bytes:
    salida = io.BytesIO()
    imagen.save(salida, formato, **opciones)
    return salida.getvalue()


def ruido(ancho: int, alto: int, semilla: int = 0, modo: str = "RGB") -> Image.Image:
    canales = {"RGB": 3, "RGBA": 4}[modo]
    pixeles = np.random.default_rng(semilla).integers(0, 256, (alto, ancho, canales), np.uint8)
    return Image.fromarray(pixeles, modo)


def esperado_color(rgb: tuple[int, int, int]) -> np.ndarray:
    escalado = (np.array(rgb, dtype=np.float64) / 255.0).astype(np.float32)
    return (escalado - MEDIA) / DESVIACION


@pytest.mark.parametrize(
    ("tamano", "esperado"),
    [
        ((640, 480), (341, 256)),  # int(256 · 640 / 480) = 341 (truncado, no redondeo)
        ((480, 640), (256, 341)),
        ((300, 300), (256, 256)),
        ((100, 75), (341, 256)),  # se amplía
        ((1024, 256), (1024, 256)),
        ((343, 257), (341, 256)),
    ],
)
def test_lado_menor_a_256_con_el_mayor_truncado(tamano, esperado):
    assert tamano_redimensionado(*tamano) == esperado


def test_recorte_central_con_division_entera():
    assert caja_recorte(256, 256) == (16, 16, 240, 240)
    assert caja_recorte(341, 256) == (58, 16, 282, 240)  # (341 − 224) // 2 = 58
    assert caja_recorte(224, 224) == (0, 0, 224, 224)


def test_salida_3x224x224_float32_contigua():
    tensor = preprocesar(codificar(ruido(640, 480), "JPEG"))
    assert tensor.shape == (3, 224, 224)
    assert tensor.dtype == np.float32
    assert tensor.flags["C_CONTIGUOUS"]


def test_normalizacion_imagenet_por_canal():
    tensor = preprocesar(codificar(Image.new("RGB", (300, 200), (255, 128, 0))))
    np.testing.assert_array_equal(tensor[:, 100, 100], esperado_color((255, 128, 0)))
    assert np.all(tensor == tensor[:, :1, :1])


def test_orientacion_exif_aplicada():
    base = ruido(320, 200, semilla=1)
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: girar 90° en sentido horario para mostrar
    con_exif = codificar(base, "PNG", exif=exif)
    girada = codificar(base.transpose(Image.Transpose.ROTATE_270))
    np.testing.assert_array_equal(preprocesar(con_exif), preprocesar(girada))
    assert not np.array_equal(preprocesar(con_exif), preprocesar(codificar(base)))


def test_alfa_se_descarta_sin_mezclar_con_fondo():
    rgba = ruido(200, 150, semilla=2, modo="RGBA")
    pixeles = np.asarray(rgba).copy()
    pixeles[..., 3] = 0  # totalmente transparente: cuentan solo los canales RGB
    transparente = Image.fromarray(pixeles, "RGBA")
    np.testing.assert_array_equal(
        preprocesar(codificar(transparente)), preprocesar(codificar(rgba.convert("RGB")))
    )


def test_gris_se_replica_en_los_tres_canales():
    gris = Image.fromarray(np.asarray(ruido(200, 120, semilla=3))[..., 0], "L")
    np.testing.assert_array_equal(
        preprocesar(codificar(gris)), preprocesar(codificar(gris.convert("RGB")))
    )


def test_igual_al_procesador_publicado_con_el_modelo():
    """pp-v1 = BitImageProcessorPil con los valores de preprocessor_config.json (ADR-EMB-04)."""
    pytest.importorskip("transformers")
    from transformers.models.bit.image_processing_pil_bit import BitImageProcessorPil

    procesador = BitImageProcessorPil(
        do_resize=True,
        size={"shortest_edge": 256},
        resample=Image.Resampling.BICUBIC,
        do_center_crop=True,
        crop_size={"height": 224, "width": 224},
        do_rescale=True,
        rescale_factor=1 / 255,
        do_normalize=True,
        image_mean=[0.485, 0.456, 0.406],
        image_std=[0.229, 0.224, 0.225],
        do_convert_rgb=True,
    )
    for semilla, (ancho, alto) in enumerate([(640, 480), (343, 257), (257, 199), (100, 75)]):
        for formato in ("PNG", "JPEG"):
            datos = codificar(ruido(ancho, alto, semilla), formato)
            referencia = procesador(Image.open(io.BytesIO(datos)), return_tensors="np")
            np.testing.assert_array_equal(preprocesar(datos), referencia["pixel_values"][0])


def test_lote_conserva_el_orden():
    imagenes = [codificar(ruido(200, 100, semilla=s), "JPEG") for s in range(3)]
    lote = preprocesar_lote(imagenes)
    assert lote.shape == (3, 3, 224, 224)
    for i, datos in enumerate(imagenes):
        np.testing.assert_array_equal(lote[i], preprocesar(datos))


def jpeg_truncado() -> bytes:
    datos = codificar(ruido(640, 480, semilla=4), "JPEG", quality=90)
    return datos[: len(datos) // 2]


@pytest.mark.parametrize(
    ("datos", "motivo"),
    [
        (b"no es una imagen", "no se pudo decodificar"),
        (jpeg_truncado(), "no se pudo decodificar"),
        (codificar(ruido(100, 100), "GIF"), "no se pudo decodificar"),
        (codificar(ruido(63, 400)), "mínimo es 64 px"),
        (codificar(ruido(400, 63)), "mínimo es 64 px"),
    ],
    ids=["basura", "jpeg-truncado", "gif", "estrecha", "baja"],
)
def test_imagenes_invalidas(datos, motivo):
    with pytest.raises(ImagenInvalida, match=motivo):
        preprocesar(datos)


def test_proporcion_maxima_32_a_1():
    """Más alargada que 32:1 se rechaza: la redimensión crearía un intermedio enorme (§5.6)."""
    assert preprocesar(codificar(ruido(64, 2048))).shape == (3, 224, 224)
    assert preprocesar(codificar(ruido(2048, 64))).shape == (3, 224, 224)
    for tamano in [(64, 2049), (2049, 64)]:
        with pytest.raises(ImagenInvalida, match="32 veces el corto"):
            preprocesar(codificar(ruido(*tamano)))
    with pytest.raises(ImagenInvalida):
        preprocesar(codificar(ruido(100, 600)), proporcion_max=5)


def test_64_px_de_lado_es_valida():
    assert preprocesar(codificar(ruido(64, 64))).shape == (3, 224, 224)


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_demasiados_pixeles_se_rechaza_antes_de_decodificar(monkeypatch):
    monkeypatch.setattr(preproceso.Image, "MAX_IMAGE_PIXELS", 100 * 100)
    with pytest.raises(ImagenInvalida, match="MP"):
        preprocesar(codificar(ruido(150, 100)))  # entre el máximo y el doble: aviso de Pillow
    with pytest.raises(ImagenInvalida, match="demasiados píxeles"):
        preprocesar(codificar(ruido(300, 300)))  # más del doble: Pillow falla al abrir


def test_el_lote_informa_el_indice_de_la_primera_invalida():
    buena = codificar(ruido(100, 100), "JPEG")
    with pytest.raises(ImagenInvalida) as error:
        preprocesar_lote([buena, buena, jpeg_truncado(), b"basura"])
    assert error.value.indice == 2
