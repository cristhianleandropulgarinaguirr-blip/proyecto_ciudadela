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


# Versión 3.5 — datos del conjunto para la página pública del pase de visitante (/pase/<token>).
# Con LATITUD y LONGITUD el visitante ve los botones «Cómo llegar» (Google Maps y Waze) apuntando al punto exacto de la portería;
# sin coordenadas se usa la dirección escrita; sin ninguna de las dos, los botones no aparecen.
def _decimal(nombre: str):
    try:
        return float(os.getenv(nombre, "").strip().replace(",", "."))
    except ValueError:
        return None


CONJUNTO_NOMBRE = os.getenv("CONJUNTO_NOMBRE", "").strip() or "Ciudadela Digital"
CONJUNTO_DIRECCION = os.getenv("CONJUNTO_DIRECCION", "").strip()
CONJUNTO_LATITUD = _decimal("CONJUNTO_LATITUD")
CONJUNTO_LONGITUD = _decimal("CONJUNTO_LONGITUD")


# Versión 3.6 — paz y salvo con QR. Cuántos días sirve un certificado y la dirección pública de la app (para el QR del PDF).
# URL_PUBLICA solo hace falta si el QR saliera con una dirección interna (p. ej. detrás de un proxy raro); normalmente se deduce sola de la petición.
PAZ_Y_SALVO_DIAS = max(1, min(365, int(os.getenv("PAZ_Y_SALVO_DIAS", "30") or "30")))
URL_PUBLICA = os.getenv("URL_PUBLICA", "").strip().rstrip("/")


# ==========================================================================================================
# Versión 4.0 (Fase 4 · presentación comercial): WHITE-LABEL, landing y solicitud de demo.
# Todo es opcional: sin ninguna de estas variables la app se ve exactamente igual que antes («Ciudadela Digital», azul marino).
# Para entregarle la app a OTRO conjunto o empresa basta con cambiar variables de entorno (y, si quieres, soltar sus logos en la carpeta marca/).
# ==========================================================================================================
from pathlib import Path as _Path   # noqa: E402

MARCA_NOMBRE_POR_DEFECTO = "Ciudadela Digital"
MARCA_NOMBRE = os.getenv("MARCA_NOMBRE", "").strip()[:60] or MARCA_NOMBRE_POR_DEFECTO                     # nombre del producto: pestaña, menú, PDF, correos, chat
MARCA_NOMBRE_CORTO = os.getenv("MARCA_NOMBRE_CORTO", "").strip()[:14] or (                                 # nombre bajo el icono del celular
    "Ciudadela" if MARCA_NOMBRE == MARCA_NOMBRE_POR_DEFECTO else MARCA_NOMBRE.split()[0][:14])
MARCA_ESLOGAN = os.getenv("MARCA_ESLOGAN", "").strip()[:80] or "Tu conjunto, siempre en orden."            # titular de la pantalla de ingreso
MARCA_DESCRIPCION = os.getenv("MARCA_DESCRIPCION", "").strip()[:200] or "Reservas, mantenimiento, cartera y portería de tu conjunto residencial en un solo lugar."
MARCA_COLOR = os.getenv("MARCA_COLOR", "").strip()                                                         # «#RRGGBB»: color principal (login, administrador y landing). Vacío = azul de siempre
# Carpeta con los logos del cliente (opcional). Si un archivo con el MISMO nombre que los de frontend/img existe aquí, se usa este.
MARCA_DIR = _Path(os.getenv("MARCA_DIR", "").strip() or (_Path(__file__).resolve().parent.parent / "marca"))

# Landing comercial en «/». SOLO debe estar en «1» en el servicio de la DEMO. En «0» (la app real de un cliente) la raíz lleva directo a la app
# y además se desactiva «Solicitar demo» (POST /demo/solicitar responde 404): una app de verdad no tiene por qué recibir contactos comerciales.
LANDING_ACTIVA = os.getenv("LANDING_ACTIVA", "1").strip() not in ("0", "false", "False", "no", "NO")
# Documentación interactiva de la API (/docs, /redoc y /openapi.json). En «1» (por defecto) sirve para la demostración y la revisión del
# instructor; en la app de un cliente ya contratado ponla en «0»: así nadie ve la lista completa de rutas internas.
DOCS_ACTIVAS = os.getenv("DOCS_ACTIVAS", "1").strip() not in ("0", "false", "False", "no", "NO")
# WhatsApp de ventas (con indicativo de país, solo dígitos; 10 dígitos que empiecen en 3 se asumen colombianos y se les antepone 57).
DEMO_WHATSAPP = "".join(ch for ch in os.getenv("DEMO_WHATSAPP", "") if ch.isdigit())
if len(DEMO_WHATSAPP) == 10 and DEMO_WHATSAPP.startswith("3"):
    DEMO_WHATSAPP = "57" + DEMO_WHATSAPP
if not 11 <= len(DEMO_WHATSAPP) <= 15:
    DEMO_WHATSAPP = ""              # número inválido = sin botón de WhatsApp (nunca un enlace roto)
# v4.2 · Nombre de quien atiende ese WhatsApp (p. ej. «Cristhian»): el mensaje de la landing arranca con «Hola Cristhian, …». Vacío = «Hola, …».
DEMO_CONTACTO = " ".join(os.getenv("DEMO_CONTACTO", "").split())[:40]
DEMO_CORREO = os.getenv("DEMO_CORREO", "").strip()[:120]                                                   # correo de ventas que se muestra en la landing (opcional)

# v4.8 · AVISO AL VENDEDOR por Telegram cuando alguien pide una demo desde la landing (ya NO le llega a ningún administrador de la app).
# El cliente no necesita Telegram: solo lo usas TÚ para enterarte al instante. Se configura una sola vez (pasos en PASOS_V4.8.md):
#   TELEGRAM_BOT_TOKEN   el token que te da @BotFather al crear tu bot. Es secreto.
#   TELEGRAM_CHAT_ID     el número de tu chat con el bot (se obtiene escribiéndole «/start» y abriendo getUpdates; ver la guía).
# Sin ambos no se envía nada (la solicitud igual queda guardada en la base).
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()[:100]
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()[:30]
MARCA_ASISTENTE = os.getenv("MARCA_ASISTENTE", "").strip()[:30] or "Ciudabot"                               # nombre del asistente de chat


# Versión 4.6 — asambleas de copropietarios (Ley 675 de 2001). Son los valores «por defecto» del conjunto; cada asamblea puede ajustar algunos.
# Confírmalos con el reglamento de propiedad horizontal de tu conjunto: si dice otra cosa, el reglamento manda.
ASAMBLEA_DIAS_ORDINARIA = _entero("ASAMBLEA_DIAS_ORDINARIA", 15) or 15          # Art. 39: días calendario de anticipación para la asamblea ordinaria
ASAMBLEA_DIAS_EXTRAORDINARIA = _entero("ASAMBLEA_DIAS_EXTRAORDINARIA", 5)       # la ley no fija un mínimo: lo prudente es lo que diga el reglamento
ASAMBLEA_MAX_PODERES = _entero("ASAMBLEA_MAX_PODERES", 2) or 2                  # cuántos poderes puede recibir una misma persona (lo limita el reglamento)
ASAMBLEA_SABADO_HABIL = os.getenv("ASAMBLEA_SABADO_HABIL", "0").strip() in ("1", "true", "True", "si", "sí")   # ¿el sábado cuenta como día hábil para la 2.ª convocatoria?
ASAMBLEA_EXIGE_FINANCIEROS = os.getenv("ASAMBLEA_EXIGE_FINANCIEROS", "1").strip() not in ("0", "false", "False", "no")   # asamblea ordinaria: exige adjuntar estados financieros
ASAMBLEA_BLOQUEA_PODER_STAFF = os.getenv("ASAMBLEA_BLOQUEA_PODER_STAFF", "1").strip() not in ("0", "false", "False", "no")   # el administrador y el personal no reciben poderes
