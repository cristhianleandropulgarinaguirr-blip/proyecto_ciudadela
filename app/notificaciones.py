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

from app import config, marca, push
from app.constantes import RolNombre
from app.models import Notificacion, Rol, Usuario, ahora_utc

logger = logging.getLogger("conjunto")
PIE_CORREO = f"\n\nIngresa a {marca.nombre()} para ver los detalles. Este es un aviso automático; no respondas a este correo."


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
              enlace: Optional[str] = None, correo: bool = False, avisar_push: bool = True, *,
              requiere_gestion: bool = False, ref_tipo: Optional[str] = None, ref_id: Optional[int] = None) -> int:
    """Crea un aviso por destinatario. Con correo=True y SMTP configurado, también envía un correo tras el commit.
    Si el destinatario activó los avisos push, también le llega al celular (tras el commit, en segundo plano).

    v5.7 · `requiere_gestion=True` marca un aviso que pide una acción (aprobar, responder, recoger…): queda «por gestionar» aunque se abra,
    hasta que se gestione a mano o hasta que se resuelva lo que pedía. Para que esto último pase solo, se indica a qué cosa se refiere
    (`ref_tipo` + `ref_id`) y quien la resuelve llama a `marcar_gestionadas()` con los mismos valores."""
    cuantos = 0
    for u in destinatarios:
        if u is None or not u.esta_activo:
            continue
        db.add(Notificacion(usuario_id=u.id, titulo=titulo[:120], mensaje=(mensaje or None) and mensaje[:300], enlace=enlace,
                            requiere_gestion=requiere_gestion, ref_tipo=ref_tipo if requiere_gestion else None, ref_id=ref_id if requiere_gestion else None))
        cuantos += 1
        if avisar_push and push.push_activo():
            db.info.setdefault("push", []).append((u.id, titulo[:120], (mensaje or None) and mensaje[:300], enlace))
        if correo and correo_activo() and u.email:
            db.info.setdefault("correos", []).append((u.email, titulo, mensaje or titulo))
    return cuantos


def marcar_gestionadas(db: Session, ref_tipo: str, ref_id: int, usuario_ids: Optional[Iterable[int]] = None) -> int:
    """Cierra los avisos «por gestionar» de una misma cosa cuando esa cosa ya se resolvió (la reserva se aprobó, la PQRS se respondió…).
    Con `usuario_ids` solo toca los avisos de esas personas (p. ej. quien ya votó); sin él, los de todos los destinatarios.
    Va en la MISMA transacción del cambio que lo provoca. Devuelve cuántos cerró."""
    q = db.query(Notificacion).filter(Notificacion.ref_tipo == ref_tipo, Notificacion.ref_id == ref_id,
                                      Notificacion.requiere_gestion.is_(True), Notificacion.gestionada_en.is_(None))
    if usuario_ids is not None:
        q = q.filter(Notificacion.usuario_id.in_(list(usuario_ids)))
    # Solo cambia «gestionada»: NO toca «leída». Si el aviso se resolvió solo (otra persona aprobó, ya recogió el paquete…) y quien lo recibió
    # nunca lo abrió, conserva su burbuja roja de «sin leer»; gestión y lectura son cosas distintas.
    return q.update({"gestionada_en": ahora_utc()}, synchronize_session=False)


@event.listens_for(Session, "after_commit")
def _despachar_correos(sesion: Session) -> None:
    pendientes = sesion.info.pop("correos", None)
    if pendientes:
        enviar_correos(pendientes)
    avisos = sesion.info.pop("push", None)
    if avisos:
        push.despachar(avisos)


@event.listens_for(Session, "after_rollback")
def _descartar_correos(sesion: Session) -> None:
    sesion.info.pop("correos", None)
    sesion.info.pop("push", None)
