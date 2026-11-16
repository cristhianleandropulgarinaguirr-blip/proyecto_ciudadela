# app/schemas/demo.py — V4.0: lo que se recibe y se devuelve en «Solicitar demo».
import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.constantes import EstadoDemo


def _limpio(v):
    v = " ".join(v.split()) if isinstance(v, str) else v      # sin saltos de línea ni espacios dobles
    return v or None


class SolicitudDemoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=80, examples=["Marcela Rojas"])
    conjunto: str = Field(..., min_length=2, max_length=100, description="Nombre del conjunto o de la administradora", examples=["Conjunto Reserva del Sol"])
    celular: str = Field(..., description="Celular colombiano de 10 dígitos (se aceptan espacios, guiones y el +57)", examples=["310 000 0000"])
    correo: Optional[EmailStr] = Field(default=None, max_length=120)
    ciudad: Optional[str] = Field(default=None, max_length=60, examples=["Facatativá"])
    apartamentos: Optional[int] = Field(default=None, ge=1, le=5000, description="Cuántas unidades tiene el conjunto")
    mensaje: Optional[str] = Field(default=None, max_length=500)
    origen: Literal["formulario", "whatsapp"] = "formulario"
    acepto_datos: bool = Field(..., description="Autoriza el tratamiento de sus datos para que lo contacten (Ley 1581 de 2012). Debe ser true.")
    sitio_web: str = Field(default="", max_length=200, description="Campo trampa para robots: las personas lo dejan vacío.")

    @field_validator("nombre", "conjunto", "ciudad", "mensaje")
    @classmethod
    def _espacios(cls, v):
        return _limpio(v)

    @field_validator("nombre", "conjunto")
    @classmethod
    def _no_vacio(cls, v):
        if not v or len(v) < 2:
            raise ValueError("Escribe al menos 2 letras.")
        return v

    @field_validator("celular")
    @classmethod
    def _celular(cls, v: str) -> str:
        d = re.sub(r"\D", "", v or "")
        if len(d) == 12 and d.startswith("57"):
            d = d[2:]
        if not re.fullmatch(r"3\d{9}", d):
            raise ValueError("Escribe un celular colombiano de 10 dígitos que empiece por 3.")
        return d

    @field_validator("correo", mode="before")
    @classmethod
    def _correo_vacio(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("acepto_datos")
    @classmethod
    def _consentimiento(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Debes autorizar el tratamiento de tus datos para que podamos contactarte.")
        return v


class SolicitudDemoRespuesta(BaseModel):
    ok: bool = True
    mensaje: str


class SolicitudDemoUpdate(BaseModel):
    estado: Optional[EstadoDemo] = None
    nota: Optional[str] = Field(default=None, max_length=300)

    @field_validator("nota")
    @classmethod
    def _nota(cls, v):
        return _limpio(v)


class SolicitudDemoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    conjunto: str
    celular: str
    correo: Optional[str] = None
    ciudad: Optional[str] = None
    apartamentos: Optional[int] = None
    mensaje: Optional[str] = None
    origen: str
    estado: str
    nota: Optional[str] = None
    fecha_creacion: datetime
