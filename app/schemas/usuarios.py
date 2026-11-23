# app/schemas/usuarios.py
# Schemas = reglas de validación de lo que entra y sale por la API (no tocan la BD).
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.constantes import RolNombre


# v5.3 · contraseñas débiles: además del largo (8 a 64), se rechazan las que cualquiera probaría primero.
_COMUNES = {
    "12345678", "123456789", "1234567890", "87654321", "11111111", "00000000", "12341234", "123123123", "contraseña", "contrasena", "contraseña1",
    "password", "password1", "password12", "password123", "passw0rd", "qwertyui", "qwerty123", "qwertyuiop", "asdfghjk", "abcd1234", "abc12345", "abcdefgh",
    "admin123", "administrador", "admin1234", "clave123", "clave1234", "claveclave", "bienvenido", "bienvenida", "colombia", "colombia1", "colombia123",
    "conjunto", "conjunto1", "conjunto123", "ciudadela", "ciudadela1", "ciudadela123", "iloveyou", "letmein1", "welcome1", "welcome123", "654321abc",
}


def validar_fortaleza(clave: str) -> str:
    """Lanza ValueError con un mensaje claro si la contraseña es demasiado fácil de adivinar."""
    if clave.lower() in _COMUNES:
        raise ValueError("Esa contraseña es de las más usadas y la adivinan en segundos. Elige otra.")
    if clave.isdigit():
        raise ValueError("Una contraseña solo de números es muy fácil de adivinar. Mezcla letras y números.")
    if len(set(clave.lower())) < 4:
        raise ValueError("La contraseña es demasiado repetitiva. Usa caracteres más variados.")
    return clave


class UsuarioBase(BaseModel):
    nombre_completo: str = Field(..., min_length=3, max_length=100, examples=["Juan Pérez"])
    email: EmailStr = Field(..., examples=["juan.perez@email.com"])
    apartamento: Optional[str] = Field(default=None, max_length=50, examples=["Torre 1 Apt 202"])


# Registro público: SIEMPRE crea un Residente (el rol no se puede elegir desde afuera).
class UsuarioCreate(UsuarioBase):
    password: str = Field(..., min_length=8, max_length=64, description="Entre 8 y 64 caracteres", examples=["claveSegura123"])

    @field_validator("password")
    @classmethod
    def _clave_fuerte(cls, v: str) -> str:
        return validar_fortaleza(v)

    @model_validator(mode="after")
    def _no_parecida_al_correo(self):
        usuario = str(self.email).split("@")[0].lower()
        if len(usuario) >= 5 and usuario in self.password.lower():
            raise ValueError("La contraseña no puede contener tu correo.")
        return self

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
    coeficiente: Optional[float] = None   # % de copropiedad del apartamento (Ley 675); lo asigna el administrador
    debe_cambiar_password: bool = False
    politica_aceptada: bool = False   # ¿ya aceptó la política de tratamiento de datos?
    delegaciones: list[str] = []      # solo inquilinos: lo que su propietario le dejó hacer ("pagar", "votar")

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
    expira_en: int = Field(default=900, description="Segundos de vida del access_token: pide uno nuevo con /auth/refresh antes de que venza")

    model_config = ConfigDict(json_schema_extra={"example": {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "rol": "Residente",
        "nombre_completo": "Juan Pérez",
    }})


class ParqueaderoUpdate(BaseModel):
    parqueadero_asignado: str = Field(..., min_length=1, max_length=20, examples=["P-202"])


class CoeficienteUpdate(BaseModel):
    coeficiente: Optional[float] = Field(default=None, gt=0, le=100, description="Porcentaje de copropiedad del apartamento (por ejemplo 0.8523). null = quitarlo.", examples=[0.8523])


class CoeficientesResumen(BaseModel):
    total: float                      # suma de los coeficientes de todos los apartamentos (debe ser 100)
    apartamentos: int
    con_coeficiente: int
    sin_coeficiente: list[str]        # apartamentos a los que aún les falta
    completo: bool                    # todos tienen coeficiente y la suma es 100


class CambioPassword(BaseModel):
    password_actual: str = Field(..., min_length=1, max_length=64)
    password_nueva: str = Field(..., min_length=8, max_length=64, description="Entre 8 y 64 caracteres")

    @field_validator("password_nueva")
    @classmethod
    def _clave_fuerte(cls, v: str) -> str:
        return validar_fortaleza(v)

    model_config = ConfigDict(json_schema_extra={"example": {"password_actual": "claveTemporal1", "password_nueva": "miNuevaClave2026"}})


class PasswordTemporalResponse(BaseModel):
    password_temporal: str
    mensaje: str


class SesionResponse(BaseModel):
    id: str
    dispositivo: Optional[str] = None
    ip: Optional[str] = None
    creada: datetime
    ultimo_uso: datetime
    actual: bool = False
