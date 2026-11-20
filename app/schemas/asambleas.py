# app/schemas/asambleas.py — esquemas de entrada y salida del módulo de asambleas (V4.6).
import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constantes import ModalidadAsamblea, TipoAsamblea


def _a_utc(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v.astimezone(timezone.utc).replace(tzinfo=None) if v.tzinfo else v      # sin zona horaria se asume UTC


def _limpia(v: Optional[str]) -> Optional[str]:
    v = re.sub(r"[ \t]+", " ", v).strip() if isinstance(v, str) else v
    return v or None


def _url(v: Optional[str]) -> Optional[str]:
    v = _limpia(v)
    if v and not re.match(r"^https?://[^\s]+$", v, re.IGNORECASE):
        raise ValueError("El enlace de la videollamada debe empezar por http:// o https://")
    return v


# ---------------------------------------------------------------- unidades
class UnidadCreate(BaseModel):
    apartamento: str = Field(..., min_length=1, max_length=40, description="Cómo se llama la unidad, p. ej. «Torre 1 Apt 101»")
    coeficiente: float = Field(..., gt=0, le=100, description="En porcentaje: 0,8523 = 0,8523 %")
    propietario_nombre: Optional[str] = Field(None, max_length=120)

    _l = field_validator("apartamento", "propietario_nombre")(lambda cls, v: _limpia(v))


class UnidadUpdate(BaseModel):
    coeficiente: Optional[float] = Field(None, gt=0, le=100)
    propietario_nombre: Optional[str] = Field(None, max_length=120)
    activa: Optional[bool] = None

    _l = field_validator("propietario_nombre")(lambda cls, v: _limpia(v))


class UnidadResponse(BaseModel):
    id: int
    apartamento: str
    coeficiente: Optional[float]
    propietario_nombre: Optional[str]
    origen: str
    activa: bool
    tiene_cuenta: bool
    editable_coeficiente: bool       # false si tiene residentes en la app: se edita en «Usuarios»
    en_mora: bool


class UnidadesResumenResponse(BaseModel):
    total: float
    unidades: int
    sin_coeficiente: list[str]
    sin_cuenta: int
    completo: bool
    problema: Optional[str]
    items: list[UnidadResponse]


# ---------------------------------------------------------------- asamblea
class AsambleaBase(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=120)
    tipo: TipoAsamblea
    modalidad: ModalidadAsamblea
    fecha_sesion: datetime = Field(..., description="Primera convocatoria (con zona horaria, p. ej. ISO 8601 en UTC)")
    fecha_segunda: Optional[datetime] = Field(None, description="Segunda convocatoria. Si se omite: tercer día hábil siguiente, 8 p. m. (Art. 41)")
    orden_del_dia: str = Field(..., min_length=10, max_length=6000)
    lugar: Optional[str] = Field(None, max_length=150)
    url_videollamada: Optional[str] = Field(None, max_length=300)
    instrucciones_virtual: Optional[str] = Field(None, max_length=500, description="Medios tecnológicos y cómo conectarse")
    max_poderes: Optional[int] = Field(None, ge=0, le=10, description="Poderes máximos por persona; por defecto el del conjunto")
    restringe_mora: bool = Field(False, description="Solo si el reglamento le quita el voto a quien está en mora")

    _f = field_validator("fecha_sesion", "fecha_segunda")(lambda cls, v: _a_utc(v))
    _t = field_validator("titulo", "lugar", "instrucciones_virtual")(lambda cls, v: _limpia(v))
    _o = field_validator("orden_del_dia")(lambda cls, v: v.strip())
    _u = field_validator("url_videollamada")(lambda cls, v: _url(v))


class AsambleaCreate(AsambleaBase):
    pass


class AsambleaUpdate(BaseModel):
    titulo: Optional[str] = Field(None, min_length=5, max_length=120)
    tipo: Optional[TipoAsamblea] = None
    modalidad: Optional[ModalidadAsamblea] = None
    fecha_sesion: Optional[datetime] = None
    fecha_segunda: Optional[datetime] = None
    orden_del_dia: Optional[str] = Field(None, min_length=10, max_length=6000)
    lugar: Optional[str] = Field(None, max_length=150)
    url_videollamada: Optional[str] = Field(None, max_length=300)
    instrucciones_virtual: Optional[str] = Field(None, max_length=500)
    max_poderes: Optional[int] = Field(None, ge=0, le=10)
    restringe_mora: Optional[bool] = None

    _f = field_validator("fecha_sesion", "fecha_segunda")(lambda cls, v: _a_utc(v))
    _t = field_validator("titulo", "lugar", "instrucciones_virtual")(lambda cls, v: _limpia(v))
    _u = field_validator("url_videollamada")(lambda cls, v: _url(v))


class DocumentoAdjuntoResponse(BaseModel):
    id: int
    titulo: str
    categoria: str


class MiUnidadResponse(BaseModel):
    apartamento: Optional[str] = None
    presente: bool = False
    poder_estado: Optional[str] = None        # Pendiente | Aprobado | Rechazado
    poder_id: Optional[int] = None


class AsambleaResponse(BaseModel):
    id: int
    titulo: str
    tipo: str
    modalidad: str
    estado: str
    orden_del_dia: str
    fecha_sesion: datetime
    fecha_segunda: datetime
    lugar: Optional[str]
    url_videollamada: Optional[str]
    instrucciones_virtual: Optional[str]
    max_poderes: int
    restringe_mora: bool
    fecha_convocatoria: Optional[datetime]
    convocatoria_hash: Optional[str]
    sin_quorum_en: Optional[datetime]
    convocatoria_numero: Optional[int]
    instalada_en: Optional[datetime]
    quorum_inicial: Optional[float]
    cerrada_en: Optional[datetime]
    quorum_final: Optional[float]
    registro_abierto: bool = False          # se calcula en la vista (no está en la tabla)
    documentos: list[DocumentoAdjuntoResponse] = []
    dias_anticipacion: int = 0              # se calcula en la vista
    mi_unidad: Optional[MiUnidadResponse] = None
    morosos: Optional[list[dict]] = None       # solo el administrador
    model_config = ConfigDict(from_attributes=True)


class AsambleaListaItem(BaseModel):
    id: int
    titulo: str
    tipo: str
    modalidad: str
    estado: str
    fecha_sesion: datetime
    fecha_segunda: datetime
    registro_abierto: bool


class AdvertenciaResponse(BaseModel):
    asamblea: AsambleaResponse
    advertencias: list[str]


class AdjuntarDocumento(BaseModel):
    documento_id: int = Field(..., ge=1)


class EntregaManual(BaseModel):
    unidad_id: int = Field(..., ge=1)
    canal: str = Field(..., pattern="^(Físico|Correo|WhatsApp|Otro)$")
    nota: Optional[str] = Field(None, max_length=120)

    _n = field_validator("nota")(lambda cls, v: _limpia(v))


class EntregaResponse(BaseModel):
    unidad_id: int
    apartamento: str
    propietario_nombre: Optional[str]
    estado: str                    # App | Manual | Pendiente
    detalle: Optional[str] = None


# ---------------------------------------------------------------- asistentes
class AcreditarCreate(BaseModel):
    unidad_id: int = Field(..., ge=1)
    tipo: str = Field("Propietario", pattern="^(Propietario|Apoderado)$")
    nombre: Optional[str] = Field(None, max_length=120, description="Obligatorio si la unidad no tiene residentes en la app")
    documento: Optional[str] = Field(None, max_length=30)
    poder_id: Optional[int] = Field(None, ge=1, description="Obligatorio si es apoderado")
    modalidad: str = Field("Presencial", pattern="^(Presencial|Virtual)$")

    _n = field_validator("nombre")(lambda cls, v: _limpia(v))


class AsistenteResponse(BaseModel):
    id: int
    unidad_id: int
    apartamento: str
    nombre: str
    documento: Optional[str]
    es_apoderado: bool
    modalidad_ingreso: str
    hora_ingreso: datetime
    hora_salida: Optional[datetime]
    presente: bool
    coeficiente_acreditado: float
    en_mora: bool
    con_voto: bool


class AcreditacionResponse(BaseModel):
    asistente: AsistenteResponse
    quorum: dict


class UnidadEstadoResponse(BaseModel):
    """Una fila del tablero de acreditación (puerta de la asamblea)."""
    unidad_id: int
    apartamento: str
    coeficiente: Optional[float]
    propietario_nombre: Optional[str]
    tiene_cuenta: bool
    en_mora: bool
    presente: bool
    ha_estado: bool
    poder_id: Optional[int] = None
    apoderado_nombre: Optional[str] = None


# ---------------------------------------------------------------- poderes
class PoderResponse(BaseModel):
    id: int
    asamblea_id: int
    unidad_id: int
    apartamento: str
    apoderado_nombre: str
    apoderado_documento: str
    apoderado_usuario_id: Optional[int]
    tipo_archivo: str
    estado: str
    motivo: Optional[str]
    subido_por: Optional[str]
    revisado_por: Optional[str]
    revisado_en: Optional[datetime]
    fecha_creacion: datetime
    poderes_del_apoderado: int = 0


class PoderAprobar(BaseModel):
    apoderado_usuario_id: Optional[int] = Field(None, ge=1, description="Si el apoderado tiene cuenta en la app, para validar que no sea personal del conjunto")


class PoderRechazar(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=200)

    _m = field_validator("motivo")(lambda cls, v: _limpia(v))


# ---------------------------------------------------------------- bitácora
class EventoResponse(BaseModel):
    secuencia: int
    tipo: str
    unidad: Optional[str]
    actor: Optional[str]
    detalle: Optional[str]
    creado_en: datetime
    hash: str


class BitacoraResponse(BaseModel):
    integra: bool
    secuencia_danada: Optional[int]
    total: int
    eventos: list[EventoResponse]
