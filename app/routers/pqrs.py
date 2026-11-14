# app/routers/pqrs.py
# Bloque 3 · PQRS (peticiones, quejas, reclamos y sugerencias): el residente radica, el administrador responde y
# cambia el estado, y el residente recibe un aviso. Cada solicitud tiene un número de radicado.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.constantes import EstadoPQRS, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import PQRS, Usuario, ahora_utc
from app.notificaciones import notificar, usuarios_activos
from app.schemas.comunicacion import PQRSCreate, PQRSResponse, PQRSUpdate

TAG = "PQRS"
router = APIRouter(prefix="/pqrs", tags=[TAG])
ADMIN, RESIDENTE, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.INQUILINO
MAX_ABIERTAS = 5          # por residente: evita saturar a la administración
ABIERTAS = (EstadoPQRS.RADICADA.value, EstadoPQRS.EN_TRAMITE.value)


def radicado(p: PQRS) -> str:
    return f"PQRS-{p.fecha_creacion.year}-{p.id:04d}"


def _vistas(db: Session, lista: list[PQRS]) -> list[PQRSResponse]:
    ids = {p.usuario_id for p in lista} | {p.respondido_por for p in lista if p.respondido_por}
    personas = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if ids else {}
    return [PQRSResponse(
        id=p.id, radicado=radicado(p), usuario_id=p.usuario_id,
        usuario_nombre=personas[p.usuario_id].nombre_completo if p.usuario_id in personas else "Residente",
        apartamento=personas[p.usuario_id].apartamento if p.usuario_id in personas else None,
        tipo=p.tipo, asunto=p.asunto, descripcion=p.descripcion, estado=p.estado, respuesta=p.respuesta,
        respondido_por=personas[p.respondido_por].nombre_completo if p.respondido_por in personas else None,
        fecha_respuesta=p.fecha_respuesta, fecha_creacion=p.fecha_creacion, fecha_actualizacion=p.fecha_actualizacion) for p in lista]


@router.post("/", response_model=PQRSResponse, status_code=status.HTTP_201_CREATED, summary="Radicar una PQRS",
             description="Roles: **Residente**, **Administrador**. Se genera un número de radicado y se avisa a los administradores. "
                         f"Máximo {MAX_ABIERTAS} solicitudes abiertas por persona.",
             responses={400: {"description": "Demasiadas PQRS abiertas"}, 422: {"description": "Datos inválidos"}})
def radicar(datos: PQRSCreate, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    abiertas = db.query(func.count(PQRS.id)).filter(PQRS.usuario_id == usuario.id, PQRS.estado.in_(ABIERTAS)).scalar()
    if abiertas >= MAX_ABIERTAS:
        raise HTTPException(status_code=400, detail=f"Ya tienes {MAX_ABIERTAS} solicitudes abiertas. Espera la respuesta de alguna antes de enviar otra.")
    p = PQRS(usuario_id=usuario.id, tipo=datos.tipo.value, asunto=datos.asunto, descripcion=datos.descripcion)
    db.add(p)
    db.flush()
    p.fecha_creacion = p.fecha_creacion or ahora_utc()
    auditar(db, usuario, "Radicó PQRS", "PQRS", p.id, f"{p.tipo}: {p.asunto}")
    notificar(db, usuarios_activos(db, [ADMIN], excluir_id=usuario.id), f"Nueva {p.tipo.lower()}: {p.asunto}",
              f"De {usuario.nombre_completo}{f' ({usuario.apartamento})' if usuario.apartamento else ''}.", "#/pqrs")
    db.commit()
    db.refresh(p)
    return _vistas(db, [p])[0]


@router.get("/", response_model=list[PQRSResponse], summary="Ver PQRS",
            description="Roles: **Residente**, **Administrador**. El residente ve solo las suyas; el administrador ve todas y puede filtrar por `estado`.")
def listar(estado: Optional[EstadoPQRS] = Query(None), limite: int = Query(100, ge=1, le=300), db: Session = Depends(get_db),
           usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    q = db.query(PQRS)
    if usuario.rol != ADMIN.value:
        q = q.filter(PQRS.usuario_id == usuario.id)
    if estado:
        q = q.filter(PQRS.estado == estado.value)
    return _vistas(db, q.order_by(PQRS.id.desc()).limit(limite).all())


@router.patch("/{pqrs_id}", response_model=PQRSResponse, summary="Responder o cambiar el estado de una PQRS",
              description="Solo **Administrador**. Una respuesta sin estado deja la solicitud «Resuelta». Para marcarla «Resuelta» debe existir una respuesta. "
                          "El residente recibe un aviso (y un correo si está configurado).",
              responses={400: {"description": "Cambio no permitido"}, 404: {"description": "PQRS no encontrada"}})
def gestionar(pqrs_id: int, datos: PQRSUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    p = db.get(PQRS, pqrs_id)
    if p is None:
        raise HTTPException(status_code=404, detail="PQRS no encontrada.")
    if datos.estado is None and datos.respuesta is None:
        raise HTTPException(status_code=400, detail="Indica un estado nuevo o escribe una respuesta.")
    nuevo = datos.estado.value if datos.estado else (EstadoPQRS.RESUELTA.value if datos.respuesta else p.estado)
    respuesta = datos.respuesta or p.respuesta
    if nuevo == EstadoPQRS.RESUELTA.value and not respuesta:
        raise HTTPException(status_code=400, detail="Para marcarla como resuelta escribe una respuesta para el residente.")
    if nuevo == p.estado and datos.respuesta is None:
        raise HTTPException(status_code=400, detail=f"La solicitud ya está «{p.estado.lower()}».")
    if datos.respuesta:
        p.respuesta, p.respondido_por, p.fecha_respuesta = datos.respuesta, admin.id, ahora_utc()
    anterior, p.estado = p.estado, nuevo
    auditar(db, admin, "Gestionó PQRS", "PQRS", p.id, f"{radicado(p)}: {anterior} → {nuevo}" + (" (con respuesta)" if datos.respuesta else ""))
    dueno = db.get(Usuario, p.usuario_id)
    if dueno is not None and dueno.id != admin.id:
        texto = f"Respondieron tu solicitud: {datos.respuesta}" if datos.respuesta else f"Tu solicitud ahora está «{nuevo.lower()}»."
        notificar(db, [dueno], f"{radicado(p)}: {p.asunto}", texto, "#/pqrs", correo=bool(datos.respuesta))
    db.commit()
    db.refresh(p)
    return _vistas(db, [p])[0]
