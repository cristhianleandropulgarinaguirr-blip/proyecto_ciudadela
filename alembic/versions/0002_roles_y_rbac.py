"""Tabla de roles (RBAC) y usuarios.rol_id, conservando los datos existentes.

- Crea la tabla `roles` con Administrador, Residente y Guardia.
- Agrega `usuarios.rol_id` y lo llena a partir del texto que ya tenía cada usuario
  en `usuarios.rol` (el "Celador" se convierte en "Guardia").
- Elimina la columna de texto `usuarios.rol`.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ROLES = [
    (1, "Administrador", "Gestiona usuarios, reservas, daños y cartera del conjunto"),
    (2, "Residente", "Reserva zonas comunes, reporta daños y consulta su estado de cuenta"),
    (3, "Guardia", "Controla el ingreso y salida de vehículos en portería"),
]


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(), nullable=False, unique=True),
        sa.Column("descripcion", sa.String(), nullable=True),
    )
    op.create_index("ix_roles_id", "roles", ["id"])
    op.bulk_insert(roles, [{"id": i, "nombre": n, "descripcion": d} for i, n, d in ROLES])

    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("rol_id", sa.Integer(), nullable=True))

    # Pasar el texto antiguo ("Residente", "Celador"...) al id del rol correspondiente
    op.execute("UPDATE usuarios SET rol = 'Guardia' WHERE lower(rol) IN ('celador', 'guardia')")
    op.execute("UPDATE usuarios SET rol_id = (SELECT roles.id FROM roles WHERE lower(roles.nombre) = lower(usuarios.rol))")
    # Cualquier valor desconocido o vacío queda como Residente (el rol con menos permisos)
    op.execute("UPDATE usuarios SET rol_id = 2 WHERE rol_id IS NULL")

    with op.batch_alter_table("usuarios") as batch:
        batch.alter_column("rol_id", existing_type=sa.Integer(), nullable=False)
        batch.create_foreign_key("fk_usuarios_rol_id_roles", "roles", ["rol_id"], ["id"])
        batch.drop_column("rol")


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(sa.Column("rol", sa.String(), nullable=True))
    op.execute("UPDATE usuarios SET rol = (SELECT roles.nombre FROM roles WHERE roles.id = usuarios.rol_id)")
    with op.batch_alter_table("usuarios") as batch:
        batch.drop_constraint("fk_usuarios_rol_id_roles", type_="foreignkey")
        batch.drop_column("rol_id")
    op.drop_index("ix_roles_id", table_name="roles")
    op.drop_table("roles")
