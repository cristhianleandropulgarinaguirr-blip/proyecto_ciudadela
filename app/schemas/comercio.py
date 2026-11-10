# app/schemas/comercio.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

WHATSAPP_REGEX = r"^3[0-9]{9}$"   # celular colombiano de 10 dígitos, sin +57


class PlanResponse(BaseModel):
    plan: str
    dias: int
    valor: int


class PlanesResponse(BaseModel):
    planes: list[PlanResponse]
    instrucciones_pago: str


class PublicidadResponse(BaseModel):
    id: int
    propietario_id: int
    propietario_nombre: str
    apartamento: Optional[str] = None
    nombre_negocio: str
    categoria: str
    titulo: str
    descripcion: str
    precio_texto: Optional[str] = None
    whatsapp: str
    tiene_imagen: bool
    plan: str
    valor: int
    estado: str
    referencia_pago: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    contactos: int
    fecha_creacion: datetime

    model_config = ConfigDict(from_attributes=True)


class InformarPago(BaseModel):
    referencia: str = Field(..., min_length=3, max_length=60, examples=["Nequi 3001234567 · comprobante M1234567"])

    @field_validator("referencia")
    @classmethod
    def limpiar(cls, v: str) -> str:
        return " ".join(v.split())


class Rechazo(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=200, examples=["La imagen no corresponde al negocio."])


class Renovacion(BaseModel):
    plan: str = Field(..., examples=["Mensual"])


class ContactoResponse(BaseModel):
    whatsapp_url: str


class ResumenComercio(BaseModel):
    activas: int
    por_revisar: int
    pendientes_pago: int
    ingresos_confirmados: int       # suma de lo cobrado en anuncios que ya se activaron
    contactos_totales: int
