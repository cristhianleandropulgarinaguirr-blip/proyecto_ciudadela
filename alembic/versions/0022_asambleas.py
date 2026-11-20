"""Versión 4.6 · asambleas de copropietarios (Ley 675 de 2001): unidades, asambleas, asistentes, poderes y bitácora de evidencia.

Tablas nuevas (no se toca ninguna existente):
- `unidades`              base del quórum: cada apartamento con su coeficiente (incluye propietarios sin cuenta en la app).
- `asambleas`             la reunión: tipo, modalidad, fechas de 1.ª y 2.ª convocatoria, orden del día, estado y quórum.
- `asamblea_documentos`   documentos que acompañan la convocatoria (estados financieros, etc.).
- `asamblea_eventos`      bitácora de evidencia con huellas encadenadas (solo se agregan filas).
- `asamblea_poderes`      poderes escritos (PDF o foto) con revisión del administrador.
- `asamblea_asistentes`   quién está en la reunión por cada unidad, con el coeficiente «fotografiado» al acreditar.

En PostgreSQL/Supabase las tablas nuevas nacen con Row Level Security activo y sin permisos para `anon` ni `authenticated`
(misma regla de las migraciones 0008, 0020 y 0021). Es seguro correrla varias veces: crea solo lo que falte.

Revision ID: 0022
Revises: 0021
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
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

TABLAS_NUEVAS = ["asamblea_asistentes", "asamblea_poderes", "asamblea_eventos", "asamblea_documentos", "asambleas", "unidades"]   # orden para borrar


def _existentes() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    if "unidades" not in _existentes():
        op.create_table(
            "unidades",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("apartamento", sa.String, nullable=False),
            sa.Column("clave", sa.String, nullable=False),
            sa.Column("coeficiente", sa.Float, nullable=True),
            sa.Column("propietario_nombre", sa.String(120), nullable=True),
            sa.Column("origen", sa.String(10), nullable=False, server_default="usuarios"),
            sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("fecha_actualizacion", sa.DateTime, nullable=True),
        )
        op.create_index("ix_unidades_id", "unidades", ["id"])
        op.create_index("ix_unidades_clave", "unidades", ["clave"], unique=True)

    if "asambleas" not in _existentes():
        op.create_table(
            "asambleas",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("titulo", sa.String(120), nullable=False),
            sa.Column("tipo", sa.String(15), nullable=False),
            sa.Column("modalidad", sa.String(10), nullable=False),
            sa.Column("estado", sa.String(10), nullable=False, server_default="Borrador"),
            sa.Column("orden_del_dia", sa.Text, nullable=False),
            sa.Column("fecha_sesion", sa.DateTime, nullable=False),
            sa.Column("fecha_segunda", sa.DateTime, nullable=False),
            sa.Column("lugar", sa.String(150), nullable=True),
            sa.Column("url_videollamada", sa.String(300), nullable=True),
            sa.Column("instrucciones_virtual", sa.String(500), nullable=True),
            sa.Column("max_poderes", sa.Integer, nullable=False, server_default="2"),
            sa.Column("restringe_mora", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("fecha_convocatoria", sa.DateTime, nullable=True),
            sa.Column("convocatoria_hash", sa.String(64), nullable=True),
            sa.Column("morosos_snapshot", sa.Text, nullable=True),
            sa.Column("sin_quorum_en", sa.DateTime, nullable=True),
            sa.Column("convocatoria_numero", sa.Integer, nullable=True),
            sa.Column("instalada_en", sa.DateTime, nullable=True),
            sa.Column("quorum_inicial", sa.Float, nullable=True),
            sa.Column("cerrada_en", sa.DateTime, nullable=True),
            sa.Column("quorum_final", sa.Float, nullable=True),
            sa.Column("creada_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("fecha_actualizacion", sa.DateTime, nullable=True),
        )
        op.create_index("ix_asambleas_id", "asambleas", ["id"])
        op.create_index("ix_asambleas_estado_fecha", "asambleas", ["estado", "fecha_sesion"])

    if "asamblea_documentos" not in _existentes():
        op.create_table(
            "asamblea_documentos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("documento_id", sa.Integer, sa.ForeignKey("documentos.id"), nullable=False),
            sa.UniqueConstraint("asamblea_id", "documento_id", name="uq_asamblea_documento"),
        )
        op.create_index("ix_asamblea_documentos_id", "asamblea_documentos", ["id"])
        op.create_index("ix_asamblea_documentos_asamblea_id", "asamblea_documentos", ["asamblea_id"])

    if "asamblea_eventos" not in _existentes():
        op.create_table(
            "asamblea_eventos",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("secuencia", sa.Integer, nullable=False),
            sa.Column("tipo", sa.String(30), nullable=False),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("unidades.id"), nullable=True),
            sa.Column("actor_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("detalle", sa.String(300), nullable=True),
            sa.Column("creado_en", sa.DateTime, nullable=False),
            sa.Column("hash_anterior", sa.String(64), nullable=False),
            sa.Column("hash", sa.String(64), nullable=False),
            sa.UniqueConstraint("asamblea_id", "secuencia", name="uq_asamblea_evento_secuencia"),
        )
        op.create_index("ix_asamblea_eventos_id", "asamblea_eventos", ["id"])
        op.create_index("ix_asamblea_eventos_asamblea_id", "asamblea_eventos", ["asamblea_id"])

    if "asamblea_poderes" not in _existentes():
        op.create_table(
            "asamblea_poderes",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("unidades.id"), nullable=False),
            sa.Column("apoderado_nombre", sa.String(120), nullable=False),
            sa.Column("apoderado_documento", sa.String(30), nullable=False),
            sa.Column("apoderado_usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("archivo", sa.String(80), nullable=False),
            sa.Column("tipo_archivo", sa.String(6), nullable=False),
            sa.Column("estado", sa.String(10), nullable=False, server_default="Pendiente"),
            sa.Column("motivo", sa.String(200), nullable=True),
            sa.Column("subido_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("revisado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("revisado_en", sa.DateTime, nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
        )
        op.create_index("ix_asamblea_poderes_id", "asamblea_poderes", ["id"])
        op.create_index("ix_asamblea_poderes_asamblea_id", "asamblea_poderes", ["asamblea_id"])
        op.create_index("ix_asamblea_poderes_asamblea_unidad", "asamblea_poderes", ["asamblea_id", "unidad_id"])

    if "asamblea_asistentes" not in _existentes():
        op.create_table(
            "asamblea_asistentes",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("asamblea_id", sa.Integer, sa.ForeignKey("asambleas.id"), nullable=False),
            sa.Column("unidad_id", sa.Integer, sa.ForeignKey("unidades.id"), nullable=False),
            sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("nombre", sa.String(120), nullable=False),
            sa.Column("documento", sa.String(30), nullable=True),
            sa.Column("es_apoderado", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("poder_id", sa.Integer, sa.ForeignKey("asamblea_poderes.id"), nullable=True),
            sa.Column("modalidad_ingreso", sa.String(10), nullable=False, server_default="Presencial"),
            sa.Column("hora_ingreso", sa.DateTime, nullable=False),
            sa.Column("hora_salida", sa.DateTime, nullable=True),
            sa.Column("coeficiente_acreditado", sa.Float, nullable=False),
            sa.Column("en_mora", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("con_voto", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("registrado_por", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=True),
            sa.UniqueConstraint("asamblea_id", "unidad_id", name="uq_asamblea_asistente_unidad"),
        )
        op.create_index("ix_asamblea_asistentes_id", "asamblea_asistentes", ["id"])
        op.create_index("ix_asamblea_asistentes_asamblea_id", "asamblea_asistentes", ["asamblea_id"])

    if bind.dialect.name == "postgresql":
        op.execute(PROTEGER_TABLAS)


def downgrade() -> None:
    existentes = _existentes()
    for tabla in TABLAS_NUEVAS:          # primero las que dependen de otras
        if tabla in existentes:
            op.drop_table(tabla)         # el RLS de las demás tablas no se revierte a propósito (sería un retroceso de seguridad)
