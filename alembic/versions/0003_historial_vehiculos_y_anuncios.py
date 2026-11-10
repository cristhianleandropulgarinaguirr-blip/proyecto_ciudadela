"""Trazabilidad de portería (quién registró) y módulo de anuncios con confirmación de asistencia.

- vehiculos_visitantes: agrega ingreso_registrado_por y salida_registrada_por.
- Crea las tablas anuncios y anuncio_asistencias.
No borra ni modifica datos existentes.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    columnas = {c["name"] for c in insp.get_columns("vehiculos_visitantes")}
    with op.batch_alter_table("vehiculos_visitantes") as batch:
        if "ingreso_registrado_por" not in columnas:
            batch.add_column(sa.Column("ingreso_registrado_por", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_vehiculo_ingreso_usuario", "usuarios", ["ingreso_registrado_por"], ["id"])
        if "salida_registrada_por" not in columnas:
            batch.add_column(sa.Column("salida_registrada_por", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_vehiculo_salida_usuario", "usuarios", ["salida_registrada_por"], ["id"])

    existentes = set(insp.get_table_names())
    if "anuncios" not in existentes:
        op.create_table(
            "anuncios",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("autor_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("titulo", sa.String(), nullable=False),
            sa.Column("contenido", sa.String(), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False, server_default="Aviso"),
            sa.Column("fecha_evento", sa.DateTime(), nullable=True),
            sa.Column("lugar", sa.String(), nullable=True),
            sa.Column("fijado", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_anuncios_id", "anuncios", ["id"])
    if "anuncio_asistencias" not in existentes:
        op.create_table(
            "anuncio_asistencias",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("anuncio_id", sa.Integer(), sa.ForeignKey("anuncios.id"), nullable=False),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("fecha", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("anuncio_id", "usuario_id", name="uq_asistencia_anuncio_usuario"),
        )
        op.create_index("ix_anuncio_asistencias_anuncio_id", "anuncio_asistencias", ["anuncio_id"])


def downgrade() -> None:
    op.drop_table("anuncio_asistencias")
    op.drop_table("anuncios")
    with op.batch_alter_table("vehiculos_visitantes") as batch:
        batch.drop_constraint("fk_vehiculo_salida_usuario", type_="foreignkey")
        batch.drop_constraint("fk_vehiculo_ingreso_usuario", type_="foreignkey")
        batch.drop_column("salida_registrada_por")
        batch.drop_column("ingreso_registrado_por")
