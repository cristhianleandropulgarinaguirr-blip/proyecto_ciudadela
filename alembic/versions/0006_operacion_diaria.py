"""Bloque 2: visitantes autorizados, paquetes y correspondencia, y contactos de emergencia.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Líneas nacionales de Colombia. El administrador puede editarlas o agregar las locales (CAI, clínica, gas...).
EMERGENCIAS_BASE = [
    ("Línea única de emergencias", "123", "Emergencias", "Atiende policía, bomberos y ambulancias. Es el primer número a marcar.", 1),
    ("Policía Nacional", "112", "Seguridad", "Línea directa de la Policía.", 2),
    ("Bomberos", "119", "Emergencias", "Incendios, rescates y emergencias con materiales peligrosos.", 3),
    ("Cruz Roja Colombiana", "132", "Salud", "Atención prehospitalaria y primeros auxilios.", 4),
    ("Defensa Civil", "144", "Emergencias", "Desastres, inundaciones y rescate.", 5),
]


def upgrade() -> None:
    tablas = set(sa.inspect(op.get_bind()).get_table_names())

    if "visitantes_autorizados" not in tablas:
        op.create_table(
            "visitantes_autorizados",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("nombre", sa.String(), nullable=False),
            sa.Column("documento", sa.String(), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False, server_default="Otro"),
            sa.Column("vigente_hasta", sa.DateTime(), nullable=True),
            sa.Column("notas", sa.String(), nullable=True),
            sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("usuario_id", "documento", name="uq_visitante_usuario_documento"),
        )
        op.create_index("ix_visitantes_autorizados_id", "visitantes_autorizados", ["id"])
        op.create_index("ix_visitantes_autorizados_usuario_id", "visitantes_autorizados", ["usuario_id"])
        op.create_index("ix_visitantes_autorizados_documento", "visitantes_autorizados", ["documento"])

    if "accesos_visitantes" not in tablas:
        op.create_table(
            "accesos_visitantes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("visitante_id", sa.Integer(), sa.ForeignKey("visitantes_autorizados.id"), nullable=False),
            sa.Column("fecha_ingreso", sa.DateTime(), nullable=True),
            sa.Column("fecha_salida", sa.DateTime(), nullable=True),
            sa.Column("ingreso_registrado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("salida_registrada_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        )
        op.create_index("ix_accesos_visitantes_id", "accesos_visitantes", ["id"])
        op.create_index("ix_accesos_visitantes_visitante_id", "accesos_visitantes", ["visitante_id"])
        op.create_index("ix_accesos_visitantes_fecha_ingreso", "accesos_visitantes", ["fecha_ingreso"])

    if "paquetes" not in tablas:
        op.create_table(
            "paquetes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("destinatario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=False),
            sa.Column("tipo", sa.String(), nullable=False, server_default="Paquete"),
            sa.Column("remitente", sa.String(), nullable=True),
            sa.Column("descripcion", sa.String(), nullable=True),
            sa.Column("estado", sa.String(), nullable=False, server_default="En porteria"),
            sa.Column("recibido_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_recepcion", sa.DateTime(), nullable=True),
            sa.Column("entregado_a", sa.String(), nullable=True),
            sa.Column("entregado_por", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
            sa.Column("fecha_entrega", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_paquetes_id", "paquetes", ["id"])
        op.create_index("ix_paquetes_destinatario_id", "paquetes", ["destinatario_id"])
        op.create_index("ix_paquetes_estado", "paquetes", ["estado"])
        op.create_index("ix_paquetes_fecha_recepcion", "paquetes", ["fecha_recepcion"])

    if "contactos_emergencia" not in tablas:
        tabla = op.create_table(
            "contactos_emergencia",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("nombre", sa.String(), nullable=False),
            sa.Column("telefono", sa.String(), nullable=False),
            sa.Column("categoria", sa.String(), nullable=False, server_default="Otros"),
            sa.Column("descripcion", sa.String(), nullable=True),
            sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fecha_creacion", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_contactos_emergencia_id", "contactos_emergencia", ["id"])
        # Solo al crear la tabla: así el administrador puede borrar los que no quiera sin que reaparezcan.
        op.bulk_insert(tabla, [{"nombre": n, "telefono": t, "categoria": c, "descripcion": d, "orden": o}
                               for n, t, c, d, o in EMERGENCIAS_BASE])


def downgrade() -> None:
    op.drop_table("contactos_emergencia")
    op.drop_table("paquetes")
    op.drop_table("accesos_visitantes")
    op.drop_table("visitantes_autorizados")
