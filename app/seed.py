# app/seed.py
# Crea los roles (si faltan) y el PRIMER administrador.
# Uso:  python -m app.seed
# Lee ADMIN_EMAIL, ADMIN_NOMBRE y ADMIN_PASSWORD del .env (si no están, los pide por teclado).
import os
from getpass import getpass

from app.constantes import DESCRIPCION_ROLES, RolNombre
from app.database import SessionLocal
from app.models import Rol, Usuario
from app.security import encriptar_password


def asegurar_roles(db) -> None:
    for rol in RolNombre:
        if not db.query(Rol).filter(Rol.nombre == rol.value).first():
            db.add(Rol(nombre=rol.value, descripcion=DESCRIPCION_ROLES[rol]))
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
