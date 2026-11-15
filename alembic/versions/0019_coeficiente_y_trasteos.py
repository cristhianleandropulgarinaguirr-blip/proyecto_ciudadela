"""Versión 3.8 (Fase 3 · legal y operativo): coeficiente de copropiedad, votación ponderada y trasteos.

- `usuarios.coeficiente` (porcentaje del apartamento, Ley 675).
- `votaciones.ponderada`, `votacion_opciones.peso`, `votacion_participaciones.peso`.
- Tabla `trasteos`.
Es seguro correrla varias veces: solo agrega lo que falte y no toca datos existentes.

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _agregar(tabla: str, columna: sa.Column) -> None:
    if columna.name not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}:
        op.add_column(tabla, columna)


def upgrade() -> None:
    _agregar("usuarios", sa.Column("coeficiente", sa.Float, nullable=True))
    _agregar("votaciones", sa.Column("ponderada", sa.Boolean, nullable=False, server_default=sa.false()))
    _agregar("votacion_opciones", sa.Column("peso", sa.Float, nullable=False, server_default="0"))
    _agregar("votacion_participaciones", sa.Column("peso", sa.Float, nullable=False, server_default="0"))

    if "trasteos" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "trasteos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("solicitante_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("titular_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("apartamento", sa.String, nullable=True),
        sa.Column("tipo", sa.String, nullable=False),
        sa.Column("fecha_inicio", sa.DateTime, nullable=False),
        sa.Column("fecha_fin", sa.DateTime, nullable=False),
        sa.Column("empresa", sa.String(80), nullable=True),
        sa.Column("placa", sa.String(15), nullable=True),
        sa.Column("observaciones", sa.String(300), nullable=True),
        sa.Column("estado", sa.String, nullable=False, server_default="Pendiente"),
        sa.Column("paz_salvo_id", sa.Integer, sa.ForeignKey("paz_y_salvos.id"), nullable=True),
        sa.Column("decidido_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("fecha_decision", sa.DateTime, nullable=True),
        sa.Column("motivo", sa.String(200), nullable=True),
        sa.Column("registrado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("inicio_real", sa.DateTime, nullable=True),
        sa.Column("fin_real", sa.DateTime, nullable=True),
        sa.Column("fecha_creacion", sa.DateTime, nullable=False),
    )
    op.create_index("ix_trasteos_id", "trasteos", ["id"])
    op.create_index("ix_trasteos_solicitante_id", "trasteos", ["solicitante_id"])
    op.create_index("ix_trasteos_titular_id", "trasteos", ["titular_id"])
    op.create_index("ix_trasteos_estado_inicio", "trasteos", ["estado", "fecha_inicio"])


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "trasteos" in insp.get_table_names():
        op.drop_table("trasteos")
    for tabla, col in (("votacion_participaciones", "peso"), ("votacion_opciones", "peso"), ("votaciones", "ponderada"), ("usuarios", "coeficiente")):
        if col in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}:
            with op.batch_alter_table(tabla) as lote:
                lote.drop_column(col)
