"""Versión 5.3 · seguridad: verificación en dos pasos (TOTP) para el administrador.

Solo AGREGA cuatro columnas a `usuarios` (todas con valor por defecto, así que ningún usuario existente cambia):
- `totp_secreto`          el secreto TOTP, cifrado (nunca en claro).
- `totp_activo`           si la persona ya activó la verificación en dos pasos.
- `totp_ultimo_paso`      último código aceptado (impide reutilizarlo).
- `codigos_recuperacion`  hashes de los códigos de recuperación de uso único.
Es seguro correrla varias veces: agrega solo lo que falte.

Revision ID: 0024
Revises: 0023
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _agregar(tabla: str, columna: sa.Column) -> None:
    if columna.name not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(tabla)}:
        op.add_column(tabla, columna)


def upgrade() -> None:
    _agregar("usuarios", sa.Column("totp_secreto", sa.String, nullable=True))
    _agregar("usuarios", sa.Column("totp_activo", sa.Boolean, nullable=False, server_default=sa.false()))
    _agregar("usuarios", sa.Column("totp_ultimo_paso", sa.Integer, nullable=True))
    _agregar("usuarios", sa.Column("codigos_recuperacion", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuarios") as t:
        for c in ("codigos_recuperacion", "totp_ultimo_paso", "totp_activo", "totp_secreto"):
            t.drop_column(c)
