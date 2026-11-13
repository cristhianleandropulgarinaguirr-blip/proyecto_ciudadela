# app/ia.py
# Capa de acceso a la IA (versión 2.9). Principios de seguridad:
#   1. La IA SOLO redacta borradores: no tiene herramientas, no escribe en la base de datos y no envía nada. Una persona
#      revisa y confirma siempre con los formularios normales de la app.
#   2. Todo lo que dice la IA es texto NO confiable: se valida con esquemas estrictos y se limpia antes de mostrarlo.
#   3. Lo que escribe el usuario también es no confiable (puede intentar «inyectar» instrucciones): va delimitado y se trata como datos.
#   4. Privacidad: antes de salir del servidor se ocultan correos, teléfonos y números largos (posibles cédulas).
#   5. La clave viaja en un encabezado, nunca en la URL, y los errores se registran sin el contenido del mensaje.
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from app import config

logger = logging.getLogger("ia")

MODELOS_POR_DEFECTO = {"gemini": "gemini-3.5-flash", "groq": "llama-3.3-70b-versatile", "compatible": ""}
NIVELES_PENSAMIENTO = ("minimal", "low", "medium", "high")
URL_GROQ = "https://api.groq.com/openai/v1"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta"
BOGOTA = timezone(timedelta(hours=-5))      # Colombia no tiene horario de verano


class IAError(Exception):
    """Fallo del proveedor de IA. `mensaje` es apto para mostrarse al usuario; `status` es el código HTTP a devolver."""

    def __init__(self, mensaje: str, status: int = 503):
        super().__init__(mensaje)
        self.mensaje, self.status = mensaje, status


def disponible() -> bool:
    if not config.IA_API_KEY or config.PROVEEDOR_IA not in MODELOS_POR_DEFECTO:
        return False
    return config.PROVEEDOR_IA != "compatible" or bool(config.IA_URL_BASE and config.IA_MODELO)


def ahora_bogota() -> datetime:
    return datetime.now(timezone.utc).astimezone(BOGOTA)


def inicio_del_dia_utc() -> datetime:
    """Medianoche de Colombia expresada en UTC sin zona (como guarda las fechas la base de datos)."""
    medianoche = ahora_bogota().replace(hour=0, minute=0, second=0, microsecond=0)
    return medianoche.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- privacidad y limpieza
_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_NUMEROS = [
    re.compile(r"(?<!\d)(?:\+?57[ -]?)?3\d{2}[ -]?\d{3}[ -]?\d{4}(?!\d)"),    # celulares colombianos
    re.compile(r"(?<!\d)\d{1,3}(?:\.\d{3}){2,3}(?!\d)"),                      # cédula con puntos: 1.023.456.789
    re.compile(r"(?<!\d)\d{7,}(?!\d)"),                                       # cualquier número largo (cédula, cuenta, teléfono)
]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
_ENLACE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def ocultar_datos_personales(texto: str) -> str:
    texto = _CORREO.sub("[correo]", texto)
    for patron in _NUMEROS:
        texto = patron.sub("[número]", texto)
    return texto


def limpiar_entrada(texto: str, maximo: int) -> str:
    """Texto del usuario listo para enviarse: sin caracteres de control, espacios normalizados y sin etiquetas de nuestro propio formato."""
    texto = _CONTROL.sub("", texto or "")
    texto = re.sub(r"</?\s*(?:mensaje_residente|instruccion_administrador|datos_del_conjunto|conversacion|pregunta_actual)\s*>", "", texto, flags=re.IGNORECASE)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", texto)).strip()[:maximo]


def limpiar_salida(texto: Optional[str], maximo: int) -> tuple[str, bool]:
    """Texto devuelto por la IA: sin control, sin enlaces (un borrador malicioso no puede colar un «link») y con largo máximo.
    Devuelve (texto, se_quitó_un_enlace)."""
    texto = _CONTROL.sub("", str(texto or ""))
    tuvo_enlace = bool(_ENLACE.search(texto))
    texto = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", _ENLACE.sub("", texto))).strip()
    return texto[:maximo].strip(), tuvo_enlace


# Palabras que indican peligro inmediato: en esos casos NO se llama a la IA; se manda a la persona a los teléfonos de emergencia.
_EMERGENCIA = re.compile(
    r"\b(incendio|fuego|humo|explosi[oó]n|fuga de gas|huele a gas|olor a gas|cortocircuito|se est[aá] quemando|"
    r"infarto|desmay|inconsciente|convulsi|ahog|sangr|herid[oa]|ambulancia|"
    r"robo en curso|me est[aá]n robando|armad[oa]|disparo|secuestr|amenaza de muerte|"
    r"ascensor atascad[oa] con|atrapad[oa]|inundaci[oó]n grave|se est[aá] inundando|derrumbe|se cae el techo)\b",
    re.IGNORECASE)


def parece_emergencia(texto: str) -> bool:
    return bool(_EMERGENCIA.search(texto or ""))


# ---------------------------------------------------------------- llamada al proveedor
def _extraer_json(texto: str) -> dict:
    texto = (texto or "").strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.IGNORECASE).strip()
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError:
        inicio, fin = texto.find("{"), texto.rfind("}")
        if inicio < 0 or fin <= inicio:
            raise IAError("El asistente dio una respuesta que no pude entender. Intenta de nuevo o usa el formulario.", 502)
        try:
            datos = json.loads(texto[inicio:fin + 1])
        except json.JSONDecodeError:
            raise IAError("El asistente dio una respuesta que no pude entender. Intenta de nuevo o usa el formulario.", 502)
    if not isinstance(datos, dict):
        raise IAError("El asistente dio una respuesta que no pude entender. Intenta de nuevo o usa el formulario.", 502)
    return datos


def _error_http(codigo: int) -> IAError:
    logger.warning("El proveedor de IA respondió HTTP %s", codigo)    # solo el código: el cuerpo podría repetir el mensaje del usuario
    if codigo == 429:
        return IAError("El asistente alcanzó su límite de uso por ahora. Inténtalo más tarde o usa el formulario normal.", 503)
    if codigo in (401, 403):
        return IAError("El asistente no está configurado correctamente. Avisa a la administración; mientras tanto usa el formulario normal.", 503)
    return IAError("El asistente no está disponible en este momento. Puedes usar el formulario normal.", 503)


def generar_json(sistema: str, usuario: str, esquema_gemini: Optional[dict] = None, *, cliente: Optional[httpx.Client] = None) -> dict:
    """Pide una respuesta JSON al proveedor configurado. Lanza IAError (con mensaje apto para el usuario) si algo falla."""
    if not disponible():
        raise IAError("El asistente no está activado en este servidor. Puedes usar el formulario normal.", 503)
    proveedor = config.PROVEEDOR_IA
    modelo = config.IA_MODELO or MODELOS_POR_DEFECTO[proveedor]
    cerrar = cliente is None
    cliente = cliente or httpx.Client(timeout=config.IA_TIMEOUT_SEGUNDOS)
    try:
        if proveedor == "gemini":
            generacion = {"responseMimeType": "application/json", "maxOutputTokens": 2048}     # holgura: en Gemini 3 el «pensamiento» también gasta tokens
            if modelo.startswith("gemini-3"):
                # Google recomienda no tocar la temperatura en Gemini 3 y controlar la velocidad con el nivel de pensamiento.
                if config.IA_PENSAMIENTO in NIVELES_PENSAMIENTO:
                    generacion["thinkingConfig"] = {"thinkingLevel": config.IA_PENSAMIENTO.upper()}
            else:
                generacion["temperature"] = 0.2
            if esquema_gemini:
                generacion["responseSchema"] = esquema_gemini
            cuerpo = {
                "systemInstruction": {"parts": [{"text": sistema}]},
                "contents": [{"role": "user", "parts": [{"text": usuario}]}],
                "generationConfig": generacion,
            }
            res = cliente.post(f"{URL_GEMINI}/models/{modelo}:generateContent", json=cuerpo, headers={"x-goog-api-key": config.IA_API_KEY})
        else:
            base = URL_GROQ if proveedor == "groq" else config.IA_URL_BASE
            cuerpo = {"model": modelo, "temperature": 0.2, "max_tokens": 900, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}]}
            res = cliente.post(f"{base}/chat/completions", json=cuerpo, headers={"Authorization": f"Bearer {config.IA_API_KEY}"})
    except httpx.TimeoutException:
        logger.warning("El proveedor de IA tardó demasiado")
        raise IAError("El asistente tardó demasiado en responder. Intenta de nuevo o usa el formulario normal.", 503)
    except httpx.HTTPError as e:
        logger.warning("No se pudo contactar al proveedor de IA (%s)", type(e).__name__)
        raise IAError("No pude comunicarme con el asistente. Puedes usar el formulario normal.", 503)
    finally:
        if cerrar:
            cliente.close()

    if res.status_code != 200:
        raise _error_http(res.status_code)
    try:
        datos = res.json()
        if proveedor == "gemini":
            candidato = datos["candidates"][0]
            texto = "".join(p.get("text", "") for p in candidato["content"]["parts"])
        else:
            texto = datos["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        # Por ejemplo, Gemini bloquea la respuesta por seguridad y no devuelve candidatos.
        raise IAError("El asistente no pudo responder a ese mensaje. Reescríbelo con otras palabras o usa el formulario normal.", 502)
    return _extraer_json(texto)
