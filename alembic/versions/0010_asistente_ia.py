"""Versión 2.9: tabla `uso_asistente` (topes diarios del asistente de IA; no guarda el texto de los mensajes).

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# Regla de la migración 0008: toda tabla nueva en PostgreSQL/Supabase nace con RLS activo y sin permisos públicos.
PROTEGER = """
DO $$
BEGIN
  EXECUTE 'ALTER TABLE public.uso_asistente ENABLE ROW LEVEL SECURITY';
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.uso_asistente FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.uso_asistente FROM authenticated';
  END IF;
END $$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if "uso_asistente" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "uso_asistente",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("funcion", sa.String(), nullable=False),
            sa.Column("fecha", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_uso_asistente_id", "uso_asistente", ["id"])
        op.create_index("ix_uso_asistente_usuario_id", "uso_asistente", ["usuario_id"])
        op.create_index("ix_uso_asistente_fecha", "uso_asistente", ["fecha"])
    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER)


def downgrade() -> None:
    op.drop_table("uso_asistente")
