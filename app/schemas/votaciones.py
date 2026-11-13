# app/schemas/votaciones.py
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class VotacionCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=120, examples=["¿Cambiamos la empresa de vigilancia?"])
    descripcion: Optional[str] = Field(default=None, max_length=1000)
    opciones: list[str] = Field(..., min_length=2, max_length=8, examples=[["Sí", "No", "Me abstengo"]])
    fecha_cierre: datetime = Field(..., description="Cuándo termina la votación (con zona horaria, p. ej. ISO 8601 en UTC)")
    un_voto_por: Literal["apartamento", "persona"] = "apartamento"
    resultados_en_vivo: bool = False
    exige_al_dia: bool = False

    @field_validator("titulo", "descripcion")
    @classmethod
    def _limpiar(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("opciones")
    @classmethod
    def _opciones(cls, v: list[str]) -> list[str]:
        limpias = [o.strip() for o in v]
        if any(not o or len(o) > 80 for o in limpias):
            raise ValueError("Cada opción debe tener entre 1 y 80 caracteres.")
        if len({o.casefold() for o in limpias}) != len(limpias):
            raise ValueError("Las opciones no pueden repetirse.")
        return limpias

    @field_validator("fecha_cierre")
    @classmethod
    def _cierre(cls, v: datetime) -> datetime:
        v = v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v      # sin zona horaria se asume UTC
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        if v < ahora + timedelta(minutes=1):
            raise ValueError("La fecha de cierre debe ser futura.")
        if v > ahora + timedelta(days=90):
            raise ValueError("Una votación no puede durar más de 90 días.")
        return v


class VotoIn(BaseModel):
    opcion_id: int


class OpcionResponse(BaseModel):
    id: int
    texto: str
    votos: Optional[int] = None            # None = los resultados aún no son visibles
    porcentaje: Optional[float] = None


class VotacionResponse(BaseModel):
    id: int
    titulo: str
    descripcion: Optional[str] = None
    estado: str                            # Abierta | Cerrada | Anulada
    fecha_inicio: datetime
    fecha_cierre: datetime
    un_voto_por: str
    resultados_en_vivo: bool
    exige_al_dia: bool
    autor_nombre: str
    opciones: list[OpcionResponse]
    resultados_visibles: bool
    total_votos: Optional[int] = None
    participacion: int                     # cuántos (apartamentos o personas) ya votaron
    elegibles: int                         # cuántos pueden votar
    ya_vote: bool = False
    puede_votar: bool = False
    motivo_no_puede: Optional[str] = None


class ParticipacionResponse(BaseModel):
    """Solo QUIÉN votó, nunca qué votó (el voto es secreto)."""
    participaron: list[str]
    pendientes: list[str]


class PendientesResponse(BaseModel):
    pendientes: int
