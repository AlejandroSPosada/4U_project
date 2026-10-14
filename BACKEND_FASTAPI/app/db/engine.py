"""Motor de SQLAlchemy.

En AWS la contraseña viene de Secrets Manager (DATABASE_SECRET_ARN) y RDS la ROTA sola
(secreto administrado). Por eso cada conexión NUEVA lee el secreto (con caché corta) en lugar de
fijar la contraseña al crear el motor; si falla la autenticación se invalida la caché y se reintenta una vez.
TLS obligatorio (rds.force_ssl = 1): sslmode=require.
"""
from functools import lru_cache

import psycopg
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import get_settings
from app.services import secrets


def _connect() -> psycopg.Connection:
    s = get_settings()
    if not (s.database_host and s.database_secret_arn):
        raise RuntimeError("Faltan DATABASE_HOST o DATABASE_SECRET_ARN")

    def attempt() -> psycopg.Connection:
        cred = secrets.get_secret_json(s.database_secret_arn)
        return psycopg.connect(
            host=s.database_host,
            port=s.database_port,
            dbname=s.database_name,
            user=cred["username"],
            password=cred["password"],
            sslmode="require",
            connect_timeout=10,
        )

    try:
        return attempt()
    except psycopg.OperationalError:
        secrets.invalidate(s.database_secret_arn)
        return attempt()


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    if s.local_database_url:
        if s.is_prod:
            raise RuntimeError("LOCAL_DATABASE_URL no se admite con APP_ENV=prod")
        return create_engine(s.local_database_url, pool_pre_ping=True)
    return create_engine(
        "postgresql+psycopg://",
        creator=_connect,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=5,
    )
