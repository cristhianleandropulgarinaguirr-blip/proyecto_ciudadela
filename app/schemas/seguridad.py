# app/schemas/seguridad.py
# v5.3 · confirmar contraseña y verificación en dos pasos.
from typing import Optional

from pydantic import BaseModel, Field


class Reautenticar(BaseModel):
    password: str = Field(..., min_length=1, max_length=64)


class ReauthRespuesta(BaseModel):
    reauth_token: str
    expira_en: int = Field(description="Segundos que sirve el pase")


class DosPasosEstado(BaseModel):
    activo: bool
    obligatorio: bool = Field(description="El servidor exige que el administrador la active (EXIGIR_2FA_ADMIN)")
    codigos_restantes: int = 0


class DosPasosIniciar(BaseModel):
    password: str = Field(..., min_length=1, max_length=64)


class DosPasosInicio(BaseModel):
    secreto: str = Field(description="Para escribirlo a mano en la app de autenticación si no se puede escanear")
    uri: str
    qr: str = Field(description="Imagen SVG (data URI) del código QR")


class DosPasosCodigo(BaseModel):
    codigo: str = Field(..., min_length=6, max_length=20)


class DosPasosConfirmar(BaseModel):
    password: str = Field(..., min_length=1, max_length=64)
    codigo: str = Field(..., min_length=6, max_length=20)


class DosPasosActivada(BaseModel):
    mensaje: str
    codigos_recuperacion: list[str] = Field(description="Se muestran UNA sola vez: guárdalos en un lugar seguro")


class MensajeSeguridad(BaseModel):
    mensaje: str
    detalle: Optional[str] = None
