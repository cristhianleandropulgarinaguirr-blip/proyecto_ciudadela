"""Versión 2.7: comprobantes de pago (tabla `pagos`) y aceptación de la política de datos.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

# Regla de la migración 0008: toda tabla nueva en PostgreSQL/Supabase nace con RLS activo y sin permisos públicos.
PROTEGER_PAGOS = """
DO $$
BEGIN
  EXECUTE 'ALTER TABLE public.pagos ENABLE ROW LEVEL SECURITY';
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.pagos FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.pagos FROM authenticated';
  END IF;
END $$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    columnas = {c["name"] for c in sa.inspect(bind).get_columns("usuarios")}
    if "politica_datos_fecha" not in columnas:
        op.add_column("usuarios", sa.Column("politica_datos_fecha", sa.DateTime(), nullable=True))

    if "pagos" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "pagos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("valor", sa.Integer(), nullable=False),
            sa.Column("saldo_anterior", sa.Integer(), nullable=False),
            sa.Column("saldo_posterior", sa.Integer(), nullable=False),
            sa.Column("fecha", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_pagos_id", "pagos", ["id"])
        op.create_index("ix_pagos_usuario_id", "pagos", ["usuario_id"])
        op.create_index("ix_pagos_fecha", "pagos", ["fecha"])
    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_PAGOS)


def downgrade() -> None:
    op.drop_table("pagos")
    with op.batch_alter_table("usuarios") as lote:
        lote.drop_column("politica_datos_fecha")
