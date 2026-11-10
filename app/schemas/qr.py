# app/schemas/qr.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PLACA_REGEX = r"^[A-Za-z]{3}[0-9]{2}[A-Za-z0-9]$"  # Carro: ABC123 · Moto: ABC12D


class VisitanteCreate(BaseModel):
    nombre_visitante: str = Field(..., min_length=3, max_length=60, examples=["Carlos Pérez"])
    placa: str = Field(..., pattern=PLACA_REGEX, examples=["XYZ123"])
    horas_validez: int = Field(12, ge=1, le=72, description="Horas que el pase sirve para INGRESAR (máx. 72).")

    @field_validator("nombre_visitante")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("El nombre del visitante debe tener al menos 3 caracteres.")
        return v

    @field_validator("placa")
    @classmethod
    def placa_mayuscula(cls, v: str) -> str:
        return v.upper()


class CodigoResponse(BaseModel):
    """Un QR del usuario. `payload` es el texto exacto que se dibuja dentro del código."""
    id: int
    tipo: str
    estado: str                      # Activo | Dentro | Usado | Revocado | Vencido
    payload: str
    nombre_visitante: Optional[str] = None
    placa: Optional[str] = None
    valido_hasta: Optional[datetime] = None
    fecha_creacion: datetime
    propietario_id: int
    propietario_nombre: str
    apartamento: Optional[str] = None

    model_config = ConfigDict(json_schema_extra={"example": {
        "id": 7, "tipo": "Visitante", "estado": "Activo", "payload": "CD1:Qm9...",
        "nombre_visitante": "Carlos Pérez", "placa": "XYZ123", "valido_hasta": "2026-11-08T22:00:00",
        "fecha_creacion": "2026-11-08T10:00:00", "propietario_id": 3, "propietario_nombre": "Ana Residente",
        "apartamento": "Torre 1 Apt 101"}})


class EscaneoRequest(BaseModel):
    codigo: str = Field(..., min_length=5, max_length=200, description="Texto leído del QR (empieza por `CD1:`).",
                        examples=["CD1:Qm9sYV9kZV9wcnVlYmFfZGVsX3Rva2Vu"])


class PersonaQR(BaseModel):
    nombre_completo: str
    rol: str
    apartamento: Optional[str] = None
    parqueadero: Optional[str] = None


class VisitanteQR(BaseModel):
    nombre_visitante: str
    placa: str
    apartamento_destino: str
    autorizado_por: str


class EscaneoResponse(BaseModel):
    """Siempre HTTP 200: `ok` dice si la acción se realizó. Un rechazo (pase vencido, usado…) es un resultado
    de negocio, no un error del cliente, y queda registrado en la bitácora."""
    ok: bool
    resultado: str                   # Identidad verificada | Ingreso registrado | Salida registrada | Rechazado
    mensaje: str
    tipo: Optional[str] = None
    persona: Optional[PersonaQR] = None
    visitante: Optional[VisitanteQR] = None
    vehiculo_id: Optional[int] = None


class EscaneoItem(BaseModel):
    id: int
    fecha: datetime
    resultado: str
    detalle: Optional[str] = None
    tipo: Optional[str] = None
    titular: Optional[str] = None
    escaneado_por: str
