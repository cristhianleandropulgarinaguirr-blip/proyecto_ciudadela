# app/generar_vapid.py — genera el par de claves VAPID para los avisos push.
# Uso:  python -m app.generar_vapid
# Copia las dos líneas al .env (y a las variables de entorno de Render). La PRIVADA nunca va al frontend ni a GitHub.
import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def _b64(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def generar() -> tuple[str, str]:
    v = Vapid()
    v.generate_keys()
    privada = _b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))
    publica = _b64(v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
    return publica, privada


if __name__ == "__main__":
    publica, privada = generar()
    print("Agrega estas variables al .env y a Render (Environment):\n")
    print(f"VAPID_PUBLIC_KEY={publica}")
    print(f"VAPID_PRIVATE_KEY={privada}")
    print("VAPID_SUBJECT=mailto:tu_correo@ejemplo.com")
