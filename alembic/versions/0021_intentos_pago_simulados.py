"""Versión 4.2 · pasarela de pagos SIMULADA (tipo Wompi/PSE): tabla `intentos_pago`.

Cada intento guarda la referencia (SIM-…), quién paga, de quién es la deuda, el valor, el método elegido y lo que «respondió» la pasarela. No guarda datos
de tarjeta, documentos ni celulares. En PostgreSQL/Supabase la tabla nace con Row Level Security activo y sin permisos para `anon` ni `authenticated`
(misma regla de las migraciones 0008 y 0020).

Es seguro correrla varias veces: si la tabla ya existe, no la vuelve a crear. No toca ningún dato existente.

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


# Mismo bloque que la migración 0008 (regla del proyecto: toda tabla nueva en PostgreSQL nace con RLS activo y sin permisos públicos).
PROTEGER_TABLAS = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN
    SELECT c.relname AS nombre
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND pg_get_userbyid(c.relowner) = current_user
  LOOP
    EXECUTE 'ALTER TABLE public.' || quote_ident(t.nombre) || ' ENABLE ROW LEVEL SECURITY';
  END LOOP;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated';
  END IF;
END $$;
"""


def _crear_tabla() -> None:
    op.create_table(
        "intentos_pago",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("referencia", sa.String(24), nullable=False),
        sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("titular_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
        sa.Column("valor", sa.Integer, nullable=False),
        sa.Column("metodo", sa.String(10), nullable=True),
        sa.Column("estado", sa.String(10), nullable=False, server_default="Creado"),
        sa.Column("mensaje", sa.String(200), nullable=True),
        sa.Column("pago_id", sa.Integer, sa.ForeignKey("pagos.id"), nullable=True),
        sa.Column("resuelve_en", sa.DateTime, nullable=True),
        sa.Column("fecha_creacion", sa.DateTime, nullable=False),
        sa.Column("fecha_resolucion", sa.DateTime, nullable=True),
    )
    op.create_index("ix_intentos_pago_id", "intentos_pago", ["id"])
    op.create_index("ix_intentos_pago_referencia", "intentos_pago", ["referencia"], unique=True)
    op.create_index("ix_intentos_pago_usuario_id", "intentos_pago", ["usuario_id"])
    op.create_index("ix_intentos_pago_estado", "intentos_pago", ["estado"])


def upgrade() -> None:
    bind = op.get_bind()
    if "intentos_pago" not in sa.inspect(bind).get_table_names():
        _crear_tabla()
    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    op.drop_table("intentos_pago")   # el RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad)
