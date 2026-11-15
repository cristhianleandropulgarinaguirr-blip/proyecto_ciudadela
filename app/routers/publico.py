# app/routers/publico.py
# Página PÚBLICA del pase de visitante (sin sesión): el residente comparte un enlace /pase/<token> por WhatsApp y el visitante
# lo abre en su celular y ve: su QR grande (fondo blanco, pantalla encendida), su PIN de 6 dígitos, «Cómo llegar» y los botones
# «Estoy en camino» / «Ya llegué» que avisan al residente y a portería.
#
# Seguridad (esta es la única parte de la API que se usa sin iniciar sesión, por eso va aparte y bien limitada):
#   · El único «permiso» es el token de 192 bits del pase: imposible de adivinar. Un token inexistente, vencido de otro tipo o de un
#     carnet responde 404 igual que uno falso (no se puede averiguar qué tokens existen).
#   · Solo se muestra lo que el visitante ya conoce: su nombre, su placa y el apartamento al que va. Nunca el nombre del residente,
#     su correo ni su cartera.
#   · Límite por IP en lecturas y avisos (app/limitador.py) y una espera de 5 minutos entre avisos del mismo tipo.
#   · La página no se guarda en caché ni se indexa, y no envía el «referer» (el token viaja en la URL).
import io
from datetime import timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import config, limitador
from app.constantes import EstadoQR, RolNombre, TipoQR
from app.database import get_db
from app.models import CodigoQR, Usuario, ahora_utc
from app.notificaciones import notificar, usuarios_activos
from app.routers.qr import PREFIJO, _estado_visible, pase_sirve

TAG = "Pase público (sin sesión)"
router = APIRouter(tags=[TAG])

ESPERA_AVISOS = timedelta(minutes=5)
PAGINA = Path(__file__).resolve().parent.parent.parent / "frontend" / "pase" / "pase.html"
# La página solo carga SU css y SU js (mismo origen) y consulta SU api: nada de terceros, nada inline.
CSP_PASE = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'")
CABECERAS_PAGINA = {"Content-Security-Policy": CSP_PASE, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                    "X-Robots-Tag": "noindex, nofollow", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}
CABECERAS_API = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex"}


class AvisoRequest(BaseModel):
    tipo: Literal["en_camino", "llegue"]


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _pase_o_404(db: Session, token: str) -> CodigoQR:
    c = db.query(CodigoQR).filter(CodigoQR.token == token).first()
    if c is None or c.tipo != TipoQR.VISITANTE.value:
        raise HTTPException(status_code=404, detail="Este enlace no es válido.")
    return c


def _limitar(clave: limitador.Ventana, request: Request) -> None:
    if not clave.intentar(_ip(request)):
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes. Espera un minuto e inténtalo de nuevo.")


def _mapas() -> dict | None:
    """Enlaces «Cómo llegar». Con coordenadas apuntan al punto exacto; con dirección, a la búsqueda; sin ninguna, no hay botones."""
    lat, lng = config.CONJUNTO_LATITUD, config.CONJUNTO_LONGITUD
    if lat is not None and lng is not None:
        return {"google": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}&travelmode=driving",
                "waze": f"https://waze.com/ul?ll={lat},{lng}&navigate=yes"}
    if config.CONJUNTO_DIRECCION:
        q = quote(f"{config.CONJUNTO_DIRECCION}")
        return {"google": f"https://www.google.com/maps/dir/?api=1&destination={q}&travelmode=driving",
                "waze": f"https://waze.com/ul?q={q}&navigate=yes"}
    return None


@router.get("/pase/{token}", response_class=HTMLResponse, include_in_schema=False)
def pagina_del_pase(token: str):
    """La página en sí es siempre la misma; ella pide sus datos a /pase-publico/<token>. Un token malo muestra «enlace no válido» ahí."""
    return HTMLResponse(PAGINA.read_text(encoding="utf-8"), headers=CABECERAS_PAGINA)


@router.get("/pase-publico/{token}", summary="Datos del pase para la página pública",
            description="**Sin sesión.** El token del enlace es la única llave. Devuelve solo lo que el visitante ya conoce (su nombre, su placa y el apartamento al que va), "
                        "el PIN mientras el pase sirva y los enlaces «Cómo llegar». Límite: 90 consultas por minuto por IP.",
            responses={404: {"description": "Enlace no válido"}, 429: {"description": "Demasiadas solicitudes"}})
def datos_del_pase(token: str, request: Request, response: Response, db: Session = Depends(get_db)):
    _limitar(limitador.LECTURAS_PUBLICAS, request)
    c = _pase_o_404(db, token)
    dueno = db.get(Usuario, c.usuario_id)
    estado = _estado_visible(c) if dueno is not None and dueno.esta_activo else EstadoQR.REVOCADO.value
    sirve = pase_sirve(c) and estado != EstadoQR.REVOCADO.value
    ahora = ahora_utc()
    response.headers.update(CABECERAS_API)
    return {"conjunto": {"nombre": config.CONJUNTO_NOMBRE, "direccion": config.CONJUNTO_DIRECCION or None, "mapas": _mapas()},
            "pase": {"visitante": c.nombre_visitante, "placa": c.placa, "apartamento": (dueno.apartamento if dueno else None) or "Administración",
                     "estado": estado, "sirve": sirve, "valido_hasta": c.valido_hasta,
                     "pin": c.pin if sirve else None,
                     "puede_avisar": sirve and estado == EstadoQR.ACTIVO.value,
                     "en_camino": bool(c.aviso_camino and ahora - c.aviso_camino < ESPERA_AVISOS),
                     "llegue": bool(c.aviso_llegada and ahora - c.aviso_llegada < ESPERA_AVISOS)}}


@router.get("/pase-publico/{token}/imagen", summary="Imagen PNG del QR del pase (página pública)", response_class=Response,
            responses={200: {"content": {"image/png": {}}}, 404: {"description": "Enlace no válido o pase que ya no sirve"}, 429: {"description": "Demasiadas solicitudes"}})
def imagen_del_pase(token: str, request: Request, db: Session = Depends(get_db)):
    _limitar(limitador.LECTURAS_PUBLICAS, request)
    c = _pase_o_404(db, token)
    dueno = db.get(Usuario, c.usuario_id)
    if dueno is None or not dueno.esta_activo or not pase_sirve(c):
        raise HTTPException(status_code=404, detail="Este pase ya no sirve.")
    buf = io.BytesIO()
    segno.make(PREFIJO + c.token, error="m").save(buf, kind="png", scale=12, border=3, dark="#000000", light="#FFFFFF")   # negro sobre blanco puro: lo lee cualquier cámara
    return Response(buf.getvalue(), media_type="image/png", headers=CABECERAS_API)


@router.post("/pase-publico/{token}/aviso", summary="«Estoy en camino» / «Ya llegué» del visitante",
             description="**Sin sesión.** El visitante avisa desde su pase. `en_camino` → notificación al residente. `llegue` → notificación al residente **y a la portería** "
                         "(los guardias activos). Solo con el pase vigente y sin usar; el mismo aviso se puede repetir pasados 5 minutos. Límite: 10 por minuto por IP.",
            responses={400: {"description": "El pase ya no admite avisos"}, 404: {"description": "Enlace no válido"},
                       429: {"description": "Aviso reciente o demasiadas solicitudes"}})
def avisar(token: str, datos: AvisoRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _limitar(limitador.AVISOS_PUBLICOS, request)
    c = _pase_o_404(db, token)
    dueno = db.get(Usuario, c.usuario_id)
    if dueno is None or not dueno.esta_activo or not pase_sirve(c) or _estado_visible(c) != EstadoQR.ACTIVO.value:
        raise HTTPException(status_code=400, detail="Este pase ya no admite avisos: está vencido, revocado o ya ingresó.")
    ahora = ahora_utc()
    campo = "aviso_camino" if datos.tipo == "en_camino" else "aviso_llegada"
    previo = getattr(c, campo)
    if previo is not None and ahora - previo < ESPERA_AVISOS:
        raise HTTPException(status_code=429, detail="Ya avisamos hace un momento. Espera unos minutos si necesitas avisar de nuevo.")
    setattr(c, campo, ahora)
    quien = f"{c.nombre_visitante} ({c.placa})"
    apto = dueno.apartamento or "Administración"
    if datos.tipo == "en_camino":
        notificar(db, [dueno], "Tu visita va en camino", f"{quien} viene hacia el conjunto.", "#/visitas")
        mensaje = "Listo, le avisamos a quien te invitó que vas en camino."
    else:
        notificar(db, usuarios_activos(db, roles=[RolNombre.GUARDIA]), "Visita en portería", f"{quien} llegó y va para {apto}.", "#/porteria")
        notificar(db, [dueno], "Tu visita llegó", f"{quien} está en la portería.", "#/visitas")
        mensaje = "Listo, avisamos a la portería y a quien te invitó. Muestra tu QR o dicta tu PIN."
    db.commit()
    response.headers.update(CABECERAS_API)
    return {"ok": True, "mensaje": mensaje}
