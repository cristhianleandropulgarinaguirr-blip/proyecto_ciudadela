# app/seed.py
# Crea los roles (si faltan) y el PRIMER administrador.
# Uso:  python -m app.seed
# Lee ADMIN_EMAIL, ADMIN_NOMBRE y ADMIN_PASSWORD del .env (si no están, los pide por teclado).
import os
from getpass import getpass

from sqlalchemy import text

from app.constantes import DESCRIPCION_ROLES, RolNombre
from app.database import SessionLocal
from app.models import Rol, Usuario
from app.security import encriptar_password


def _alinear_secuencia_roles(db) -> None:
    """PostgreSQL: la migración 0002 creó los roles con ids puestos a mano (1, 2, 3) y dejó el contador automático atrasado.
    Se alinea con el id más alto para que un INSERT sin id no choque con un rol existente. En SQLite no hace falta."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT setval(pg_get_serial_sequence('roles', 'id'), (SELECT COALESCE(MAX(id), 1) FROM roles))"))


def asegurar_roles(db) -> None:
    _alinear_secuencia_roles(db)
    for rol in RolNombre:
        if not db.query(Rol).filter(Rol.nombre == rol.value).first():
            db.add(Rol(nombre=rol.value, descripcion=DESCRIPCION_ROLES[rol]))
            db.flush()              # cada rol recibe su id al momento, con el contador ya alineado
    db.commit()


def crear_admin(db, email: str, nombre: str, password: str) -> Usuario:
    rol_admin = db.query(Rol).filter(Rol.nombre == RolNombre.ADMINISTRADOR.value).one()
    admin = db.query(Usuario).filter(Usuario.email == email).first()
    if admin:
        return admin
    admin = Usuario(nombre_completo=nombre, email=email, password_encriptada=encriptar_password(password), rol_id=rol_admin.id)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


if __name__ == "__main__":
    email = os.getenv("ADMIN_EMAIL") or input("Correo del administrador: ").strip()
    nombre = os.getenv("ADMIN_NOMBRE") or "Administrador del Conjunto"
    password = os.getenv("ADMIN_PASSWORD") or getpass("Contraseña (mín. 8 caracteres): ")
    if len(password) < 8:
        raise SystemExit("La contraseña debe tener al menos 8 caracteres.")

    with SessionLocal() as db:
        asegurar_roles(db)
        existente = db.query(Usuario).filter(Usuario.email == email).first()
        crear_admin(db, email, nombre, password)
        print("El administrador ya existía." if existente else f"Administrador creado: {email}")
