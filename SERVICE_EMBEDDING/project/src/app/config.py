"""Identidad del modelo y parámetros del servicio (ARCHITECTURE §5.2, §5.3, §5.5 y §5.7).

Las constantes de identidad (modelo, revisión, preprocesamiento, `version_vector`) son contrato:
cambiar cualquiera exige una `version_vector` nueva y re-indexar (ADR-EMB-08). Este módulo también
lo importa `tools/descargar_modelo.py` durante el build, así que solo depende de pydantic-settings.

Los parámetros de `Settings` se pueden sobrescribir con una variable de entorno del mismo nombre;
las que inyecta la infraestructura están en infra §5.4.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICIO = "campus-locator-embedding"
VERSION_SERVICIO = "0.1.0"

MODELO_ID = "facebook/dinov2-small"
# Commit del repositorio de Hugging Face fijado en 0.5.0 (ARCHITECTURE §5.3, ADR-EMB-11).
MODELO_REVISION = "ed25f3a31f01632728cabb09d1542f84ab7b0056"
ARQUITECTURA = "ViT-S/14"
PREPROCESAMIENTO = "pp-v1"
VERSION_VECTOR = "dinov2-vits14/pp-v1"
DIM = 384
NORMALIZACION = "l2"
METRICA = "coseno"
DISPOSITIVO = "cpu"

# Archivos del repositorio del modelo que entran en la imagen (/opt/modelo) y el registro que deja
# el build con la revisión descargada; el servicio no arranca si no coincide con MODELO_REVISION.
ARCHIVOS_MODELO = ("config.json", "model.safetensors", "preprocessor_config.json")
ARCHIVO_REVISION = "revision.json"

_PATRON_SHA = re.compile(r"[0-9a-f]{7,40}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Inyectadas por la infraestructura (infra §5.4).
    app_env: str = "local"
    log_level: str = "INFO"
    torch_num_threads: int = Field(default=1, ge=1)

    # Fijadas en el Dockerfile (§5.5).
    modelo_dir: Path = Path("/opt/modelo")
    git_commit: str = "desconocido"

    # Parámetros operativos (§5.7). Los usa la vectorización (EMB-2.1).
    lote_max: int = Field(default=8, ge=1)
    bytes_max_imagen: int = 4 * 1024 * 1024
    bytes_max_peticion: int = 16 * 1024 * 1024
    lado_min_px: int = 64
    cola_max_imagenes: int = 40
    retry_after_s: int = 5

    @property
    def commit_corto(self) -> str:
        """SHA corto del commit de la imagen (7 caracteres), o el valor tal cual si no es un SHA."""
        commit = self.git_commit.strip().lower()
        return commit[:7] if _PATRON_SHA.fullmatch(commit) else self.git_commit


@lru_cache
def obtener_settings() -> Settings:
    return Settings()
