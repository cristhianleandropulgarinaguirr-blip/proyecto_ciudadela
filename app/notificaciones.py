# app/notificaciones.py
# Avisos dentro de la app (tabla `notificaciones`) y, si hay un servidor SMTP configurado, también por correo.
# Las notificaciones se crean en la MISMA transacción del cambio que las provoca (si algo falla, no se envía nada).
# Los correos se envían solo después del commit y en un hilo aparte, para no hacer esperar a quien hizo la acción.
import logging
import smtplib
import threading
from email.message import EmailMessage
from typing import Iterable, Optional

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import config
from app.constantes import RolNombre
from app.models import Notificacion, Rol, Usuario

logger = logging.getLogger("conjunto")
PIE_CORREO = "\n\nIngresa a Ciudadela Digital para ver los detalles. Este es un aviso automático; no respondas a este correo."


def correo_activo() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_FROM)


def _enviar_ahora(mensajes: list[tuple[str, str, str]]) -> None:
    """mensajes = [(correo, asunto, texto)]. Usa una sola conexión SMTP para todos."""
    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            for destino, asunto, texto in mensajes:
                m = EmailMessage()
                m["From"], m["To"], m["Subject"] = config.SMTP_FROM, destino, asunto
                m.set_content(texto + PIE_CORREO)
                smtp.send_message(m)
    except Exception:   # un correo caído nunca debe romper la app
        logger.exception("No se pudieron enviar %d correo(s)", len(mensajes))


def enviar_correos(mensajes: list[tuple[str, str, str]]) -> None:
    """Punto único de envío (las pruebas lo reemplazan). Lo hace en un hilo para no bloquear la respuesta."""
    if mensajes and correo_activo():
        threading.Thread(target=_enviar_ahora, args=(mensajes,), daemon=True).start()


def usuarios_activos(db: Session, roles: Optional[Iterable[RolNombre]] = None, excluir_id: Optional[int] = None) -> list[Usuario]:
    q = db.query(Usuario).filter(Usuario.esta_activo.is_(True))
    if roles:
        q = q.join(Rol, Rol.id == Usuario.rol_id).filter(Rol.nombre.in_([r.value for r in roles]))
    if excluir_id is not None:
        q = q.filter(Usuario.id != excluir_id)
    return q.all()


def notificar(db: Session, destinatarios: Iterable[Usuario], titulo: str, mensaje: Optional[str] = None,
              enlace: Optional[str] = None, correo: bool = False) -> int:
    """Crea un aviso por destinatario. Con correo=True y SMTP configurado, también envía un correo tras el commit."""
    cuantos = 0
    for u in destinatarios:
        if u is None or not u.esta_activo:
            continue
        db.add(Notificacion(usuario_id=u.id, titulo=titulo[:120], mensaje=(mensaje or None) and mensaje[:300], enlace=enlace))
        cuantos += 1
        if correo and correo_activo() and u.email:
            db.info.setdefault("correos", []).append((u.email, titulo, mensaje or titulo))
    return cuantos


@event.listens_for(Session, "after_commit")
def _despachar_correos(sesion: Session) -> None:
    pendientes = sesion.info.pop("correos", None)
    if pendientes:
        enviar_correos(pendientes)


@event.listens_for(Session, "after_rollback")
def _descartar_correos(sesion: Session) -> None:
    sesion.info.pop("correos", None)
