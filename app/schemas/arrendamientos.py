# app/schemas/arrendamientos.py
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ArrendamientoCreate(BaseModel):
    nombre_completo: str = Field(..., min_length=3, max_length=100, examples=["Marta Rojas"])
    email: EmailStr = Field(..., examples=["marta.rojas@email.com"])
    fecha_inicio: date = Field(..., examples=["2026-12-01"])
    fecha_fin: date = Field(..., description="Último día del contrato: el acceso se cierra solo al terminar ese día", examples=["2027-11-30"])
    propietario_id: Optional[int] = Field(default=None, description="Solo lo usa el Administrador, para registrar el contrato a nombre de un propietario")

    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre_completo": "Marta Rojas", "email": "marta.rojas@email.com", "fecha_inicio": "2026-12-01", "fecha_fin": "2027-11-30"}})


class Motivo(BaseModel):
    motivo: Optional[str] = Field(default=None, max_length=150, examples=["Documentos incompletos"])


class ArrendamientoResponse(BaseModel):
    id: int
    estado: str
    apartamento: Optional[str] = None
    propietario_id: int
    propietario_nombre: str
    inquilino_id: int
    inquilino_nombre: str
    inquilino_email: str
    fecha_inicio: date
    fecha_fin: date
    dias_restantes: Optional[int] = None
    motivo_cierre: Optional[str] = None
    fecha_creacion: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AprobacionResponse(BaseModel):
    arrendamiento: ArrendamientoResponse
    password_temporal: str
    mensaje: str
