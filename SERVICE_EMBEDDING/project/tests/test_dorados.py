"""Vectores dorados (§5.4, ADR-EMB-12): tests/golden/ contra el modelo real.

Las pruebas con el modelo necesitan los pesos de la revisión fijada en MODELO_DIR (o en
project/.modelo, ver tools/dorados.py). Sin ellos se omiten, salvo con DORADOS_OBLIGATORIOS=1
(así corre en embedding.yml): entonces fallan, para que CI no las dé por buenas sin calcularlas.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app import config
from app.preproceso import preprocesar, preprocesar_lote

PROYECTO = Path(__file__).resolve().parents[1]
DIR_DORADOS = PROYECTO / "tests" / "golden"
ESPERADOS = json.loads((DIR_DORADOS / "esperados.json").read_text(encoding="utf-8"))
TOLERANCIA = 1e-5
TIPOS = {".jpg": "image/jpeg", ".png": "image/png"}


def directorio_modelo() -> Path:
    return Path(os.environ.get("MODELO_DIR") or PROYECTO / ".modelo")


def leer(entrada: dict) -> bytes:
    return (DIR_DORADOS / entrada["archivo"]).read_bytes()


def sinteticas(n: int = 3) -> list[bytes]:
    """JPEG de 640 × 480 con semilla fija (los mismos tipos de imagen que validate21 C2)."""
    rng = np.random.default_rng(2101)
    imagenes = []
    for _ in range(n):
        pixeles = rng.integers(0, 256, (480 // 8, 640 // 8, 3), dtype=np.uint8)
        imagen = Image.fromarray(pixeles).resize((640, 480), Image.Resampling.BILINEAR)
        salida = io.BytesIO()
        imagen.save(salida, "JPEG", quality=90)
        imagenes.append(salida.getvalue())
    return imagenes


# --- Sin modelo: los archivos y el preprocesamiento -----------------------------------------


def test_esperados_corresponden_a_la_version_del_codigo():
    assert ESPERADOS["version_vector"] == config.VERSION_VECTOR
    assert ESPERADOS["modelo"] == config.MODELO_ID
    assert ESPERADOS["revision"] == config.MODELO_REVISION
    assert ESPERADOS["dim"] == config.DIM
    assert ESPERADOS["tolerancia"] == TOLERANCIA


def test_cinco_imagenes_versionadas_y_sin_cambios():
    archivos = sorted(p.name for p in DIR_DORADOS.iterdir() if p.suffix in TIPOS)
    assert archivos == sorted(e["archivo"] for e in ESPERADOS["imagenes"])
    assert len(archivos) == 5
    for entrada in ESPERADOS["imagenes"]:
        assert entrada["archivo"].startswith("validacion-")
        assert entrada["tipo"] == TIPOS[Path(entrada["archivo"]).suffix]
        assert hashlib.sha256(leer(entrada)).hexdigest() == entrada["sha256"], entrada["archivo"]


def test_vectores_esperados_normalizados():
    for entrada in ESPERADOS["imagenes"]:
        vector = np.array(entrada["vector"], dtype=np.float32)
        assert vector.shape == (config.DIM,)
        assert abs(float(np.linalg.norm(vector)) - 1.0) <= 1e-4


def test_preprocesado_identico_al_de_los_dorados():
    """pp-v1 da los mismos bits que al calcular los dorados (Pillow y NumPy de uv.lock).

    Si una actualización cambia la decodificación o la redimensión, esto falla aunque los vectores
    sigan dentro de 1e-5: compruébalo con `tools/dorados.py comparar` y, si la tolerancia se
    cumple, recalcula con `tools/dorados.py vectores`; si no, hace falta una `version_vector` nueva.
    """
    for entrada in ESPERADOS["imagenes"]:
        huella = hashlib.sha256(preprocesar(leer(entrada)).tobytes()).hexdigest()
        assert huella == entrada["sha256_preprocesado"], entrada["archivo"]


# --- Con el modelo real ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def modelo():
    pytest.importorskip("torch")
    directorio = directorio_modelo()
    if not (directorio / config.ARCHIVO_REVISION).is_file():
        mensaje = f"sin pesos en {directorio} (MODELO_DIR o project/.modelo)"
        if os.environ.get("DORADOS_OBLIGATORIOS") == "1":
            pytest.fail(f"DORADOS_OBLIGATORIOS=1 y {mensaje}")
        pytest.skip(mensaje)
    from app.modelo import ModeloDinov2

    cargado = ModeloDinov2(directorio, hilos=1)
    cargado.cargar()
    return cargado


def test_vectores_dorados(modelo):
    """§5.4 y PLAN EMB-2.1 C1: cada imagen sola, ≤ 1e-5 por componente."""
    diferencias = {}
    for entrada in ESPERADOS["imagenes"]:
        obtenido = modelo.inferir(preprocesar_lote([leer(entrada)]))[0]
        esperado = np.array(entrada["vector"], dtype=np.float32)
        diferencias[entrada["archivo"]] = float(np.abs(obtenido - esperado).max())
    assert max(diferencias.values()) <= TOLERANCIA, diferencias


def test_el_vector_no_depende_del_lote(modelo):
    """§5.4 y PLAN EMB-2.1 C2: las 5 doradas y 3 sintéticas en un lote de 8 frente a solas."""
    imagenes = [leer(e) for e in ESPERADOS["imagenes"]] + sinteticas()
    lote = modelo.inferir(preprocesar_lote(imagenes))
    solas = np.concatenate([modelo.inferir(preprocesar_lote([imagen])) for imagen in imagenes])
    assert lote.shape == (8, config.DIM)
    assert float(np.abs(lote - solas).max()) <= TOLERANCIA
