# app/security.py
# Contraseñas con bcrypt y tokens JWT firmados.
import hmac
import re
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, obtener_secret_key

SECRET_KEY = obtener_secret_key()

_HASH_SHA256_ANTIGUO = re.compile(r"^[0-9a-f]{64}$")


def encriptar_password(password: str) -> str:
    """Genera un hash bcrypt (con sal aleatoria incluida). bcrypt solo lee los primeros 72 bytes."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def es_hash_antiguo(hash_guardado: str) -> bool:
    """True si el hash es de la versión anterior del proyecto (SHA-256 sin sal)."""
    return bool(_HASH_SHA256_ANTIGUO.match(hash_guardado or ""))


def verificar_password(password_plana: str, hash_guardado: str) -> bool:
    """Compara la contraseña con el hash. Soporta bcrypt y, temporalmente, el SHA-256 antiguo."""
    if es_hash_antiguo(hash_guardado):
        import hashlib

        calculado = hashlib.sha256(password_plana.encode("utf-8")).hexdigest()
        return hmac.compare_digest(calculado, hash_guardado)
    try:
        return bcrypt.checkpw(password_plana.encode("utf-8")[:72], hash_guardado.encode("utf-8"))
    except ValueError:
        return False


def crear_token_acceso(data: dict, minutos: int | None = None) -> str:
    """Genera el JWT firmado con fecha de expiración (por defecto, la configurada para todos)."""
    datos = data.copy()
    datos["exp"] = datetime.now(timezone.utc) + timedelta(minutes=minutos or ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(datos, SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> dict:
    """Valida la firma y la expiración. Lanza jwt.PyJWTError si el token no sirve."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
