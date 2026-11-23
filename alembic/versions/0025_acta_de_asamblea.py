"""Versión 5.4 · acta de la asamblea (Fase 4 del módulo de asambleas, Art. 47 de la Ley 675 de 2001).

Tabla nueva (no se modifica ninguna tabla existente):
- `asamblea_actas`   el acta de cada asamblea: borrador editable (presidente, secretario, comisión verificadora, desarrollo), copia CONGELADA del contenido
                     con su huella SHA-256 al sellarla, copia firmada escaneada y fecha de publicación a los propietarios. Una sola por asamblea.

En PostgreSQL/Supabase la tabla nueva nace con Row Level Security activo y sin permisos para `anon` ni `authenticated`
(misma regla de las migraciones 0008, 0020, 0021, 0022 y 0023; la 0024 es la de seguridad de la v5.3). Es seguro correrla varias veces: crea solo lo que falte.

Revision ID: 0025
Revises: 0024
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

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


def _existentes() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "asamblea_actas" not in _existentes():
        op.create_table(
            "asamblea_actas",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("estado", sa.String(10), nullable=False, server_default="Borrador"),
            sa.Column("presidente_nombre", sa.String(120), nullable=True),
            sa.Column("secretario_nombre", sa.String(120), nullable=True),
            sa.Column("comision", sa.String(500), nullable=True),
            sa.Column("desarrollo", sa.Text, nullable=True),
            sa.Column("editada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("fecha_actualizacion", sa.DateTime, nullable=True),
            sa.Column("sellada_en", sa.DateTime, nullable=True),
            sa.Column("sellada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("contenido", sa.Text, nullable=True),
            sa.Column("contenido_hash", sa.String(64), nullable=True),
            sa.Column("firmada_archivo", sa.String(80), nullable=True),
            sa.Column("firmada_hash", sa.String(64), nullable=True),
            sa.Column("firmada_en", sa.DateTime, nullable=True),
            sa.Column("firmada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("publicada_en", sa.DateTime, nullable=True),
            sa.Column("publicada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
        )
        op.create_index("ix_asamblea_actas_id", "asamblea_actas", ["id"])
        op.create_index("ix_asamblea_actas_asamblea_id", "asamblea_actas", ["asamblea_id"], unique=True)

    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    if "asamblea_actas" in _existentes():
        op.drop_table("asamblea_actas")          # el RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad)
