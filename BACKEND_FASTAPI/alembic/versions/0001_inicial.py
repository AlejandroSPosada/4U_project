"""esquema inicial + extensión pgvector

Revision ID: 0001
Revises:
"""
import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Fijos a propósito: una migración no debe depender de constantes que luego cambien.
EMBEDDING_DIM = 768
CATEGORIAS = "'BIBLIOTECA','CAFETERIA','BANO','BLOQUE','AUDITORIO','DEPORTES','ADMINISTRACION','ENTRADA'"
TIPOS_ALERTA = "'agua','mobiliario','escalones','obra','vehiculos','otro'"


def upgrade() -> None:
    # Lo que pide la infra (ARCHITECTURE infra 12.1). Terraform no ejecuta SQL.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("correo", sa.String(254), nullable=False, unique=True),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("rol", sa.String(10), nullable=False, server_default="USER"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint("rol IN ('USER','ADMIN')", name="ck_usuarios_rol"),
    )

    op.create_table(
        "videos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("nombre", sa.String(40), nullable=False),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("inicio_lat", sa.Float()),
        sa.Column("inicio_lng", sa.Float()),
        sa.Column("inicio_rumbo", sa.Float()),
        sa.Column("estado", sa.String(20), nullable=False, server_default="SUBIDA"),
        sa.Column("duracion_s", sa.Float()),
        sa.Column("distancia_m", sa.Float()),
        sa.Column("pasos", sa.Integer()),
    )

    op.create_table(
        "lugares",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(120), nullable=False, unique=True),
        sa.Column("categoria", sa.String(20), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("alias", sa.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("descripcion", sa.Text()),
        sa.Column("referencias", sa.Text()),
        sa.Column("imagen_s3_key", sa.Text()),
        sa.CheckConstraint(f"categoria IN ({CATEGORIAS})", name="ck_lugares_categoria"),
    )

    op.create_table(
        "fotos",
        sa.Column("video_id", sa.String(64), sa.ForeignKey("videos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("rumbo", sa.Float()),
        sa.Column("capturada_en", sa.DateTime(timezone=True)),
        sa.Column("lugar_id", sa.Integer(), sa.ForeignKey("lugares.id", ondelete="SET NULL")),
        sa.Column("estado", sa.String(12), nullable=False, server_default="SUBIDA"),
        sa.Column("calidad", sa.String(10), nullable=False, server_default="NORMAL"),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(EMBEDDING_DIM)),
        sa.CheckConstraint("rumbo IS NULL OR (rumbo >= 0 AND rumbo < 360)", name="ck_fotos_rumbo"),
        sa.CheckConstraint("estado IN ('SUBIDA','PROCESADA','ERROR')", name="ck_fotos_estado"),
        sa.CheckConstraint("calidad IN ('ALTA','NORMAL','BAJA')", name="ck_fotos_calidad"),
    )
    op.create_index(
        "ix_fotos_embedding_hnsw",
        "fotos",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "alertas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("mensaje", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(12), nullable=False),
        sa.Column("prioridad", sa.String(8), nullable=False, server_default="normal"),
        sa.Column("radio", sa.Integer(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("vigencia_inicio", sa.DateTime(timezone=True)),
        sa.Column("vigencia_fin", sa.DateTime(timezone=True)),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(f"tipo IN ({TIPOS_ALERTA})", name="ck_alertas_tipo"),
        sa.CheckConstraint("prioridad IN ('normal','alta')", name="ck_alertas_prioridad"),
        sa.CheckConstraint("radio BETWEEN 5 AND 100", name="ck_alertas_radio"),
    )

    op.create_table(
        "consultas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("creada_en", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("confianza", sa.Float()),
        sa.Column("lat", sa.Float()),
        sa.Column("lng", sa.Float()),
        sa.CheckConstraint("tipo IN ('localize','frame')", name="ck_consultas_tipo"),
    )


def downgrade() -> None:
    op.drop_table("consultas")
    op.drop_table("alertas")
    op.drop_index("ix_fotos_embedding_hnsw", table_name="fotos")
    op.drop_table("fotos")
    op.drop_table("lugares")
    op.drop_table("videos")
    op.drop_table("usuarios")
    # La extensión se deja instalada a propósito.
