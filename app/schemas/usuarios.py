# app/schemas/usuarios.py
# Schemas = reglas de validación de lo que entra y sale por la API (no tocan la BD).
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.constantes import RolNombre


class UsuarioBase(BaseModel):
    nombre_completo: str = Field(..., min_length=3, max_length=100, examples=["Juan Pérez"])
    email: EmailStr = Field(..., examples=["juan.perez@email.com"])
    apartamento: Optional[str] = Field(default=None, max_length=50, examples=["Torre 1 Apt 202"])


# Registro público: SIEMPRE crea un Residente (el rol no se puede elegir desde afuera).
class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=8, max_length=64, description="Entre 8 y 64 caracteres", examples=["claveSegura123"])

    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre_completo": "Juan Pérez",
        "email": "juan.perez@email.com",
        "apartamento": "Torre 1 Apt 202",
        "password": "claveSegura123",
    }})


# Creación por el administrador: puede asignar cualquier rol.
class UsuarioCreateAdmin(UsuarioCreate):
    rol: RolNombre = Field(default=RolNombre.RESIDENTE, description="Rol que tendrá el usuario")

    model_config = ConfigDict(json_schema_extra={"example": {
        "nombre_completo": "Pedro Gómez",
        "email": "pedro.gomez@email.com",
        "apartamento": None,
        "password": "claveSegura123",
        "rol": "Guardia",
    }})


class UsuarioResponse(UsuarioBase):
    id: int
    rol: str
    esta_activo: bool
    esta_al_dia: bool
    parqueadero_asignado: str
    debe_cambiar_password: bool = False
    politica_aceptada: bool = False   # ¿ya aceptó la política de tratamiento de datos?

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"example": {
        "id": 1,
        "nombre_completo": "Juan Pérez",
        "email": "juan.perez@email.com",
        "apartamento": "Torre 1 Apt 202",
        "rol": "Residente",
        "esta_activo": True,
        "esta_al_dia": True,
        "parqueadero_asignado": "Ninguno",
    }})


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str
    debe_cambiar_password: bool = False

    model_config = ConfigDict(json_schema_extra={"example": {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "rol": "Residente",
        "nombre_completo": "Juan Pérez",
    }})


class ParqueaderoUpdate(BaseModel):
    parqueadero_asignado: str = Field(..., min_length=1, max_length=20, examples=["P-202"])


class CambioPassword(BaseModel):
    password_actual: str = Field(..., min_length=1, max_length=64)
    password_nueva: str = Field(..., min_length=8, max_length=64, description="Entre 8 y 64 caracteres")

    model_config = ConfigDict(json_schema_extra={"example": {"password_actual": "claveTemporal1", "password_nueva": "miNuevaClave2026"}})


class PasswordTemporalResponse(BaseModel):
    password_temporal: str
    mensaje: str
