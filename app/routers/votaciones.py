# app/routers/votaciones.py
# Votaciones y consultas del conjunto. VOTO SECRETO por diseño: la tabla de participaciones guarda quién votó y la de opciones
# guarda cuántos votos tiene cada una; no existe ningún dato que una ambas cosas. Un voto por apartamento (o por persona).
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app import arrendamientos as reglas_arr
from app.constantes import Delegacion, RolNombre
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import Rol, Usuario, Votacion, VotacionOpcion, VotacionParticipacion, ahora_utc
from app.notificaciones import notificar, usuarios_activos
from app.schemas.negocio import MensajeResponse
from app.schemas.votaciones import (OpcionResponse, ParticipacionResponse, PendientesResponse, VotacionCreate, VotacionResponse, VotoIn)

TAG = "Votaciones"
router = APIRouter(prefix="/votaciones", tags=[TAG])
ADMIN, RESIDENTE, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.INQUILINO
MSG_VOTO = "Tu propietario no te delegó el voto. Pídele que lo active en «Mis inquilinos»."


def _votante(db: Session, usuario: Usuario) -> Usuario:
    """Quién vota de verdad. Un inquilino con el voto delegado vota POR el apartamento: se usa al propietario (su clave de apartamento y su estado
    de cuenta), así hay un solo voto por apartamento y el propietario no puede votar dos veces. Un inquilino sin delegación recibe 403."""
    return reglas_arr.titular_con_delegacion(db, usuario, Delegacion.VOTAR, MSG_VOTO)


def _norm(apto: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (apto or "").strip().casefold())


def _clave(u: Usuario, un_voto_por: str) -> str:
    if un_voto_por == "apartamento" and _norm(u.apartamento):
        return f"apto:{_norm(u.apartamento)}"
    return f"usr:{u.id}"


def _estado(v: Votacion) -> str:
    return "Cerrada" if v.estado == "Abierta" and v.fecha_cierre <= ahora_utc() else v.estado


def _residentes(db: Session) -> list[Usuario]:
    return (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id)
            .filter(Rol.nombre == RESIDENTE.value, Usuario.esta_activo.is_(True)).all())


def _armar(db: Session, votaciones: list[Votacion], usuario: Usuario) -> list[VotacionResponse]:
    if not votaciones:
        return []
    ids = [v.id for v in votaciones]
    opciones: dict[int, list[VotacionOpcion]] = {}
    for o in db.query(VotacionOpcion).filter(VotacionOpcion.votacion_id.in_(ids)).order_by(VotacionOpcion.orden).all():
        opciones.setdefault(o.votacion_id, []).append(o)
    claves: dict[int, set[str]] = {}
    for vid, clave in db.query(VotacionParticipacion.votacion_id, VotacionParticipacion.clave).filter(VotacionParticipacion.votacion_id.in_(ids)).all():
        claves.setdefault(vid, set()).add(clave)
    autores = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_({v.autor_id for v in votaciones})).all()}
    residentes = _residentes(db)
    elegibles = {m: len({_clave(r, m) for r in residentes}) for m in ("apartamento", "persona")}

    salida = []
    for v in votaciones:
        estado = _estado(v)
        ops = opciones.get(v.id, [])
        visibles = estado == "Cerrada" or (estado == "Abierta" and v.resultados_en_vivo)
        total = sum(o.conteo for o in ops)
        ya = _clave(usuario, v.un_voto_por) in claves.get(v.id, set())
        motivo = None
        if usuario.rol != RESIDENTE.value:
            motivo = "Solo los residentes votan."
        elif estado != "Abierta":
            motivo = "La votación ya terminó."
        elif ya:
            motivo = "Tu apartamento ya votó." if v.un_voto_por == "apartamento" else "Ya votaste."
        elif v.exige_al_dia and not usuario.esta_al_dia:
            motivo = "Solo pueden votar quienes están al día con la administración."
        salida.append(VotacionResponse(
            id=v.id, titulo=v.titulo, descripcion=v.descripcion, estado=estado, fecha_inicio=v.fecha_inicio, fecha_cierre=v.fecha_cierre,
            un_voto_por=v.un_voto_por, resultados_en_vivo=v.resultados_en_vivo, exige_al_dia=v.exige_al_dia,
            autor_nombre=autores.get(v.autor_id, "Administración"),
            opciones=[OpcionResponse(id=o.id, texto=o.texto, votos=o.conteo if visibles else None,
                                     porcentaje=(round(o.conteo * 100 / total, 1) if total else 0.0) if visibles else None) for o in ops],
            resultados_visibles=visibles, total_votos=total if visibles else None,
            participacion=len(claves.get(v.id, ())), elegibles=elegibles[v.un_voto_por],
            ya_vote=ya, puede_votar=motivo is None, motivo_no_puede=motivo))
    return salida


def _obtener(db: Session, votacion_id: int) -> Votacion:
    v = db.get(Votacion, votacion_id)
    if v is None:
        raise HTTPException(status_code=404, detail="Votación no encontrada.")
    return v


@router.get("/", response_model=list[VotacionResponse], summary="Listar votaciones",
            description="Roles: **Administrador, Residente** e **Inquilino** (solo con el voto delegado). Primero las abiertas (las que cierran antes, arriba), luego las terminadas. "
                        "Los resultados solo aparecen cuando la votación cierra (o al instante si se creó con resultados en vivo).")
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, INQUILINO))):
    votante = _votante(db, usuario)
    todas = db.query(Votacion).order_by(Votacion.id.desc()).limit(60).all()
    abiertas = sorted([v for v in todas if _estado(v) == "Abierta"], key=lambda v: v.fecha_cierre)
    resto = [v for v in todas if _estado(v) != "Abierta"]
    return _armar(db, abiertas + resto, votante)


@router.get("/pendientes", response_model=PendientesResponse, summary="Cuántas votaciones abiertas me faltan por votar",
            description="Roles: **Residente** e **Inquilino** (con el voto delegado). Para el aviso del inicio.")
def pendientes(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO))):
    usuario = _votante(db, usuario)
    abiertas = [v for v in db.query(Votacion).filter(Votacion.estado == "Abierta").all() if _estado(v) == "Abierta"]
    if not abiertas:
        return PendientesResponse(pendientes=0)
    ya = {(vid, c) for vid, c in db.query(VotacionParticipacion.votacion_id, VotacionParticipacion.clave)
          .filter(VotacionParticipacion.votacion_id.in_([v.id for v in abiertas])).all()}
    return PendientesResponse(pendientes=sum(1 for v in abiertas if (v.id, _clave(usuario, v.un_voto_por)) not in ya
                                             and not (v.exige_al_dia and not usuario.esta_al_dia)))


@router.get("/{votacion_id}", response_model=VotacionResponse, summary="Ver una votación",
            responses={404: {"description": "Votación no encontrada"}})
def obtener(votacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, INQUILINO))):
    return _armar(db, [_obtener(db, votacion_id)], _votante(db, usuario))[0]


@router.post("/", response_model=VotacionResponse, status_code=status.HTTP_201_CREATED, summary="Crear una votación",
             description="Roles: **Administrador**. Avisa a todos los residentes (campana y, si activaron los avisos, al celular).")
def crear(datos: VotacionCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    v = Votacion(autor_id=admin.id, titulo=datos.titulo, descripcion=datos.descripcion or None, fecha_cierre=datos.fecha_cierre,
                 un_voto_por=datos.un_voto_por, resultados_en_vivo=datos.resultados_en_vivo, exige_al_dia=datos.exige_al_dia)
    db.add(v)
    db.flush()
    db.add_all([VotacionOpcion(votacion_id=v.id, texto=t, orden=i) for i, t in enumerate(datos.opciones)])
    auditar(db, admin, "Creó una votación", "Votación", v.id, v.titulo)
    notificar(db, [u for u in usuarios_activos(db) if u.rol == RESIDENTE.value] + reglas_arr.inquilinos_con_delegacion(db, Delegacion.VOTAR), "Nueva votación: " + v.titulo,
              "Participa antes de que cierre.", "#/votaciones")
    db.commit()
    return _armar(db, [v], admin)[0]


@router.post("/{votacion_id}/votar", response_model=VotacionResponse, summary="Votar",
             description="Roles: **Residente** e **Inquilino** (con el voto delegado: vota en nombre del apartamento). El voto es secreto y no se puede cambiar. Un voto por apartamento (o por persona, según la votación).",
             responses={400: {"description": "Votación cerrada u opción inválida"}, 403: {"description": "No puedes votar"},
                        409: {"description": "Ya votaste"}})
def votar(votacion_id: int, datos: VotoIn, db: Session = Depends(get_db), quien: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO))):
    usuario = _votante(db, quien)                       # = el propietario si vota su inquilino con el voto delegado
    v = _obtener(db, votacion_id)
    if _estado(v) != "Abierta":
        raise HTTPException(status_code=400, detail="Esta votación ya terminó.")
    if v.exige_al_dia and not usuario.esta_al_dia:
        raise HTTPException(status_code=403, detail="Solo pueden votar quienes están al día con la administración.")
    opcion = db.get(VotacionOpcion, datos.opcion_id)
    if opcion is None or opcion.votacion_id != v.id:
        raise HTTPException(status_code=400, detail="Esa opción no pertenece a esta votación.")
    db.add(VotacionParticipacion(votacion_id=v.id, clave=_clave(usuario, v.un_voto_por), usuario_id=quien.id))   # queda quién lo emitió de verdad
    # Incremento atómico en la base de datos: dos votos simultáneos nunca se pisan.
    db.execute(update(VotacionOpcion).where(VotacionOpcion.id == opcion.id).values(conteo=VotacionOpcion.conteo + 1))
    auditar(db, quien, "Votó" if quien.id == usuario.id else "Votó por delegación del propietario", "Votación", v.id, v.titulo)   # se audita que votó, JAMÁS qué votó
    if quien.id != usuario.id:
        notificar(db, [usuario], f"{quien.nombre_completo} votó por tu apartamento", f"En «{v.titulo}». Tu voto ya quedó contado: en esta consulta no puedes votar tú.", "#/votaciones")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tu apartamento ya votó en esta consulta." if v.un_voto_por == "apartamento" else "Ya votaste en esta consulta.")
    db.refresh(v)
    return _armar(db, [v], usuario)[0]


def _cerrar(db: Session, votacion_id: int, admin: Usuario, nuevo_estado: str) -> Votacion:
    v = _obtener(db, votacion_id)
    if _estado(v) != "Abierta":
        raise HTTPException(status_code=400, detail="Esta votación ya terminó.")
    v.estado, v.cerrada_en = nuevo_estado, ahora_utc()
    return v


@router.post("/{votacion_id}/cerrar", response_model=VotacionResponse, summary="Cerrar la votación ahora",
             description="Roles: **Administrador**. Publica los resultados y avisa a los residentes.")
def cerrar(votacion_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    v = _cerrar(db, votacion_id, admin, "Cerrada")
    auditar(db, admin, "Cerró una votación", "Votación", v.id, v.titulo)
    notificar(db, [u for u in usuarios_activos(db) if u.rol == RESIDENTE.value] + reglas_arr.inquilinos_con_delegacion(db, Delegacion.VOTAR), "Resultados: " + v.titulo, "La votación terminó. Ya puedes ver el resultado.", "#/votaciones")
    db.commit()
    return _armar(db, [v], admin)[0]


@router.post("/{votacion_id}/anular", response_model=VotacionResponse, summary="Anular la votación",
             description="Roles: **Administrador**. Los resultados no se publican. Queda en la auditoría.")
def anular(votacion_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    v = _cerrar(db, votacion_id, admin, "Anulada")
    auditar(db, admin, "Anuló una votación", "Votación", v.id, v.titulo)
    db.commit()
    return _armar(db, [v], admin)[0]


@router.get("/{votacion_id}/participacion", response_model=ParticipacionResponse, summary="Quién ya votó y quién falta",
            description="Roles: **Administrador**. Sirve para el quórum y para recordarle a quien falta. NUNCA muestra qué votó cada uno.")
def participacion(votacion_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    v = _obtener(db, votacion_id)
    ya = {c for (c,) in db.query(VotacionParticipacion.clave).filter(VotacionParticipacion.votacion_id == v.id).all()}
    participaron, pendientes_ = {}, {}
    for r in _residentes(db):
        c = _clave(r, v.un_voto_por)
        etiqueta = (r.apartamento or r.nombre_completo) if v.un_voto_por == "apartamento" else r.nombre_completo
        (participaron if c in ya else pendientes_)[c] = etiqueta
    for c in participaron:                      # quien votó nunca figura como pendiente aunque otro del mismo apartamento no
        pendientes_.pop(c, None)
    return ParticipacionResponse(participaron=sorted(participaron.values()), pendientes=sorted(pendientes_.values()))
