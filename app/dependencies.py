# app/dependencies.py
# "Middleware" de seguridad por inyección de dependencias:
#   1. get_current_user  -> valida el JWT y devuelve al usuario (401 si falla)
#   2. requiere_roles    -> valida el rol del usuario (403 si no tiene permiso)
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.constantes import RolNombre
from app.database import get_db
from app.models import Usuario
from app.security import decodificar_token

# tokenUrl hace que Swagger muestre el botón "Authorize" y pida usuario/clave.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Usuario:
    error_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token inválido o expirado. Inicia sesión nuevamente.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decodificar_token(token)
    except jwt.PyJWTError:
        raise error_401

    usuario_id = payload.get("usuario_id")
    if not isinstance(usuario_id, int):
        raise error_401

    # Se consulta el usuario en la BD: así el rol siempre está actualizado
    # (si el administrador cambia un rol o desactiva a alguien, aplica de inmediato).
    usuario = db.get(Usuario, usuario_id)
    if usuario is None or not usuario.esta_activo:
        raise error_401
    return usuario


def requiere_roles(*roles_permitidos: RolNombre):
    """Fábrica de dependencias RBAC. Uso: Depends(requiere_roles(RolNombre.ADMINISTRADOR))"""
    nombres = {r.value for r in roles_permitidos}

    def verificador(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.rol not in nombres:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado: tu rol ({usuario.rol}) no tiene permiso para esta acción.",
            )
        return usuario

    return verificador
