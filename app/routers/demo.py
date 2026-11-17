# app/routers/demo.py — V4.0 (Fase 4 · presentación comercial): el botón «Solicitar demo» de la landing.
#
#   · POST /demo/solicitar        SIN sesión. Guarda el contacto y avisa a los administradores (campana + push). Es la única ruta pública que ESCRIBE
#                                 en la base de datos, así que va muy limitada: tope por IP, campo trampa para robots, consentimiento obligatorio,
#                                 y un mismo celular no se duplica en 24 horas.
#   · GET  /demo/solicitudes      solo Administrador: la lista de contactos.
#   · PATCH /demo/solicitudes/id  solo Administrador: marcar como contactada/agendada/descartada y dejar una nota de seguimiento.
# No se guarda la IP ni nada del dispositivo: solo lo que la persona escribió.
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app import limitador
from app.auditoria import auditar
from app.constantes import EstadoDemo, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import SolicitudDemo, Usuario, ahora_utc
from app.notificaciones import notificar, usuarios_activos
from app.schemas.demo import SolicitudDemoCreate, SolicitudDemoResponse, SolicitudDemoRespuesta, SolicitudDemoUpdate

TAG = "Presentación comercial (demo)"
router = APIRouter(prefix="/demo", tags=[TAG])
solo_admin = requiere_roles(RolNombre.ADMINISTRADOR)

MENSAJE_OK = "¡Listo! Recibimos tu solicitud y te contactaremos para agendar la demostración."
VENTANA_DUPLICADO = timedelta(hours=24)
MAX_LISTA = 500


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


@router.post("/solicitar", response_model=SolicitudDemoRespuesta, status_code=201, summary="Solicitar una demostración (sin sesión)",
             description="**Sin sesión.** Lo usa la landing. Guarda el contacto y avisa a los administradores. Límite: 5 envíos por IP cada 10 minutos. "
                         "`acepto_datos` debe ser `true` (Ley 1581 de 2012). `sitio_web` es un campo trampa: debe ir vacío.",
             responses={422: {"description": "Datos inválidos o sin autorización de datos"}, 429: {"description": "Demasiados envíos desde esta conexión"}})
def solicitar_demo(datos: SolicitudDemoCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    response.headers.update({"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})
    if not limitador.SOLICITUDES_DEMO.intentar(_ip(request)):
        raise HTTPException(status_code=429, detail="Enviaste varias solicitudes seguidas. Espera unos minutos e inténtalo de nuevo.")
    if not limitador.SOLICITUDES_DEMO_TOTAL.intentar("global"):      # no depende de la IP (que se puede falsear con X-Forwarded-For)
        raise HTTPException(status_code=429, detail="Estamos recibiendo muchas solicitudes. Inténtalo de nuevo en unos minutos o escríbenos por WhatsApp.")
    if datos.sitio_web.strip():
        return SolicitudDemoRespuesta(mensaje=MENSAJE_OK)           # un robot llenó el campo trampa: se le dice «ok» y no se guarda nada
    reciente = (db.query(SolicitudDemo.id)
                .filter(SolicitudDemo.celular == datos.celular, SolicitudDemo.fecha_creacion >= ahora_utc() - VENTANA_DUPLICADO,
                        SolicitudDemo.estado != EstadoDemo.DESCARTADA.value).first())
    if reciente is not None:
        return SolicitudDemoRespuesta(mensaje=MENSAJE_OK)           # ya la tenemos: no se duplica (ni se avisa dos veces a los administradores)
    s = SolicitudDemo(nombre=datos.nombre, conjunto=datos.conjunto, celular=datos.celular, correo=datos.correo, ciudad=datos.ciudad,
                      apartamentos=datos.apartamentos, mensaje=datos.mensaje, origen=datos.origen, acepto_datos=ahora_utc())
    db.add(s)
    db.flush()
    cuando = "por WhatsApp" if datos.origen == "whatsapp" else "desde el formulario"
    notificar(db, usuarios_activos(db, roles=[RolNombre.ADMINISTRADOR]), "Nueva solicitud de demo", f"{datos.nombre} · {datos.conjunto} ({cuando}).", "#/demos")
    db.commit()
    return SolicitudDemoRespuesta(mensaje=MENSAJE_OK)


@router.get("/solicitudes", response_model=list[SolicitudDemoResponse], summary="Ver las solicitudes de demo",
            description="Solo **Administrador**. Las más recientes primero (máximo 500). Filtra con `estado`.")
def listar_solicitudes(estado: Optional[EstadoDemo] = Query(default=None), db: Session = Depends(get_db), _: Usuario = Depends(solo_admin)):
    q = db.query(SolicitudDemo)
    if estado is not None:
        q = q.filter(SolicitudDemo.estado == estado.value)
    return q.order_by(SolicitudDemo.fecha_creacion.desc(), SolicitudDemo.id.desc()).limit(MAX_LISTA).all()


@router.patch("/solicitudes/{solicitud_id}", response_model=SolicitudDemoResponse, summary="Actualizar el seguimiento de una solicitud",
              description="Solo **Administrador**. Cambia el estado y/o deja una nota interna.", responses={404: {"description": "Solicitud no encontrada"}})
def actualizar_solicitud(solicitud_id: int, datos: SolicitudDemoUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(solo_admin)):
    s = db.get(SolicitudDemo, solicitud_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada.")
    cambios = []
    if datos.estado is not None and datos.estado.value != s.estado:
        cambios.append(f"estado {s.estado} → {datos.estado.value}")
        s.estado = datos.estado.value
    if "nota" in datos.model_fields_set and datos.nota != s.nota:
        cambios.append("nota actualizada")
        s.nota = datos.nota
    if cambios:
        auditar(db, admin, "Actualizó solicitud de demo", "Demo", s.id, f"{s.conjunto}: {', '.join(cambios)}")
        db.commit()
        db.refresh(s)
    return s
