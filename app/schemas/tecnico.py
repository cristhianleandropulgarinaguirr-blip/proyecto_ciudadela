# app/schemas/tecnico.py
# v5.6 · Esquemas del enlace de técnico de mantenimiento.
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.constantes import MAX_VIGENCIA_ENLACE_TECNICO_HORAS, VIGENCIA_ENLACE_TECNICO_HORAS


class EnlaceTecnicoCrear(BaseModel):
    horas: int = Field(VIGENCIA_ENLACE_TECNICO_HORAS, ge=1, le=MAX_VIGENCIA_ENLACE_TECNICO_HORAS, description="Cuántas horas sirve el enlace (máximo 168 = 7 días)")
    etiqueta: Optional[str] = Field(None, max_length=80, description="Solo para que tú distingas el enlace, ej. «Plomero · Don Jaime»")


class EnlaceTecnicoResponse(BaseModel):
    """Vista del administrador. `enlace` (la ruta con el token) solo viene mientras el enlace está Vigente: ya vencido o anulado no hay nada que compartir."""
    id: int
    reporte_id: int
    estado: Literal["Vigente", "Vencido", "Revocado", "Cerrado"]
    etiqueta: Optional[str] = None
    valido_hasta: datetime
    fecha_creacion: datetime
    ultimo_uso: Optional[datetime] = None
    enlace: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "id": 4, "reporte_id": 12, "estado": "Vigente", "etiqueta": "Plomero · Don Jaime", "valido_hasta": "2026-11-27T15:00:00",
        "fecha_creacion": "2026-11-24T15:00:00", "ultimo_uso": None, "enlace": "/tecnico/Qm9y3bT0uJ0kqk2m6j1h8m3Vd0m2mQmZ",
    }})
