"""Bloque 1: contraseña obligatoria de cambiar tras restablecer, bitácora de auditoría y límite de intentos de login.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "debe_cambiar_password" not in {c["name"] for c in insp.get_columns("usuarios")}:
        with op.batch_alter_table("usuarios") as lote:
            lote.add_column(sa.Column("debe_cambiar_password", sa.Boolean(), nullable=False, server_default=sa.false()))
    tablas = set(insp.get_table_names())
    if "auditoria" not in tablas:
        op.create_table(
            "auditoria",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("accion", sa.String(), nullable=False),
            sa.Column("entidad", sa.String(), nullable=False),
            sa.Column("entidad_id", sa.Integer(), nullable=True),
            sa.Column("detalle", sa.String(), nullable=True),
            sa.Column("fecha", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_auditoria_id", "auditoria", ["id"])
        op.create_index("ix_auditoria_entidad", "auditoria", ["entidad"])
        op.create_index("ix_auditoria_fecha", "auditoria", ["fecha"])
    if "intentos_login" not in tablas:
        op.create_table(
            "intentos_login",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("clave", sa.String(), nullable=False),
            sa.Column("fallos", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ultimo_intento", sa.DateTime(), nullable=True),
            sa.Column("bloqueado_hasta", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_intentos_login_id", "intentos_login", ["id"])
        op.create_index("ix_intentos_login_clave", "intentos_login", ["clave"], unique=True)


def downgrade() -> None:
    op.drop_table("intentos_login")
    op.drop_table("auditoria")
    with op.batch_alter_table("usuarios") as lote:
        lote.drop_column("debe_cambiar_password")
