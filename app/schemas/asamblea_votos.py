# app/schemas/asamblea_votos.py — esquemas de entrada y salida de las votaciones dentro de la asamblea (V5.2, Fase 3).
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.constantes import MayoriaAsamblea, TipoVotacionAsamblea


def _limpia(v: Optional[str]) -> Optional[str]:
    v = re.sub(r"[ \t]+", " ", v).strip() if isinstance(v, str) else v
    return v or None


class VotacionAsambleaCreate(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=160, description="La pregunta o el punto del orden del día que se va a votar")
    descripcion: Optional[str] = Field(None, max_length=500, description="Detalle de la propuesta (valor, plazo, etc.)")
    tipo: TipoVotacionAsamblea = Field(TipoVotacionAsamblea.DECISION, description="«Decisión» (A favor / En contra / Abstención) o «Elección» (candidatos u opciones que escribes)")
    mayoria: MayoriaAsamblea = Field(MayoriaAsamblea.SIMPLE, description="«Simple» (más del 50 % del coeficiente presente) o «Calificada» (70 % del coeficiente de todo el conjunto)")
    opciones: list[str] = Field(default_factory=list, max_length=12, description="Solo para «Elección»: de 2 a 12 opciones. En una «Decisión» no se escriben: son fijas")

    _l = field_validator("titulo", "descripcion")(lambda cls, v: _limpia(v))

    @field_validator("opciones")
    @classmethod
    def _opciones(cls, v: list[str]) -> list[str]:
        limpias = [_limpia(x) for x in v]
        if any(x is None for x in limpias):
            raise ValueError("Hay una opción vacía.")
        if any(len(x) > 120 for x in limpias):
            raise ValueError("Cada opción puede tener hasta 120 caracteres.")
        if len({x.casefold() for x in limpias}) != len(limpias):
            raise ValueError("Hay opciones repetidas.")
        return limpias

    @model_validator(mode="after")
    def _coherente(self):
        if self.tipo == TipoVotacionAsamblea.ELECCION:
            if not 2 <= len(self.opciones) <= 12:
                raise ValueError("Una elección necesita entre 2 y 12 opciones.")
            if self.mayoria == MayoriaAsamblea.CALIFICADA:
                raise ValueError("La mayoría calificada (70 %) aplica a decisiones, no a elecciones.")
        elif self.opciones:
            raise ValueError("Una decisión tiene opciones fijas (A favor, En contra, Abstención): no las escribas.")
        return self


class VotoAsambleaIn(BaseModel):
    opcion_id: int = Field(..., description="La opción que escoges")
    unidad_id: Optional[int] = Field(None, description="Solo si representas a más de una unidad (poderes): por cuál unidad votas")


class VotoPresencialIn(BaseModel):
    unidad_id: int
    opcion_id: int


class AnularIn(BaseModel):
    motivo: str = Field(..., min_length=5, max_length=200, description="Por qué se anula (queda en la bitácora)")

    _l = field_validator("motivo")(lambda cls, v: _limpia(v))


class OpcionAsambleaResponse(BaseModel):
    id: int
    texto: str
    votos: Optional[int] = None                       # solo cuando la votación está cerrada
    coeficiente: Optional[float] = None
    porcentaje_presentes: Optional[float] = None
    porcentaje_conjunto: Optional[float] = None


class UnidadVotanteResponse(BaseModel):
    unidad_id: int
    apartamento: str
    coeficiente: float
    ya_voto: bool
    puede_votar: bool = True


class PadronFilaResponse(BaseModel):
    unidad_id: int
    apartamento: str
    nombre: str
    coeficiente: float
    via: str                                          # App | Manual
    ya_voto: bool
    sin_medio: bool = False                           # virtual sin cuenta: no puede votar
    opcion_registrada: Optional[str] = None           # solo en votos presenciales (nominales)
    sigue_presente: bool = True


class ParticipacionResponse(BaseModel):
    unidades_padron: int = 0
    unidades_votaron: int = 0
    coeficiente_padron: float = 0.0
    coeficiente_votaron: float = 0.0
    porcentaje: float = 0.0                           # del coeficiente del padrón que ya votó


class VotacionAsambleaResponse(BaseModel):
    id: int
    asamblea_id: int
    numero: int
    titulo: str
    descripcion: Optional[str] = None
    tipo: str
    mayoria: str
    estado: str
    requisito: str
    opciones: list[OpcionAsambleaResponse]
    abierta_en: Optional[datetime] = None
    cerrada_en: Optional[datetime] = None
    quorum_apertura: Optional[float] = None
    quorum_cierre: Optional[float] = None
    participacion: Optional[ParticipacionResponse] = None
    resultado: Optional[dict] = None                  # solo cuando está cerrada
    resultado_hash: Optional[str] = None
    motivo_anulacion: Optional[str] = None
    # --- según quién pregunta ---
    mis_unidades: Optional[list[UnidadVotanteResponse]] = None      # residente: por cuáles unidades puedo votar
    mensaje_votante: Optional[str] = None                           # residente: por qué no puedo votar (si aplica)
    padron: Optional[list[PadronFilaResponse]] = None               # administrador, mientras está abierta
    advertencias: list[str] = []
