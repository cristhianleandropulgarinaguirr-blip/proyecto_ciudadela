"""Versión 3.5 (Fase 0 de rendimiento): tres índices que faltaban en consultas que corren constantemente.

  · usuarios.rol_id            → el rol se une a CADA petición autenticada. PostgreSQL NO indexa solo las llaves foráneas.
  · vehiculos_visitantes.estado        → «vehículos dentro» y la validación de «ya figura dentro» en cada escaneo de QR.
  · vehiculos_visitantes.fecha_ingreso → el historial de portería se ordena y filtra por fecha.
Es seguro correrla varias veces: solo crea lo que falta (igual que la 0011).

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

INDICES = [
    ("ix_usuarios_rol_id", "usuarios", ["rol_id"]),
    ("ix_vehiculos_visitantes_estado", "vehiculos_visitantes", ["estado"]),
    ("ix_vehiculos_visitantes_fecha_ingreso", "vehiculos_visitantes", ["fecha_ingreso"]),
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
