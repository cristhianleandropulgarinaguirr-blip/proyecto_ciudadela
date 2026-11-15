"""Versión 3.5 (Fase 1): PIN de 6 dígitos y avisos «estoy en camino / llegué» en los pases de visitante.

Agrega a `codigos_qr`:
  · pin            → PIN numérico del pase (plan B si falla la cámara). Nulo en los pases creados antes de esta versión.
  · aviso_camino   → cuándo el visitante pulsó «Estoy en camino» por última vez.
  · aviso_llegada  → cuándo pulsó «Ya llegué» por última vez.
Es seguro correrla varias veces: solo agrega lo que falta.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

INDICE = "ix_codigos_qr_pin"


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    existentes = {c["name"] for c in insp.get_columns("codigos_qr")}
    if "pin" not in existentes:
        op.add_column("codigos_qr", sa.Column("pin", sa.String(6), nullable=True))
    if "aviso_camino" not in existentes:
        op.add_column("codigos_qr", sa.Column("aviso_camino", sa.DateTime, nullable=True))
    if "aviso_llegada" not in existentes:
        op.add_column("codigos_qr", sa.Column("aviso_llegada", sa.DateTime, nullable=True))
    if INDICE not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("codigos_qr")}:
        op.create_index(INDICE, "codigos_qr", ["pin"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if INDICE in {i["name"] for i in insp.get_indexes("codigos_qr")}:
        op.drop_index(INDICE, table_name="codigos_qr")
    with op.batch_alter_table("codigos_qr") as batch:
        for nombre in ("aviso_llegada", "aviso_camino", "pin"):
            batch.drop_column(nombre)
