"""Carga, calentamiento y descriptor del modelo (§4.2, §5.3, §5.4) con un DINOv2 diminuto aleatorio.

No usa los pesos reales (los prueban los vectores dorados de EMB-2.1 y validate11 en la imagen);
aquí se comprueba la mecánica — revisión verificada, float32, CLS tras la layernorm y norma L2 = 1.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from app import config  # noqa: E402
from app.modelo import ErrorModelo, ModeloDinov2, verificar_revision  # noqa: E402


def guardar_modelo(directorio, hidden_size=config.DIM, revision=config.MODELO_REVISION):
    torch.manual_seed(0)
    cfg = transformers.Dinov2Config(
        hidden_size=hidden_size,
        num_hidden_layers=1,
        num_attention_heads=12,
        mlp_ratio=1,
        image_size=224,
        patch_size=14,
    )
    transformers.Dinov2Model(cfg).save_pretrained(directorio, safe_serialization=True)
    registro = {"modelo": config.MODELO_ID, "revision": revision, "archivos": []}
    (directorio / config.ARCHIVO_REVISION).write_text(json.dumps(registro), encoding="utf-8")
    return directorio


@pytest.fixture(scope="module")
def modelo(tmp_path_factory):
    directorio = guardar_modelo(tmp_path_factory.mktemp("modelo"))
    modelo = ModeloDinov2(directorio, hilos=1)
    modelo.cargar()
    return modelo


def test_carga_en_float32_y_modo_evaluacion(modelo):
    assert modelo.cargado
    assert not modelo._red.training
    assert all(p.dtype == torch.float32 for p in modelo._red.parameters())


def test_calentamiento_con_lotes_de_1_y_8(modelo, monkeypatch):
    tamanos = []
    original = modelo.inferir
    monkeypatch.setattr(modelo, "inferir", lambda lote: tamanos.append(len(lote)) or original(lote))
    modelo.calentar()
    assert tamanos == [1, 8]


def test_vectores_de_dim_float32_con_norma_1(modelo):
    lote = torch.rand((3, 3, 224, 224), generator=torch.Generator().manual_seed(1))
    vectores = modelo.inferir(lote)
    assert vectores.shape == (3, config.DIM)
    assert vectores.dtype == np.float32
    np.testing.assert_allclose(np.linalg.norm(vectores, axis=1), 1.0, atol=1e-4)


def test_descriptor_es_el_cls_tras_la_layernorm_final(modelo):
    lote = torch.rand((2, 3, 224, 224), generator=torch.Generator().manual_seed(2))
    with torch.inference_mode():
        salida = modelo._red(pixel_values=lote)
        cls = salida.last_hidden_state[:, 0, :]
        esperado = torch.nn.functional.normalize(cls, dim=1).numpy()
    np.testing.assert_allclose(modelo.inferir(lote), esperado, atol=1e-6)


def test_misma_entrada_mismo_vector(modelo):
    lote = torch.rand((1, 3, 224, 224), generator=torch.Generator().manual_seed(3))
    np.testing.assert_array_equal(modelo.inferir(lote), modelo.inferir(lote.clone()))


def test_no_infiere_sin_cargar(tmp_path):
    with pytest.raises(ErrorModelo):
        ModeloDinov2(tmp_path, hilos=1).inferir(torch.zeros((1, 3, 224, 224)))


def test_sin_registro_de_revision_no_carga(tmp_path):
    with pytest.raises(ErrorModelo, match="no los descargó el build"):
        ModeloDinov2(tmp_path, hilos=1).cargar()


def test_revision_distinta_no_carga(tmp_path):
    guardar_modelo(tmp_path, revision="0" * 40)
    with pytest.raises(ErrorModelo, match="se esperaba"):
        verificar_revision(tmp_path)
    with pytest.raises(ErrorModelo):
        ModeloDinov2(tmp_path, hilos=1).cargar()


def test_dimension_distinta_no_carga(tmp_path):
    guardar_modelo(tmp_path, hidden_size=192)
    with pytest.raises(ErrorModelo, match="192"):
        ModeloDinov2(tmp_path, hilos=1).cargar()
