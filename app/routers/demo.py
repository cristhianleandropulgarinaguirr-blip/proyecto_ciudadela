# app/routers/demo.py — V4.8: el botón «Solicitar demo» de la landing.
#
#   · POST /demo/solicitar   SIN sesión. Guarda el contacto y te avisa por Telegram a ti, el VENDEDOR (app/avisos_demo.py).
#                            Es la única ruta pública que ESCRIBE en la base de datos, así que va muy limitada: tope por IP y global, campo
#                            trampa para robots, consentimiento obligatorio, y un mismo celular no se duplica en 24 horas.
#
# Qué cambió desde la v4.7 (a petición del dueño del producto):
#   · Ya NO hay pantalla «Solicitudes de demo» para el administrador, ni campana, ni push: los prospectos son del negocio de quien vende la app,
#     no del administrador de un conjunto (además son datos personales de terceros). Se quitaron GET/PATCH /demo/solicitudes.
#   · La fila se sigue guardando como RESPALDO (si Telegram falla, el contacto no se pierde) y para no duplicar. Se consulta en el panel de la
#     base de datos (Supabase → Table Editor → solicitudes_demo), no en la app.
#   · Si LANDING_ACTIVA=0 (la app real de un cliente), esta ruta responde 404: no existe.
# No se guarda la IP ni nada del dispositivo: solo lo que la persona escribió.
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app import avisos_demo, config, limitador
from app.constantes import EstadoDemo
from app.database import get_db
from app.models import SolicitudDemo, ahora_utc
from app.schemas.demo import SolicitudDemoCreate, SolicitudDemoRespuesta

TAG = "Presentación comercial (demo)"


def _solo_con_landing():
    """La demo solo existe donde la landing está activa. Se evalúa en cada petición (no al arrancar)."""
    if not config.LANDING_ACTIVA:
        raise HTTPException(status_code=404, detail="Not Found")


router = APIRouter(prefix="/demo", tags=[TAG], dependencies=[Depends(_solo_con_landing)])

MENSAJE_OK = "¡Listo! Recibimos tu solicitud y te contactaremos para agendar la demostración."
VENTANA_DUPLICADO = timedelta(hours=24)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


@router.post("/solicitar", response_model=SolicitudDemoRespuesta, status_code=201, summary="Solicitar una demostración (sin sesión)",
             description="**Sin sesión.** Lo usa la landing. Guarda el contacto y avisa por Telegram al vendedor. Límite: 5 envíos por IP cada 10 minutos. "
                         "`acepto_datos` debe ser `true` (Ley 1581 de 2012). `sitio_web` es un campo trampa: debe ir vacío.",
             responses={404: {"description": "Esta app no tiene demo (LANDING_ACTIVA=0)"}, 422: {"description": "Datos inválidos o sin autorización de datos"},
                        429: {"description": "Demasiados envíos desde esta conexión"}})
def solicitar_demo(datos: SolicitudDemoCreate, request: Request, response: Response, tareas: BackgroundTasks, db: Session = Depends(get_db)):
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
        return SolicitudDemoRespuesta(mensaje=MENSAJE_OK)           # ya la tenemos: no se duplica (ni te llega el aviso dos veces)
    s = SolicitudDemo(nombre=datos.nombre, conjunto=datos.conjunto, celular=datos.celular, correo=datos.correo, ciudad=datos.ciudad,
                      apartamentos=datos.apartamentos, mensaje=datos.mensaje, origen=datos.origen, acepto_datos=ahora_utc())
    aviso = avisos_demo.texto_de_solicitud(s)     # se arma ANTES del commit: así no hace falta volver a leer la fila de la base
    db.add(s)
    db.commit()           # primero se guarda (respaldo); el aviso sale DESPUÉS de responder y, pase lo que pase con Telegram, el contacto no se pierde
    tareas.add_task(avisos_demo.enviar, aviso)
    return SolicitudDemoRespuesta(mensaje=MENSAJE_OK)
