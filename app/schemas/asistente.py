# app/schemas/asistente.py — Versión 2.9: asistente de IA (solo borradores; nunca publica nada por sí mismo).
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class MensajeResidente(BaseModel):
    mensaje: str = Field(..., min_length=10, max_length=600, examples=["Hace una semana hay una fuga de agua en el sótano 2 y el piso está resbaloso."])


class InstruccionAnuncio(BaseModel):
    instruccion: str = Field(..., min_length=10, max_length=800, examples=["Avisar que mañana de 8 a 12 se corta el agua por mantenimiento del tanque."])


class BorradorPQRS(BaseModel):
    tipo: Literal["Peticion", "Queja", "Reclamo", "Sugerencia"]
    asunto: str
    descripcion: str


class BorradorDanio(BaseModel):
    titulo: str
    descripcion: str


class SolicitudResumen(BaseModel):
    clase: Literal["PQRS", "Daño"]
    referencia: str                     # radicado (PQRS-2026-0003) o «Daño #12»
    titulo: str
    estado: str
    fecha: datetime
    enlace: str                         # ruta de la app donde se ve completa


class RespuestaResidente(BaseModel):
    intencion: Literal["pqrs", "danio", "estado", "emergencia", "otro"]
    mensaje: str
    pqrs: Optional[BorradorPQRS] = None
    danio: Optional[BorradorDanio] = None
    solicitudes: list[SolicitudResumen] = []


class BorradorAnuncio(BaseModel):
    titulo: str
    contenido: str
    tipo: str
    fecha_evento: Optional[datetime] = None
    lugar: Optional[str] = None
    fijado: bool = False
    destinatarios: int                  # a cuántas personas llegaría si lo publica
    enviara_correo: bool                # True si además del aviso en la app saldrá un correo
    advertencias: list[str] = []


class EstadoAsistente(BaseModel):
    disponible: bool
    limite_diario: int
    restantes: int


# ---- Lo que se le exige a la IA (estricto: cualquier cosa fuera de este formato se rechaza) ----
class SalidaResidente(BaseModel):
    model_config = ConfigDict(extra="ignore")
    intencion: Literal["pqrs", "danio", "estado", "otro"]
    tipo: Optional[str] = None
    asunto: Optional[str] = Field(None, max_length=400)
    descripcion: Optional[str] = Field(None, max_length=4000)
    mensaje: Optional[str] = Field(None, max_length=1000)


class SalidaAnuncio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    valido: bool = True
    titulo: Optional[str] = Field(None, max_length=600)
    contenido: Optional[str] = Field(None, max_length=6000)
    tipo: Optional[str] = Field(None, max_length=40)
    fecha_evento: Optional[str] = Field(None, max_length=40)
    lugar: Optional[str] = Field(None, max_length=400)


# ---------------------------------------------------------------- Chat (v3.2)
class TurnoChat(BaseModel):
    rol: Literal["usuario", "asistente"]
    texto: str = Field(..., max_length=900)


class MensajeChat(BaseModel):
    mensaje: str = Field(..., min_length=2, max_length=400, examples=["¿Qué días suele estar más congestionado el BBQ?"])
    historial: list[TurnoChat] = Field(default_factory=list, max_length=10)


class DiaConteo(BaseModel):
    dia: str                            # «lunes», «martes»…
    total: int
    destacado: bool = False             # el/los más concurridos


class GraficoZona(BaseModel):
    zona: str
    total: int
    dias: list[DiaConteo]


class AccionChat(BaseModel):
    texto: str
    enlace: str                         # ruta de la app, p. ej. «#/reservas»


class TablaChat(BaseModel):
    """v5.7 · Datos reales que el chat trae para el administrador (la tabla la arma el SERVIDOR; la IA nunca la escribe ni ve los nombres)."""
    titulo: str
    columnas: list[str]
    filas: list[list[str]]
    total: int                          # cuántos hay en total
    mostrando: int                      # cuántas filas trae la tabla (el resto se ve completo en la sección)
    vacio: str = ""                     # qué decir si no hay nada


class RespuestaChat(BaseModel):
    respuesta: str
    modo: Literal["ia", "basico"]       # «basico» = respondió el servidor con los datos, sin IA
    grafico: Optional[GraficoZona] = None
    accion: Optional[AccionChat] = None
    solicitudes: list[SolicitudResumen] = []
    tabla: Optional[TablaChat] = None   # v5.7 · lista de datos reales (residentes en mora, reservas pendientes…), solo para quien tiene permiso
    sugerencias: list[str] = []
    restantes: Optional[int] = None


class EstadoChat(BaseModel):
    ia: bool                            # True si hay IA conectada; si no, el chat responde igual con los datos de reservas
    limite_diario: int
    restantes: int
    sugerencias: list[str] = []         # v4.2 · las preguntas con las que arranca el chat, según el rol (y lo que el propietario delegó al inquilino)


class SalidaChat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    respuesta: Optional[str] = Field(None, max_length=4000)
    zona: Optional[str] = Field(None, max_length=80)
    accion: Optional[str] = Field(None, max_length=30)
    sugerencias: Optional[list[str]] = Field(None, max_length=8)
    consulta: Optional[str] = Field(None, max_length=40)            # v5.7 · id de una consulta del catálogo (se valida en el servidor)
    parametros: Optional[dict[str, Any]] = None                    # v5.7 · parámetros de esa consulta (se validan contra listas y rangos cerrados)


class SalidaRedaccion(BaseModel):
    """v5.7 · Segundo paso: la IA redacta el análisis de los datos que ya consultó el servidor."""
    model_config = ConfigDict(extra="ignore")
    respuesta: Optional[str] = Field(None, max_length=4000)
    sugerencias: Optional[list[str]] = Field(None, max_length=8)
