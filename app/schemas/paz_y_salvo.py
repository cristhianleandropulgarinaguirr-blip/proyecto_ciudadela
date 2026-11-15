# app/schemas/paz_y_salvo.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class PazSalvoCreate(BaseModel):
    destino: Optional[str] = Field(None, max_length=80, description="Para qué lo necesitas (opcional): «Mudanza», «Trámite bancario»…", examples=["Trámite bancario"])
    usuario_id: Optional[int] = Field(None, description="Solo el administrador: el residente para quien se emite. Los demás lo piden para su propio apartamento.")

    @field_validator("destino")
    @classmethod
    def limpiar(cls, v):
        v = " ".join((v or "").split())
        return v or None


class PazSalvoResponse(BaseModel):
    id: int
    folio: str                      # PS-000123
    estado: str                     # Vigente | Vencido | Revocado | No vigente
    titular: str
    apartamento: Optional[str] = None
    destino: Optional[str] = None
    fecha_emision: datetime
    valido_hasta: datetime
    enlace: str                     # ruta pública de verificación: /verificar/<codigo>
