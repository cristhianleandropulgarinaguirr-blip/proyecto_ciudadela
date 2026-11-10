# app/routers/auditoria.py — consulta de la bitácora de auditoría (solo administrador).
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import Auditoria, Usuario

router = APIRouter(prefix="/auditoria", tags=["Auditoría"])


class AuditoriaItem(BaseModel):
    id: int
    fecha: datetime
    actor: str
    accion: str
    entidad: str
    entidad_id: Optional[int] = None
    detalle: Optional[str] = None


@router.get("/", response_model=list[AuditoriaItem], summary="Ver la bitácora de auditoría",
            description="Solo **Administrador**. Quién hizo qué y cuándo (reservas, usuarios, cartera, daños, cartelera, comercio y "
                        "seguridad), de lo más reciente a lo más antiguo. Filtra por `entidad` y pagina con `limite` y `desplazar`.")
def listar(entidad: Optional[str] = Query(None, max_length=30), limite: int = Query(40, ge=1, le=200),
           desplazar: int = Query(0, ge=0), db: Session = Depends(get_db),
           _: Usuario = Depends(requiere_roles(RolNombre.ADMINISTRADOR))):
    q = db.query(Auditoria, Usuario.nombre_completo).outerjoin(Usuario, Usuario.id == Auditoria.actor_id)
    if entidad:
        q = q.filter(Auditoria.entidad == entidad)
    filas = q.order_by(Auditoria.id.desc()).offset(desplazar).limit(limite).all()
    return [AuditoriaItem(id=a.id, fecha=a.fecha, actor=nombre or "Sistema", accion=a.accion, entidad=a.entidad,
                          entidad_id=a.entidad_id, detalle=a.detalle) for a, nombre in filas]
