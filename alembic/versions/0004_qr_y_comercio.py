"""Fase 2: códigos QR (carnet y pases de visitante), bitácora de escaneos y comercio (publicidad paga).

Crea las tablas codigos_qr, escaneos_qr y publicidad. No modifica ni borra datos existentes.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    existentes = set(sa.inspect(op.get_bind()).get_table_names())

    if "codigos_qr" not in existentes:
        op.create_table(
            "codigos_qr",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False),
            sa.Column("token", sa.String(), nullable=False),
            sa.Column("estado", sa.String(), nullable=False, server_default="Activo"),
            sa.Column("nombre_visitante", sa.String(), nullable=True),
            sa.Column("placa", sa.String(), nullable=True),
            sa.Column("valido_hasta", sa.DateTime(), nullable=True),
            sa.Column("vehiculo_id", sa.Integer(), sa.ForeignKey("vehiculos_visitantes.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_codigos_qr_id", "codigos_qr", ["id"])
        op.create_index("ix_codigos_qr_usuario_id", "codigos_qr", ["usuario_id"])
        op.create_index("ix_codigos_qr_token", "codigos_qr", ["token"], unique=True)

    if "escaneos_qr" not in existentes:
        op.create_table(
            "escaneos_qr",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("codigo_id", sa.Integer(), sa.ForeignKey("codigos_qr.id"), nullable=True),
            sa.Column("escaneado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("resultado", sa.String(), nullable=False),
            sa.Column("detalle", sa.String(), nullable=True),
            sa.Column("fecha", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_escaneos_qr_id", "escaneos_qr", ["id"])
        op.create_index("ix_escaneos_qr_codigo_id", "escaneos_qr", ["codigo_id"])
        op.create_index("ix_escaneos_qr_fecha", "escaneos_qr", ["fecha"])

    if "publicidad" not in existentes:
        op.create_table(
            "publicidad",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("propietario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("nombre_negocio", sa.String(), nullable=False),
            sa.Column("categoria", sa.String(), nullable=False),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("descripcion", sa.String(), nullable=False),
            sa.Column("precio_texto", sa.String(), nullable=True),
            sa.Column("whatsapp", sa.String(), nullable=False),
            sa.Column("imagen", sa.String(), nullable=True),
            sa.Column("plan", sa.String(), nullable=False),
            sa.Column("valor", sa.Integer(), nullable=False),
            sa.Column("estado", sa.String(), nullable=False, server_default="Pendiente de pago"),
            sa.Column("referencia_pago", sa.String(), nullable=True),
            sa.Column("motivo_rechazo", sa.String(), nullable=True),
            sa.Column("fecha_inicio", sa.DateTime(), nullable=True),
            sa.Column("fecha_fin", sa.DateTime(), nullable=True),
            sa.Column("contactos", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("revisado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_publicidad_id", "publicidad", ["id"])
        op.create_index("ix_publicidad_propietario_id", "publicidad", ["propietario_id"])
        op.create_index("ix_publicidad_estado", "publicidad", ["estado"])


def downgrade() -> None:
    op.drop_table("publicidad")
    op.drop_table("escaneos_qr")
    op.drop_table("codigos_qr")
