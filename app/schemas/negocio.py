# app/schemas/negocio.py
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constantes import EstadoReserva


# ---------------- RESERVAS ----------------
class ReservaCreate(BaseModel):
    zona_comun: str = Field(..., min_length=3, max_length=50, examples=["Salon Comunal"])
    fecha_reserva: datetime = Field(..., examples=["2026-12-20T14:00:00"])

    # Validación: no se puede reservar en el pasado
    @field_validator("fecha_reserva")
    @classmethod
    def validar_fecha_futura(cls, v: datetime) -> datetime:
        if v.date() < datetime.now().date():
            raise ValueError("La fecha de la reserva no puede ser en el pasado.")
        return v


class ReservaResponse(BaseModel):
    id: int
    usuario_id: int
    zona_comun: str
    fecha_reserva: datetime
    estado: str
    fecha_creacion: datetime
    usuario_nombre: Optional[str] = None   # quién reservó (para que portería valide)
    apartamento: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "id": 1,
        "usuario_id": 3,
        "usuario_nombre": "Ana Residente",
        "apartamento": "Torre 1 Apt 101",
        "zona_comun": "Salon Comunal",
        "fecha_reserva": "2026-12-20T14:00:00",
        "estado": "Pendiente",
        "fecha_creacion": "2026-11-06T16:30:00",
    }})


# ---------------- REPORTES DE DAÑOS ----------------
class ReporteResponse(BaseModel):
    id: int
    usuario_id: int
    titulo: str
    descripcion: str
    foto_url: Optional[str]
    estado: str
    fecha_creacion: datetime

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "id": 1,
        "usuario_id": 3,
        "titulo": "Ascensor Torre 3 trabado",
        "descripcion": "El ascensor se detiene entre el piso 4 y 5.",
        "foto_url": "9f8c1d2e3a4b4c5d8e7f6a5b4c3d2e1f.jpg",
        "estado": "Abierto",
        "fecha_creacion": "2026-11-06T16:30:00",
    }})


# ---------------- ADMINISTRACIÓN ----------------
class EstadoCuentaResponse(BaseModel):
    apartamento: Optional[str]
    nombre_completo: str
    valor_administracion: int
    saldo_pendiente: int
    esta_al_dia: bool

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "apartamento": "Torre 1 Apt 202",
        "nombre_completo": "Juan Pérez",
        "valor_administracion": 150000,
        "saldo_pendiente": 300000,
        "esta_al_dia": False,
    }})


class PagoResponse(BaseModel):
    status: str
    mensaje: str
    saldo_pendiente: int
    esta_al_dia: bool
    pago_id: Optional[int] = None    # para descargar el comprobante

    model_config = ConfigDict(json_schema_extra={"example": {
        "status": "Transacción Exitosa",
        "mensaje": "Pago recibido. El apartamento Torre 1 Apt 202 está al día.",
        "saldo_pendiente": 0,
        "esta_al_dia": True,
    }})


# ---------------- PORTERÍA ----------------
class VehiculoResponse(BaseModel):
    id: int
    placa: str
    apartamento_destino: str
    fecha_ingreso: datetime
    fecha_salida: Optional[datetime]
    estado: str

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "id": 1,
        "placa": "XYZ123",
        "apartamento_destino": "Torre 1 Apt 202",
        "fecha_ingreso": "2026-11-06T16:30:00",
        "fecha_salida": None,
        "estado": "Dentro",
    }})


class VehiculoHistorialItem(BaseModel):
    id: int
    placa: str
    apartamento_destino: str
    fecha_ingreso: datetime
    fecha_salida: Optional[datetime]
    estado: str
    ingreso_registrado_por: Optional[str] = None
    salida_registrada_por: Optional[str] = None
    duracion_minutos: Optional[int] = None


class HistorialVehiculosResponse(BaseModel):
    total: int
    pagina: int
    limite: int
    items: list[VehiculoHistorialItem]


class MensajeResponse(BaseModel):
    mensaje: str

    model_config = ConfigDict(json_schema_extra={"example": {"mensaje": "Operación realizada con éxito."}})


class PagoRegistroResponse(BaseModel):
    id: int
    comprobante: str            # REC-2026-000012
    valor: int
    saldo_anterior: int
    saldo_posterior: int
    fecha: datetime


class OcupacionDia(BaseModel):
    dia: date
    estado: str                 # Aprobada | Pendiente
