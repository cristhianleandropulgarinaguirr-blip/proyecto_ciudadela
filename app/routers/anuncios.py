# app/routers/anuncios.py
# Cartelera del conjunto: el administrador publica reuniones, eventos y avisos; todos los usuarios los leen
# y pueden confirmar su asistencia a los que tienen fecha.
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auditoria import auditar
from app.notificaciones import notificar, usuarios_activos
from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Anuncio, AnuncioAsistencia, Usuario
from app.schemas.anuncios import AnuncioCreate, AnuncioResponse, AnuncioUpdate, AsistenteResponse
from app.schemas.negocio import MensajeResponse

TAG = "Anuncios y Comunicados"
router = APIRouter(prefix="/anuncios", tags=[TAG])
ADMIN = RolNombre.ADMINISTRADOR


def _armar(db: Session, anuncios: list[Anuncio], usuario_id: int) -> list[AnuncioResponse]:
    """Agrega nombre del autor, cantidad de asistentes y si el usuario actual ya confirmó."""
    if not anuncios:
        return []
    ids = [a.id for a in anuncios]
    conteo = dict(db.query(AnuncioAsistencia.anuncio_id, func.count(AnuncioAsistencia.id))
                  .filter(AnuncioAsistencia.anuncio_id.in_(ids)).group_by(AnuncioAsistencia.anuncio_id).all())
    mios = {i for (i,) in db.query(AnuncioAsistencia.anuncio_id)
            .filter(AnuncioAsistencia.anuncio_id.in_(ids), AnuncioAsistencia.usuario_id == usuario_id).all()}
    autores = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_({a.autor_id for a in anuncios})).all()}
    return [AnuncioResponse(id=a.id, autor_id=a.autor_id, autor_nombre=autores.get(a.autor_id, "Administración"),
                            titulo=a.titulo, contenido=a.contenido, tipo=a.tipo, fecha_evento=a.fecha_evento,
                            lugar=a.lugar, fijado=a.fijado, fecha_creacion=a.fecha_creacion,
                            asistentes=conteo.get(a.id, 0), asistire=a.id in mios) for a in anuncios]


def _obtener(db: Session, anuncio_id: int) -> Anuncio:
    a = db.get(Anuncio, anuncio_id)
    if a is None:
        raise HTTPException(status_code=404, detail="Anuncio no encontrado.")
    return a


@router.get("/", response_model=list[AnuncioResponse], summary="Ver la cartelera de anuncios",
            description="Roles: **todos**. Primero los fijados y luego los más recientes (máx. 200).")
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    anuncios = db.query(Anuncio).order_by(Anuncio.fijado.desc(), Anuncio.fecha_creacion.desc()).limit(200).all()
    return _armar(db, anuncios, usuario.id)


@router.post("/", response_model=AnuncioResponse, status_code=status.HTTP_201_CREATED, summary="Publicar un anuncio",
             description="Rol: **Administrador**.")
def crear(datos: AnuncioCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = Anuncio(autor_id=admin.id, titulo=datos.titulo.strip(), contenido=datos.contenido.strip(), tipo=datos.tipo.value,
                fecha_evento=datos.fecha_evento, lugar=(datos.lugar or "").strip() or None, fijado=datos.fijado)
    db.add(a)
    db.flush()
    auditar(db, admin, "Publicó anuncio", "Anuncio", a.id, a.titulo)
    notificar(db, usuarios_activos(db, excluir_id=admin.id), f"{a.tipo}: {a.titulo}", a.contenido[:140], "#/anuncios", correo=a.tipo == "Urgente")
    db.commit()
    db.refresh(a)
    return _armar(db, [a], admin.id)[0]


@router.patch("/{anuncio_id}", response_model=AnuncioResponse, summary="Editar un anuncio",
              description="Rol: **Administrador**. Solo se cambian los campos enviados.",
              responses={404: {"description": "Anuncio no encontrado"}})
def editar(anuncio_id: int, datos: AnuncioUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = _obtener(db, anuncio_id)
    cambios = datos.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        if campo == "tipo" and valor is not None:
            valor = valor.value
        if campo in ("titulo", "contenido") and valor is not None:
            valor = valor.strip()
        if campo == "lugar":
            valor = (valor or "").strip() or None
        if campo in ("titulo", "contenido", "tipo", "fijado") and valor is None:
            continue  # estos campos no admiten vacío
        setattr(a, campo, valor)
    auditar(db, admin, "Editó anuncio", "Anuncio", a.id, f"{a.titulo} (campos: {', '.join(cambios)})")
    db.commit()
    db.refresh(a)
    return _armar(db, [a], admin.id)[0]


@router.delete("/{anuncio_id}", response_model=MensajeResponse, summary="Eliminar un anuncio",
               description="Rol: **Administrador**.", responses={404: {"description": "Anuncio no encontrado"}})
def eliminar(anuncio_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = _obtener(db, anuncio_id)
    auditar(db, admin, "Eliminó anuncio", "Anuncio", a.id, a.titulo)
    db.query(AnuncioAsistencia).filter(AnuncioAsistencia.anuncio_id == a.id).delete()
    db.delete(a)
    db.commit()
    return {"mensaje": "Anuncio eliminado."}


@router.put("/{anuncio_id}/asistencia", response_model=AnuncioResponse, summary="Confirmar o quitar mi asistencia",
            description="Roles: **todos**. Solo aplica a anuncios que tienen fecha de evento. Es idempotente.",
            responses={400: {"description": "El anuncio no tiene un evento al que asistir"}, 404: {"description": "Anuncio no encontrado"}})
def asistencia(anuncio_id: int, asistire: bool = Query(...), db: Session = Depends(get_db), usuario: Usuario = Depends(get_current_user)):
    a = _obtener(db, anuncio_id)
    if a.fecha_evento is None:
        raise HTTPException(status_code=400, detail="Este anuncio no tiene un evento al que confirmar asistencia.")
    actual = db.query(AnuncioAsistencia).filter(AnuncioAsistencia.anuncio_id == a.id, AnuncioAsistencia.usuario_id == usuario.id).first()
    if asistire and actual is None:
        db.add(AnuncioAsistencia(anuncio_id=a.id, usuario_id=usuario.id))
    elif not asistire and actual is not None:
        db.delete(actual)
    db.commit()
    return _armar(db, [a], usuario.id)[0]


@router.get("/{anuncio_id}/asistentes", response_model=list[AsistenteResponse], summary="Ver quién confirmó asistencia",
            description="Rol: **Administrador**.", responses={404: {"description": "Anuncio no encontrado"}})
def asistentes(anuncio_id: int, db: Session = Depends(get_db), _: Usuario = Depends(requiere_roles(ADMIN))):
    a = _obtener(db, anuncio_id)
    filas = (db.query(Usuario).join(AnuncioAsistencia, AnuncioAsistencia.usuario_id == Usuario.id)
             .filter(AnuncioAsistencia.anuncio_id == a.id).order_by(Usuario.nombre_completo).all())
    return [AsistenteResponse(usuario_id=u.id, nombre_completo=u.nombre_completo, apartamento=u.apartamento) for u in filas]
