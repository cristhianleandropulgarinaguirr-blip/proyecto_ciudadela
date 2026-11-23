# app/security.py
# Contraseñas con bcrypt y tokens JWT firmados.
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, BCRYPT_ROUNDS, MODO_DEMO, REAUTH_MINUTOS, obtener_secret_key

# v5.0: en MODO_DEMO los tokens se firman con otra clave derivada: un token de la demo jamás es válido en la app real (ni al revés), aunque ambas
# usen el mismo SECRET_KEY del .env.
SECRET_KEY = obtener_secret_key() + (":modo-demo" if MODO_DEMO else "")

_HASH_SHA256_ANTIGUO = re.compile(r"^[0-9a-f]{64}$")


def encriptar_password(password: str, rondas: int | None = None) -> str:
    """Genera un hash bcrypt (con sal aleatoria incluida). bcrypt solo lee los primeros 72 bytes.
    `rondas` solo se usa para las claves TEMPORALES de una importación masiva (ver app/importacion.py); nunca sube del valor configurado."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=min(rondas or BCRYPT_ROUNDS, BCRYPT_ROUNDS))).decode("utf-8")


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


def nuevo_token_renovacion() -> str:
    """Token opaco y aleatorio (384 bits) para la cookie de renovación. En la base de datos solo se guarda su hash."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- v5.3 · confirmación de contraseña (acciones sensibles)
# El «pase de reautenticación» se firma con OTRA clave derivada: aunque lleve usuario_id y sid, jamás sirve como token de acceso.
_CLAVE_REAUTH = SECRET_KEY + ":reauth-v1"


def crear_token_reauth(usuario_id: int, sid: str) -> str:
    return jwt.encode({"usuario_id": usuario_id, "sid": sid, "tipo": "reauth", "exp": datetime.now(timezone.utc) + timedelta(minutes=REAUTH_MINUTOS)},
                      _CLAVE_REAUTH, algorithm=ALGORITHM)


def decodificar_token_reauth(token: str) -> dict:
    datos = jwt.decode(token, _CLAVE_REAUTH, algorithms=[ALGORITHM])
    if datos.get("tipo") != "reauth":
        raise jwt.InvalidTokenError("no es un pase de reautenticación")
    return datos


# Hash bcrypt de una clave que nadie conoce: cuando el correo NO existe se calcula igual una comparación, para que la respuesta tarde
# lo mismo que con un correo real y el tiempo no delate qué cuentas existen.
HASH_FALSO = encriptar_password(secrets.token_urlsafe(16))
