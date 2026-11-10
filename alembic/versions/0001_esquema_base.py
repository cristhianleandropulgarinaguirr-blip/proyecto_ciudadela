"""Esquema base: las 4 tablas que ya existían en el proyecto.

Es IDEMPOTENTE: solo crea las tablas que falten. Así funciona igual en una base
nueva (ej. Supabase vacía) y en tu propiedad_horizontal.db que ya tenía tablas,
sin perder ningún dato.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existentes = set(sa.inspect(op.get_bind()).get_table_names())

    if "usuarios" not in existentes:
        op.create_table(
            "usuarios",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nombre_completo", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("password_encriptada", sa.String(), nullable=False),
            sa.Column("rol", sa.String(), nullable=True),  # versión antigua: texto. La 0002 lo reemplaza por rol_id
            sa.Column("apartamento", sa.String(), nullable=True),
            sa.Column("esta_activo", sa.Boolean(), nullable=True),
            sa.Column("esta_al_dia", sa.Boolean(), nullable=True),
            sa.Column("valor_administracion", sa.Integer(), nullable=True),
            sa.Column("saldo_pendiente", sa.Integer(), nullable=True),
            sa.Column("parqueadero_asignado", sa.String(), nullable=True),
        )
        op.create_index("ix_usuarios_id", "usuarios", ["id"])
        op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    if "reservas" not in existentes:
        op.create_table(
            "reservas",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("zona_comun", sa.String(), nullable=False),
            sa.Column("fecha_reserva", sa.DateTime(), nullable=False),
            sa.Column("estado", sa.String(), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_reservas_id", "reservas", ["id"])

    if "reportes_danios" not in existentes:
        op.create_table(
            "reportes_danios",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("descripcion", sa.String(), nullable=False),
            sa.Column("foto_url", sa.String(), nullable=True),
            sa.Column("estado", sa.String(), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_reportes_danios_id", "reportes_danios", ["id"])

    if "vehiculos_visitantes" not in existentes:
        op.create_table(
            "vehiculos_visitantes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("placa", sa.String(), nullable=False),
            sa.Column("apartamento_destino", sa.String(), nullable=False),
            sa.Column("fecha_ingreso", sa.DateTime(), nullable=True),
            sa.Column("fecha_salida", sa.DateTime(), nullable=True),
            sa.Column("estado", sa.String(), nullable=True),
        )
        op.create_index("ix_vehiculos_visitantes_id", "vehiculos_visitantes", ["id"])
        op.create_index("ix_vehiculos_visitantes_placa", "vehiculos_visitantes", ["placa"])


def downgrade() -> None:
    # No se borran las tablas base por seguridad (podrían contener datos reales).
    pass
