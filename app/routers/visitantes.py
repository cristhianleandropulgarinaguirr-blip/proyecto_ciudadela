# app/routers/visitantes.py
# Bloque 2 · Visitantes autorizados: el residente deja registradas a las personas que entran con frecuencia
# (familia, empleada, cuidador...). El guardia las busca por nombre o documento, ve quién las autoriza y registra
# su ingreso y salida a pie. Es distinto del pase QR (/qr/visitantes), que es de un solo uso y con vehículo.
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, aliased

from app.auditoria import auditar
from app.constantes import MAX_VISITAS_INQUILINO, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import AccesoVisitante, Usuario, VisitanteAutorizado, ahora_utc
from app.schemas.negocio import MensajeResponse
from app.schemas.operacion import (
    AccesoVisitanteItem, VisitanteAutorizadoCreate, VisitanteAutorizadoResponse, VisitanteAutorizadoUpdate,
)

TAG = "Visitantes Autorizados"
router = APIRouter(prefix="/visitantes-autorizados", tags=[TAG])

ADMIN, RESIDENTE, GUARDIA = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA
INQUILINO = RolNombre.INQUILINO
MAX_AUTORIZADOS = 20                              # por residente: evita que la lista se vuelva una puerta abierta
HORA_COLOMBIA = timezone(timedelta(hours=-5))     # Colombia no tiene horario de verano


def _hoy() -> date:
    return datetime.now(HORA_COLOMBIA).date()


def _vigente(v: VisitanteAutorizado) -> bool:
    """La fecha «vigente hasta» incluye el día completo."""
    return v.vigente_hasta is None or v.vigente_hasta.date() >= _hoy()


def _vistas(db: Session, lista: list[VisitanteAutorizado]) -> list[VisitanteAutorizadoResponse]:
    if not lista:
        return []
    ids = [v.id for v in lista]
    anfitriones = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({v.usuario_id for v in lista})).all()}
    abiertos, ultimos = {}, {}
    for a in db.query(AccesoVisitante).filter(AccesoVisitante.visitante_id.in_(ids)).order_by(AccesoVisitante.id.desc()).all():
        ultimos.setdefault(a.visitante_id, a.fecha_ingreso)
        if a.fecha_salida is None:
            abiertos.setdefault(a.visitante_id, a.id)
    salida = []
    for v in lista:
        u = anfitriones.get(v.usuario_id)
        salida.append(VisitanteAutorizadoResponse(
            id=v.id, usuario_id=v.usuario_id, anfitrion_nombre=u.nombre_completo if u else "Residente",
            apartamento=u.apartamento if u else None, nombre=v.nombre, documento=v.documento, tipo=v.tipo,
            vigente_hasta=v.vigente_hasta.date() if v.vigente_hasta else None, vigente=_vigente(v), notas=v.notas,
            dentro=v.id in abiertos, acceso_id=abiertos.get(v.id), ultimo_ingreso=ultimos.get(v.id),
            fecha_creacion=v.fecha_creacion))
    return salida


def _fin_del_dia(d: Optional[date]) -> Optional[datetime]:
    return datetime.combine(d, time(23, 59, 59)) if d else None


def _validar_fecha(d: Optional[date]) -> None:
    if d is not None and d < _hoy():
        raise HTTPException(status_code=422, detail="La fecha «vigente hasta» no puede ser anterior a hoy.")


def _obtener_propio(db: Session, visitante_id: int, usuario: Usuario) -> VisitanteAutorizado:
    v = db.get(VisitanteAutorizado, visitante_id)
    if v is None or not v.activo:
        raise HTTPException(status_code=404, detail="Visitante no encontrado.")
    if v.usuario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Este visitante no lo autorizaste tú.")
    return v


# ---------------------------------------------------------------- RESIDENTE
@router.post("/", response_model=VisitanteAutorizadoResponse, status_code=status.HTTP_201_CREATED,
             summary="Autorizar a un visitante frecuente",
             description="Roles: **Residente**, **Inquilino**, **Administrador**. Máximo 20 personas autorizadas por usuario (5 para el inquilino). "
                         "Si autorizaste antes a esa persona y la retiraste, se reactiva con los datos nuevos.",
             responses={400: {"description": "Ya está autorizada o llegaste al límite"}, 422: {"description": "Datos inválidos"}})
def autorizar(datos: VisitanteAutorizadoCreate, db: Session = Depends(get_db),
              usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    _validar_fecha(datos.vigente_hasta)
    # Solo cuentan las autorizaciones vigentes: las visitas de un día que ya pasaron no ocupan cupo.
    activos = db.query(func.count(VisitanteAutorizado.id)).filter(
        VisitanteAutorizado.usuario_id == usuario.id, VisitanteAutorizado.activo.is_(True),
        or_(VisitanteAutorizado.vigente_hasta.is_(None), VisitanteAutorizado.vigente_hasta >= datetime.combine(_hoy(), time.min))).scalar()
    previo = db.query(VisitanteAutorizado).filter(VisitanteAutorizado.usuario_id == usuario.id,
                                                  VisitanteAutorizado.documento == datos.documento).first()
    if previo is not None and previo.activo and _vigente(previo):
        raise HTTPException(status_code=400, detail=f"Ya tienes autorizada a {previo.nombre} con ese documento.")
    # (una autorización vencida se renueva sobre el mismo registro: no pide cupo nuevo)
    tope = MAX_VISITAS_INQUILINO if usuario.rol == INQUILINO.value else MAX_AUTORIZADOS
    if activos >= tope and not (previo is not None and previo.activo):
        raise HTTPException(status_code=400, detail=f"Ya tienes {tope} personas autorizadas. Retira alguna para agregar otra.")
    if previo is None:
        previo = VisitanteAutorizado(usuario_id=usuario.id, documento=datos.documento)
        db.add(previo)
    previo.nombre, previo.tipo, previo.notas = datos.nombre, datos.tipo.value, datos.notas
    previo.vigente_hasta, previo.activo = _fin_del_dia(datos.vigente_hasta), True
    db.flush()
    auditar(db, usuario, "Autorizó visitante", "Visitante", previo.id,
            f"{previo.nombre} ({previo.tipo}) para {usuario.apartamento or usuario.nombre_completo}")
    db.commit()
    db.refresh(previo)
    return _vistas(db, [previo])[0]


@router.get("/", response_model=list[VisitanteAutorizadoResponse], summary="Ver mis visitantes autorizados",
            description="Roles: **Residente**, **Administrador**. El administrador ve los de todos con `todos=true`.")
def mis_visitantes(todos: bool = Query(False), db: Session = Depends(get_db),
                   usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    q = db.query(VisitanteAutorizado).filter(VisitanteAutorizado.activo.is_(True))
    if not (todos and usuario.rol == ADMIN.value):
        q = q.filter(VisitanteAutorizado.usuario_id == usuario.id)
    return _vistas(db, q.order_by(VisitanteAutorizado.nombre).limit(300).all())


@router.patch("/{visitante_id}", response_model=VisitanteAutorizadoResponse, summary="Editar un visitante autorizado",
              description="Quien lo autorizó o el **Administrador**. Solo se cambia lo que se envíe (el documento no se edita).",
              responses={403: {"description": "No lo autorizaste tú"}, 404: {"description": "Visitante no encontrado"}})
def editar(visitante_id: int, datos: VisitanteAutorizadoUpdate, db: Session = Depends(get_db),
           usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    v = _obtener_propio(db, visitante_id, usuario)
    cambios = datos.model_dump(exclude_unset=True)
    if "vigente_hasta" in cambios:
        _validar_fecha(cambios["vigente_hasta"])
        v.vigente_hasta = _fin_del_dia(cambios["vigente_hasta"])
    if cambios.get("nombre"):
        v.nombre = cambios["nombre"]
    if cambios.get("tipo"):
        v.tipo = cambios["tipo"].value
    if "notas" in cambios:
        v.notas = " ".join((cambios["notas"] or "").split()) or None
    auditar(db, usuario, "Editó visitante autorizado", "Visitante", v.id, f"{v.nombre} (campos: {', '.join(cambios) or 'ninguno'})")
    db.commit()
    db.refresh(v)
    return _vistas(db, [v])[0]


@router.delete("/{visitante_id}", response_model=MensajeResponse, summary="Retirar la autorización",
               description="Quien lo autorizó o el **Administrador**. La persona deja de poder ingresar, pero su historial de ingresos se conserva.",
               responses={403: {"description": "No lo autorizaste tú"}, 404: {"description": "Visitante no encontrado"}})
def retirar(visitante_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    v = _obtener_propio(db, visitante_id, usuario)
    v.activo = False
    auditar(db, usuario, "Retiró visitante autorizado", "Visitante", v.id, v.nombre)
    db.commit()
    return {"mensaje": "Autorización retirada."}


# ---------------------------------------------------------------- PORTERÍA
@router.get("/buscar", response_model=list[VisitanteAutorizadoResponse], summary="Buscar un visitante en portería",
            description="Roles: **Guardia**, **Administrador**. Busca por nombre o documento (mínimo 3 caracteres) entre las personas autorizadas. "
                        "Si no aparece, no está autorizada. Indica si la autorización venció (`vigente`) o si ya está dentro (`dentro`).")
def buscar(q: str = Query(..., min_length=3, max_length=40), db: Session = Depends(get_db),
           _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    limpio = "".join(c for c in q if c.isalnum()).upper()
    filtros = [VisitanteAutorizado.nombre.icontains(q.strip(), autoescape=True)]
    if len(limpio) >= 3:
        filtros.append(VisitanteAutorizado.documento.contains(limpio, autoescape=True))
    lista = (db.query(VisitanteAutorizado).join(Usuario, Usuario.id == VisitanteAutorizado.usuario_id)
             .filter(VisitanteAutorizado.activo.is_(True), Usuario.esta_activo.is_(True), or_(*filtros))
             .order_by(VisitanteAutorizado.nombre).limit(15).all())
    return _vistas(db, lista)


def ingresar_visitante(db: Session, personal: Usuario, visitante_id: int, cuando: Optional[datetime] = None) -> tuple[VisitanteAutorizado, AccesoVisitante]:
    """Lógica de ingreso (sin commit), reutilizada por la sincronización de portería sin internet."""
    v = db.get(VisitanteAutorizado, visitante_id)
    if v is None or not v.activo:
        raise HTTPException(status_code=404, detail="Visitante no encontrado o sin autorización.")
    anfitrion = db.get(Usuario, v.usuario_id)
    if anfitrion is None or not anfitrion.esta_activo:
        raise HTTPException(status_code=400, detail="Quien autorizó a esta persona está desactivado.")
    if not _vigente(v):
        raise HTTPException(status_code=400, detail=f"La autorización de {v.nombre} venció. Pide al residente que la renueve.")
    if db.query(AccesoVisitante).filter(AccesoVisitante.visitante_id == v.id, AccesoVisitante.fecha_salida.is_(None)).first():
        raise HTTPException(status_code=400, detail=f"{v.nombre} ya figura dentro del conjunto.")
    acceso = AccesoVisitante(visitante_id=v.id, ingreso_registrado_por=personal.id)
    if cuando is not None:
        acceso.fecha_ingreso = cuando
    db.add(acceso)
    db.flush()
    return v, acceso


def sacar_visitante(db: Session, personal: Usuario, acceso: Optional[AccesoVisitante], cuando: Optional[datetime] = None) -> AccesoVisitante:
    if acceso is None:
        raise HTTPException(status_code=404, detail="Registro de ingreso no encontrado.")
    if acceso.fecha_salida is not None:
        raise HTTPException(status_code=400, detail="La salida de esta persona ya estaba registrada.")
    acceso.fecha_salida, acceso.salida_registrada_por = cuando or ahora_utc(), personal.id
    return acceso


@router.post("/{visitante_id}/ingreso", response_model=VisitanteAutorizadoResponse, summary="Registrar el ingreso de un visitante",
             description="Roles: **Guardia**, **Administrador**. Se rechaza si la autorización venció, si quien la dio está desactivado o si la persona ya figura dentro.",
             responses={400: {"description": "No puede ingresar"}, 404: {"description": "Visitante no encontrado"}})
def registrar_ingreso(visitante_id: int, db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    v, _ = ingresar_visitante(db, personal, visitante_id)
    db.commit()
    return _vistas(db, [v])[0]


def _items_acceso(db: Session, *condiciones, orden=None, limite: Optional[int] = None) -> list[AccesoVisitanteItem]:
    anfitrion, g_in, g_out = aliased(Usuario), aliased(Usuario), aliased(Usuario)
    q = (db.query(AccesoVisitante, VisitanteAutorizado, anfitrion, g_in.nombre_completo, g_out.nombre_completo)
         .join(VisitanteAutorizado, VisitanteAutorizado.id == AccesoVisitante.visitante_id)
         .join(anfitrion, anfitrion.id == VisitanteAutorizado.usuario_id)
         .outerjoin(g_in, g_in.id == AccesoVisitante.ingreso_registrado_por)
         .outerjoin(g_out, g_out.id == AccesoVisitante.salida_registrada_por)
         .filter(*condiciones).order_by(orden if orden is not None else AccesoVisitante.id))
    filas = (q.limit(limite) if limite else q).all()
    return [AccesoVisitanteItem(id=a.id, visitante_id=v.id, nombre=v.nombre, documento=v.documento, tipo=v.tipo,
                                anfitrion_nombre=h.nombre_completo, apartamento=h.apartamento, fecha_ingreso=a.fecha_ingreso,
                                fecha_salida=a.fecha_salida, ingreso_registrado_por=gi, salida_registrada_por=go)
            for a, v, h, gi, go in filas]


@router.patch("/accesos/{acceso_id}/salida", response_model=AccesoVisitanteItem, summary="Registrar la salida de un visitante",
              description="Roles: **Guardia**, **Administrador**.",
              responses={400: {"description": "La salida ya estaba registrada"}, 404: {"description": "Registro no encontrado"}})
def registrar_salida(acceso_id: int, db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    a = sacar_visitante(db, personal, db.get(AccesoVisitante, acceso_id))
    db.commit()
    return _items_acceso(db, AccesoVisitante.id == a.id)[0]


@router.get("/dentro", response_model=list[AccesoVisitanteItem], summary="Visitantes a pie que están dentro",
            description="Roles: **Guardia**, **Administrador**. Quienes ingresaron y aún no tienen salida registrada.")
def dentro(db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    return _items_acceso(db, AccesoVisitante.fecha_salida.is_(None), orden=AccesoVisitante.fecha_ingreso)


@router.get("/accesos", response_model=list[AccesoVisitanteItem], summary="Historial de ingresos de visitantes a pie",
            description="Roles: **Guardia**, **Administrador**. Los últimos ingresos y salidas con el guardia que los registró.")
def historial(limite: int = Query(30, ge=1, le=200), db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    return _items_acceso(db, orden=AccesoVisitante.id.desc(), limite=limite)


class VisitanteSnapshot(BaseModel):
    id: int
    nombre: str
    documento: Optional[str] = None
    tipo: Optional[str] = None
    anfitrion_nombre: str
    apartamento: Optional[str] = None
    vigente_hasta: Optional[datetime] = None
    notas: Optional[str] = None
    dentro: bool = False
    acceso_id: Optional[int] = None


@router.get("/sincronizacion", response_model=list[VisitanteSnapshot], summary="Lista liviana de visitantes vigentes (portería sin internet)",
            description="Roles: **Guardia**, **Administrador**. La app la guarda en el equipo de portería para poder buscar y registrar visitantes aunque se caiga "
                        "el internet. Solo incluye autorizaciones activas y vigentes, y se borra del equipo al cerrar sesión.")
def instantanea(db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    abiertos = dict((vid, aid) for vid, aid in db.query(AccesoVisitante.visitante_id, AccesoVisitante.id).filter(AccesoVisitante.fecha_salida.is_(None)).all())
    filas = (db.query(VisitanteAutorizado, Usuario.nombre_completo, Usuario.apartamento)
             .join(Usuario, Usuario.id == VisitanteAutorizado.usuario_id)
             .filter(VisitanteAutorizado.activo.is_(True), Usuario.esta_activo.is_(True)).order_by(VisitanteAutorizado.nombre).limit(3000).all())
    return [VisitanteSnapshot(id=v.id, nombre=v.nombre, documento=v.documento, tipo=getattr(v, "tipo", None), anfitrion_nombre=nom, apartamento=apto,
                              vigente_hasta=v.vigente_hasta, notas=v.notas, dentro=v.id in abiertos, acceso_id=abiertos.get(v.id))
            for v, nom, apto in filas if _vigente(v)]
