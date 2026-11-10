# app/auditoria.py
# Bitácora de auditoría: quién hizo qué y cuándo. Protege al administrador ante reclamos y deja rastro de cambios sensibles.
# Se llama ANTES del commit de la operación, así el registro y el cambio se guardan juntos (o ninguno).
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Auditoria, Usuario


def auditar(db: Session, actor: Optional[Usuario], accion: str, entidad: str,
            entidad_id: Optional[int] = None, detalle: Optional[str] = None) -> None:
    db.add(Auditoria(actor_id=actor.id if actor else None, accion=accion, entidad=entidad,
                     entidad_id=entidad_id, detalle=(detalle or None) and detalle[:300]))
