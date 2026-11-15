# app/schemas/dashboard.py
from typing import Optional

from pydantic import BaseModel


class CarteraKPI(BaseModel):
    unidades: int                 # residentes (propietarios) activos
    al_dia: int
    en_mora: int
    pct_al_dia: float             # 0 a 100
    saldo_total: int              # suma de lo que se debe, en pesos


class ZonaKPI(BaseModel):
    zona: str
    total: int


class ReservasKPI(BaseModel):
    dias: int
    por_zona: list[ZonaKPI]       # zonas más reservadas (aprobadas) en esos días
    pendientes: int


class PqrsKPI(BaseModel):
    abiertas: int
    respondidas: int              # en la ventana
    horas_promedio_respuesta: Optional[float] = None
    dias: int


class VisitantesKPI(BaseModel):
    dias: int
    por_hora: list[int]           # 24 valores: ingresos por hora local (0 a 23)
    hora_pico: Optional[int] = None
    total: int


class OperacionKPI(BaseModel):
    vehiculos_dentro: int
    paquetes_sin_entregar: int
    danios_sin_resolver: int
    arrendamientos_por_aprobar: int


class KPIsResponse(BaseModel):
    generado: str                 # ISO UTC
    cartera: CarteraKPI
    reservas: ReservasKPI
    pqrs: PqrsKPI
    visitantes: VisitantesKPI
    operacion: OperacionKPI
