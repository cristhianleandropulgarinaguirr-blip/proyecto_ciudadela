# app/asambleas.py
# Reglas de negocio de las asambleas de copropietarios (Ley 675 de 2001). Los endpoints (routers/asambleas.py) solo traducen HTTP a estas funciones.
#
# Lo que resuelve este módulo:
#  · Bitácora de evidencia con huellas encadenadas (SHA-256): si alguien altera un evento, la cadena se rompe y `verificar_bitacora` lo detecta.
#  · Quórum en vivo: suma del coeficiente de quienes están presentes, sobre el 100 % del conjunto (tabla `unidades`).
#  · Plazos de la convocatoria (Art. 39) y fecha de la segunda convocatoria (Art. 41).
#
# Qué NO hace: no reemplaza al administrador, al presidente y al secretario de la asamblea, ni a un abogado. La app deja la evidencia ordenada;
# la validez de una asamblea depende de que el proceso se cumpla y de lo que diga el reglamento de propiedad horizontal del conjunto.
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import config, unidades as reglas_unidades
from app.calendario_co import HORA_COLOMBIA
from app.constantes import EstadoAsamblea, EstadoPoder, ModalidadAsamblea, TipoAsamblea
from app.models import Asamblea, AsambleaAsistente, AsambleaDocumento, AsambleaEvento, AsambleaPoder, Documento, Unidad, Usuario, ahora_utc

HASH_INICIAL = "0" * 64
VENTANA_REGISTRO = timedelta(hours=3)        # el registro de asistentes abre 3 horas antes de la reunión (la «fila» de las primeras horas)
TOLERANCIA_INSTALAR = timedelta(minutes=60)  # se puede instalar desde 1 hora antes de la hora citada
UMBRAL_QUORUM = 50.0                         # más de la mitad de los coeficientes (Art. 45)
MAX_EVENTOS_VISTA = 500


def local(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA)


def fmt_local(d: datetime) -> str:
    return local(d).strftime("%d/%m/%Y %I:%M %p").lower().replace("am", "a. m.").replace("pm", "p. m.")


def normaliza_documento(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isalnum()).upper()


# ---------------------------------------------------------------- acceso
def obtener(db: Session, asamblea_id: int, bloquear: bool = False) -> Asamblea:
    """Busca la asamblea. Con `bloquear` toma un candado de fila (PostgreSQL) para que dos acciones simultáneas no bifurquen la bitácora."""
    q = db.query(Asamblea).filter(Asamblea.id == asamblea_id)
    if bloquear:
        q = q.with_for_update()
    a = q.one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="La asamblea no existe.")
    return a


def exige_estado(a: Asamblea, *permitidos: EstadoAsamblea, accion: str) -> None:
    if a.estado not in {e.value for e in permitidos}:
        raise HTTPException(status_code=409, detail=f"No se puede {accion}: la asamblea está «{a.estado}».")


def registro_abierto(a: Asamblea, ahora: Optional[datetime] = None) -> bool:
    """¿Se puede acreditar gente? Mientras está en sesión, o desde 3 horas antes de la reunión (1.ª o, si ya fracasó la primera, 2.ª convocatoria)."""
    ahora = ahora or ahora_utc()
    if a.estado == EstadoAsamblea.EN_SESION.value:
        return True
    if a.estado != EstadoAsamblea.CONVOCADA.value:
        return False
    hito = a.fecha_segunda if a.sin_quorum_en else a.fecha_sesion
    return ahora >= hito - VENTANA_REGISTRO


# ---------------------------------------------------------------- bitácora de evidencia
def _huella(asamblea_id: int, secuencia: int, tipo: str, unidad_id: Optional[int], actor_id: Optional[int], detalle: Optional[str],
            creado_en: datetime, hash_anterior: str) -> str:
    cadena = f"{asamblea_id}|{secuencia}|{tipo}|{unidad_id or ''}|{actor_id or ''}|{detalle or ''}|{creado_en.isoformat()}|{hash_anterior}"
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


class Cadena:
    """Cadena de eventos de UNA asamblea para UNA operación: lee el último evento una sola vez y encadena los siguientes en memoria.
    Úsala con la asamblea bloqueada (`obtener(..., bloquear=True)`) y dentro de la misma transacción; así la secuencia nunca se bifurca."""

    def __init__(self, db: Session, asamblea_id: int):
        self.db, self.asamblea_id = db, asamblea_id
        ultimo = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == asamblea_id).order_by(AsambleaEvento.secuencia.desc()).first()
        self.secuencia = ultimo.secuencia if ultimo else 0
        self.hash = ultimo.hash if ultimo else HASH_INICIAL

    def agregar(self, tipo: str, actor: Optional[Usuario] = None, unidad_id: Optional[int] = None, detalle: Optional[str] = None) -> AsambleaEvento:
        detalle = (detalle or None) and detalle[:300]
        self.secuencia += 1
        creado = ahora_utc()
        actor_id = actor.id if actor else None
        ev = AsambleaEvento(asamblea_id=self.asamblea_id, secuencia=self.secuencia, tipo=tipo, unidad_id=unidad_id, actor_id=actor_id, detalle=detalle,
                            creado_en=creado, hash_anterior=self.hash,
                            hash=_huella(self.asamblea_id, self.secuencia, tipo, unidad_id, actor_id, detalle, creado, self.hash))
        self.hash = ev.hash
        self.db.add(ev)
        return ev


def registrar_evento(db: Session, asamblea_id: int, tipo: str, actor: Optional[Usuario] = None, unidad_id: Optional[int] = None,
                     detalle: Optional[str] = None) -> AsambleaEvento:
    """Agrega UN evento a la cadena (ver `Cadena`). Para varios eventos seguidos usa `Cadena` directamente."""
    ev = Cadena(db, asamblea_id).agregar(tipo, actor, unidad_id, detalle)
    db.flush()          # la sesión no autoenvía: así el siguiente evento de esta misma transacción ve este
    return ev


def verificar_bitacora(db: Session, asamblea_id: int) -> tuple[bool, Optional[int], int]:
    """(íntegra, primera secuencia dañada, total de eventos). Recalcula cada huella y comprueba el encadenamiento."""
    anterior, total = HASH_INICIAL, 0
    for ev in db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == asamblea_id).order_by(AsambleaEvento.secuencia).all():
        total += 1
        esperado = _huella(ev.asamblea_id, ev.secuencia, ev.tipo, ev.unidad_id, ev.actor_id, ev.detalle, ev.creado_en, ev.hash_anterior)
        if ev.secuencia != total or ev.hash_anterior != anterior or ev.hash != esperado:
            return False, ev.secuencia, total
        anterior = ev.hash
    return True, None, total


# ---------------------------------------------------------------- quórum
def quorum(db: Session, a: Asamblea) -> dict:
    """Quórum al instante. El coeficiente presente es la suma de las «fotos» tomadas al acreditar, de quienes no han salido."""
    resumen = reglas_unidades.resumen(db)
    presentes = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.hora_salida.is_(None)).all()
    coef_presente = round(sum(p.coeficiente_acreditado for p in presentes), 4)
    pct = round(coef_presente * 100.0 / resumen.total, 4) if resumen.total > 0 else 0.0
    con_voto = round(sum(p.coeficiente_acreditado for p in presentes if p.con_voto), 4)
    return {
        "coeficiente_total": resumen.total, "coeficiente_presente": coef_presente, "porcentaje": pct,
        "unidades_total": resumen.unidades, "unidades_presentes": len(presentes),
        "presenciales": sum(1 for p in presentes if p.modalidad_ingreso == "Presencial"),
        "virtuales": sum(1 for p in presentes if p.modalidad_ingreso == "Virtual"),
        "coeficiente_con_voto": con_voto,
        "hay_quorum": pct > UMBRAL_QUORUM,          # estrictamente más de la mitad
        "faltan_para_quorum": round(max(0.0, UMBRAL_QUORUM - pct), 4),
        "base_completa": resumen.completo, "problema_base": resumen.problema,
    }


# ---------------------------------------------------------------- convocatoria
def dias_de_anticipacion(a: Asamblea) -> int:
    return config.ASAMBLEA_DIAS_ORDINARIA if a.tipo == TipoAsamblea.ORDINARIA.value else config.ASAMBLEA_DIAS_EXTRAORDINARIA


def validar_plazo(a: Asamblea, ahora: Optional[datetime] = None) -> None:
    """Los días de anticipación son «completos»: no cuentan ni el día del envío ni el de la reunión (lectura prudente del Art. 39)."""
    ahora = ahora or ahora_utc()
    dias = dias_de_anticipacion(a)
    diferencia = (local(a.fecha_sesion).date() - local(ahora).date()).days
    if diferencia <= dias:
        primera = (local(ahora).date() + timedelta(days=dias + 1)).strftime("%d/%m/%Y")
        raise HTTPException(status_code=400, detail=f"La asamblea {a.tipo.lower()} se convoca con mínimo {dias} días calendario completos de anticipación "
                                                    f"(sin contar el día del envío ni el de la reunión). Si la envías hoy, la fecha más próxima es el {primera}.")


def documentos_adjuntos(db: Session, asamblea_id: int) -> list[Documento]:
    return (db.query(Documento).join(AsambleaDocumento, AsambleaDocumento.documento_id == Documento.id)
            .filter(AsambleaDocumento.asamblea_id == asamblea_id).order_by(Documento.id).all())


def morosos(db: Session) -> list[dict]:
    """Relación de unidades en mora (Art. 39, parágrafo 2: va dentro de la convocatoria)."""
    por_unidad = reglas_unidades.residentes_por_unidad(db)
    filas = []
    for u in db.query(Unidad).filter(Unidad.activa.is_(True)).order_by(Unidad.apartamento).all():
        residentes = por_unidad.get(u.clave, [])
        if residentes and reglas_unidades.en_mora(residentes):
            filas.append({"apartamento": u.apartamento, "saldo": max((r.saldo_pendiente or 0) for r in residentes)})
    return filas


def contenido_convocatoria(a: Asamblea, documentos: list[Documento], lista_morosos: list[dict]) -> dict:
    return {"titulo": a.titulo, "tipo": a.tipo, "modalidad": a.modalidad, "fecha_sesion": a.fecha_sesion.isoformat(), "fecha_segunda": a.fecha_segunda.isoformat(),
            "lugar": a.lugar, "url_videollamada": a.url_videollamada, "instrucciones_virtual": a.instrucciones_virtual, "orden_del_dia": a.orden_del_dia,
            "documentos": [d.id for d in documentos], "morosos": lista_morosos, "restringe_mora": a.restringe_mora}


def huella_convocatoria(contenido: dict) -> str:
    return hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- poderes
def usuario_es_personal(db: Session, usuario_id: Optional[int]) -> bool:
    """¿Es el administrador o personal del conjunto? (no pueden recibir poderes: conflicto de interés)."""
    if not (config.ASAMBLEA_BLOQUEA_PODER_STAFF and usuario_id):
        return False
    from app.constantes import RolNombre
    u = db.query(Usuario).filter(Usuario.id == usuario_id).one_or_none()
    return bool(u and u.rol in (RolNombre.ADMINISTRADOR.value, RolNombre.GUARDIA.value))


def poderes_del_apoderado(db: Session, a: Asamblea, documento: str, excluir_poder_id: Optional[int] = None) -> int:
    """Cuántos poderes APROBADOS tiene esa persona en esta asamblea (por número de documento)."""
    q = db.query(func.count(AsambleaPoder.id)).filter(AsambleaPoder.asamblea_id == a.id, AsambleaPoder.apoderado_documento == documento,
                                                       AsambleaPoder.estado == EstadoPoder.APROBADO.value)
    if excluir_poder_id:
        q = q.filter(AsambleaPoder.id != excluir_poder_id)
    return q.scalar() or 0


def valida_modalidad_ingreso(a: Asamblea, modalidad: str) -> None:
    if modalidad == "Virtual" and a.modalidad == ModalidadAsamblea.PRESENCIAL.value:
        raise HTTPException(status_code=400, detail="Esta asamblea es presencial: no admite conexiones virtuales.")
    if modalidad == "Presencial" and a.modalidad == ModalidadAsamblea.VIRTUAL.value:
        raise HTTPException(status_code=400, detail="Esta asamblea es virtual: no admite ingreso presencial.")
