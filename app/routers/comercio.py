# app/routers/comercio.py
# Fase 2: comercio entre vecinos. Un residente que vende algo (comida, servicios...) paga un plan para
# aparecer en el directorio del conjunto. Flujo:
#   Pendiente de pago -> (el dueño informa el comprobante) En revision -> (el administrador confirma) Activa -> Vencida
# El cobro es manual (transferencia + comprobante); más adelante se puede cambiar por una pasarela como Wompi.
import os
from datetime import timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.archivos import borrar_imagen, guardar_imagen_validada, leer_imagen
from app.config import INSTRUCCIONES_PAGO
from app.constantes import CategoriaComercio, EstadoPublicidad, PLANES_PUBLICIDAD, PlanPublicidad, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Publicidad, Usuario, ahora_utc
from app.schemas.comercio import (
    ContactoResponse, InformarPago, PlanesResponse, PlanResponse, PublicidadResponse, Rechazo, Renovacion,
    ResumenComercio, WHATSAPP_REGEX,
)
from app.schemas.negocio import MensajeResponse

TAG = "Comercio y Publicidad"
router = APIRouter(prefix="/comercio", tags=[TAG])
ADMIN, RESIDENTE = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE
E = EstadoPublicidad
MAX_ABIERTOS = 5   # anuncios sin terminar por usuario (evita spam)


def _vencer(db: Session) -> None:
    """Pasa a 'Vencida' lo que ya cumplió su plazo (sin necesidad de tareas programadas)."""
    n = (db.query(Publicidad).filter(Publicidad.estado == E.ACTIVA.value, Publicidad.fecha_fin < ahora_utc())
         .update({"estado": E.VENCIDA.value}, synchronize_session=False))
    if n:
        db.commit()


def _vista(db: Session, anuncios: list[Publicidad]) -> list[PublicidadResponse]:
    duenos = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({a.propietario_id for a in anuncios})).all()} if anuncios else {}
    res = []
    for a in anuncios:
        d = duenos.get(a.propietario_id)
        res.append(PublicidadResponse(
            id=a.id, propietario_id=a.propietario_id, propietario_nombre=d.nombre_completo if d else "Vecino",
            apartamento=d.apartamento if d else None, nombre_negocio=a.nombre_negocio, categoria=a.categoria,
            titulo=a.titulo, descripcion=a.descripcion, precio_texto=a.precio_texto, whatsapp=a.whatsapp,
            tiene_imagen=bool(a.imagen), plan=a.plan, valor=a.valor, estado=a.estado, referencia_pago=a.referencia_pago,
            motivo_rechazo=a.motivo_rechazo, fecha_inicio=a.fecha_inicio, fecha_fin=a.fecha_fin,
            contactos=a.contactos, fecha_creacion=a.fecha_creacion))
    return res


def _obtener(db: Session, anuncio_id: int) -> Publicidad:
    a = db.get(Publicidad, anuncio_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Anuncio no encontrado.")
    return a


def _del_dueno(a: Publicidad, usuario: Usuario) -> None:
    if a.propietario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Este anuncio no es tuyo.")


@router.get("/planes", response_model=PlanesResponse, summary="Ver los planes y cómo pagar",
            description="Roles: **todos**.")
def planes(_: Usuario = Depends(get_current_user)):
    return PlanesResponse(planes=[PlanResponse(plan=p.value, dias=d, valor=v) for p, (d, v) in PLANES_PUBLICIDAD.items()],
                          instrucciones_pago=INSTRUCCIONES_PAGO)


@router.get("/", response_model=list[PublicidadResponse], summary="Directorio comercial del conjunto",
            description="Roles: **todos**. Solo anuncios **Activos** y vigentes. Filtros opcionales: `categoria` y `q` (busca en negocio, título y descripción).")
def directorio(categoria: Optional[CategoriaComercio] = None, q: Optional[str] = Query(None, max_length=60),
               db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    _vencer(db)
    cons = db.query(Publicidad).filter(Publicidad.estado == E.ACTIVA.value)
    if categoria:
        cons = cons.filter(Publicidad.categoria == categoria.value)
    if q and q.strip():
        like = f"%{q.strip()}%"
        cons = cons.filter(Publicidad.nombre_negocio.ilike(like) | Publicidad.titulo.ilike(like) | Publicidad.descripcion.ilike(like))
    return _vista(db, cons.order_by(Publicidad.fecha_inicio.desc()).limit(200).all())


@router.get("/mios", response_model=list[PublicidadResponse], summary="Ver mis anuncios (todos los estados)",
            description="Roles: **Residente**, **Administrador**.")
def mios(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    _vencer(db)
    return _vista(db, db.query(Publicidad).filter(Publicidad.propietario_id == usuario.id).order_by(Publicidad.id.desc()).all())


@router.get("/gestion", response_model=list[PublicidadResponse], summary="Gestionar todos los anuncios",
            description="Rol: **Administrador**. Filtra por `estado`. Los que esperan revisión salen primero.")
def gestion(estado: Optional[EstadoPublicidad] = None, db: Session = Depends(get_db),
            _: Usuario = Depends(requiere_roles(ADMIN))):
    _vencer(db)
    cons = db.query(Publicidad)
    if estado:
        cons = cons.filter(Publicidad.estado == estado.value)
    filas = cons.order_by(Publicidad.id.desc()).limit(300).all()
    filas.sort(key=lambda a: a.estado != E.EN_REVISION.value)   # estable: revisión primero, resto por id desc
    return _vista(db, filas)


@router.get("/resumen", response_model=ResumenComercio, summary="Resumen del negocio de publicidad",
            description="Rol: **Administrador**. Ingresos confirmados = suma del valor de los anuncios que ya se activaron alguna vez.")
def resumen(db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    _vencer(db)
    def cuenta(*estados):
        return db.query(func.count(Publicidad.id)).filter(Publicidad.estado.in_([e.value for e in estados])).scalar() or 0
    cobrados = db.query(func.coalesce(func.sum(Publicidad.valor), 0)).filter(Publicidad.fecha_inicio.isnot(None)).scalar()
    contactos = db.query(func.coalesce(func.sum(Publicidad.contactos), 0)).scalar()
    return ResumenComercio(activas=cuenta(E.ACTIVA), por_revisar=cuenta(E.EN_REVISION), pendientes_pago=cuenta(E.PENDIENTE_PAGO),
                           ingresos_confirmados=int(cobrados), contactos_totales=int(contactos))


@router.post("/", response_model=PublicidadResponse, status_code=status.HTTP_201_CREATED,
             summary="Crear un anuncio (queda pendiente de pago)",
             description="Roles: **Residente**, **Administrador**. Se envía como `multipart/form-data`; la imagen es opcional "
                         "(JPG, PNG o WEBP, máx. 5 MB). El anuncio no se ve hasta que el administrador confirme el pago.",
             responses={400: {"description": "Plan inválido o demasiados anuncios sin terminar"}})
async def crear(nombre_negocio: str = Form(..., min_length=2, max_length=60, examples=["Arepas Doña Rosa"]),
                categoria: CategoriaComercio = Form(...),
                titulo: str = Form(..., min_length=5, max_length=80, examples=["Arepas rellenas, domicilio en el conjunto"]),
                descripcion: str = Form(..., min_length=10, max_length=600),
                whatsapp: str = Form(..., pattern=WHATSAPP_REGEX, description="Celular de 10 dígitos, sin +57", examples=["3001234567"]),
                plan: PlanPublicidad = Form(...),
                precio_texto: Optional[str] = Form(None, max_length=40, examples=["Desde $6.000"]),
                imagen: UploadFile | None = File(default=None),
                db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, ADMIN))):
    abiertos = (db.query(func.count(Publicidad.id)).filter(Publicidad.propietario_id == usuario.id,
                Publicidad.estado.in_([E.PENDIENTE_PAGO.value, E.EN_REVISION.value, E.ACTIVA.value])).scalar())
    if abiertos >= MAX_ABIERTOS:
        raise HTTPException(status_code=400, detail=f"Ya tienes {MAX_ABIERTOS} anuncios en curso. Espera a que venzan o elimina alguno.")
    nombre_img = await guardar_imagen_validada(imagen) if imagen and imagen.filename else None
    _, valor = PLANES_PUBLICIDAD[plan]
    a = Publicidad(propietario_id=usuario.id, nombre_negocio=nombre_negocio.strip(), categoria=categoria.value,
                   titulo=titulo.strip(), descripcion=descripcion.strip(), precio_texto=(precio_texto or "").strip() or None,
                   whatsapp=whatsapp, imagen=nombre_img, plan=plan.value, valor=valor, estado=E.PENDIENTE_PAGO.value)
    db.add(a)
    db.commit()
    db.refresh(a)
    return _vista(db, [a])[0]


@router.post("/{anuncio_id}/informar-pago", response_model=PublicidadResponse, summary="Informar que ya pagué",
             description="Dueño del anuncio. Pasa de *Pendiente de pago* a *En revisión* para que el administrador confirme.",
             responses={400: {"description": "El anuncio no está pendiente de pago"}, 403: {"description": "No es tu anuncio"}})
def informar_pago(anuncio_id: int, datos: InformarPago, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    a = _obtener(db, anuncio_id)
    if a.propietario_id != usuario.id:
        raise HTTPException(status_code=403, detail="Este anuncio no es tuyo.")
    if a.estado != E.PENDIENTE_PAGO.value:
        raise HTTPException(status_code=400, detail="Este anuncio no está pendiente de pago.")
    a.referencia_pago, a.estado, a.motivo_rechazo = datos.referencia, E.EN_REVISION.value, None
    db.commit()
    return _vista(db, [a])[0]


@router.post("/{anuncio_id}/aprobar", response_model=PublicidadResponse, summary="Confirmar el pago y activar el anuncio",
             description="Rol: **Administrador**. Desde *En revisión* o *Pendiente de pago* (pago en efectivo). El plazo empieza a correr ahora.",
             responses={400: {"description": "El anuncio no se puede activar en su estado actual"}})
def aprobar(anuncio_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = _obtener(db, anuncio_id)
    if a.estado not in (E.EN_REVISION.value, E.PENDIENTE_PAGO.value):
        raise HTTPException(status_code=400, detail=f"No se puede activar un anuncio en estado «{a.estado}».")
    dias, _ = PLANES_PUBLICIDAD[PlanPublicidad(a.plan)]
    a.estado, a.fecha_inicio, a.fecha_fin = E.ACTIVA.value, ahora_utc(), ahora_utc() + timedelta(days=dias)
    a.revisado_por, a.motivo_rechazo = admin.id, None
    auditar(db, admin, "Confirmó pago de anuncio", "Comercio", a.id, f"{a.nombre_negocio} · plan {a.plan} · ${a.valor}")
    db.commit()
    return _vista(db, [a])[0]


@router.post("/{anuncio_id}/rechazar", response_model=PublicidadResponse, summary="Rechazar un anuncio",
             description="Rol: **Administrador**. Indica el motivo; el dueño lo verá en *Mis anuncios*.",
             responses={400: {"description": "El anuncio ya está activo o terminado"}})
def rechazar(anuncio_id: int, datos: Rechazo, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = _obtener(db, anuncio_id)
    if a.estado not in (E.EN_REVISION.value, E.PENDIENTE_PAGO.value):
        raise HTTPException(status_code=400, detail=f"No se puede rechazar un anuncio en estado «{a.estado}».")
    a.estado, a.motivo_rechazo, a.revisado_por = E.RECHAZADA.value, datos.motivo.strip(), admin.id
    auditar(db, admin, "Rechazó anuncio", "Comercio", a.id, f"{a.nombre_negocio}: {a.motivo_rechazo}")
    db.commit()
    return _vista(db, [a])[0]


@router.post("/{anuncio_id}/renovar", response_model=PublicidadResponse, summary="Renovar un anuncio vencido o rechazado",
             description="Dueño del anuncio. Vuelve a *Pendiente de pago* con el plan elegido; hay que pagar de nuevo.",
             responses={400: {"description": "Plan inválido o el anuncio sigue vigente"}, 403: {"description": "No es tu anuncio"}})
def renovar(anuncio_id: int, datos: Renovacion, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    a = _obtener(db, anuncio_id)
    _del_dueno(a, usuario)
    _vencer(db); db.refresh(a)
    if a.estado not in (E.VENCIDA.value, E.RECHAZADA.value):
        raise HTTPException(status_code=400, detail="Solo se renuevan anuncios vencidos o rechazados.")
    try:
        plan = PlanPublicidad(datos.plan)
    except ValueError:
        raise HTTPException(status_code=400, detail="Plan inválido. Usa Semanal, Mensual o Trimestral.")
    a.plan, a.valor = plan.value, PLANES_PUBLICIDAD[plan][1]
    a.estado, a.referencia_pago, a.motivo_rechazo, a.fecha_inicio, a.fecha_fin = E.PENDIENTE_PAGO.value, None, None, None, None
    db.commit()
    return _vista(db, [a])[0]


@router.delete("/{anuncio_id}", response_model=MensajeResponse, summary="Eliminar un anuncio",
               description="Dueño (si no está activo) o **Administrador** (cualquiera, para moderar).",
               responses={400: {"description": "Un anuncio activo solo lo elimina el administrador"}, 403: {"description": "No es tu anuncio"}})
def eliminar(anuncio_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    a = _obtener(db, anuncio_id)
    _del_dueno(a, usuario)
    _vencer(db); db.refresh(a)
    if a.estado == E.ACTIVA.value and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=400, detail="Tu anuncio está activo y pagado. Pide al administrador que lo retire.")
    img = a.imagen
    auditar(db, usuario, "Eliminó anuncio comercial", "Comercio", a.id, f"{a.nombre_negocio} (estado {a.estado})")
    db.delete(a)
    db.commit()
    if img:
        borrar_imagen(img)
    return {"mensaje": "Anuncio eliminado."}


@router.post("/{anuncio_id}/contacto", response_model=ContactoResponse, summary="Registrar un contacto y obtener el enlace de WhatsApp",
             description="Roles: **todos**. Suma 1 al contador de contactos (métrica que el dueño ve para saber si su anuncio funciona).",
             responses={400: {"description": "El anuncio no está activo"}})
def contacto(anuncio_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    _vencer(db)
    a = _obtener(db, anuncio_id)
    if a.estado != E.ACTIVA.value:
        raise HTTPException(status_code=400, detail="Este anuncio no está activo.")
    if a.propietario_id != usuario.id:   # los clics del propio dueño no inflan la métrica
        a.contactos = (a.contactos or 0) + 1
        db.commit()
    texto = quote(f"Hola, vi tu anuncio «{a.titulo}» en Ciudadela Digital.")
    return ContactoResponse(whatsapp_url=f"https://wa.me/57{a.whatsapp}?text={texto}")


@router.get("/{anuncio_id}/imagen", summary="Ver la imagen de un anuncio",
            description="Cualquier usuario si el anuncio está activo; si no, solo el dueño o el administrador.",
            responses={404: {"description": "Sin imagen"}, 403: {"description": "Sin permiso"}})
def imagen(anuncio_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    a = _obtener(db, anuncio_id)
    if a.estado != E.ACTIVA.value and a.propietario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver esta imagen.")
    datos = leer_imagen(a.imagen) if a.imagen else None
    if datos is None:
        raise HTTPException(status_code=404, detail="Este anuncio no tiene imagen.")
    return Response(content=datos[0], media_type=datos[1], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})
