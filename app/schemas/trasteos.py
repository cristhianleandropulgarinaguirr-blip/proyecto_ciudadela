# app/schemas/trasteos.py
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constantes import MAX_DIAS_ANTICIPACION, MAX_HORAS_TRASTEO


def _a_utc_sin_zona(v: datetime) -> datetime:
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v      # sin zona horaria se asume UTC


class TrasteoCreate(BaseModel):
    tipo: Literal["Entrada", "Salida"] = Field(..., description="Entrada = llegan muebles. Salida = salen muebles (exige paz y salvo vigente).")
    fecha_inicio: datetime = Field(..., description="Desde qué hora puede entrar o salir el trasteo (con zona horaria, p. ej. ISO 8601)")
    fecha_fin: datetime = Field(..., description="Hasta qué hora (máximo 12 horas después del inicio)")
    empresa: Optional[str] = Field(default=None, max_length=80, examples=["Trasteos El Rápido"])
    placa: Optional[str] = Field(default=None, max_length=15, examples=["ABC123"])
    observaciones: Optional[str] = Field(default=None, max_length=300)

    @field_validator("empresa", "placa", "observaciones")
    @classmethod
    def _limpiar(cls, v):
        v = v.strip() if isinstance(v, str) else v
        return v or None

    @field_validator("placa")
    @classmethod
    def _placa(cls, v):
        return v.upper().replace(" ", "").replace("-", "") if v else v

    @field_validator("fecha_inicio", "fecha_fin")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _a_utc_sin_zona(v)

    @model_validator(mode="after")
    def _ventana(self):
        ahora = datetime.now(timezone.utc).replace(tzinfo=None)
        if self.fecha_inicio < ahora - timedelta(minutes=5):
            raise ValueError("La hora de inicio ya pasó. Elige una fecha y hora futuras.")
        if self.fecha_inicio > ahora + timedelta(days=MAX_DIAS_ANTICIPACION):
            raise ValueError(f"Solo puedes pedir un trasteo con máximo {MAX_DIAS_ANTICIPACION} días de anticipación.")
        if self.fecha_fin <= self.fecha_inicio:
            raise ValueError("La hora final debe ser posterior a la de inicio.")
        if self.fecha_fin - self.fecha_inicio > timedelta(hours=MAX_HORAS_TRASTEO):
            raise ValueError(f"El trasteo no puede durar más de {MAX_HORAS_TRASTEO} horas.")
        return self


class AprobarIn(BaseModel):
    permitir_simultaneo: bool = Field(default=False, description="Aprobar aunque ya haya otro trasteo aprobado en el mismo horario")


class MotivoIn(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=200, examples=["La fecha coincide con el mantenimiento del ascensor."])

    @field_validator("motivo")
    @classmethod
    def _limpiar(cls, v: str) -> str:
        return v.strip()


class TrasteoResponse(BaseModel):
    id: int
    tipo: str
    estado: str                                   # Pendiente | Aprobado | En curso | Completado | Rechazado | Cancelado | Vencido
    apartamento: Optional[str] = None
    solicitante: str
    titular: str
    fecha_inicio: datetime
    fecha_fin: datetime
    empresa: Optional[str] = None
    placa: Optional[str] = None
    observaciones: Optional[str] = None
    paz_salvo_folio: Optional[str] = None         # solo Salida
    paz_salvo_estado: Optional[str] = None        # Vigente | Vencido | Revocado | No vigente (se calcula en el momento de consultar)
    motivo: Optional[str] = None
    inicio_real: Optional[datetime] = None
    fin_real: Optional[datetime] = None
    puede_iniciar: bool = False                   # para la portería: ¿se puede registrar el inicio ahora?
    motivo_no_puede_iniciar: Optional[str] = None
    simultaneo_con: Optional[str] = None          # apartamento de otro trasteo ya aprobado en el mismo horario (aviso para el administrador)
