"""Versión 5.2 · votaciones dentro de la asamblea (Fase 3 del módulo de asambleas, Ley 675 de 2001).

Tablas nuevas (no se toca ninguna existente, ni siquiera las de «Votaciones» del conjunto):
- `asamblea_votaciones`          cada pregunta votada en una asamblea: tipo, mayoría exigida, padrón al abrir y resultado congelado con su huella.
- `asamblea_votacion_opciones`   las opciones y su contador (el voto de la app es secreto: el contador no está unido a ninguna persona).
- `asamblea_votos`               que una unidad ya votó (una sola vez por pregunta) y por qué vía (App o Manual).

Además, un índice único parcial garantiza que solo haya UNA votación abierta por asamblea (lo impone la base de datos, no solo el código).

En PostgreSQL/Supabase las tablas nuevas nacen con Row Level Security activo y sin permisos para `anon` ni `authenticated`
(misma regla de las migraciones 0008, 0020, 0021 y 0022). Es seguro correrla varias veces: crea solo lo que falte.

Revision ID: 0023
Revises: 0022
"""
import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
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

TABLAS_NUEVAS = ["asamblea_votos", "asamblea_votacion_opciones", "asamblea_votaciones"]   # orden para borrar (primero las que dependen de otras)


def _existentes() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "asamblea_votaciones" not in _existentes():
        op.create_table(
            "asamblea_votaciones",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("numero", sa.Integer, nullable=False),
            sa.Column("titulo", sa.String(160), nullable=False),
            sa.Column("descripcion", sa.String(500), nullable=True),
            sa.Column("tipo", sa.String(10), nullable=False),
            sa.Column("mayoria", sa.String(12), nullable=False, server_default="Simple"),
            sa.Column("estado", sa.String(10), nullable=False, server_default="Borrador"),
            sa.Column("creada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("abierta_en", sa.DateTime, nullable=True),
            sa.Column("abierta_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("padron", sa.Text, nullable=True),
            sa.Column("coef_padron", sa.Float, nullable=True),
            sa.Column("coef_total", sa.Float, nullable=True),
            sa.Column("quorum_apertura", sa.Float, nullable=True),
            sa.Column("cerrada_en", sa.DateTime, nullable=True),
            sa.Column("cerrada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("quorum_cierre", sa.Float, nullable=True),
            sa.Column("resultado", sa.Text, nullable=True),
            sa.Column("resultado_hash", sa.String(64), nullable=True),
            sa.Column("motivo_anulacion", sa.String(200), nullable=True),
            sa.UniqueConstraint("asamblea_id", "numero", name="uq_asamblea_votacion_numero"),
        )
        op.create_index("ix_asamblea_votaciones_id", "asamblea_votaciones", ["id"])
        op.create_index("ix_asamblea_votaciones_asamblea_id", "asamblea_votaciones", ["asamblea_id"])
        op.create_index("uq_asamblea_votacion_una_abierta", "asamblea_votaciones", ["asamblea_id"], unique=True,
                        sqlite_where=sa.text("estado = 'Abierta'"), postgresql_where=sa.text("estado = 'Abierta'"))

    if "asamblea_votacion_opciones" not in _existentes():
        op.create_table(
            "asamblea_votacion_opciones",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("votacion_id", sa.Integer, sa.ForeignKey("asamblea_votaciones.id"), nullable=False),
            sa.Column("texto", sa.String(120), nullable=False),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.Column("conteo", sa.Integer, nullable=False, server_default="0"),
            sa.Column("peso", sa.Float, nullable=False, server_default="0"),
        )
        op.create_index("ix_asamblea_votacion_opciones_id", "asamblea_votacion_opciones", ["id"])
        op.create_index("ix_asamblea_votacion_opciones_votacion_id", "asamblea_votacion_opciones", ["votacion_id"])

    if "asamblea_votos" not in _existentes():
        op.create_table(
            "asamblea_votos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("votacion_id", sa.Integer, sa.ForeignKey("asamblea_votaciones.id"), nullable=False),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("unidades.id"), nullable=False),
            sa.Column("asistente_id", sa.Integer, sa.ForeignKey("asamblea_asistentes.id"), nullable=False),
            sa.Column("peso", sa.Float, nullable=False),
            sa.Column("via", sa.String(6), nullable=False),
            sa.Column("emitido_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("opcion_id", sa.Integer, sa.ForeignKey("asamblea_votacion_opciones.id"), nullable=True),
            sa.Column("fecha", sa.DateTime, nullable=True),
            sa.UniqueConstraint("votacion_id", "unidad_id", name="uq_asamblea_voto_unidad"),
        )
        op.create_index("ix_asamblea_votos_id", "asamblea_votos", ["id"])
        op.create_index("ix_asamblea_votos_votacion_id", "asamblea_votos", ["votacion_id"])

    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    existentes = _existentes()
    for tabla in TABLAS_NUEVAS:
        if tabla in existentes:
            op.drop_table(tabla)         # el RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad)
