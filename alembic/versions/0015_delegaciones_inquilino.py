"""Delegaciones del propietario a su inquilino: pagar la administración y votar.

Agrega dos columnas a `arrendamientos`, ambas apagadas por defecto (el inquilino no puede nada de esto hasta que el propietario lo active):
  · puede_pagar → ver la cartera del apartamento y pagar la administración en nombre del propietario.
  · puede_votar → votar en las asambleas en nombre del apartamento (sigue siendo un voto por apartamento).
Es seguro correrla varias veces: solo agrega la columna que falte.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

COLUMNAS = ("puede_pagar", "puede_votar")


def upgrade() -> None:
    existentes = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("arrendamientos")}
    for nombre in COLUMNAS:
        if nombre not in existentes:
            op.add_column("arrendamientos", sa.Column(nombre, sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("arrendamientos") as batch:
        for nombre in COLUMNAS:
            batch.drop_column(nombre)
