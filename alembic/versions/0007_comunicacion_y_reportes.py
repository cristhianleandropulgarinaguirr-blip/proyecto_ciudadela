"""Bloque 3: notificaciones, PQRS y documentos del conjunto.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tablas = set(sa.inspect(op.get_bind()).get_table_names())

    if "notificaciones" not in tablas:
        op.create_table(
            "notificaciones",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("mensaje", sa.String(), nullable=True),
            sa.Column("enlace", sa.String(), nullable=True),
            sa.Column("leida", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fecha", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_notificaciones_id", "notificaciones", ["id"])
        op.create_index("ix_notificaciones_usuario_id", "notificaciones", ["usuario_id"])
        op.create_index("ix_notificaciones_leida", "notificaciones", ["leida"])
        op.create_index("ix_notificaciones_fecha", "notificaciones", ["fecha"])

    if "pqrs" not in tablas:
        op.create_table(
            "pqrs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False),
            sa.Column("asunto", sa.String(), nullable=False),
            sa.Column("descripcion", sa.String(), nullable=False),
            sa.Column("estado", sa.String(), nullable=False, server_default="Radicada"),
            sa.Column("respuesta", sa.String(), nullable=True),
            sa.Column("respondido_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_respuesta", sa.DateTime(), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
            sa.Column("fecha_actualizacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_pqrs_id", "pqrs", ["id"])
        op.create_index("ix_pqrs_usuario_id", "pqrs", ["usuario_id"])
        op.create_index("ix_pqrs_estado", "pqrs", ["estado"])
        op.create_index("ix_pqrs_fecha_creacion", "pqrs", ["fecha_creacion"])

    if "documentos" not in tablas:
        op.create_table(
            "documentos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("categoria", sa.String(), nullable=False, server_default="Otros"),
            sa.Column("descripcion", sa.String(), nullable=True),
            sa.Column("archivo", sa.String(), nullable=False),
            sa.Column("nombre_original", sa.String(), nullable=False),
            sa.Column("tamano", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("subido_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_documentos_id", "documentos", ["id"])
        op.create_index("ix_documentos_fecha_creacion", "documentos", ["fecha_creacion"])


def downgrade() -> None:
    op.drop_table("documentos")
    op.drop_table("pqrs")
    op.drop_table("notificaciones")
