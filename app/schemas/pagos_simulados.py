# app/schemas/pagos_simulados.py — v4.2: pasarela de pagos de PRUEBAS (tipo Wompi / PSE).
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Metodo = Literal["PSE", "Tarjeta", "Nequi"]
Banco = Literal["aprueba", "rechaza", "pendiente"]


class IniciarPago(BaseModel):
    valor: int = Field(..., gt=0, le=100_000_000, examples=[150000])


class PagarIntento(BaseModel):
    """Lo que la persona escribió en la pasarela. Solo viaja lo mínimo para decidir el resultado de la PRUEBA y NADA de esto se guarda:
    de la tarjeta solo los 4 últimos dígitos (la app nunca envía el número completo, ni el CVC, ni el vencimiento)."""
    model_config = ConfigDict(extra="forbid")
    metodo: Metodo
    banco: Optional[Banco] = None                                        # PSE
    terminacion: Optional[str] = Field(None, pattern=r"^\d{4}$")         # Tarjeta: últimos 4 dígitos
    celular: Optional[str] = Field(None, pattern=r"^3\d{9}$")            # Nequi


class IntentoOut(BaseModel):
    referencia: str
    valor: int
    estado: Literal["Creado", "Pendiente", "Aprobado", "Rechazado", "Expirado"]
    metodo: Optional[Metodo] = None
    mensaje: Optional[str] = None
    pago_id: Optional[int] = None
    saldo_pendiente: int
    esta_al_dia: bool
    segundos_para_confirmar: Optional[int] = None                         # si quedó «Pendiente»
    fecha_creacion: datetime
    modo_pruebas: bool = True
    metodos: list[str] = []
    bancos: list[dict] = []
