# app/routers/paquetes.py
# Bloque 2 · Paquetes y correspondencia: el guardia registra lo que llega a portería, el residente ve en la app
# que tiene algo esperándolo y el guardia registra la entrega (quién lo recogió y cuándo). Todo queda en la auditoría.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.constantes import EstadoPaquete, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Paquete, Rol, Usuario, ahora_utc
from app.notificaciones import notificar
from app.schemas.operacion import DestinatarioResponse, EntregaRequest, PaqueteCreate, PaqueteResponse

TAG = "Paquetes y Correspondencia"
router = APIRouter(prefix="/paquetes", tags=[TAG])

ADMIN, RESIDENTE, GUARDIA = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA


def _vistas(db: Session, paquetes: list[Paquete]) -> list[PaqueteResponse]:
    if not paquetes:
        return []
    ids = {p.destinatario_id for p in paquetes} | {i for p in paquetes for i in (p.recibido_por, p.entregado_por) if i}
    personas = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()}
    nombre = lambda i: personas[i].nombre_completo if i in personas else None   # noqa: E731
    return [PaqueteResponse(id=p.id, destinatario_id=p.destinatario_id, destinatario_nombre=nombre(p.destinatario_id) or "Residente",
                            apartamento=personas[p.destinatario_id].apartamento if p.destinatario_id in personas else None,
                            tipo=p.tipo, remitente=p.remitente, descripcion=p.descripcion, estado=p.estado,
                            fecha_recepcion=p.fecha_recepcion, recibido_por=nombre(p.recibido_por), entregado_a=p.entregado_a,
                            entregado_por=nombre(p.entregado_por), fecha_entrega=p.fecha_entrega) for p in paquetes]


def _en_porteria(db: Session, paquete_id: int) -> Paquete:
    p = db.get(Paquete, paquete_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Paquete no encontrado.")
    if p.estado != EstadoPaquete.EN_PORTERIA.value:
        raise HTTPException(status_code=400, detail=f"Este paquete ya está «{p.estado.lower()}».")
    return p


def _resumen(p: Paquete, destinatario: Optional[Usuario]) -> str:
    quien = f"{destinatario.nombre_completo} ({destinatario.apartamento or 'sin apto.'})" if destinatario else f"usuario #{p.destinatario_id}"
    return f"{p.tipo} para {quien}" + (f" · {p.remitente}" if p.remitente else "")


@router.get("/destinatarios", response_model=list[DestinatarioResponse], summary="Residentes que pueden recibir paquetes",
            description="Roles: **Guardia**, **Administrador**. Solo nombre y apartamento de los residentes activos, para elegir a quién va el paquete. Filtra con `q`.")
def destinatarios(q: Optional[str] = Query(None, max_length=40), db: Session = Depends(get_db),
                  _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    consulta = (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id)
                .filter(Rol.nombre == RESIDENTE.value, Usuario.esta_activo.is_(True)))
    if q and q.strip():
        consulta = consulta.filter(Usuario.nombre_completo.icontains(q.strip(), autoescape=True) | Usuario.apartamento.icontains(q.strip(), autoescape=True))
    return [DestinatarioResponse(id=u.id, nombre_completo=u.nombre_completo, apartamento=u.apartamento)
            for u in consulta.order_by(Usuario.apartamento, Usuario.nombre_completo).limit(300).all()]


@router.post("/", response_model=PaqueteResponse, status_code=status.HTTP_201_CREATED, summary="Registrar un paquete o correspondencia",
             description="Roles: **Guardia**, **Administrador**. Queda «En portería» hasta que se entregue. El destinatario debe ser un residente activo.",
             responses={400: {"description": "Destinatario inválido"}})
def registrar(datos: PaqueteCreate, db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    dest = db.get(Usuario, datos.destinatario_id)
    if dest is None or not dest.esta_activo or dest.rol != RESIDENTE.value:
        raise HTTPException(status_code=400, detail="El destinatario debe ser un residente activo.")
    p = Paquete(destinatario_id=dest.id, tipo=datos.tipo.value, remitente=datos.remitente, descripcion=datos.descripcion,
                estado=EstadoPaquete.EN_PORTERIA.value, recibido_por=personal.id)
    db.add(p)
    db.flush()
    auditar(db, personal, "Registró paquete", "Paquete", p.id, _resumen(p, dest))
    notificar(db, [dest], "Tienes un paquete en portería", f"{p.tipo}" + (f" de {p.remitente}" if p.remitente else "") + ". Pasa a recogerlo cuando puedas.",
              "#/paquetes", correo=True)
    db.commit()
    db.refresh(p)
    return _vistas(db, [p])[0]


@router.get("/", response_model=list[PaqueteResponse], summary="Ver paquetes",
            description="Roles: **todos**. El residente ve solo los suyos; el guardia y el administrador ven todos. Filtra con `estado` (`En porteria`, `Entregado`, `Anulado`).")
def listar(estado: Optional[EstadoPaquete] = Query(None), limite: int = Query(100, ge=1, le=300), db: Session = Depends(get_db),
           usuario: Usuario = Depends(get_current_user)):
    q = db.query(Paquete)
    if usuario.rol == RESIDENTE.value:
        q = q.filter(Paquete.destinatario_id == usuario.id)
    if estado:
        q = q.filter(Paquete.estado == estado.value)
    return _vistas(db, q.order_by(Paquete.id.desc()).limit(limite).all())


@router.patch("/{paquete_id}/entregar", response_model=PaqueteResponse, summary="Registrar la entrega",
              description="Roles: **Guardia**, **Administrador**. Indica quién lo recogió (`entregado_a`); si no se envía, se asume que fue el destinatario.",
              responses={400: {"description": "El paquete ya no está en portería"}, 404: {"description": "Paquete no encontrado"}})
def entregar(paquete_id: int, datos: Optional[EntregaRequest] = None, db: Session = Depends(get_db),
             personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    p = _en_porteria(db, paquete_id)
    dest = db.get(Usuario, p.destinatario_id)
    p.estado, p.fecha_entrega, p.entregado_por = EstadoPaquete.ENTREGADO.value, ahora_utc(), personal.id
    p.entregado_a = (datos.entregado_a if datos else None) or (dest.nombre_completo if dest else None)
    auditar(db, personal, "Entregó paquete", "Paquete", p.id, f"{_resumen(p, dest)} · lo recibió {p.entregado_a}")
    db.commit()
    db.refresh(p)
    return _vistas(db, [p])[0]


@router.patch("/{paquete_id}/anular", response_model=PaqueteResponse, summary="Anular un registro hecho por error",
              description="Roles: **Guardia**, **Administrador**. Solo se anulan paquetes que siguen en portería (ej. apartamento equivocado). Queda en la auditoría.",
              responses={400: {"description": "El paquete ya no está en portería"}, 404: {"description": "Paquete no encontrado"}})
def anular(paquete_id: int, db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    p = _en_porteria(db, paquete_id)
    p.estado = EstadoPaquete.ANULADO.value
    auditar(db, personal, "Anuló paquete", "Paquete", p.id, _resumen(p, db.get(Usuario, p.destinatario_id)))
    db.commit()
    db.refresh(p)
    return _vistas(db, [p])[0]
