# app/routers/notificaciones.py — la campana: cada usuario ve y marca solo SUS avisos.
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notificacion, Usuario
from app.schemas.comunicacion import ConteoNotificaciones, NotificacionResponse
from app.schemas.negocio import MensajeResponse

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])


@router.get("/", response_model=list[NotificacionResponse], summary="Ver mis notificaciones",
            description="Roles: **todos** (solo las tuyas). Las más recientes primero; `solo_no_leidas=true` filtra las pendientes.")
def listar(solo_no_leidas: bool = Query(False), limite: int = Query(30, ge=1, le=100), db: Session = Depends(get_db),
           usuario: Usuario = Depends(get_current_user)):
    q = db.query(Notificacion).filter(Notificacion.usuario_id == usuario.id)
    if solo_no_leidas:
        q = q.filter(Notificacion.leida.is_(False))
    return q.order_by(Notificacion.id.desc()).limit(limite).all()


@router.get("/conteo", response_model=ConteoNotificaciones, summary="Cuántas notificaciones tengo sin leer",
            description="Roles: **todos**. Es lo que muestra la burbuja de la campana.")
def conteo(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = db.query(func.count(Notificacion.id)).filter(Notificacion.usuario_id == usuario.id, Notificacion.leida.is_(False)).scalar()
    return {"no_leidas": n}


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
    return {"mensaje": "Notificación leída."}
