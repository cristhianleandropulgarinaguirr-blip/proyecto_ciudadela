"""Versión 3.6 (Fase 2): tabla de paz y salvo con código QR de verificación.

Crea `paz_y_salvos`. Es seguro correrla varias veces: solo crea la tabla si falta.

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "paz_y_salvos" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "paz_y_salvos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("codigo", sa.String, nullable=False),
        sa.Column("destino", sa.String(80), nullable=True),
        sa.Column("fecha_emision", sa.DateTime, nullable=False),
        sa.Column("valido_hasta", sa.DateTime, nullable=False),
        sa.Column("emitido_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("revocado", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_paz_y_salvos_id", "paz_y_salvos", ["id"])
    op.create_index("ix_paz_y_salvos_usuario_id", "paz_y_salvos", ["usuario_id"])
    op.create_index("ix_paz_y_salvos_codigo", "paz_y_salvos", ["codigo"], unique=True)
    op.create_index("ix_paz_y_salvos_fecha_emision", "paz_y_salvos", ["fecha_emision"])


def downgrade() -> None:
    if "paz_y_salvos" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("paz_y_salvos")
