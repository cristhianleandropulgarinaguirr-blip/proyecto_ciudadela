"""Versión 5.6 · enlace de técnico de mantenimiento (rol Mantenimiento, sin cuenta).

Tablas NUEVAS (no se modifica ninguna tabla existente, así que no hay riesgo para los datos que ya tienes):
- `enlaces_tecnico`   un enlace temporal por reporte de daño: token aleatorio, quién lo creó, cuándo vence, si se anuló o se cerró.
- `evidencias_danio`  lo que el técnico fue dejando desde su enlace: estado al que pasó el reporte, nota y foto de evidencia.

En PostgreSQL/Supabase las tablas nuevas nacen con Row Level Security activo y sin permisos para `anon` ni `authenticated`
(misma regla de las migraciones 0008, 0020 a 0025). Es seguro correrla varias veces: crea solo lo que falte.

Revision ID: 0026
Revises: 0025
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
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
    if "enlaces_tecnico" not in _existentes():
        op.create_table(
            "enlaces_tecnico",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("reporte_id", sa.Integer, sa.ForeignKey("reportes_danios.id"), nullable=False),
            sa.Column("token", sa.String, nullable=False),
            sa.Column("creado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("etiqueta", sa.String(80), nullable=True),
            sa.Column("valido_hasta", sa.DateTime, nullable=False),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("revocado_en", sa.DateTime, nullable=True),
            sa.Column("revocado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("cerrado_en", sa.DateTime, nullable=True),
            sa.Column("ultimo_uso", sa.DateTime, nullable=True),
        )
        op.create_index("ix_enlaces_tecnico_id", "enlaces_tecnico", ["id"])
        op.create_index("ix_enlaces_tecnico_reporte_id", "enlaces_tecnico", ["reporte_id"])
        op.create_index("ix_enlaces_tecnico_token", "enlaces_tecnico", ["token"], unique=True)

    if "evidencias_danio" not in _existentes():
        op.create_table(
            "evidencias_danio",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("reporte_id", sa.Integer, sa.ForeignKey("reportes_danios.id"), nullable=False),
            sa.Column("enlace_id", sa.Integer, sa.ForeignKey("enlaces_tecnico.id"), nullable=False),
            sa.Column("estado", sa.String(20), nullable=False),
            sa.Column("nota", sa.String(500), nullable=True),
            sa.Column("foto", sa.String(80), nullable=True),
            sa.Column("fecha", sa.DateTime, nullable=True),
        )
        op.create_index("ix_evidencias_danio_id", "evidencias_danio", ["id"])
        op.create_index("ix_evidencias_danio_reporte_id", "evidencias_danio", ["reporte_id"])
        op.create_index("ix_evidencias_danio_enlace_id", "evidencias_danio", ["enlace_id"])

    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    # Se borra primero la tabla que depende de la otra. El RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad).
    for tabla in ("evidencias_danio", "enlaces_tecnico"):
        if tabla in _existentes():
            op.drop_table(tabla)
