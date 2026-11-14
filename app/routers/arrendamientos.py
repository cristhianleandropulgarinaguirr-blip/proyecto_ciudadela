# app/routers/arrendamientos.py
# El propietario (Residente) registra a su inquilino, el administrador lo aprueba y el acceso vence con el contrato.
import secrets
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import arrendamientos as reglas
from app.auditoria import auditar
from app.constantes import EstadoArrendamiento, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import Arrendamiento, Rol, Usuario
from app.notificaciones import notificar
from app.schemas.arrendamientos import AprobacionResponse, ArrendamientoCreate, ArrendamientoResponse, Motivo
from app.security import encriptar_password

TAG = "Arrendamientos (Inquilinos)"
router = APIRouter(prefix="/arrendamientos", tags=[TAG])
ADMIN, RESIDENTE, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.INQUILINO
MAX_INQUILINOS = 3            # contratos pendientes + activos por propietario
MAX_ANIOS_CONTRATO = 5
ABIERTOS = (EstadoArrendamiento.PENDIENTE.value, EstadoArrendamiento.ACTIVO.value)


def _hoy() -> date:
    return reglas.ahora_local().date()


def _vista(c: Arrendamiento) -> ArrendamientoResponse:
    restantes = max(0, (c.fecha_fin.date() - _hoy()).days) if c.estado == EstadoArrendamiento.ACTIVO.value else None
    return ArrendamientoResponse(
        id=c.id, estado=c.estado, apartamento=c.apartamento, propietario_id=c.propietario_id, propietario_nombre=c.propietario.nombre_completo,
        inquilino_id=c.inquilino_id, inquilino_nombre=c.inquilino.nombre_completo, inquilino_email=c.inquilino.email,
        fecha_inicio=c.fecha_inicio.date(), fecha_fin=c.fecha_fin.date(), dias_restantes=restantes, motivo_cierre=c.motivo_cierre,
        fecha_creacion=c.fecha_creacion)


def _obtener(db: Session, contrato_id: int) -> Arrendamiento:
    c = db.get(Arrendamiento, contrato_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Arrendamiento no encontrado.")
    return c


@router.post("/", response_model=ArrendamientoResponse, status_code=status.HTTP_201_CREATED, summary="Registrar a mi inquilino",
             description="Roles: **Residente** (propietario) y **Administrador** (indicando `propietario_id`). Crea la cuenta del inquilino **bloqueada** y deja el contrato "
                         f"«Pendiente»: el administrador lo aprueba y recién ahí se entrega la clave temporal. Máximo {MAX_INQUILINOS} contratos abiertos por propietario.",
             responses={400: {"description": "Fechas inválidas, correo repetido o límite de inquilinos"}, 404: {"description": "Propietario no encontrado"}})
def registrar(datos: ArrendamientoCreate, db: Session = Depends(get_db), actor: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    if actor.rol == ADMIN.value:
        if datos.propietario_id is None:
            raise HTTPException(status_code=400, detail="Indica el propietario (propietario_id) al que pertenece el contrato.")
        propietario = db.get(Usuario, datos.propietario_id)
        if propietario is None or propietario.rol != RESIDENTE.value or not propietario.esta_activo:
            raise HTTPException(status_code=404, detail="Propietario no encontrado.")
    else:
        propietario = actor
    if not (propietario.apartamento or "").strip():
        raise HTTPException(status_code=400, detail="El propietario no tiene apartamento registrado. Pídele a la administración que lo asigne.")
    if datos.fecha_fin <= datos.fecha_inicio:
        raise HTTPException(status_code=400, detail="La fecha de fin debe ser posterior a la de inicio.")
    if datos.fecha_fin < _hoy():
        raise HTTPException(status_code=400, detail="La fecha de fin ya pasó.")
    if (datos.fecha_fin - datos.fecha_inicio).days > 365 * MAX_ANIOS_CONTRATO:
        raise HTTPException(status_code=400, detail=f"El contrato no puede durar más de {MAX_ANIOS_CONTRATO} años.")
    abiertos = db.query(func.count(Arrendamiento.id)).filter(Arrendamiento.propietario_id == propietario.id, Arrendamiento.estado.in_(ABIERTOS)).scalar()
    if abiertos >= MAX_INQUILINOS:
        raise HTTPException(status_code=400, detail=f"Ya hay {MAX_INQUILINOS} inquilinos registrados en este apartamento. Cierra un contrato para agregar otro.")
    if db.query(Usuario).filter(Usuario.email == datos.email).first():
        raise HTTPException(status_code=400, detail="El correo electrónico ya se encuentra registrado.")
    rol = db.query(Rol).filter(Rol.nombre == INQUILINO.value).first()
    if rol is None:
        raise HTTPException(status_code=500, detail="Roles sin configurar. Ejecuta: alembic upgrade head")

    inquilino = Usuario(nombre_completo=" ".join(datos.nombre_completo.split()), email=datos.email, rol_id=rol.id, apartamento=propietario.apartamento,
                        password_encriptada=encriptar_password(secrets.token_urlsafe(24)),      # nadie la conoce: la clave real se genera al aprobar
                        esta_activo=False, debe_cambiar_password=True)
    db.add(inquilino)
    db.flush()
    contrato = Arrendamiento(propietario_id=propietario.id, inquilino_id=inquilino.id, apartamento=propietario.apartamento,
                             fecha_inicio=datetime.combine(datos.fecha_inicio, time.min), fecha_fin=datetime.combine(datos.fecha_fin, time(23, 59, 59)),
                             estado=EstadoArrendamiento.PENDIENTE.value)
    db.add(contrato)
    db.flush()
    auditar(db, actor, "Registró arrendamiento", "Arrendamiento", contrato.id,
            f"{inquilino.nombre_completo} en {contrato.apartamento} (propietario: {propietario.nombre_completo})")
    notificar(db, reglas.administradores(db), f"Arrendamiento por aprobar: {inquilino.nombre_completo}",
              f"{contrato.apartamento} · propietario {propietario.nombre_completo}.", "#/inquilinos")
    db.commit()
    db.refresh(contrato)
    return _vista(contrato)


@router.get("/", response_model=list[ArrendamientoResponse], summary="Ver arrendamientos",
            description="Roles: **Residente** y **Administrador**. El propietario ve los de su apartamento; el administrador ve todos y puede filtrar por `estado`. "
                        "Al consultar se cierran los contratos que ya vencieron.")
def listar(estado: EstadoArrendamiento | None = Query(None), db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    if reglas.vencer_contratos(db):
        db.commit()
    q = db.query(Arrendamiento)
    if usuario.rol != ADMIN.value:
        q = q.filter(Arrendamiento.propietario_id == usuario.id)
    if estado:
        q = q.filter(Arrendamiento.estado == estado.value)
    return [_vista(c) for c in q.order_by(Arrendamiento.id.desc()).limit(200).all()]


@router.get("/mio", response_model=ArrendamientoResponse, summary="Ver mi contrato de arrendamiento",
            description="Rol: **Inquilino**. Su contrato vigente: de quién es el apartamento y hasta cuándo tiene acceso.",
            responses={404: {"description": "No tiene un contrato vigente"}})
def mi_contrato(db: Session = Depends(get_db), inquilino: Usuario = Depends(requiere_roles(INQUILINO))):
    c = reglas.contrato_activo(db, inquilino.id)
    if c is None:
        raise HTTPException(status_code=404, detail="No tienes un contrato vigente.")
    return _vista(c)


@router.post("/{contrato_id}/aprobar", response_model=AprobacionResponse, summary="Aprobar un arrendamiento",
             description="Solo **Administrador**. Activa la cuenta del inquilino y genera una clave temporal que se muestra **una sola vez**; "
                         "la persona deberá cambiarla al ingresar. Se avisa al propietario.",
             responses={400: {"description": "El contrato no está pendiente o ya venció"}, 404: {"description": "Arrendamiento no encontrado"}})
def aprobar(contrato_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    c = _obtener(db, contrato_id)
    if c.estado != EstadoArrendamiento.PENDIENTE.value:
        raise HTTPException(status_code=400, detail=f"Este arrendamiento ya está «{c.estado.lower()}».")
    if c.fecha_fin < reglas.ahora_local():
        raise HTTPException(status_code=400, detail="La fecha de fin del contrato ya pasó. Pídele al propietario que registre uno nuevo.")
    temporal = secrets.token_urlsafe(9)
    c.inquilino.password_encriptada = encriptar_password(temporal)
    c.inquilino.debe_cambiar_password, c.inquilino.esta_activo = True, True
    c.estado, c.aprobado_por, c.fecha_decision = EstadoArrendamiento.ACTIVO.value, admin.id, reglas.ahora_local()
    auditar(db, admin, "Aprobó arrendamiento", "Arrendamiento", c.id, f"{c.inquilino.nombre_completo} · {c.apartamento}")
    notificar(db, [c.propietario], f"Tu inquilino fue aprobado: {c.inquilino.nombre_completo}",
              "Ya puede ingresar a la aplicación con la clave temporal que le entregue la administración.", "#/inquilinos")
    db.commit()
    db.refresh(c)
    return AprobacionResponse(arrendamiento=_vista(c), password_temporal=temporal,
                              mensaje=f"Entrégale esta clave a {c.inquilino.nombre_completo} ({c.inquilino.email}). Deberá cambiarla al ingresar.")


@router.post("/{contrato_id}/rechazar", response_model=ArrendamientoResponse, summary="Rechazar un arrendamiento",
             description="Solo **Administrador**. La cuenta del inquilino queda bloqueada y se avisa al propietario.",
             responses={400: {"description": "El contrato no está pendiente"}, 404: {"description": "Arrendamiento no encontrado"}})
def rechazar(contrato_id: int, datos: Motivo | None = None, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    c = _obtener(db, contrato_id)
    if c.estado != EstadoArrendamiento.PENDIENTE.value:
        raise HTTPException(status_code=400, detail=f"Este arrendamiento ya está «{c.estado.lower()}».")
    motivo = (datos.motivo if datos and datos.motivo else "").strip() or "Sin motivo indicado"
    reglas.finalizar(db, c, motivo, admin, EstadoArrendamiento.RECHAZADO)
    notificar(db, [c.propietario], f"No se aprobó el arrendamiento de {c.inquilino.nombre_completo}", motivo, "#/inquilinos")
    db.commit()
    db.refresh(c)
    return _vista(c)


@router.post("/{contrato_id}/finalizar", response_model=ArrendamientoResponse, summary="Terminar un arrendamiento",
             description="El **propietario** del contrato o el **Administrador**. Cierra el acceso del inquilino al instante: desactiva su cuenta, cierra sus sesiones, "
                         "revoca sus pases QR y retira a sus visitantes autorizados. Si aún estaba pendiente, queda cancelado.",
             responses={400: {"description": "El contrato ya está cerrado"}, 403: {"description": "No es tu contrato"}, 404: {"description": "Arrendamiento no encontrado"}})
def finalizar(contrato_id: int, datos: Motivo | None = None, db: Session = Depends(get_db), actor: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    c = _obtener(db, contrato_id)
    if actor.rol != ADMIN.value and c.propietario_id != actor.id:
        raise HTTPException(status_code=403, detail="Solo puedes cerrar los contratos de tu apartamento.")
    if c.estado not in ABIERTOS:
        raise HTTPException(status_code=400, detail=f"Este arrendamiento ya está «{c.estado.lower()}».")
    quien = "el administrador" if actor.rol == ADMIN.value else "el propietario"
    motivo = (datos.motivo if datos and datos.motivo else "").strip() or f"Cerrado por {quien}"
    pendiente = c.estado == EstadoArrendamiento.PENDIENTE.value
    reglas.finalizar(db, c, motivo, actor, EstadoArrendamiento.RECHAZADO if pendiente else EstadoArrendamiento.FINALIZADO)
    db.commit()
    db.refresh(c)
    return _vista(c)
