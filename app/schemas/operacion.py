# app/schemas/operacion.py — Bloque 2: visitantes autorizados, paquetes y contactos de emergencia.
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constantes import CategoriaEmergencia, TipoPaquete, TipoVisitante

TELEFONO_REGEX = re.compile(r"^\+?[0-9][0-9 ()\-]{1,18}[0-9]$|^[0-9]{3}$")   # 123 · 601 234 5678 · +57 300 123 4567


def _limpiar(v: Optional[str]) -> Optional[str]:
    v = " ".join((v or "").split())
    return v or None


# ---------------------------------------------------------------- VISITANTES AUTORIZADOS
class VisitanteAutorizadoCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=60, examples=["María Gómez"])
    documento: str = Field(..., min_length=5, max_length=20, description="Cédula o pasaporte (puntos y espacios se ignoran).", examples=["1020304050"])
    tipo: TipoVisitante = TipoVisitante.OTRO
    vigente_hasta: Optional[date] = Field(None, description="Último día que puede ingresar. Vacío = sin vencimiento.", examples=["2026-12-31"])
    notas: Optional[str] = Field(None, max_length=120, examples=["Viene martes y jueves"])

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 3:
            raise ValueError("El nombre debe tener al menos 3 caracteres.")
        return v

    @field_validator("documento")
    @classmethod
    def validar_documento(cls, v: str) -> str:
        v = re.sub(r"[\s.\-]", "", v).upper()
        if not re.fullmatch(r"[A-Z0-9]{5,15}", v):
            raise ValueError("El documento debe tener entre 5 y 15 letras o números.")
        return v

    @field_validator("notas")
    @classmethod
    def limpiar_notas(cls, v: Optional[str]) -> Optional[str]:
        return _limpiar(v)


class VisitanteAutorizadoUpdate(BaseModel):
    """Solo se cambia lo que se envíe. El documento no se edita: para otra persona, crea otra autorización."""
    nombre: Optional[str] = Field(None, min_length=3, max_length=60)
    tipo: Optional[TipoVisitante] = None
    vigente_hasta: Optional[date] = None
    notas: Optional[str] = Field(None, max_length=120)

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: Optional[str]) -> Optional[str]:
        return " ".join(v.split()) if v else v


class VisitanteAutorizadoResponse(BaseModel):
    id: int
    usuario_id: int
    anfitrion_nombre: str
    apartamento: Optional[str] = None
    nombre: str
    documento: str
    tipo: str
    vigente_hasta: Optional[date] = None
    vigente: bool                      # False si ya venció
    notas: Optional[str] = None
    dentro: bool = False               # ¿está ahora en el conjunto?
    acceso_id: Optional[int] = None    # registro abierto (para registrar la salida)
    ultimo_ingreso: Optional[datetime] = None
    fecha_creacion: datetime

    model_config = ConfigDict(json_schema_extra={"example": {
        "id": 4, "usuario_id": 3, "anfitrion_nombre": "Ana Residente", "apartamento": "Torre 1 Apt 101",
        "nombre": "María Gómez", "documento": "1020304050", "tipo": "Servicio domestico", "vigente_hasta": "2026-12-31",
        "vigente": True, "notas": "Martes y jueves", "dentro": False, "acceso_id": None, "ultimo_ingreso": "2026-11-05T13:10:00",
        "fecha_creacion": "2026-10-01T09:00:00"}})


class AccesoVisitanteItem(BaseModel):
    id: int
    visitante_id: int
    nombre: str
    documento: str
    tipo: str
    anfitrion_nombre: str
    apartamento: Optional[str] = None
    fecha_ingreso: datetime
    fecha_salida: Optional[datetime] = None
    ingreso_registrado_por: Optional[str] = None
    salida_registrada_por: Optional[str] = None


# ---------------------------------------------------------------- PAQUETES
class PaqueteCreate(BaseModel):
    destinatario_id: int = Field(..., description="Residente que recibe (ver `GET /paquetes/destinatarios`).", examples=[3])
    tipo: TipoPaquete = TipoPaquete.PAQUETE
    remitente: Optional[str] = Field(None, max_length=60, description="Empresa o mensajero.", examples=["Servientrega"])
    descripcion: Optional[str] = Field(None, max_length=120, examples=["Caja mediana, frágil"])

    @field_validator("remitente", "descripcion")
    @classmethod
    def limpiar(cls, v: Optional[str]) -> Optional[str]:
        return _limpiar(v)


class EntregaRequest(BaseModel):
    entregado_a: Optional[str] = Field(None, max_length=60, description="Quién lo recogió. Vacío = el mismo destinatario.", examples=["Pedro Gómez (hermano)"])

    @field_validator("entregado_a")
    @classmethod
    def limpiar(cls, v: Optional[str]) -> Optional[str]:
        return _limpiar(v)


class PaqueteResponse(BaseModel):
    id: int
    destinatario_id: int
    destinatario_nombre: str
    apartamento: Optional[str] = None
    tipo: str
    remitente: Optional[str] = None
    descripcion: Optional[str] = None
    estado: str
    fecha_recepcion: datetime
    recibido_por: Optional[str] = None
    entregado_a: Optional[str] = None
    entregado_por: Optional[str] = None
    fecha_entrega: Optional[datetime] = None


class DestinatarioResponse(BaseModel):
    id: int
    nombre_completo: str
    apartamento: Optional[str] = None


# ---------------------------------------------------------------- CONTACTOS DE EMERGENCIA
class ContactoCreate(BaseModel):
    nombre: str = Field(..., min_length=3, max_length=60, examples=["Clínica San Rafael"])
    telefono: str = Field(..., min_length=3, max_length=20, examples=["601 234 5678"])
    categoria: CategoriaEmergencia = CategoriaEmergencia.OTROS
    descripcion: Optional[str] = Field(None, max_length=120, examples=["Urgencias 24 horas, a 5 minutos del conjunto"])
    orden: int = Field(100, ge=0, le=1000, description="Menor número = aparece primero.")

    @field_validator("nombre")
    @classmethod
    def limpiar_nombre(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str) -> str:
        v = " ".join(v.split())
        if not TELEFONO_REGEX.match(v):
            raise ValueError("Escribe un teléfono válido (ej. 123, 601 234 5678 o +57 300 123 4567).")
        return v

    @field_validator("descripcion")
    @classmethod
    def limpiar_descripcion(cls, v: Optional[str]) -> Optional[str]:
        return _limpiar(v)


class ContactoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=3, max_length=60)
    telefono: Optional[str] = Field(None, min_length=3, max_length=20)
    categoria: Optional[CategoriaEmergencia] = None
    descripcion: Optional[str] = Field(None, max_length=120)
    orden: Optional[int] = Field(None, ge=0, le=1000)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = " ".join(v.split())
        if not TELEFONO_REGEX.match(v):
            raise ValueError("Escribe un teléfono válido (ej. 123, 601 234 5678 o +57 300 123 4567).")
        return v


class ContactoResponse(BaseModel):
    id: int
    nombre: str
    telefono: str
    categoria: str
    descripcion: Optional[str] = None
    orden: int

    model_config = ConfigDict(from_attributes=True)
