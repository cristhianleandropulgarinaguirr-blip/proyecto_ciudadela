# app/avisos_demo.py — V4.8: avisarle al VENDEDOR (tú) por Telegram cuando alguien pide una demostración.
#
# Por qué Telegram y no WhatsApp: WhatsApp no deja que un servidor le escriba a un número personal sin un servicio intermedio (el gratuito,
# CallMeBot, tiene el cupo lleno). La API de bots de Telegram es oficial, gratuita y llega al celular al instante. El CLIENTE no necesita
# Telegram para nada: él solo usa el formulario y WhatsApp. Telegram lo usas SOLO tú, para enterarte aunque el cliente no termine de escribirte.
#
# Reglas de este módulo:
#   · NUNCA lanza una excepción ni le devuelve un error al visitante: si Telegram falla, la solicitud ya quedó guardada en la base.
#   · El token del bot viaja en la dirección de la petición, así que JAMÁS se escribe en el registro (ni el texto de las excepciones,
#     que puede traer la dirección completa): solo el tipo de error o el código HTTP.
#   · Se llama desde una tarea en segundo plano (BackgroundTasks): el visitante no espera a Telegram.
import logging

import httpx

from app import config

log = logging.getLogger("ciudadela.avisos")

MAX_TEXTO = 1500         # Telegram admite 4096; un aviso más largo no sirve en el celular y el detalle completo queda en la base
TIEMPO_MAXIMO = 10.0     # segundos


def configurado() -> bool:
    """¿Hay token y destino? Sin ambos no se intenta nada."""
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def enviar(texto: str) -> bool:
    """Manda `texto` a tu chat de Telegram. True si Telegram lo aceptó; False en cualquier otro caso (sin excepciones)."""
    if not configurado():
        log.info("Aviso de demo no enviado: faltan TELEGRAM_BOT_TOKEN y/o TELEGRAM_CHAT_ID. La solicitud quedó guardada en la base.")
        return False
    try:
        # Sin parse_mode: el texto va tal cual (lo escribió un desconocido; así nada se interpreta como formato). disable_web_page_preview evita la vista previa del enlace.
        r = httpx.post(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
                       json={"chat_id": config.TELEGRAM_CHAT_ID, "text": texto[:MAX_TEXTO], "disable_web_page_preview": True}, timeout=TIEMPO_MAXIMO)
    except Exception as e:   # noqa: BLE001 — cualquier fallo de red/TLS/tiempo: se registra el TIPO, nunca el mensaje (trae el token)
        log.warning("No se pudo enviar el aviso de demo por Telegram (%s). La solicitud quedó guardada en la base.", type(e).__name__)
        return False
    if r.status_code != 200:
        log.warning("Telegram rechazó el aviso de demo (HTTP %s). Revisa TELEGRAM_BOT_TOKEN y que hayas escrito «/start» al bot desde tu cuenta.", r.status_code)
        return False
    return True


def texto_de_solicitud(s) -> str:
    """Arma el mensaje que te llega. Texto plano. Termina con un enlace que abre el chat de WhatsApp con el cliente."""
    lineas = ["Nueva solicitud de demo", f"Nombre: {s.nombre}", f"Conjunto: {s.conjunto}", f"Celular: {s.celular}"]
    if s.correo:
        lineas.append(f"Correo: {s.correo}")
    if s.ciudad:
        lineas.append(f"Ciudad: {s.ciudad}")
    if s.apartamentos:
        lineas.append(f"Apartamentos: {s.apartamentos}")
    if s.mensaje:
        lineas.append(f"Mensaje: {s.mensaje}")
    lineas.append("Llegó desde: " + ("el botón «Solicitar demo» (se le abrió WhatsApp con sus datos: revisa tu WhatsApp, seguramente ya te escribió)" if s.origen == "whatsapp" else "el formulario"))
    lineas.append(f"Escríbele por WhatsApp: https://wa.me/57{s.celular}")
    return "\n".join(lineas)
