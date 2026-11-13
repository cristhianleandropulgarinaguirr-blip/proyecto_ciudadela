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
# Versión 3.1 — sesión segura. El token de acceso (JWT) dura POCO (15 min) y vive solo en la pestaña; lo renueva una cookie
# «refresh» HttpOnly (JavaScript no puede leerla) que se rota en cada uso y se puede revocar desde el servidor.
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
# Cuánto dura la sesión (se renueva sola mientras la persona use la app) antes de pedir la clave otra vez:
#   - Guardia: un turno completo (12 h por defecto), con tope absoluto de 24 h.
#   - Administrador: 7 días · Residente: 14 días. Tope absoluto para todos: SESION_MAXIMA_DIAS (60).
GUARDIA_TOKEN_HORAS = int(os.getenv("GUARDIA_TOKEN_HORAS", "12"))
SESION_DIAS_ADMIN = int(os.getenv("SESION_DIAS_ADMIN", "7"))
SESION_DIAS = int(os.getenv("SESION_DIAS", "14"))
SESION_MAXIMA_DIAS = int(os.getenv("SESION_MAXIMA_DIAS", "60"))
ALGORITHM = "HS256"
# Coste de bcrypt (12 = recomendado en producción). Las pruebas automáticas lo bajan para correr en segundos.
BCRYPT_ROUNDS = max(4, min(15, int(os.getenv("BCRYPT_ROUNDS", "12"))))

# Versión 3.1 — avisos push (Web Push). Sin las dos claves VAPID los avisos solo se ven dentro de la app (campana).
# Genera el par con:  python -m app.generar_vapid
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "").strip() or "mailto:admin@ciudadela.local"

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


# Versión 2.9 — asistente de IA (borradores de PQRS, daños y avisos). La clave vive SOLO en el servidor (.env).
#   PROVEEDOR_IA: gemini (gratis en Google AI Studio) | groq | compatible (cualquier API estilo OpenAI: exige IA_URL_BASE).
#   Si falta la clave, el asistente queda apagado y toda la app funciona igual con sus formularios normales.
def _entero(nombre: str, defecto: int) -> int:
    try:
        return max(0, int(os.getenv(nombre, str(defecto))))
    except ValueError:
        return defecto


PROVEEDOR_IA = os.getenv("PROVEEDOR_IA", "gemini").strip().lower()
IA_API_KEY = (os.getenv("IA_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
IA_MODELO = os.getenv("IA_MODELO", "").strip()                    # vacío = modelo por defecto del proveedor
IA_URL_BASE = os.getenv("IA_URL_BASE", "").strip().rstrip("/")    # solo para PROVEEDOR_IA=compatible
IA_TIMEOUT_SEGUNDOS = _entero("IA_TIMEOUT_SEGUNDOS", 45) or 45
# Modelos Gemini 3.x: cuánto «piensan» antes de responder (minimal | low | medium | high). Para borradores cortos basta «low»: es mucho más rápido.
# Vacío = no enviar nada (usa el valor por defecto de Google, que es más lento). Se ignora en modelos que no son Gemini 3.
IA_PENSAMIENTO = os.getenv("IA_PENSAMIENTO", "low").strip().lower()
# Topes para proteger la cuota gratuita y evitar abuso: por persona y para todo el conjunto, por día (hora de Colombia).
IA_LIMITE_DIARIO_USUARIO = _entero("IA_LIMITE_DIARIO_USUARIO", 10)
IA_LIMITE_DIARIO_GLOBAL = _entero("IA_LIMITE_DIARIO_GLOBAL", 100)
# Chat (v3.2): tiene topes propios para que una conversación larga no gaste las consultas de los borradores.
IA_LIMITE_CHAT_USUARIO = _entero("IA_LIMITE_CHAT_USUARIO", 30)
IA_LIMITE_CHAT_GLOBAL = _entero("IA_LIMITE_CHAT_GLOBAL", 300)
