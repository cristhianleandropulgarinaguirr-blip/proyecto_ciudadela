# app/routers/notificaciones.py — la campana: cada usuario ve y marca solo SUS avisos.
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notificacion, Usuario, ahora_utc
from app.schemas.comunicacion import ConteoNotificaciones, NotificacionResponse
from app.schemas.negocio import MensajeResponse

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


@router.get("/", response_model=list[NotificacionResponse], summary="Ver mis notificaciones",
            description="Roles: **todos** (solo las tuyas). Las más recientes primero; `solo_no_leidas=true` filtra las no leídas. "
                        "`gestion=por_gestionar` trae solo los avisos que piden una acción y aún no se gestionaron (aunque ya estén leídos); "
                        "`gestion=gestionadas` los que ya se gestionaron.")
def listar(solo_no_leidas: bool = Query(False), gestion: Optional[Literal["por_gestionar", "gestionadas"]] = Query(None),
           limite: int = Query(30, ge=1, le=100), db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    q = db.query(Notificacion).filter(Notificacion.usuario_id == usuario.id)
    if solo_no_leidas:
        q = q.filter(Notificacion.leida.is_(False))
    if gestion == "por_gestionar":
        q = q.filter(Notificacion.requiere_gestion.is_(True), Notificacion.gestionada_en.is_(None))
    elif gestion == "gestionadas":
        q = q.filter(Notificacion.requiere_gestion.is_(True), Notificacion.gestionada_en.is_not(None))
    # Lo que sigue por gestionar va primero: es justo lo que no se debe perder de vista aunque sea viejo.
    return q.order_by((Notificacion.requiere_gestion.is_(True) & Notificacion.gestionada_en.is_(None)).desc(), Notificacion.id.desc()).limit(limite).all()


@router.get("/conteo", response_model=ConteoNotificaciones, summary="Cuántas notificaciones tengo sin leer y cuántas por gestionar",
            description="Roles: **todos**. `no_leidas` es la burbuja roja de la campana; `por_gestionar` (avisos que piden una acción y siguen sin gestionar, "
                        "aunque ya los hayas abierto) es la burbuja ámbar.")
def conteo(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = db.query(func.count(Notificacion.id)).filter(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False)).scalar()
    g = db.query(func.count(Notificacion.id)).filter(Notificacion.usuario_id == usuario.id, Notificacion.requiere_gestion.is_(True),
                                                      Notificacion.gestionada_en.is_(None)).scalar()
    return {"no_leidas": n, "por_gestionar": g}


@router.post("/leer-todas", response_model=MensajeResponse, summary="Marcar todas como leídas", description="Roles: **todos**.")
def leer_todas(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    db.query(Notificacion).filter(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False)).update({"leida": True})
    db.commit()
    return {"mensaje": "Todas las notificaciones quedaron como leídas."}


@router.post("/{notificacion_id}/leer", response_model=MensajeResponse, summary="Marcar una notificación como leída",
             description="Roles: **todos**. Solo puedes marcar las tuyas.", responses={404: {"description": "Notificación no encontrada"}})
def leer(notificacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = db.get(Notificacion, notificacion_id)
    if n is None or n.usuario_id != usuario.id:   # no revelamos si existe una de otra persona
        raise HTTPException(status_code=404, detail="Notificación no encontrada.")
    n.leida = True
    db.commit()
    return {"mensaje": "Notificación leída."}      # ojo: leerla NO la gestiona; si pedía una acción sigue «por gestionar»


def _mia(db: Session, usuario: Usuario, notificacion_id: int) -> Notificacion:
    n = db.get(Notificacion, notificacion_id)
    if n is None or n.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Notificación no encontrada.")
    if not n.requiere_gestion:
        raise HTTPException(status_code=400, detail="Este aviso es solo informativo: no hay nada que gestionar.")
    return n


@router.post("/{notificacion_id}/gestionar", response_model=NotificacionResponse, summary="Marcar un aviso como gestionado",
             description="Roles: **todos** (solo tus avisos). Para los avisos que piden una acción. También los marca como leídos. "
                         "Normalmente no hace falta: el aviso se marca solo cuando se resuelve lo que pedía (se aprueba la reserva, se responde la PQRS…).",
             responses={400: {"description": "El aviso es informativo"}, 404: {"description": "Notificación no encontrada"}})
def gestionar(notificacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = _mia(db, usuario, notificacion_id)
    if n.gestionada_en is None:
        n.gestionada_en = ahora_utc()
    n.leida = True
    db.commit()
    db.refresh(n)
    return n


@router.post("/{notificacion_id}/pendiente", response_model=NotificacionResponse, summary="Devolver un aviso a «por gestionar»",
             description="Roles: **todos** (solo tus avisos). Por si lo marcaste como gestionado por error.",
             responses={400: {"description": "El aviso es informativo"}, 404: {"description": "Notificación no encontrada"}})
def volver_a_pendiente(notificacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = _mia(db, usuario, notificacion_id)
    n.gestionada_en = None
    db.commit()
    db.refresh(n)
    return n
