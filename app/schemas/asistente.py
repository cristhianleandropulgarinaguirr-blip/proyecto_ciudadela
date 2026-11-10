# app/schemas/asistente.py — Versión 2.9: asistente de IA (solo borradores; nunca publica nada por sí mismo).
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MensajeResidente(BaseModel):
    mensaje: str = Field(..., min_length=10, max_length=600, examples=["Hace una semana hay una fuga de agua en el sótano 2 y el piso está resbaloso."])


class InstruccionAnuncio(BaseModel):
    instruccion: str = Field(..., min_length=10, max_length=800, examples=["Avisar que mañana de 8 a 12 se corta el agua por mantenimiento del tanque."])


class BorradorPQRS(BaseModel):
    tipo: Literal["Peticion", "Queja", "Reclamo", "Sugerencia"]
    asunto: str
    descripcion: str


class BorradorDanio(BaseModel):
    titulo: str
    descripcion: str


class SolicitudResumen(BaseModel):
    clase: Literal["PQRS", "Daño"]
    referencia: str                     # radicado (PQRS-2026-0003) o «Daño #12»
    titulo: str
    estado: str
    fecha: datetime
    enlace: str                         # ruta de la app donde se ve completa


class RespuestaResidente(BaseModel):
    intencion: Literal["pqrs", "danio", "estado", "emergencia", "otro"]
    mensaje: str
    pqrs: Optional[BorradorPQRS] = None
    danio: Optional[BorradorDanio] = None
    solicitudes: list[SolicitudResumen] = []


class BorradorAnuncio(BaseModel):
    titulo: str
    contenido: str
    tipo: str
    fecha_evento: Optional[datetime] = None
    lugar: Optional[str] = None
    fijado: bool = False
    destinatarios: int                  # a cuántas personas llegaría si lo publica
    enviara_correo: bool                # True si además del aviso en la app saldrá un correo
    advertencias: list[str] = []


class EstadoAsistente(BaseModel):
    disponible: bool
    limite_diario: int
    restantes: int


# ---- Lo que se le exige a la IA (estricto: cualquier cosa fuera de este formato se rechaza) ----
class SalidaResidente(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intencion: Literal["pqrs", "danio", "estado", "otro"]
    tipo: Optional[str] = None
    asunto: Optional[str] = Field(None, max_length=400)
    descripcion: Optional[str] = Field(None, max_length=4000)
    mensaje: Optional[str] = Field(None, max_length=1000)


class SalidaAnuncio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    valido: bool = True
    titulo: Optional[str] = Field(None, max_length=600)
    contenido: Optional[str] = Field(None, max_length=6000)
    tipo: Optional[str] = Field(None, max_length=40)
    fecha_evento: Optional[str] = Field(None, max_length=40)
    lugar: Optional[str] = Field(None, max_length=400)
