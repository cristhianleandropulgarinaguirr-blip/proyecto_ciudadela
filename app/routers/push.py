# app/routers/push.py — suscripción a los avisos push (cada persona gestiona solo los suyos).
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import config, push
from app.database import get_db
from app.dependencies import get_current_user
from app.models import SuscripcionPush, Usuario
from app.schemas.negocio import MensajeResponse

router = APIRouter(prefix="/push", tags=["Notificaciones"])
MAX_SUSCRIPCIONES = 8


class ConfigPush(BaseModel):
    activo: bool
    clave_publica: Optional[str] = None
    suscripciones: int = 0


class Claves(BaseModel):
    p256dh: str = Field(..., min_length=20, max_length=200)
    auth: str = Field(..., min_length=8, max_length=100)


class SuscripcionIn(BaseModel):
    endpoint: str = Field(..., min_length=20, max_length=1000, pattern=r"^https://")
    keys: Claves


class EndpointIn(BaseModel):
    endpoint: str = Field(..., min_length=20, max_length=1000)


@router.get("/config", response_model=ConfigPush, summary="¿Están activos los avisos push y con qué clave?",
            description="Roles: **todos**. Devuelve la clave pública (VAPID) que necesita el navegador para suscribirse.")
def configuracion(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    n = db.query(SuscripcionPush).filter(SuscripcionPush.usuario_id == usuario.id).count()
    return ConfigPush(activo=push.push_activo(), clave_publica=config.VAPID_PUBLIC_KEY or None, suscripciones=n)


@router.post("/suscribir", response_model=MensajeResponse, summary="Activar avisos push en este dispositivo",
             responses={503: {"description": "El servidor no tiene claves VAPID"}})
def suscribir(datos: SuscripcionIn, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if not push.push_activo():
        raise HTTPException(status_code=503, detail="Los avisos push no están configurados en este servidor.")
    sub = db.query(SuscripcionPush).filter(SuscripcionPush.endpoint == datos.endpoint).first()
    if sub is None:
        sub = SuscripcionPush(endpoint=datos.endpoint)
        db.add(sub)
    # El mismo celular puede cambiar de persona (portería, turnos): la suscripción pasa a quien inició sesión ahora.
    sub.usuario_id, sub.p256dh, sub.auth, sub.fallos = usuario.id, datos.keys.p256dh, datos.keys.auth, 0
    db.flush()
    propias = db.query(SuscripcionPush).filter(SuscripcionPush.usuario_id == usuario.id).order_by(SuscripcionPush.id.desc()).all()
    for vieja in propias[MAX_SUSCRIPCIONES:]:
        db.delete(vieja)
    db.commit()
    return {"mensaje": "Avisos activados en este dispositivo."}


@router.post("/desuscribir", response_model=MensajeResponse, summary="Desactivar avisos push en este dispositivo")
def desuscribir(datos: EndpointIn, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    db.query(SuscripcionPush).filter(SuscripcionPush.endpoint == datos.endpoint, SuscripcionPush.usuario_id == usuario.id).delete()
    db.commit()
    return {"mensaje": "Avisos desactivados en este dispositivo."}


@router.post("/probar", response_model=MensajeResponse, summary="Enviarme un aviso de prueba",
             responses={503: {"description": "El servidor no tiene claves VAPID"}})
def probar(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    if not push.push_activo():
        raise HTTPException(status_code=503, detail="Los avisos push no están configurados en este servidor.")
    n = push.enviar_ahora([usuario.id], "Aviso de prueba", "Si ves esto, los avisos funcionan en este dispositivo.", "#/configuracion", "prueba")
    if n == 0:
        raise HTTPException(status_code=400, detail="No pudimos enviar el aviso. Activa los avisos en este dispositivo e inténtalo de nuevo.")
    return {"mensaje": f"Aviso enviado a {n} dispositivo(s)."}
