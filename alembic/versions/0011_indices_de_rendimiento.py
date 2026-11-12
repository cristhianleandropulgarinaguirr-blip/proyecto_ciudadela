"""Versión 3.0: índices en las consultas más frecuentes (reservas y reportes de daños).

Las demás tablas ya tenían índices en sus columnas de filtro. Es seguro correrla varias veces: solo crea lo que falta.

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

INDICES = [
    ("ix_reservas_usuario_id", "reservas", ["usuario_id"]),
    ("ix_reservas_fecha_reserva", "reservas", ["fecha_reserva"]),
    ("ix_reservas_estado", "reservas", ["estado"]),
    ("ix_reportes_danios_usuario_id", "reportes_danios", ["usuario_id"]),
    ("ix_reportes_danios_estado", "reportes_danios", ["estado"]),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for nombre, tabla, columnas in INDICES:
        if tabla in insp.get_table_names() and nombre not in {i["name"] for i in insp.get_indexes(tabla)}:
            op.create_index(nombre, tabla, columnas)


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for nombre, tabla, _ in INDICES:
        if tabla in insp.get_table_names() and nombre in {i["name"] for i in insp.get_indexes(tabla)}:
            op.drop_index(nombre, table_name=tabla)
