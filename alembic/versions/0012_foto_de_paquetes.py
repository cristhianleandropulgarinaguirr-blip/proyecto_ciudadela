"""Versión 3.0: foto opcional en los paquetes (evidencia de lo que llegó a portería).

Es seguro correrla varias veces: solo agrega la columna si falta.

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _columnas() -> set[str]:
    insp = sa.inspect(op.get_bind())
    return {c["name"] for c in insp.get_columns("paquetes")} if "paquetes" in insp.get_table_names() else set()


def upgrade() -> None:
    if "paquetes" in sa.inspect(op.get_bind()).get_table_names() and "foto_url" not in _columnas():
        with op.batch_alter_table("paquetes") as lote:
            lote.add_column(sa.Column("foto_url", sa.String(), nullable=True))


def downgrade() -> None:
    if "foto_url" in _columnas():
        with op.batch_alter_table("paquetes") as lote:
            lote.drop_column("foto_url")
