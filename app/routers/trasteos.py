# app/routers/trasteos.py
# Flujo de trasteos (mudanzas): SOLICITUD (residente o inquilino) → VALIDACIÓN de paz y salvo → APROBACIÓN (administrador) →
# ALERTA a la portería → INICIO y FIN registrados por el guardia.
# Regla legal/operativa: una SALIDA de muebles solo se aprueba y se inicia si el apartamento tiene paz y salvo VIGENTE. Se vuelve a comprobar en
# cada paso (solicitud, aprobación e inicio en portería) porque la cartera puede cambiar entre un paso y otro.
import secrets
from datetime import timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import arrendamientos as reglas_arr, config
from app.auditoria import auditar
from app.constantes import (EstadoTrasteo, HORAS_ANTES_PERMITIDAS, MAX_TRASTEOS_ACTIVOS, RolNombre, TipoTrasteo)
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import PazSalvo, Trasteo, Usuario, ahora_utc
from app.notificaciones import notificar, usuarios_activos
from app.routers.paz_y_salvo import estado_de, folio
from app.schemas.trasteos import AprobarIn, MotivoIn, TrasteoCreate, TrasteoResponse

TAG = "Trasteos"
router = APIRouter(prefix="/trasteos", tags=[TAG])
ADMIN, RESIDENTE, GUARDIA, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA, RolNombre.INQUILINO
ABIERTOS = (EstadoTrasteo.PENDIENTE.value, EstadoTrasteo.APROBADO.value, EstadoTrasteo.EN_CURSO.value)
HORA_COLOMBIA = timezone(timedelta(hours=-5))


def _cuando(t: Trasteo) -> str:
    """«sáb 21/11 · 8:00 a. m.–12:00 m.» en hora de Colombia, para los avisos."""
    a, b = (d.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA) for d in (t.fecha_inicio, t.fecha_fin))
    return f"{a:%d/%m/%Y} de {a:%H:%M} a {b:%H:%M}"


def _estado(t: Trasteo) -> str:
    """Pendiente/Aprobado que ya pasó de fecha sin iniciarse se muestra como «Vencido» (no se guarda)."""
    if t.estado in (EstadoTrasteo.PENDIENTE.value, EstadoTrasteo.APROBADO.value) and t.fecha_fin < ahora_utc():
        return "Vencido"
    return t.estado


def _paz_vigente(db: Session, titular: Usuario) -> Optional[PazSalvo]:
    """El paz y salvo vigente más reciente del apartamento (no revocado, no vencido y con la cartera al día), o None."""
    for p in db.query(PazSalvo).filter(PazSalvo.usuario_id == titular.id, PazSalvo.revocado.is_(False), PazSalvo.valido_hasta > ahora_utc()).order_by(PazSalvo.id.desc()).limit(5).all():
        if estado_de(p, titular) == "Vigente":
            return p
    return None


def _sin_deuda(titular: Usuario) -> bool:
    return bool(titular.esta_activo and titular.esta_al_dia and (titular.saldo_pendiente or 0) <= 0)


def _titular(db: Session, t: Trasteo) -> Usuario:
    return db.get(Usuario, t.titular_id)


def _simultaneo(db: Session, t: Trasteo) -> Optional[Trasteo]:
    return (db.query(Trasteo).filter(Trasteo.id != t.id, Trasteo.estado.in_((EstadoTrasteo.APROBADO.value, EstadoTrasteo.EN_CURSO.value)),
                                     Trasteo.fecha_inicio < t.fecha_fin, Trasteo.fecha_fin > t.fecha_inicio).first())


def _motivo_no_inicia(db: Session, t: Trasteo, titular: Usuario) -> Optional[str]:
    """Por qué la portería NO puede registrar el inicio ahora (None = puede)."""
    if t.estado != EstadoTrasteo.APROBADO.value:
        return "Solo se inicia un trasteo aprobado."
    ahora = ahora_utc()
    if ahora < t.fecha_inicio - timedelta(hours=HORAS_ANTES_PERMITIDAS):
        return "Todavía no es la hora acordada."
    if ahora > t.fecha_fin:
        return "La ventana del trasteo ya terminó. Pide una nueva solicitud."
    if t.tipo == TipoTrasteo.SALIDA.value:
        if t.paz_salvo_id is None or _paz_vigente(db, titular) is None:
            return "El apartamento ya no tiene paz y salvo vigente. No dejes salir el trasteo y avisa a la administración."
    return None


def _vista(db: Session, t: Trasteo, nombres: dict[int, Usuario], con_simultaneo: bool = False) -> TrasteoResponse:
    titular = nombres.get(t.titular_id) or _titular(db, t)
    paz = db.get(PazSalvo, t.paz_salvo_id) if t.paz_salvo_id else None
    motivo_no = _motivo_no_inicia(db, t, titular)
    otro = _simultaneo(db, t) if con_simultaneo and t.estado == EstadoTrasteo.PENDIENTE.value else None
    return TrasteoResponse(
        id=t.id, tipo=t.tipo, estado=_estado(t), apartamento=t.apartamento, solicitante=(nombres.get(t.solicitante_id) or db.get(Usuario, t.solicitante_id)).nombre_completo,
        titular=titular.nombre_completo, fecha_inicio=t.fecha_inicio, fecha_fin=t.fecha_fin, empresa=t.empresa, placa=t.placa, observaciones=t.observaciones,
        paz_salvo_folio=folio(paz) if paz else None, paz_salvo_estado=estado_de(paz, titular) if paz else None, motivo=t.motivo,
        inicio_real=t.inicio_real, fin_real=t.fin_real, puede_iniciar=motivo_no is None, motivo_no_puede_iniciar=motivo_no if t.estado == EstadoTrasteo.APROBADO.value else None,
        simultaneo_con=(otro.apartamento or "otro apartamento") if otro else None)


def _vistas(db: Session, filas: list[Trasteo], con_simultaneo: bool = False) -> list[TrasteoResponse]:
    ids = {x for t in filas for x in (t.titular_id, t.solicitante_id)}
    nombres = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_(ids or {0})).all()}
    return [_vista(db, t, nombres, con_simultaneo) for t in filas]


def _obtener(db: Session, trasteo_id: int) -> Trasteo:
    t = db.get(Trasteo, trasteo_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Trasteo no encontrado.")
    return t


def _guardias(db: Session) -> list[Usuario]:
    return usuarios_activos(db, [GUARDIA])


def _de_mi_apartamento(db: Session, actual: Usuario, t: Trasteo) -> bool:
    return actual.rol == ADMIN.value or t.titular_id == reglas_arr.titular_de(db, actual).id or t.solicitante_id == actual.id


# ---------------------------------------------------------------- solicitud
@router.post("", response_model=TrasteoResponse, status_code=status.HTTP_201_CREATED, summary="Solicitar un trasteo",
             description="Roles: **Residente** e **Inquilino**. `tipo`: **Entrada** (llegan muebles) o **Salida** (salen muebles). Una **Salida** exige que el apartamento esté al día: "
                         "se enlaza (o se genera) su **paz y salvo** y, si hay saldo pendiente, se rechaza la solicitud. Máximo 2 solicitudes abiertas por apartamento. "
                         "Queda **Pendiente** hasta que el administrador la apruebe.",
             responses={400: {"description": "Saldo pendiente (Salida) o datos inválidos"}, 429: {"description": "Demasiadas solicitudes abiertas"}})
def solicitar(datos: TrasteoCreate, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO))):
    titular = reglas_arr.titular_de(db, actual)
    if not (titular.apartamento or actual.apartamento):
        raise HTTPException(status_code=400, detail="Tu usuario no tiene apartamento asignado. Pídele a la administración que lo registre.")
    abiertas = db.query(func.count(Trasteo.id)).filter(Trasteo.titular_id == titular.id, Trasteo.estado.in_(ABIERTOS), Trasteo.fecha_fin >= ahora_utc()).scalar()
    if abiertas >= MAX_TRASTEOS_ACTIVOS:
        raise HTTPException(status_code=429, detail=f"Ya tienes {abiertas} solicitudes de trasteo abiertas. Cancela una o espera a que se complete.")
    paz = None
    if datos.tipo == TipoTrasteo.SALIDA.value:
        if not _sin_deuda(titular):
            raise HTTPException(status_code=400, detail="Para sacar un trasteo el apartamento debe estar al día con la administración (paz y salvo). Hoy registra saldo pendiente: ponte al día y vuelve a solicitarlo.")
        paz = _paz_vigente(db, titular)
        if paz is None:                  # el paz y salvo lo genera el sistema: el inquilino no necesita el permiso de «pagar» solo para mudarse
            paz = PazSalvo(usuario_id=titular.id, codigo=secrets.token_urlsafe(16), destino="Trasteo", emitido_por=actual.id, fecha_emision=ahora_utc(),
                           valido_hasta=ahora_utc() + timedelta(days=config.PAZ_Y_SALVO_DIAS))
            db.add(paz)
            db.flush()
    t = Trasteo(solicitante_id=actual.id, titular_id=titular.id, apartamento=titular.apartamento or actual.apartamento, tipo=datos.tipo,
                fecha_inicio=datos.fecha_inicio, fecha_fin=datos.fecha_fin, empresa=datos.empresa, placa=datos.placa, observaciones=datos.observaciones,
                paz_salvo_id=paz.id if paz else None)
    db.add(t)
    db.flush()
    auditar(db, actual, "Solicitó un trasteo", "Trasteo", t.id, f"{t.tipo} · {t.apartamento or 'sin apto'} · {_cuando(t)}" + (f" · paz y salvo {folio(paz)}" if paz else ""))
    notificar(db, reglas_arr.administradores(db), f"Nueva solicitud de trasteo ({t.tipo.lower()})", f"{t.apartamento or actual.nombre_completo} · {_cuando(t)}", "#/trasteos")
    if actual.id != titular.id:
        reglas_arr.avisar_al_propietario(db, actual, "Tu inquilino solicitó un trasteo", f"{t.tipo} · {_cuando(t)}", "#/trasteos")
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]


# ---------------------------------------------------------------- consulta
@router.get("", response_model=list[TrasteoResponse], summary="Ver los trasteos",
            description="**Residente / Inquilino**: los de su apartamento. **Administrador**: todos (filtra con `estado`; los pendientes primero). "
                        "**Guardia**: solo los aprobados o en curso de hoy y los próximos 7 días, con el aviso de si se puede iniciar.")
def listar(estado: Optional[EstadoTrasteo] = Query(None), db: Session = Depends(get_db),
           actual: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, INQUILINO, GUARDIA))):
    q = db.query(Trasteo)
    if actual.rol == GUARDIA.value:
        ahora = ahora_utc()
        q = q.filter(Trasteo.estado.in_((EstadoTrasteo.APROBADO.value, EstadoTrasteo.EN_CURSO.value)), Trasteo.fecha_fin >= ahora - timedelta(hours=12),
                     Trasteo.fecha_inicio <= ahora + timedelta(days=7)).order_by(Trasteo.fecha_inicio)
    elif actual.rol == ADMIN.value:
        if estado:
            q = q.filter(Trasteo.estado == estado.value)
        q = q.order_by((Trasteo.estado != EstadoTrasteo.PENDIENTE.value), Trasteo.fecha_inicio.desc()).limit(150)
    else:
        titular = reglas_arr.titular_de(db, actual)
        q = q.filter(or_(Trasteo.titular_id == titular.id, Trasteo.solicitante_id == actual.id))
        if estado:
            q = q.filter(Trasteo.estado == estado.value)
        q = q.order_by(Trasteo.fecha_inicio.desc()).limit(50)
    return _vistas(db, q.all(), con_simultaneo=actual.rol == ADMIN.value)


# ---------------------------------------------------------------- decisión del administrador
@router.post("/{trasteo_id}/aprobar", response_model=TrasteoResponse, summary="Aprobar un trasteo",
             description="Solo **Administrador**. En una **Salida** vuelve a comprobar el paz y salvo (si el apartamento volvió a deber, no se aprueba). "
                         "Si ya hay otro trasteo aprobado en el mismo horario devuelve 409, salvo que envíes `permitir_simultaneo=true`. "
                         "Al aprobar se **avisa a la portería** (campana y celular) y al solicitante.",
             responses={400: {"description": "Sin paz y salvo vigente o ya no está pendiente"}, 409: {"description": "Hay otro trasteo en el mismo horario"}})
def aprobar(trasteo_id: int, datos: Optional[AprobarIn] = None, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    t = _obtener(db, trasteo_id)
    if _estado(t) != EstadoTrasteo.PENDIENTE.value:
        raise HTTPException(status_code=400, detail="Solo se aprueban las solicitudes pendientes y vigentes.")
    titular = _titular(db, t)
    if t.tipo == TipoTrasteo.SALIDA.value and _paz_vigente(db, titular) is None:
        raise HTTPException(status_code=400, detail="El apartamento no tiene paz y salvo vigente (registra saldo pendiente o el certificado se revocó). No se puede aprobar la salida.")
    otro = _simultaneo(db, t)
    if otro is not None and not (datos and datos.permitir_simultaneo):
        raise HTTPException(status_code=409, detail=f"Ya hay un trasteo aprobado en ese horario ({otro.apartamento or 'otro apartamento'}). Cambia la hora o aprueba de todas formas.")
    t.estado, t.decidido_por, t.fecha_decision = EstadoTrasteo.APROBADO.value, admin.id, ahora_utc()
    auditar(db, admin, "Aprobó un trasteo", "Trasteo", t.id, f"{t.tipo} · {t.apartamento or 'sin apto'} · {_cuando(t)}")
    interesados = {u.id: u for u in (db.get(Usuario, t.solicitante_id), titular)}
    notificar(db, list(interesados.values()), "Tu trasteo fue aprobado", f"{t.tipo} · {_cuando(t)}. Avisamos a la portería.", "#/trasteos")
    notificar(db, _guardias(db), f"Trasteo aprobado: {t.apartamento or 'apartamento'} ({t.tipo.lower()})",
              f"{_cuando(t)}" + (f" · {t.empresa}" if t.empresa else "") + (f" · placa {t.placa}" if t.placa else ""), "#/trasteos")
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]


@router.post("/{trasteo_id}/rechazar", response_model=TrasteoResponse, summary="Rechazar un trasteo",
             description="Solo **Administrador**. Hay que explicar el motivo; se le avisa al solicitante.")
def rechazar(trasteo_id: int, datos: MotivoIn, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    t = _obtener(db, trasteo_id)
    if _estado(t) != EstadoTrasteo.PENDIENTE.value:
        raise HTTPException(status_code=400, detail="Solo se rechazan las solicitudes pendientes.")
    t.estado, t.decidido_por, t.fecha_decision, t.motivo = EstadoTrasteo.RECHAZADO.value, admin.id, ahora_utc(), datos.motivo
    auditar(db, admin, "Rechazó un trasteo", "Trasteo", t.id, f"{t.apartamento or 'sin apto'} · {datos.motivo}")
    notificar(db, [db.get(Usuario, t.solicitante_id), _titular(db, t)] if t.solicitante_id != t.titular_id else [_titular(db, t)],
              "Tu solicitud de trasteo no fue aprobada", datos.motivo, "#/trasteos")
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]


@router.post("/{trasteo_id}/cancelar", response_model=TrasteoResponse, summary="Cancelar un trasteo",
             description="Quien lo solicitó, su propietario o el **Administrador**, mientras esté pendiente o aprobado. Si ya estaba aprobado, se avisa a la portería.")
def cancelar(trasteo_id: int, datos: Optional[MotivoIn] = None, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, INQUILINO))):
    t = _obtener(db, trasteo_id)
    if not _de_mi_apartamento(db, actual, t):
        raise HTTPException(status_code=403, detail="Este trasteo no es de tu apartamento.")
    if t.estado not in (EstadoTrasteo.PENDIENTE.value, EstadoTrasteo.APROBADO.value):
        raise HTTPException(status_code=400, detail="Solo se cancela un trasteo pendiente o aprobado que aún no empieza.")
    estaba_aprobado = t.estado == EstadoTrasteo.APROBADO.value
    t.estado, t.motivo = EstadoTrasteo.CANCELADO.value, (datos.motivo if datos else None)
    auditar(db, actual, "Canceló un trasteo", "Trasteo", t.id, f"{t.apartamento or 'sin apto'} · {_cuando(t)}")
    if estaba_aprobado:
        notificar(db, _guardias(db), f"Trasteo cancelado: {t.apartamento or 'apartamento'}", f"{_cuando(t)}. Ya no debe pasar.", "#/trasteos")
    if actual.rol != ADMIN.value:
        notificar(db, reglas_arr.administradores(db), "Se canceló un trasteo", f"{t.apartamento or actual.nombre_completo} · {_cuando(t)}", "#/trasteos")
    else:
        notificar(db, [db.get(Usuario, t.solicitante_id)], "Tu trasteo fue cancelado por la administración", (datos.motivo if datos else None), "#/trasteos")
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]


# ---------------------------------------------------------------- portería
@router.post("/{trasteo_id}/iniciar", response_model=TrasteoResponse, summary="Registrar el inicio del trasteo en portería",
             description="Roles: **Guardia** y **Administrador**. Solo un trasteo aprobado, dentro de su horario (hasta 2 h antes). En una **Salida** vuelve a comprobar el paz y salvo: "
                         "si ya no está vigente devuelve 409 y el trasteo **no debe salir**.",
             responses={409: {"description": "Todavía no es la hora, ya pasó, o la Salida ya no tiene paz y salvo vigente"}})
def iniciar(trasteo_id: int, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    t = _obtener(db, trasteo_id)
    motivo = _motivo_no_inicia(db, t, _titular(db, t))
    if motivo:
        raise HTTPException(status_code=409, detail=motivo)
    t.estado, t.inicio_real, t.registrado_por = EstadoTrasteo.EN_CURSO.value, ahora_utc(), actual.id
    auditar(db, actual, "Inició un trasteo en portería", "Trasteo", t.id, f"{t.tipo} · {t.apartamento or 'sin apto'}")
    notificar(db, [db.get(Usuario, t.solicitante_id)], "Tu trasteo comenzó", f"Portería registró el {'ingreso' if t.tipo == 'Entrada' else 'retiro'} de tus cosas.", "#/trasteos", avisar_push=False)
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]


@router.post("/{trasteo_id}/finalizar", response_model=TrasteoResponse, summary="Registrar el fin del trasteo",
             description="Roles: **Guardia** y **Administrador**. Solo un trasteo en curso.")
def finalizar(trasteo_id: int, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    t = _obtener(db, trasteo_id)
    if t.estado != EstadoTrasteo.EN_CURSO.value:
        raise HTTPException(status_code=400, detail="Solo se finaliza un trasteo que está en curso.")
    t.estado, t.fin_real = EstadoTrasteo.COMPLETADO.value, ahora_utc()
    auditar(db, actual, "Finalizó un trasteo", "Trasteo", t.id, f"{t.tipo} · {t.apartamento or 'sin apto'}")
    notificar(db, [db.get(Usuario, t.solicitante_id)], "Tu trasteo terminó", "Portería lo registró como completado.", "#/trasteos", avisar_push=False)
    db.commit()
    db.refresh(t)
    return _vistas(db, [t])[0]
