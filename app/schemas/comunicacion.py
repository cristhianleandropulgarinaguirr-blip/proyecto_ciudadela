# app/schemas/comunicacion.py — Bloque 3: PQRS, documentos y notificaciones.
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constantes import CategoriaDocumento, EstadoPQRS, TipoPQRS


def _limpiar(v: Optional[str]) -> Optional[str]:
    v = " ".join((v or "").split())
    return v or None


class PQRSCreate(BaseModel):
    tipo: TipoPQRS = Field(..., examples=["Queja"])
    asunto: str = Field(..., min_length=5, max_length=100, examples=["Ruido en el parqueadero después de las 11 p. m."])
    descripcion: str = Field(..., min_length=10, max_length=2000, examples=["Desde hace una semana se escucha música alta en el sótano 2 todas las noches."])

    @field_validator("asunto")
    @classmethod
    def limpiar_asunto(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 5:
            raise ValueError("El asunto debe tener al menos 5 caracteres.")
        return v

    @field_validator("descripcion")
    @classmethod
    def limpiar_descripcion(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Cuéntanos un poco más: la descripción debe tener al menos 10 caracteres.")
        return v


class PQRSUpdate(BaseModel):
    """El administrador cambia el estado y/o responde. Si envía una respuesta sin estado, queda «Resuelta»."""
    estado: Optional[EstadoPQRS] = None
    respuesta: Optional[str] = Field(None, min_length=5, max_length=2000, examples=["Hablamos con portería y reforzamos la ronda nocturna."])

    @field_validator("respuesta")
    @classmethod
    def limpiar_respuesta(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class PQRSResponse(BaseModel):
    id: int
    radicado: str                     # PQRS-2026-0003
    usuario_id: int
    usuario_nombre: str
    apartamento: Optional[str] = None
    tipo: str
    asunto: str
    descripcion: str
    estado: str
    respuesta: Optional[str] = None
    respondido_por: Optional[str] = None
    fecha_respuesta: Optional[datetime] = None
    fecha_creacion: datetime
    fecha_actualizacion: Optional[datetime] = None


class DocumentoResponse(BaseModel):
    id: int
    titulo: str
    categoria: str
    descripcion: Optional[str] = None
    nombre_original: str
    tamano: int
    subido_por: Optional[str] = None
    fecha_creacion: datetime


class NotificacionResponse(BaseModel):
    id: int
    titulo: str
    mensaje: Optional[str] = None
    enlace: Optional[str] = None
    leida: bool
    fecha: datetime

    model_config = ConfigDict(from_attributes=True)


class ConteoNotificaciones(BaseModel):
    no_leidas: int
