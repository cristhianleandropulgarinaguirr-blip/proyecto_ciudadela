# app/schemas/anuncios.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.constantes import TipoAnuncio


class AnuncioCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=120, examples=["Asamblea general ordinaria"])
    contenido: str = Field(..., min_length=5, max_length=2000, examples=["Se tratarán el presupuesto y las obras de fachada."])
    tipo: TipoAnuncio = TipoAnuncio.AVISO
    fecha_evento: Optional[datetime] = Field(None, examples=["2026-12-05T19:00:00"])
    lugar: Optional[str] = Field(None, max_length=100, examples=["Salón comunal"])
    fijado: bool = False


class AnuncioUpdate(BaseModel):
    """Todos los campos son opcionales: solo se cambia lo que se envíe."""
    titulo: Optional[str] = Field(None, min_length=3, max_length=120)
    contenido: Optional[str] = Field(None, min_length=5, max_length=2000)
    tipo: Optional[TipoAnuncio] = None
    fecha_evento: Optional[datetime] = None
    lugar: Optional[str] = Field(None, max_length=100)
    fijado: Optional[bool] = None


class AnuncioResponse(BaseModel):
    id: int
    autor_id: int
    autor_nombre: str
    titulo: str
    contenido: str
    tipo: str
    fecha_evento: Optional[datetime]
    lugar: Optional[str]
    fijado: bool
    fecha_creacion: datetime
    asistentes: int = 0
    asistire: bool = False

    model_config = ConfigDict(from_attributes=True)


class AsistenteResponse(BaseModel):
    usuario_id: int
    nombre_completo: str
    apartamento: Optional[str]
