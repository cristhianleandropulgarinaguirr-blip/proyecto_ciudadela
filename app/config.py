# app/config.py
# Configuración central. Todo lo sensible (claves, conexión a la BD) se lee desde
# variables de entorno / archivo .env, NUNCA se escribe directamente en el código.
import os
from dotenv import load_dotenv

load_dotenv()


def _normalizar_url_bd(url: str) -> str:
    """Acepta la URL tal como la entrega Supabase y la adapta a SQLAlchemy + psycopg2."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalizar_url_bd(os.getenv("DATABASE_URL", "sqlite:///./propiedad_horizontal.db"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
# La portería trabaja turnos largos con el computador a la vista: su sesión dura un turno completo (por defecto 12 h)
# para no pedirle la clave a cada rato. Las demás cuentas conservan la duración normal.
GUARDIA_TOKEN_HORAS = int(os.getenv("GUARDIA_TOKEN_HORAS", "12"))
ALGORITHM = "HS256"

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
MAX_UPLOAD_MB = 5

# Fase 2 (comercio): texto que ve el vecino que quiere publicar un anuncio para saber cómo pagar.
INSTRUCCIONES_PAGO = os.getenv(
    "COMERCIO_INSTRUCCIONES_PAGO",
    "Transfiere el valor del plan a la cuenta de la administración y escribe aquí el número del comprobante. "
    "El administrador confirmará el pago y activará tu anuncio.",
)


# Bloque 3 (notificaciones por correo). Si SMTP_HOST está vacío, la app NO envía correos: solo avisos dentro de la app.
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "").strip() or SMTP_USER
MAX_PDF_MB = 10

# Versión 2.8 — dónde se guardan las fotos y los PDF.
#   local    -> carpeta UPLOAD_DIR (desarrollo; en hostings gratuitos se borra al reiniciar).
#   supabase -> Supabase Storage (bucket privado; recomendado en producción).
ALMACEN = os.getenv("ALMACEN", "local").strip().lower()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()   # SOLO en el servidor, nunca en el frontend
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "ciudadela-archivos").strip()

# Versión 2.8 — pagos. En «1» el botón «Pagar ahora» es una SIMULACIÓN (sirve para la demostración); en producción
# debe ir en «0»: el residente paga por transferencia y la administración registra el pago recibido.
PAGOS_SIMULADOS = os.getenv("PAGOS_SIMULADOS", "1").strip() not in ("0", "false", "False", "no")
PAGOS_INSTRUCCIONES = os.getenv(
    "PAGOS_INSTRUCCIONES",
    "Paga por transferencia a la cuenta de la administración y avisa en la oficina; "
    "el administrador registrará tu pago y quedará tu comprobante en esta pantalla.",
)


def obtener_secret_key() -> str:
    clave = os.getenv("SECRET_KEY", "")
    if len(clave) < 32:
        raise RuntimeError(
            "Falta SECRET_KEY (mínimo 32 caracteres). Copia .env.example a .env y genera una con: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return clave
