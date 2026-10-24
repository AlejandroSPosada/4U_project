"""Identidad del modelo y parámetros (§5.3, §5.5, §5.7) y coherencia con la documentación."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from app import config
from app.config import Settings

PROYECTO = Path(__file__).resolve().parents[1]
ARCHITECTURE = PROYECTO.parent / "docs" / "ARCHITECTURE.md"

VARIABLES = (
    "APP_ENV",
    "LOG_LEVEL",
    "TORCH_NUM_THREADS",
    "MODELO_DIR",
    "GIT_COMMIT",
    "LOTE_MAX",
    "BYTES_MAX_IMAGEN",
    "BYTES_MAX_PETICION",
    "LADO_MIN_PX",
    "COLA_MAX_IMAGENES",
    "RETRY_AFTER_S",
)


@pytest.fixture
def entorno_limpio(monkeypatch):
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    return monkeypatch


def test_identidad_del_vector():
    assert config.MODELO_ID == "facebook/dinov2-small"
    assert config.VERSION_VECTOR == "dinov2-vits14/pp-v1"
    assert config.DIM == 384
    assert re.fullmatch(r"[0-9a-f]{40}", config.MODELO_REVISION)


def test_revision_coincide_con_architecture():
    """La revisión del código es la de ARCHITECTURE §5.3 (validate11 C2 lo exige en la imagen)."""
    filas = [
        linea
        for linea in ARCHITECTURE.read_text(encoding="utf-8").splitlines()
        if linea.startswith("| Revisión |")
    ]
    assert len(filas) == 1, "ARCHITECTURE §5.3 debe tener una sola fila «Revisión»"
    anotadas = re.findall(r"\b[0-9a-f]{40}\b", filas[0])
    assert anotadas == [config.MODELO_REVISION]


def test_parametros_por_defecto(entorno_limpio):
    settings = Settings()
    assert settings.app_env == "local"
    assert settings.torch_num_threads == 1
    assert settings.modelo_dir == Path("/opt/modelo")
    assert settings.lote_max == 8
    assert settings.bytes_max_imagen == 4 * 1024 * 1024
    assert settings.bytes_max_peticion == 16 * 1024 * 1024
    assert settings.lado_min_px == 64
    assert settings.cola_max_imagenes == 40
    assert settings.retry_after_s == 5
    assert settings.commit_corto == "desconocido"


def test_variables_que_inyecta_la_infraestructura(entorno_limpio):
    entorno_limpio.setenv("APP_ENV", "dev")
    entorno_limpio.setenv("LOG_LEVEL", "DEBUG")
    entorno_limpio.setenv("TORCH_NUM_THREADS", "2")
    entorno_limpio.setenv("MODELO_DIR", "/tmp/modelo")
    entorno_limpio.setenv("GIT_COMMIT", "ABCDEF0123456789abcdef0123456789abcdef01")
    settings = Settings()
    assert (settings.app_env, settings.log_level, settings.torch_num_threads) == ("dev", "DEBUG", 2)
    assert settings.modelo_dir == Path("/tmp/modelo")
    assert settings.commit_corto == "abcdef0"


def test_hilos_invalidos_se_rechazan(entorno_limpio):
    entorno_limpio.setenv("TORCH_NUM_THREADS", "0")
    with pytest.raises(ValueError):
        Settings()


def test_descargar_modelo_usa_la_revision_fija(tmp_path, monkeypatch):
    pytest.importorskip("huggingface_hub")
    spec = importlib.util.spec_from_file_location(
        "descargar_modelo", PROYECTO / "tools" / "descargar_modelo.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    llamadas = {}

    def falso_snapshot(**kwargs):
        llamadas.update(kwargs)
        for nombre in kwargs["allow_patterns"]:
            (Path(kwargs["local_dir"]) / nombre).write_text("x")

    monkeypatch.setattr(modulo, "snapshot_download", falso_snapshot)
    assert modulo.main([str(tmp_path)]) == 0
    assert llamadas["repo_id"] == config.MODELO_ID
    assert llamadas["revision"] == config.MODELO_REVISION

    from app.modelo import verificar_revision

    registro = verificar_revision(tmp_path)
    assert registro["archivos"] == list(config.ARCHIVOS_MODELO)
