# app/schemas/asamblea_acta.py — esquemas de entrada y salida del acta de la asamblea (V5.4, Fase 4).
import re
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _limpia(v: Optional[str]) -> Optional[str]:
    v = re.sub(r"[ \t]+", " ", _CONTROL.sub("", v)).strip() if isinstance(v, str) else v
    return v or None


class ActaEdit(BaseModel):
    """Solo se cambia lo que se envía. Un texto vacío borra ese campo."""
    presidente_nombre: Optional[str] = Field(None, max_length=120, description="Nombre completo del presidente de la reunión")
    secretario_nombre: Optional[str] = Field(None, max_length=120, description="Nombre completo del secretario de la reunión")
    comision: Optional[str] = Field(None, max_length=500, description="Personas designadas para verificar la redacción del acta (si la asamblea las nombró)")
    desarrollo: Optional[str] = Field(None, max_length=20000, description="Desarrollo del orden del día y decisiones adoptadas, redactado por el secretario")

    @field_validator("presidente_nombre", "secretario_nombre")
    @classmethod
    def _nombre(cls, v: Optional[str]) -> Optional[str]:
        v = _limpia(v)
        if v is not None and len(v) < 3:
            raise ValueError("Escribe el nombre completo (mínimo 3 letras).")
        return v

    @field_validator("comision")
    @classmethod
    def _comision(cls, v: Optional[str]) -> Optional[str]:
        return _limpia(v)

    @field_validator("desarrollo")
    @classmethod
    def _desarrollo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = "\n".join(re.sub(r"[ \t]+", " ", _CONTROL.sub("", l)).rstrip() for l in v.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
        return v or None


class ActaResponse(BaseModel):
    asamblea_id: int
    estado: str                                   # «Sin iniciar» | «Borrador» | «Sellada»
    editable: bool = False
    publicada: bool = False
    presidente_nombre: Optional[str] = None       # los cuatro campos de texto: solo los ve el administrador (el residente recibe el PDF publicado)
    secretario_nombre: Optional[str] = None
    comision: Optional[str] = None
    desarrollo: Optional[str] = None
    sellada_en: Optional[datetime] = None
    contenido_hash: Optional[str] = None
    tiene_firmada: bool = False
    firmada_en: Optional[datetime] = None
    firmada_hash: Optional[str] = None
    publicada_en: Optional[datetime] = None
    limite_publicacion: Optional[date] = None
    plazo_vencido: bool = False
    puede_sellar: bool = False
    motivo_no_sellar: Optional[str] = None
    advertencias: list[str] = []


class ComprobacionResponse(BaseModel):
    nombre: str
    ok: bool
    detalle: str


class VerificacionResponse(BaseModel):
    ok: bool
    huella: str
    sellada_en: Optional[datetime]
    comprobaciones: list[ComprobacionResponse]
