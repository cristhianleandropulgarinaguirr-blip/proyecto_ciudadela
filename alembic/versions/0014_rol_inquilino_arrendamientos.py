"""Rol Inquilino y tabla de arrendamientos.

Crea el rol «Inquilino» (si falta) y la tabla `arrendamientos`, que une al propietario, al inquilino y al apartamento.
Es seguro correrla varias veces: solo crea lo que falta. En PostgreSQL activa RLS en la tabla nueva (regla de la 0008).

Revision ID: 0014
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

DESCRIPCION = "Vive en el apartamento por arrendamiento: reserva zonas, recibe paquetes y radica solicitudes; sin cartera ni votaciones"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "arrendamientos" not in insp.get_table_names():
        op.create_table(
            "arrendamientos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("propietario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("inquilino_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("apartamento", sa.String, nullable=True),
            sa.Column("fecha_inicio", sa.DateTime, nullable=False),
            sa.Column("fecha_fin", sa.DateTime, nullable=False),
            sa.Column("estado", sa.String, nullable=False, server_default="Pendiente"),
            sa.Column("motivo_cierre", sa.String, nullable=True),
            sa.Column("aprobado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime),
            sa.Column("fecha_decision", sa.DateTime, nullable=True),
        )
        op.create_index("ix_arrendamientos_id", "arrendamientos", ["id"])
        op.create_index("ix_arrendamientos_inquilino_id", "arrendamientos", ["inquilino_id"])
        op.create_index("ix_arrendamientos_propietario_estado", "arrendamientos", ["propietario_id", "estado"])
        if bind.dialect.name == "postgresql":
            op.execute("ALTER TABLE public.arrendamientos ENABLE ROW LEVEL SECURITY")

    existe = bind.execute(sa.text("SELECT 1 FROM roles WHERE nombre = :n"), {"n": "Inquilino"}).first()
    if existe is None:
        bind.execute(sa.text("INSERT INTO roles (nombre, descripcion) VALUES (:n, :d)"), {"n": "Inquilino", "d": DESCRIPCION})


def downgrade() -> None:
    # Si ya hay usuarios con el rol, se conserva (borrarlo rompería sus cuentas); solo se elimina la tabla.
    op.drop_table("arrendamientos")
