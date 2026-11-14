# app/routers/qr.py
# Fase 2: códigos QR.
#   - Carnet: identificación permanente de cada usuario. El guardia lo escanea y ve quién es.
#   - Pase de visitante: el residente lo crea con la placa de su invitado; el guardia lo escanea al llegar
#     (registra el ingreso) y otra vez al irse (registra la salida). Todo queda en el historial de portería.
# Seguridad: el QR solo contiene un token aleatorio. Qué significa y si sigue vigente se decide en el servidor,
# por eso se puede revocar al instante y, si alguien lo fotografía, no revela datos personales.
import io
import secrets
from datetime import timedelta
from typing import Optional

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from app.constantes import MAX_VISITAS_INQUILINO, EstadoQR, RolNombre, TipoQR
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import CodigoQR, EscaneoQR, Usuario, VehiculoVisitante, ahora_utc
from app.schemas.qr import (
    CodigoResponse, EscaneoItem, EscaneoRequest, EscaneoResponse, PersonaQR, VisitanteCreate, VisitanteQR,
)

TAG = "Códigos QR"
router = APIRouter(prefix="/qr", tags=[TAG])

ADMIN, RESIDENTE, GUARDIA = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA
INQUILINO = RolNombre.INQUILINO
PREFIJO = "CD1:"          # versión 1 del formato; permite cambiar el formato en el futuro sin romper QR viejos
MAX_PASES_ACTIVOS = 10    # por usuario: evita llenar la base de datos de pases


def _payload(token: str) -> str:
    return PREFIJO + token


def _token_de(texto: str) -> str:
    texto = texto.strip()
    return texto[len(PREFIJO):] if texto.startswith(PREFIJO) else texto


def _estado_visible(c: CodigoQR) -> str:
    """Un pase 'Activo' cuyo plazo para ingresar ya pasó se muestra como 'Vencido'."""
    if c.tipo == TipoQR.VISITANTE.value and c.estado == EstadoQR.ACTIVO.value and c.valido_hasta and c.valido_hasta < ahora_utc():
        return "Vencido"
    return c.estado


def _vista(c: CodigoQR, dueno: Usuario) -> CodigoResponse:
    return CodigoResponse(id=c.id, tipo=c.tipo, estado=_estado_visible(c), payload=_payload(c.token),
                          nombre_visitante=c.nombre_visitante, placa=c.placa, valido_hasta=c.valido_hasta,
                          fecha_creacion=c.fecha_creacion, propietario_id=dueno.id,
                          propietario_nombre=dueno.nombre_completo, apartamento=dueno.apartamento)


def _nuevo_token() -> str:
    return secrets.token_urlsafe(24)   # 192 bits de azar: imposible de adivinar


def _obtener_propio(db: Session, codigo_id: int, usuario: Usuario) -> CodigoQR:
    c = db.get(CodigoQR, codigo_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Código no encontrado.")
    if c.usuario_id != usuario.id and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Este código no es tuyo.")
    return c


# ---------------------------------------------------------------- CARNET
@router.get("/mi-carnet", response_model=CodigoResponse, summary="Ver mi carnet QR",
            description="Roles: **todos**. Si todavía no tienes carnet, se crea uno. Es permanente hasta que lo renueves.")
def mi_carnet(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    c = (db.query(CodigoQR).filter(CodigoQR.usuario_id == usuario.id, CodigoQR.tipo == TipoQR.CARNET.value,
                                   CodigoQR.estado == EstadoQR.ACTIVO.value).first())
    if c is None:
        c = CodigoQR(usuario_id=usuario.id, tipo=TipoQR.CARNET.value, token=_nuevo_token())
        db.add(c)
        db.commit()
        db.refresh(c)
    return _vista(c, usuario)


@router.post("/mi-carnet/renovar", response_model=CodigoResponse, summary="Renovar mi carnet QR",
             description="Roles: **todos**. Anula el carnet actual y genera uno nuevo. Úsalo si perdiste el celular "
                         "o compartiste tu QR por error: el anterior deja de funcionar de inmediato.")
def renovar_carnet(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    db.query(CodigoQR).filter(CodigoQR.usuario_id == usuario.id, CodigoQR.tipo == TipoQR.CARNET.value,
                              CodigoQR.estado == EstadoQR.ACTIVO.value).update({"estado": EstadoQR.REVOCADO.value})
    nuevo = CodigoQR(usuario_id=usuario.id, tipo=TipoQR.CARNET.value, token=_nuevo_token())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return _vista(nuevo, usuario)


# ---------------------------------------------------------------- PASES DE VISITANTE
@router.post("/visitantes", response_model=CodigoResponse, status_code=status.HTTP_201_CREATED,
             summary="Crear un pase QR para un visitante",
             description="Roles: **Residente**, **Inquilino**, **Administrador**. El pase sirve para ingresar durante `horas_validez`; "
                         "se escanea al llegar (ingreso) y al salir (salida). Máximo 10 pases vigentes por usuario (5 para el inquilino).",
             responses={400: {"description": "Demasiados pases vigentes"}})
def crear_pase(datos: VisitanteCreate, db: Session = Depends(get_db),
               usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    tope = MAX_VISITAS_INQUILINO if usuario.rol == INQUILINO.value else MAX_PASES_ACTIVOS
    vigentes = (db.query(func.count(CodigoQR.id))
                .filter(CodigoQR.usuario_id == usuario.id, CodigoQR.tipo == TipoQR.VISITANTE.value,
                        CodigoQR.estado.in_([EstadoQR.ACTIVO.value, EstadoQR.DENTRO.value]),
                        (CodigoQR.valido_hasta.is_(None)) | (CodigoQR.valido_hasta >= ahora_utc())).scalar())
    if vigentes >= tope:
        raise HTTPException(status_code=400, detail=f"Ya tienes {tope} pases vigentes. Revoca alguno para crear otro.")
    c = CodigoQR(usuario_id=usuario.id, tipo=TipoQR.VISITANTE.value, token=_nuevo_token(),
                 nombre_visitante=datos.nombre_visitante, placa=datos.placa.upper(),
                 valido_hasta=ahora_utc() + timedelta(hours=datos.horas_validez))
    db.add(c)
    db.commit()
    db.refresh(c)
    return _vista(c, usuario)


@router.get("/visitantes", response_model=list[CodigoResponse], summary="Ver mis pases de visitante",
            description="Roles: **Residente**, **Administrador**. El administrador puede ver los de todos con `todos=true`.")
def listar_pases(todos: bool = Query(False), db: Session = Depends(get_db),
                 usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    q = (db.query(CodigoQR, Usuario).join(Usuario, Usuario.id == CodigoQR.usuario_id)
         .filter(CodigoQR.tipo == TipoQR.VISITANTE.value))
    if not (todos and usuario.rol == ADMIN.value):
        q = q.filter(CodigoQR.usuario_id == usuario.id)
    return [_vista(c, u) for c, u in q.order_by(CodigoQR.id.desc()).limit(100).all()]


@router.post("/visitantes/{codigo_id}/revocar", response_model=CodigoResponse, summary="Revocar un pase de visitante",
             description="Dueño del pase o **Administrador**. Solo se pueden revocar pases que aún no han ingresado.",
             responses={400: {"description": "El pase ya no se puede revocar"}, 403: {"description": "No es tu pase"},
                        404: {"description": "Pase no encontrado"}})
def revocar_pase(codigo_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    c = _obtener_propio(db, codigo_id, usuario)
    if c.tipo != TipoQR.VISITANTE.value:
        raise HTTPException(status_code=400, detail="El carnet no se revoca: se renueva en /qr/mi-carnet/renovar.")
    if c.estado == EstadoQR.DENTRO.value:
        raise HTTPException(status_code=400, detail="El visitante ya está dentro; su salida la registra la portería.")
    if c.estado != EstadoQR.ACTIVO.value:
        raise HTTPException(status_code=400, detail=f"Este pase ya está {c.estado.lower()}.")
    c.estado = EstadoQR.REVOCADO.value
    db.commit()
    db.refresh(c)
    return _vista(c, db.get(Usuario, c.usuario_id))


# ---------------------------------------------------------------- IMAGEN DEL QR
@router.get("/{codigo_id}/imagen", summary="Descargar la imagen del QR",
            description="Dueño del código o **Administrador**. `formato=png` (para compartir por WhatsApp) o `svg` (para imprimir).",
            response_class=Response, responses={200: {"content": {"image/png": {}, "image/svg+xml": {}}}})
def imagen_qr(codigo_id: int, formato: str = Query("png", pattern="^(png|svg)$"),
              db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    c = _obtener_propio(db, codigo_id, usuario)
    qr = segno.make(_payload(c.token), error="m")   # nivel M: tolera ~15 % de daño o reflejos
    buf = io.BytesIO()
    if formato == "svg":
        qr.save(buf, kind="svg", scale=10, border=2, xmldecl=False)
        tipo = "image/svg+xml"
    else:
        qr.save(buf, kind="png", scale=12, border=2)
        tipo = "image/png"
    return Response(content=buf.getvalue(), media_type=tipo, headers={"Cache-Control": "private, no-store"})


# ---------------------------------------------------------------- ESCANEO (PORTERÍA)
def _bitacora(db: Session, codigo: Optional[CodigoQR], personal: Usuario, resultado: str, detalle: str) -> None:
    db.add(EscaneoQR(codigo_id=codigo.id if codigo else None, escaneado_por=personal.id, resultado=resultado, detalle=detalle))


def _rechazo(db: Session, codigo: Optional[CodigoQR], personal: Usuario, motivo: str) -> EscaneoResponse:
    _bitacora(db, codigo, personal, "Rechazado", motivo)
    db.commit()
    return EscaneoResponse(ok=False, resultado="Rechazado", mensaje=motivo, tipo=codigo.tipo if codigo else None)


@router.post("/escanear", response_model=EscaneoResponse, summary="Escanear un código QR en portería",
             description="Roles: **Guardia**, **Administrador**. Recibe el texto leído del QR y actúa según su tipo:\n\n"
                         "- **Carnet** → muestra quién es (nombre, apartamento, parqueadero). No cambia nada.\n"
                         "- **Pase de visitante** sin usar → registra el **ingreso** del vehículo.\n"
                         "- **Pase de visitante** con el vehículo dentro → registra la **salida**.\n\n"
                         "Responde siempre 200; revisa el campo `ok`. Todo intento queda en la bitácora (`GET /qr/escaneos`).")
def escanear(datos: EscaneoRequest, db: Session = Depends(get_db),
             personal: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    codigo = db.query(CodigoQR).filter(CodigoQR.token == _token_de(datos.codigo)).first()
    if codigo is None:
        return _rechazo(db, None, personal, "Código no reconocido. Puede ser falso o de otro sistema.")

    dueno = db.get(Usuario, codigo.usuario_id)
    if dueno is None or not dueno.esta_activo:
        return _rechazo(db, codigo, personal, "El titular de este código está desactivado.")
    if codigo.estado == EstadoQR.REVOCADO.value:
        return _rechazo(db, codigo, personal, "Este código fue revocado y ya no es válido.")

    # ---- Carnet: solo verifica identidad. Por privacidad no muestra datos de cartera.
    if codigo.tipo == TipoQR.CARNET.value:
        _bitacora(db, codigo, personal, "Identidad verificada", dueno.nombre_completo)
        db.commit()
        return EscaneoResponse(ok=True, resultado="Identidad verificada", mensaje=f"{dueno.nombre_completo} está registrado en el conjunto.",
                               tipo=codigo.tipo, persona=PersonaQR(nombre_completo=dueno.nombre_completo, rol=dueno.rol,
                                                                   apartamento=dueno.apartamento, parqueadero=dueno.parqueadero_asignado))

    # ---- Pase de visitante
    apto = dueno.apartamento or "Administración"
    info = VisitanteQR(nombre_visitante=codigo.nombre_visitante or "Visitante", placa=codigo.placa or "",
                       apartamento_destino=apto, autorizado_por=dueno.nombre_completo)

    if codigo.estado == EstadoQR.USADO.value:
        return _rechazo(db, codigo, personal, "Este pase ya fue usado: el visitante ya ingresó y salió.")

    if codigo.estado == EstadoQR.DENTRO.value:      # segunda lectura = salida
        v = db.get(VehiculoVisitante, codigo.vehiculo_id) if codigo.vehiculo_id else None
        if v is not None and v.estado == "Dentro":
            v.estado, v.fecha_salida, v.salida_registrada_por = "Salido", ahora_utc(), personal.id
            mensaje = f"Salida registrada: {info.placa} sale de {apto}."
        else:
            mensaje = f"El vehículo {info.placa} ya tenía la salida registrada; el pase queda cerrado."
        codigo.estado = EstadoQR.USADO.value
        _bitacora(db, codigo, personal, "Salida registrada", f"{info.placa} · {apto}")
        db.commit()
        return EscaneoResponse(ok=True, resultado="Salida registrada", mensaje=mensaje, tipo=codigo.tipo,
                               visitante=info, vehiculo_id=codigo.vehiculo_id)

    # estado Activo: primera lectura = ingreso
    if codigo.valido_hasta and codigo.valido_hasta < ahora_utc():
        return _rechazo(db, codigo, personal, "Este pase venció. Pide al residente que cree uno nuevo.")
    ya_dentro = db.query(VehiculoVisitante).filter(VehiculoVisitante.placa == info.placa, VehiculoVisitante.estado == "Dentro").first()
    if ya_dentro:
        return _rechazo(db, codigo, personal, f"El vehículo {info.placa} ya figura dentro del conjunto.")

    v = VehiculoVisitante(placa=info.placa, apartamento_destino=apto, ingreso_registrado_por=personal.id)
    db.add(v)
    db.flush()
    codigo.vehiculo_id, codigo.estado = v.id, EstadoQR.DENTRO.value
    _bitacora(db, codigo, personal, "Ingreso registrado", f"{info.placa} → {apto}")
    db.commit()
    return EscaneoResponse(ok=True, resultado="Ingreso registrado", mensaje=f"Ingreso registrado: {info.placa} va para {apto}.",
                           tipo=codigo.tipo, visitante=info, vehiculo_id=v.id)


@router.get("/escaneos", response_model=list[EscaneoItem], summary="Bitácora de escaneos",
            description="Roles: **Guardia**, **Administrador**. Los últimos escaneos (aciertos y rechazos) con quién los hizo.")
def bitacora(limite: int = Query(30, ge=1, le=200), db: Session = Depends(get_db),
             _: Usuario = Depends(requiere_roles(GUARDIA, ADMIN))):
    guardia, titular = aliased(Usuario), aliased(Usuario)
    filas = (db.query(EscaneoQR, CodigoQR.tipo, titular.nombre_completo, guardia.nombre_completo)
             .join(guardia, guardia.id == EscaneoQR.escaneado_por)
             .outerjoin(CodigoQR, CodigoQR.id == EscaneoQR.codigo_id)
             .outerjoin(titular, titular.id == CodigoQR.usuario_id)
             .order_by(EscaneoQR.id.desc()).limit(limite).all())
    return [EscaneoItem(id=e.id, fecha=e.fecha, resultado=e.resultado, detalle=e.detalle, tipo=tipo,
                        titular=nombre_titular, escaneado_por=nombre_guardia) for e, tipo, nombre_titular, nombre_guardia in filas]
