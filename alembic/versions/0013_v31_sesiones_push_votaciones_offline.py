"""Versión 3.1: sesiones seguras, avisos push, votaciones y portería sin internet.

Tablas nuevas: sesiones, suscripciones_push, votaciones, votacion_opciones, votacion_participaciones, operaciones_offline.
Índices nuevos para las consultas más frecuentes (campana, paquetes por residente, vehículos dentro, visitantes dentro).
Es seguro correrla varias veces: solo crea lo que falta. En PostgreSQL activa RLS en las tablas nuevas (regla de la 0008).

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

NUEVAS = ["sesiones", "suscripciones_push", "votaciones", "votacion_opciones", "votacion_participaciones", "operaciones_offline"]


def _crear(nombre: str, *elementos) -> None:
    if nombre not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(nombre, *elementos)


def _indice(nombre: str, tabla: str, columnas: list[str], unico: bool = False) -> None:
    insp = sa.inspect(op.get_bind())
    if tabla in insp.get_table_names() and nombre not in {i["name"] for i in insp.get_indexes(tabla)}:
        op.create_index(nombre, tabla, columnas, unique=unico)


def upgrade() -> None:
    _crear("sesiones",
           sa.Column("id", sa.String(32), primary_key=True),
           sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
           sa.Column("token_hash", sa.String(64), nullable=False),
           sa.Column("token_anterior_hash", sa.String(64), nullable=True),
           sa.Column("rotado_en", sa.DateTime, nullable=True),
           sa.Column("creada", sa.DateTime),
           sa.Column("ultimo_uso", sa.DateTime),
           sa.Column("expira", sa.DateTime, nullable=False),
           sa.Column("maxima", sa.DateTime, nullable=False),
           sa.Column("revocada", sa.DateTime, nullable=True),
           sa.Column("dispositivo", sa.String(120), nullable=True),
           sa.Column("ip", sa.String(45), nullable=True))
    _indice("ix_sesiones_usuario_id", "sesiones", ["usuario_id"])
    _indice("ix_sesiones_token_hash", "sesiones", ["token_hash"], unico=True)
    _indice("ix_sesiones_token_anterior_hash", "sesiones", ["token_anterior_hash"])

    _crear("suscripciones_push",
           sa.Column("id", sa.Integer, primary_key=True),
           sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
           sa.Column("endpoint", sa.String, nullable=False),
           sa.Column("p256dh", sa.String, nullable=False),
           sa.Column("auth", sa.String, nullable=False),
           sa.Column("dispositivo", sa.String(120), nullable=True),
           sa.Column("creada", sa.DateTime),
           sa.Column("ultimo_exito", sa.DateTime, nullable=True),
           sa.Column("fallos", sa.Integer, nullable=False, server_default="0"))
    _indice("ix_suscripciones_push_id", "suscripciones_push", ["id"])
    _indice("ix_suscripciones_push_usuario_id", "suscripciones_push", ["usuario_id"])
    _indice("ix_suscripciones_push_endpoint", "suscripciones_push", ["endpoint"], unico=True)

    _crear("votaciones",
           sa.Column("id", sa.Integer, primary_key=True),
           sa.Column("autor_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
           sa.Column("titulo", sa.String, nullable=False),
           sa.Column("descripcion", sa.String, nullable=True),
           sa.Column("estado", sa.String, nullable=False, server_default="Abierta"),
           sa.Column("fecha_inicio", sa.DateTime),
           sa.Column("fecha_cierre", sa.DateTime, nullable=False),
           sa.Column("un_voto_por", sa.String, nullable=False, server_default="apartamento"),
           sa.Column("resultados_en_vivo", sa.Boolean, nullable=False, server_default=sa.false()),
           sa.Column("exige_al_dia", sa.Boolean, nullable=False, server_default=sa.false()),
           sa.Column("cerrada_en", sa.DateTime, nullable=True),
           sa.Column("fecha_creacion", sa.DateTime))
    _indice("ix_votaciones_id", "votaciones", ["id"])
    _indice("ix_votaciones_estado", "votaciones", ["estado"])

    _crear("votacion_opciones",
           sa.Column("id", sa.Integer, primary_key=True),
           sa.Column("votacion_id", sa.Integer, sa.ForeignKey("votaciones.id"), nullable=False),
           sa.Column("texto", sa.String, nullable=False),
           sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
           sa.Column("conteo", sa.Integer, nullable=False, server_default="0"))
    _indice("ix_votacion_opciones_votacion_id", "votacion_opciones", ["votacion_id"])

    _crear("votacion_participaciones",
           sa.Column("id", sa.Integer, primary_key=True),
           sa.Column("votacion_id", sa.Integer, sa.ForeignKey("votaciones.id"), nullable=False),
           sa.Column("clave", sa.String, nullable=False),
           sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
           sa.Column("fecha", sa.DateTime),
           sa.UniqueConstraint("votacion_id", "clave", name="uq_participacion_votacion_clave"))
    _indice("ix_votacion_participaciones_votacion_id", "votacion_participaciones", ["votacion_id"])

    _crear("operaciones_offline",
           sa.Column("id", sa.Integer, primary_key=True),
           sa.Column("usuario_id", sa.Integer, sa.ForeignKey("usuarios.id"), nullable=False),
           sa.Column("uuid", sa.String(64), nullable=False),
           sa.Column("tipo", sa.String, nullable=False),
           sa.Column("ok", sa.Boolean, nullable=False, server_default=sa.true()),
           sa.Column("resultado", sa.String, nullable=True),
           sa.Column("fecha", sa.DateTime),
           sa.UniqueConstraint("usuario_id", "uuid", name="uq_operacion_usuario_uuid"))
    _indice("ix_operaciones_offline_usuario_id", "operaciones_offline", ["usuario_id"])
    _indice("ix_operaciones_offline_fecha", "operaciones_offline", ["fecha"])

    # Rendimiento: consultas que corren en casi cada pantalla.
    _indice("ix_notificaciones_usuario_leida", "notificaciones", ["usuario_id", "leida"])
    _indice("ix_paquetes_destinatario_estado", "paquetes", ["destinatario_id", "estado"])
    _indice("ix_vehiculos_estado", "vehiculos_visitantes", ["estado"])
    _indice("ix_accesos_visitantes_salida", "accesos_visitantes", ["fecha_salida"])

    if op.get_bind().dialect.name == "postgresql":
        for t in NUEVAS:
            op.execute(f"ALTER TABLE public.{t} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    for ix, t in (("ix_accesos_visitantes_salida", "accesos_visitantes"), ("ix_vehiculos_estado", "vehiculos_visitantes"),
                  ("ix_paquetes_destinatario_estado", "paquetes"), ("ix_notificaciones_usuario_leida", "notificaciones")):
        op.drop_index(ix, table_name=t)
    for t in reversed(NUEVAS):
        op.drop_table(t)
