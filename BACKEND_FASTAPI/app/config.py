"""Única fuente de configuración. Ningún otro archivo lee os.environ.

Los nombres coinciden con la tabla 4.1 de INFRASTRUCTURA_TERRAFORM/ARCHITECTURE.md.
Todo tiene valor por defecto para que el proceso arranque (y /health responda) aunque falte algo;
lo que falte se detecta al usarlo (ver app.db.engine y /health/ready).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")  # nombres de entorno sin distinguir mayúsculas

    # --- Inyectadas por Terraform ---
    app_env: str = "dev"
    aws_region: str = "us-east-1"
    database_host: str = ""
    database_port: int = 5432  # llega como texto; pydantic lo convierte
    database_name: str = "campus"
    database_secret_arn: str = ""
    s3_bucket_dataset: str = ""
    s3_bucket_scans: str = ""  # llega VACÍO si el bucket no existe
    embedding_service_url: str = ""
    jwt_secret_arn: str = ""

    # --- Solo desarrollo local (NO la inyecta la infra; se ignora/rechaza en prod) ---
    local_database_url: str = ""

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
