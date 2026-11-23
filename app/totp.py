# app/totp.py
# Verificación en dos pasos (TOTP, RFC 6238) hecha con la librería estándar: compatible con Google Authenticator, Microsoft Authenticator, Authy, 1Password…
#  - El secreto se guarda CIFRADO (Fernet, con una clave derivada de SECRET_KEY): si alguien copia la base de datos no puede generar códigos.
#  - Cada código sirve UNA sola vez (se guarda el último «paso» de 30 s aceptado) y se tolera 1 paso de desfase de reloj.
#  - Los códigos de recuperación (uso único) se guardan solo como hash SHA-256.
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.security import SECRET_KEY

PASO_S = 30
DIGITOS = 6
VENTANA = 1                 # se aceptan el código anterior y el siguiente (relojes un poco desfasados)
N_RECUPERACION = 8


# ---------------------------------------------------------------- cifrado del secreto
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((SECRET_KEY + ":totp-v1").encode()).digest()))


def cifrar(secreto: str) -> str:
    return _fernet().encrypt(secreto.encode()).decode()


def descifrar(cifrado: Optional[str]) -> Optional[str]:
    if not cifrado:
        return None
    try:
        return _fernet().decrypt(cifrado.encode()).decode()
    except (InvalidToken, ValueError):
        return None             # SECRET_KEY cambió o el dato está dañado: se trata como «sin secreto» (nunca como acceso)


# ---------------------------------------------------------------- códigos
def nuevo_secreto() -> str:
    """20 bytes aleatorios en base32 (32 caracteres), el formato que entienden todas las apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo(secreto: str, paso: int) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8), casefold=True)
    mac = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    i = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[i:i + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITOS)
    return str(n).zfill(DIGITOS)


def paso_actual(ahora: Optional[float] = None) -> int:
    return int((time.time() if ahora is None else ahora) // PASO_S)


def verificar(secreto: str, codigo: str, ultimo_paso: Optional[int] = None, ahora: Optional[float] = None) -> Optional[int]:
    """Devuelve el paso aceptado (para guardarlo) o None. Un paso ya usado, o más viejo, nunca se acepta otra vez."""
    limpio = "".join(ch for ch in (codigo or "") if ch.isdigit())
    if len(limpio) != DIGITOS or not secreto:
        return None
    actual, aceptado = paso_actual(ahora), None
    for p in range(actual - VENTANA, actual + VENTANA + 1):          # se recorren todos: el tiempo de respuesta no delata cuál acertó
        if hmac.compare_digest(_codigo(secreto, p), limpio) and (ultimo_paso is None or p > ultimo_paso):
            aceptado = p
    return aceptado


def uri(secreto: str, correo: str, emisor: str) -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(emisor)}:{quote(correo)}?secret={secreto}&issuer={quote(emisor)}&algorithm=SHA1&digits={DIGITOS}&period={PASO_S}"


def qr_svg(contenido: str) -> str:
    """El QR como «data URI» SVG (la política de contenido de la app ya permite imágenes data:)."""
    import segno
    return segno.make(contenido, error="m").svg_data_uri(scale=5, border=2)


# ---------------------------------------------------------------- códigos de recuperación (uso único)
def _hash_rec(codigo: str) -> str:
    return hashlib.sha256("".join(ch for ch in codigo.lower() if ch.isalnum()).encode()).hexdigest()


def generar_recuperacion() -> tuple[list[str], str]:
    """(códigos en claro para mostrar UNA vez, JSON con sus hashes para guardar)."""
    claros = []
    for _ in range(N_RECUPERACION):
        t = secrets.token_hex(5)                     # 40 bits cada uno; además el login se bloquea tras 5 fallos
        claros.append(f"{t[:5]}-{t[5:]}")
    return claros, json.dumps([_hash_rec(c) for c in claros])


def consumir_recuperacion(guardados: Optional[str], codigo: str) -> Optional[str]:
    """Si el código es uno de los guardados, devuelve la lista nueva (sin ese código) ya en JSON; si no, None."""
    try:
        hashes = json.loads(guardados or "[]")
    except ValueError:
        return None
    h = _hash_rec(codigo or "")
    encontrado = None
    for x in hashes:
        if hmac.compare_digest(x, h):
            encontrado = x
    if encontrado is None:
        return None
    hashes.remove(encontrado)
    return json.dumps(hashes)


def quedan_recuperacion(guardados: Optional[str]) -> int:
    try:
        return len(json.loads(guardados or "[]"))
    except ValueError:
        return 0
