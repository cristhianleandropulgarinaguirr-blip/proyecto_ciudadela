"""Seguridad en PostgreSQL/Supabase: activa Row Level Security en todas las tablas y quita permisos a los roles públicos.

Por qué: Supabase publica el esquema `public` mediante una API REST (PostgREST) que se usa con una clave pública
(`anon`). Las tablas creadas por migraciones (no desde el panel de Supabase) nacen SIN RLS, y en proyectos con la
API de datos activa cualquiera con esa clave podría leer tablas como `usuarios`. Este proyecto NO usa esa API: el
backend entra con el usuario `postgres`, que es dueño de las tablas y por eso NO se ve afectado por el RLS.
Con RLS activo y sin políticas, `anon` y `authenticated` no ven nada.

En SQLite no hace nada. REGLA para el futuro: toda migración que cree una tabla en PostgreSQL debe activar RLS en ella
(`ALTER TABLE public.<tabla> ENABLE ROW LEVEL SECURITY;`) o volver a ejecutar esta migración (es idempotente).

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

SQL = """
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

  -- Los roles `anon` y `authenticated` solo existen en Supabase.
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


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(SQL)


def downgrade() -> None:
    # A propósito no se revierte: volver a dejar las tablas abiertas sería un retroceso de seguridad.
    pass
