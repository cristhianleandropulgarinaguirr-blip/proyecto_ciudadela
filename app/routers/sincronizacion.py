# app/routers/sincronizacion.py
# Portería sin internet: el celular guarda cada registro en una cola local y, al volver la conexión, los envía aquí en orden.
# Cada operación trae un `uuid` generado en el celular: si la red se corta a mitad y el celular reintenta, NADA se duplica.
# Los registros conservan la hora real en que ocurrieron (`ocurrido_en`), no la de la sincronización.
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationError
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import AccesoVisitante, OperacionOffline, Usuario, VehiculoVisitante, ahora_utc
from app.routers.modulos import PLACA_REGEX, ingresar_vehiculo, sacar_vehiculo
from app.routers.paquetes import crear_paquete, entregar_paquete
from app.routers.visitantes import ingresar_visitante, sacar_visitante
from app.schemas.operacion import PaqueteCreate

logger = logging.getLogger("conjunto")
router = APIRouter(prefix="/porteria", tags=["Control de Parqueaderos"])
PERSONAL = (RolNombre.GUARDIA, RolNombre.ADMINISTRADOR)
MAX_OPERACIONES = 100
MAX_ANTIGUEDAD = timedelta(days=7)

Tipo = Literal["vehiculo_ingreso", "vehiculo_salida", "visitante_ingreso", "visitante_salida", "paquete_registro", "paquete_entrega"]


class OperacionIn(BaseModel):
    uuid: str = Field(..., min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    tipo: Tipo
    ocurrido_en: Optional[datetime] = Field(None, description="Hora real en que el guardia hizo el registro (ISO 8601).")
    datos: dict[str, Any] = Field(default_factory=dict)


class SincronizarIn(BaseModel):
    operaciones: list[OperacionIn] = Field(..., max_length=MAX_OPERACIONES)


class ResultadoOperacion(BaseModel):
    uuid: str
    estado: Literal["ok", "duplicada", "rechazada", "reintentar"]
    id: Optional[int] = None
    mensaje: Optional[str] = None


class SincronizarOut(BaseModel):
    resultados: list[ResultadoOperacion]


# ---- datos de cada tipo (validados con la misma regla que los endpoints normales)
class _VehIngreso(BaseModel):
    placa: str = Field(..., pattern=PLACA_REGEX)
    apartamento: str = Field(..., min_length=1, max_length=50)


class _VehSalida(BaseModel):
    vehiculo_id: Optional[int] = None
    ref: Optional[str] = None            # uuid de la operación de ingreso hecha también sin internet
    placa: Optional[str] = Field(None, pattern=PLACA_REGEX)


class _VisIngreso(BaseModel):
    visitante_id: int


class _VisSalida(BaseModel):
    acceso_id: Optional[int] = None
    ref: Optional[str] = None
    visitante_id: Optional[int] = None


class _PaqEntrega(BaseModel):
    paquete_id: Optional[int] = None
    ref: Optional[str] = None
    entregado_a: Optional[str] = Field(None, max_length=60)


def _cuando(ocurrido: Optional[datetime]) -> datetime:
    """Hora real del evento, en UTC sin zona. Se acota: nunca en el futuro ni de hace más de 7 días."""
    ahora = ahora_utc()
    if ocurrido is None:
        return ahora
    if ocurrido.tzinfo is not None:
        ocurrido = ocurrido.astimezone(timezone.utc).replace(tzinfo=None)
    return min(max(ocurrido, ahora - MAX_ANTIGUEDAD), ahora)


def _id_de_ref(db: Session, personal: Usuario, ref: Optional[str]) -> Optional[int]:
    if not ref:
        return None
    op = db.query(OperacionOffline).filter(OperacionOffline.usuario_id == personal.id, OperacionOffline.uuid == ref, OperacionOffline.ok.is_(True)).first()
    try:
        return int(json.loads(op.resultado)["id"]) if op and op.resultado else None
    except (ValueError, KeyError, TypeError):
        return None


def _vehiculo_ingreso(db, personal, datos, cuando):
    d = _VehIngreso(**datos)
    return ingresar_vehiculo(db, personal, d.placa, d.apartamento, cuando).id


def _vehiculo_salida(db, personal, datos, cuando):
    d = _VehSalida(**datos)
    v = None
    vid = d.vehiculo_id or _id_de_ref(db, personal, d.ref)
    if vid:
        v = db.get(VehiculoVisitante, vid)
    if v is None and d.placa:       # el ingreso original pudo fallar (ya estaba dentro): se cierra el que esté dentro con esa placa
        v = db.query(VehiculoVisitante).filter(VehiculoVisitante.placa == d.placa.upper(), VehiculoVisitante.estado == "Dentro").first()
    return sacar_vehiculo(db, personal, v, cuando).id


def _visitante_ingreso(db, personal, datos, cuando):
    d = _VisIngreso(**datos)
    return ingresar_visitante(db, personal, d.visitante_id, cuando)[1].id


def _visitante_salida(db, personal, datos, cuando):
    d = _VisSalida(**datos)
    aid = d.acceso_id or _id_de_ref(db, personal, d.ref)
    a = db.get(AccesoVisitante, aid) if aid else None
    if a is None and d.visitante_id:
        a = db.query(AccesoVisitante).filter(AccesoVisitante.visitante_id == d.visitante_id, AccesoVisitante.fecha_salida.is_(None)).first()
    return sacar_visitante(db, personal, a, cuando).id


def _paquete_registro(db, personal, datos, cuando):
    return crear_paquete(db, personal, PaqueteCreate(**datos), cuando).id


def _paquete_entrega(db, personal, datos, cuando):
    d = _PaqEntrega(**datos)
    pid = d.paquete_id or _id_de_ref(db, personal, d.ref)
    if not pid:
        raise HTTPException(status_code=404, detail="Paquete no encontrado.")
    return entregar_paquete(db, personal, pid, (d.entregado_a or "").strip() or None, cuando).id


EJECUTORES: dict[str, Callable] = {
    "vehiculo_ingreso": _vehiculo_ingreso, "vehiculo_salida": _vehiculo_salida,
    "visitante_ingreso": _visitante_ingreso, "visitante_salida": _visitante_salida,
    "paquete_registro": _paquete_registro, "paquete_entrega": _paquete_entrega,
}


@router.post("/sincronizar", response_model=SincronizarOut, summary="Sincronizar lo registrado sin internet",
             description="Roles: **Guardia**, **Administrador**. Recibe, en orden, las operaciones guardadas en el celular. Es **idempotente**: repetir el envío "
                         "devuelve `duplicada` y no crea nada dos veces. `rechazada` = el servidor la entendió pero no es válida (p. ej. el vehículo ya figuraba dentro): "
                         "no hay que reintentarla. `reintentar` = fallo temporal.")
def sincronizar(datos: SincronizarIn, db: Session = Depends(get_db), personal: Usuario = Depends(requiere_roles(*PERSONAL))):
    resultados: list[ResultadoOperacion] = []
    db.query(OperacionOffline).filter(OperacionOffline.fecha < ahora_utc() - timedelta(days=30)).delete(synchronize_session=False)   # la tabla no crece sin límite
    for op in datos.operaciones:
        previo = db.query(OperacionOffline).filter(OperacionOffline.usuario_id == personal.id, OperacionOffline.uuid == op.uuid).first()
        if previo is not None:
            info = json.loads(previo.resultado) if previo.resultado else {}
            resultados.append(ResultadoOperacion(uuid=op.uuid, estado="duplicada", id=info.get("id"), mensaje=info.get("mensaje")))
            continue
        try:
            nuevo_id = EJECUTORES[op.tipo](db, personal, op.datos, _cuando(op.ocurrido_en))
            db.add(OperacionOffline(usuario_id=personal.id, uuid=op.uuid, tipo=op.tipo, ok=True, resultado=json.dumps({"id": nuevo_id})))
            db.commit()
            resultados.append(ResultadoOperacion(uuid=op.uuid, estado="ok", id=nuevo_id))
        except (HTTPException, ValidationError, TypeError) as e:
            db.rollback()
            msg = e.detail if isinstance(e, HTTPException) else "Datos inválidos en el registro guardado."
            db.add(OperacionOffline(usuario_id=personal.id, uuid=op.uuid, tipo=op.tipo, ok=False, resultado=json.dumps({"mensaje": str(msg)})))
            db.commit()
            resultados.append(ResultadoOperacion(uuid=op.uuid, estado="rechazada", mensaje=str(msg)))
        except Exception:    # noqa: BLE001 - un fallo inesperado no se registra como definitivo: el celular lo reintenta
            db.rollback()
            logger.exception("Error sincronizando la operación %s", op.uuid)
            resultados.append(ResultadoOperacion(uuid=op.uuid, estado="reintentar", mensaje="Error temporal del servidor."))
    return SincronizarOut(resultados=resultados)
