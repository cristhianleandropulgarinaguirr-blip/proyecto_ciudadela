# app/push.py
# Avisos push (Web Push + VAPID): llegan al celular aunque la app esté cerrada.
# Se envían DESPUÉS del commit y en un grupo pequeño de hilos, igual que los correos: quien hizo la acción nunca espera.
# Si faltan las claves VAPID, todo queda apagado y la app funciona igual con la campana.
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, Optional

from app import config
from app.database import SessionLocal
from app.models import SuscripcionPush, ahora_utc

logger = logging.getLogger("conjunto")
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="push")
MAX_FALLOS = 5            # tras varios fallos que no son 404/410 (red caída del servicio push), la suscripción se descarta
TTL_SEGUNDOS = 60 * 60 * 24


def push_activo() -> bool:
    return bool(config.VAPID_PUBLIC_KEY and config.VAPID_PRIVATE_KEY)


def _enviar_una(sub: SuscripcionPush, carga: str) -> Optional[int]:
    """Devuelve None si salió bien, o el código HTTP del fallo (0 = error de red/otro)."""
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}, data=carga,
                vapid_private_key=config.VAPID_PRIVATE_KEY, vapid_claims={"sub": config.VAPID_SUBJECT}, ttl=TTL_SEGUNDOS, timeout=10)
        return None
    except WebPushException as e:
        return getattr(getattr(e, "response", None), "status_code", 0) or 0
    except Exception:   # noqa: BLE001 - un servicio push caído nunca debe romper la app
        logger.exception("Fallo inesperado enviando push")
        return 0


def enviar_ahora(usuario_ids: Iterable[int], titulo: str, mensaje: Optional[str], enlace: Optional[str], etiqueta: Optional[str] = None) -> int:
    """Envía a todas las suscripciones de esos usuarios (en el hilo que llama). Devuelve cuántas salieron bien."""
    ids = list(set(usuario_ids))
    if not ids or not push_activo():
        return 0
    carga = json.dumps({"titulo": titulo, "mensaje": mensaje or "", "enlace": enlace or "#/", "etiqueta": etiqueta or "ciudadela"}, ensure_ascii=False)
    enviados = 0
    with SessionLocal() as db:
        subs = db.query(SuscripcionPush).filter(SuscripcionPush.usuario_id.in_(ids)).all()
        for sub in subs:
            codigo = _enviar_una(sub, carga)
            if codigo is None:
                sub.ultimo_exito, sub.fallos = ahora_utc(), 0
                enviados += 1
            elif codigo in (404, 410):       # el usuario revocó el permiso o desinstaló la app: la suscripción ya no existe
                db.delete(sub)
            else:
                sub.fallos += 1
                if sub.fallos >= MAX_FALLOS:
                    db.delete(sub)
        db.commit()
    return enviados


def despachar(avisos: list[tuple[int, str, Optional[str], Optional[str]]]) -> None:
    """avisos = [(usuario_id, titulo, mensaje, enlace)]. Agrupa por contenido y lo manda en segundo plano."""
    if not avisos or not push_activo():
        return
    grupos: dict[tuple, list[int]] = {}
    for uid, titulo, mensaje, enlace in avisos:
        grupos.setdefault((titulo, mensaje, enlace), []).append(uid)
    for (titulo, mensaje, enlace), ids in grupos.items():
        _pool.submit(enviar_ahora, ids, titulo, mensaje, enlace)
