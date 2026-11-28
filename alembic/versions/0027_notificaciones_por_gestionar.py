"""Versión 5.7 · notificaciones «por gestionar» (que lo pendiente no se pierda aunque el aviso ya se haya abierto).

Solo AGREGA cuatro columnas a `notificaciones` (todas con valor por defecto o vacías, así que ningún aviso existente cambia
ni pasa a «pendiente»: los avisos viejos quedan como informativos):
- `requiere_gestion`  el aviso pide una acción (aprobar, responder, recoger…). Por defecto falso.
- `gestionada_en`     cuándo se gestionó (a mano, o solo cuando se resolvió lo que pedía).
- `ref_tipo`          a qué se refiere: reserva, danio, pqrs, arrendamiento, trasteo, poder, paquete, votacion.
- `ref_id`            el número de esa cosa. Con `ref_tipo` permite marcar el aviso como gestionado al resolverla.
Más un índice (ref_tipo, ref_id) para encontrar rápido los avisos de una misma cosa.
Es seguro correrla varias veces: agrega solo lo que falte. La tabla ya existe, así que conserva su Row Level Security en Supabase.

Revision ID: 0027
Revises: 0026
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

INDICE = "ix_notificaciones_ref"


def _agregar(tabla: str, columna: sa.Column) -> None:
    if columna.name not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}:
        op.add_column(tabla, columna)


def upgrade() -> None:
    _agregar("notificaciones", sa.Column("requiere_gestion", sa.Boolean, nullable=False, server_default=sa.false()))
    _agregar("notificaciones", sa.Column("gestionada_en", sa.DateTime, nullable=True))
    _agregar("notificaciones", sa.Column("ref_tipo", sa.String(30), nullable=True))
    _agregar("notificaciones", sa.Column("ref_id", sa.Integer, nullable=True))
    if INDICE not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("notificaciones")}:
        op.create_index(INDICE, "notificaciones", ["ref_tipo", "ref_id"])


def downgrade() -> None:
    if INDICE in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("notificaciones")}:
        op.drop_index(INDICE, table_name="notificaciones")
    with op.batch_alter_table("notificaciones") as t:
        for c in ("ref_id", "ref_tipo", "gestionada_en", "requiere_gestion"):
            t.drop_column(c)
