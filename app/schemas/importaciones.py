# app/schemas/importaciones.py
from typing import Optional

from pydantic import BaseModel


class FilaImportacion(BaseModel):
    fila: int                      # número de fila en el Excel/CSV del administrador (la 1 es el encabezado)
    accion: str                    # crear | actualizar | sin_cambios | error
    mensaje: str = ""              # por qué falló, o qué cambia
    nombre: Optional[str] = None
    email: Optional[str] = None
    apartamento: Optional[str] = None
    saldo_anterior: Optional[int] = None    # solo cartera
    saldo_nuevo: Optional[int] = None


class CredencialNueva(BaseModel):
    nombre_completo: str
    email: str
    apartamento: Optional[str] = None
    clave_temporal: str


class ResumenImportacion(BaseModel):
    tipo: str
    archivo: str
    aplicado: bool                 # False = vista previa (no se guardó nada)
    total: int
    crear: int = 0
    actualizar: int = 0
    sin_cambios: int = 0
    errores: int = 0
    filas: list[FilaImportacion]
    filas_omitidas: int = 0        # filas válidas que no se listan para no inflar la respuesta (los errores siempre se listan)
    # Solo en «aplicar» de residentes: las claves temporales de las cuentas creadas. Se muestran UNA vez y no se guardan en claro.
    credenciales: list[CredencialNueva] = []
    # Solo cartera aplicada:
    entraron_en_mora: int = 0
    salieron_de_mora: int = 0
