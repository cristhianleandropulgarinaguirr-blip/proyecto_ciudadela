"""Versión 4.0 (Fase 4 · presentación comercial): tabla `solicitudes_demo` (los contactos de «Solicitar demo» de la landing).

Además, en PostgreSQL/Supabase vuelve a aplicar la regla de la migración 0008 (Row Level Security en TODAS las tablas, sin permisos para `anon` ni
`authenticated`). Esto protege la tabla nueva —guarda nombres y celulares de personas— y repara `paz_y_salvos` y `trasteos`, que las migraciones 0018 y
0019 crearon sin activar RLS. Es idempotente.

Es seguro correrla varias veces: si la tabla ya existe, no la vuelve a crear. No toca ningún dato existente.

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
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
        "solicitudes_demo",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("nombre", sa.String(80), nullable=False),
        sa.Column("conjunto", sa.String(100), nullable=False),
        sa.Column("celular", sa.String(15), nullable=False),
        sa.Column("correo", sa.String(120), nullable=True),
        sa.Column("ciudad", sa.String(60), nullable=True),
        sa.Column("apartamentos", sa.Integer, nullable=True),
        sa.Column("mensaje", sa.String(500), nullable=True),
        sa.Column("origen", sa.String(12), nullable=False, server_default="formulario"),
        sa.Column("estado", sa.String(12), nullable=False, server_default="Nueva"),
        sa.Column("nota", sa.String(300), nullable=True),
        sa.Column("acepto_datos", sa.DateTime, nullable=False),
        sa.Column("fecha_creacion", sa.DateTime, nullable=False),
        sa.Column("fecha_actualizacion", sa.DateTime, nullable=True),
    )
    op.create_index("ix_solicitudes_demo_id", "solicitudes_demo", ["id"])
    op.create_index("ix_solicitudes_demo_celular", "solicitudes_demo", ["celular"])
    op.create_index("ix_solicitudes_demo_estado", "solicitudes_demo", ["estado"])
    op.create_index("ix_solicitudes_demo_fecha_creacion", "solicitudes_demo", ["fecha_creacion"])
    op.create_index("ix_solicitudes_demo_estado_fecha", "solicitudes_demo", ["estado", "fecha_creacion"])


def upgrade() -> None:
    bind = op.get_bind()
    if "solicitudes_demo" not in sa.inspect(bind).get_table_names():
        _crear_tabla()
    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    op.drop_table("solicitudes_demo")   # el RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad)
