# app/routers/asambleas.py — Asambleas de copropietarios (Ley 675 de 2001) y base de unidades/coeficientes. V4.6
#
# Flujo: Borrador → Convocada → En sesión → Cerrada (o Cancelada).
#   Convocar guarda la huella del contenido enviado y avisa a cada propietario; el registro de asistentes abre 3 horas antes; instalar valida el quórum
#   (1.ª convocatoria: más de la mitad de los coeficientes; 2.ª: cualquier número plural de propietarios); todo movimiento queda en la bitácora encadenada.
import io
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import asambleas as reglas, calendario_co, config, marca, notificaciones, unidades as reglas_unidades
from app.archivos import guardar_imagen_validada, guardar_pdf_validado, leer_documento, leer_imagen
from app.auditoria import auditar
from app.coeficientes import norm_apto
from app.constantes import CategoriaDocumento, EstadoAsamblea, EstadoPoder, ModalidadAsamblea, RolNombre, TipoAsamblea
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import (Asamblea, AsambleaAsistente, AsambleaDocumento, AsambleaEvento, AsambleaPoder, Documento, Unidad, Usuario, ahora_utc)
from app.notificaciones import notificar
from app.schemas import asambleas as esq
from app.schemas.negocio import MensajeResponse

TAG = "Asambleas de Copropietarios"
TAG_UNIDADES = "Unidades y Coeficientes"
router = APIRouter(prefix="/asambleas", tags=[TAG])
router_unidades = APIRouter(prefix="/unidades", tags=[TAG_UNIDADES])
ADMIN, RESIDENTE, GUARDIA = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA
ESTADOS_VISIBLES_RESIDENTE = {EstadoAsamblea.CONVOCADA.value, EstadoAsamblea.EN_SESION.value, EstadoAsamblea.CERRADA.value}
MAX_ASAMBLEAS_LISTA = 100


# ================================================================ unidades y coeficientes
def _vista_unidad(u: Unidad, cuentas: dict[str, list[Usuario]]) -> esq.UnidadResponse:
    residentes = cuentas.get(u.clave, [])
    return esq.UnidadResponse(id=u.id, apartamento=u.apartamento, coeficiente=u.coeficiente, propietario_nombre=u.propietario_nombre, origen=u.origen,
                              activa=u.activa, tiene_cuenta=bool(residentes), editable_coeficiente=not residentes, en_mora=reglas_unidades.en_mora(residentes))


@router_unidades.get("/", response_model=esq.UnidadesResumenResponse, summary="Ver las unidades y sus coeficientes",
                     description="Solo **Administrador**. Es la **base del quórum**: cada apartamento con su coeficiente (debe sumar 100 %). Los apartamentos que tienen "
                                 "residentes en la app se mantienen solos desde «Usuarios»; los propietarios **sin cuenta** se agregan aquí.")
def listar_unidades(db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    cuentas = reglas_unidades.residentes_por_unidad(db)
    r = reglas_unidades.resumen(db)
    filas = db.query(Unidad).order_by(Unidad.apartamento).all()
    return esq.UnidadesResumenResponse(total=r.total, unidades=r.unidades, sin_coeficiente=r.sin_coeficiente, sin_cuenta=r.sin_cuenta, completo=r.completo,
                                       problema=r.problema, items=[_vista_unidad(u, cuentas) for u in filas])


@router_unidades.post("/", response_model=esq.UnidadResponse, status_code=status.HTTP_201_CREATED, summary="Registrar una unidad sin cuenta en la app",
                      description="Solo **Administrador**. Para propietarios que no usan la app: así su coeficiente cuenta en el quórum. La suma de coeficientes no puede pasar de 100 %.",
                      responses={400: {"description": "La suma pasaría de 100 %"}, 409: {"description": "Esa unidad ya existe"}})
def crear_unidad(datos: esq.UnidadCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    clave = norm_apto(datos.apartamento)
    if not clave:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la unidad.")
    if db.query(Unidad).filter(Unidad.clave == clave).first():
        raise HTTPException(status_code=409, detail="Esa unidad ya existe.")
    total = reglas_unidades.total_con(db, sumar=datos.coeficiente)
    if reglas_unidades.limite_superado(total):
        raise HTTPException(status_code=400, detail=f"Con esa unidad los coeficientes sumarían {total:g} %, y el máximo es 100 %.")
    u = Unidad(apartamento=datos.apartamento, clave=clave, coeficiente=datos.coeficiente, propietario_nombre=datos.propietario_nombre, origen="manual", activa=True)
    db.add(u)
    db.flush()
    auditar(db, admin, "Registró una unidad", "Unidad", u.id, f"{u.apartamento} · {u.coeficiente:g} %")
    db.commit()
    return _vista_unidad(u, reglas_unidades.residentes_por_unidad(db))


@router_unidades.patch("/{unidad_id}", response_model=esq.UnidadResponse, summary="Editar una unidad",
                       description="Solo **Administrador**. El coeficiente solo se edita aquí si la unidad **no** tiene residentes en la app (si los tiene, se cambia en «Usuarios»).",
                       responses={400: {"description": "Dato inválido o suma mayor a 100 %"}, 404: {"description": "No existe"}, 409: {"description": "El coeficiente se edita en Usuarios"}})
def editar_unidad(unidad_id: int, datos: esq.UnidadUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    u = db.query(Unidad).filter(Unidad.id == unidad_id).one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="La unidad no existe.")
    cuentas = reglas_unidades.residentes_por_unidad(db)
    tiene_cuenta = u.clave in cuentas
    cambios = []
    if datos.coeficiente is not None and datos.coeficiente != u.coeficiente:
        if tiene_cuenta:
            raise HTTPException(status_code=409, detail="Esta unidad tiene residentes en la app: cambia su coeficiente en «Usuarios».")
        total = reglas_unidades.total_con(db, sumar=datos.coeficiente, excluir_id=u.id) if u.activa else reglas_unidades.total_con(db, sumar=datos.coeficiente)
        if reglas_unidades.limite_superado(total):
            raise HTTPException(status_code=400, detail=f"Con ese cambio los coeficientes sumarían {total:g} %, y el máximo es 100 %.")
        cambios.append(f"coeficiente {u.coeficiente if u.coeficiente is not None else '—'} → {datos.coeficiente:g}")
        u.coeficiente = datos.coeficiente
    if datos.propietario_nombre is not None and not tiene_cuenta and datos.propietario_nombre != u.propietario_nombre:
        cambios.append("propietario")
        u.propietario_nombre = datos.propietario_nombre
    if datos.activa is not None and datos.activa != u.activa:
        if datos.activa is False and tiene_cuenta:
            raise HTTPException(status_code=409, detail="Esta unidad tiene residentes activos en la app: no se puede desactivar.")
        if datos.activa:
            total = reglas_unidades.total_con(db, sumar=u.coeficiente or 0.0)
            if reglas_unidades.limite_superado(total):
                raise HTTPException(status_code=400, detail=f"Al activarla los coeficientes sumarían {total:g} %, y el máximo es 100 %.")
        cambios.append("activada" if datos.activa else "desactivada")
        u.activa = datos.activa
    if cambios:
        auditar(db, admin, "Editó una unidad", "Unidad", u.id, f"{u.apartamento} · " + ", ".join(cambios))
        db.commit()
    return _vista_unidad(u, cuentas)


# ================================================================ utilidades de asambleas
def _unidad_de(db: Session, usuario: Usuario) -> Optional[Unidad]:
    clave = norm_apto(usuario.apartamento)
    return db.query(Unidad).filter(Unidad.clave == clave).first() if clave else None


def _visible_para(a: Asamblea, usuario: Usuario) -> bool:
    if usuario.rol == ADMIN.value:
        return True
    if usuario.rol == GUARDIA.value:
        return a.estado in (EstadoAsamblea.CONVOCADA.value, EstadoAsamblea.EN_SESION.value)
    return a.estado in ESTADOS_VISIBLES_RESIDENTE or (a.estado == EstadoAsamblea.CANCELADA.value and a.fecha_convocatoria is not None)


def _con_acceso(db: Session, asamblea_id: int, usuario: Usuario, bloquear: bool = False) -> Asamblea:
    a = reglas.obtener(db, asamblea_id, bloquear=bloquear)
    if not _visible_para(a, usuario):
        raise HTTPException(status_code=404, detail="La asamblea no existe.")          # no se revela que existe un borrador
    return a


def _vista(db: Session, a: Asamblea, usuario: Usuario) -> esq.AsambleaResponse:
    docs = reglas.documentos_adjuntos(db, a.id)
    r = esq.AsambleaResponse.model_validate(a)
    r.registro_abierto = reglas.registro_abierto(a)
    r.documentos = [esq.DocumentoAdjuntoResponse(id=d.id, titulo=d.titulo, categoria=d.categoria) for d in docs]
    r.dias_anticipacion = reglas.dias_de_anticipacion(a)
    if usuario.rol == ADMIN.value:
        r.morosos = json.loads(a.morosos_snapshot) if a.morosos_snapshot else None
    elif usuario.rol == RESIDENTE.value:
        u = _unidad_de(db, usuario)
        mi = esq.MiUnidadResponse(apartamento=u.apartamento if u else usuario.apartamento)
        if u:
            mi.presente = db.query(AsambleaAsistente.id).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.unidad_id == u.id,
                                                                AsambleaAsistente.hora_salida.is_(None)).first() is not None
            poder = (db.query(AsambleaPoder).filter(AsambleaPoder.asamblea_id == a.id, AsambleaPoder.unidad_id == u.id)
                     .order_by(AsambleaPoder.id.desc()).first())
            if poder:
                mi.poder_estado, mi.poder_id = poder.estado, poder.id
        r.mi_unidad = mi
    return r


def _residentes_activos_lista(db: Session) -> list[Usuario]:
    return [u for us in reglas_unidades.residentes_por_unidad(db).values() for u in us]


def _unidad_o_404(db: Session, unidad_id: int) -> Unidad:
    u = db.query(Unidad).filter(Unidad.id == unidad_id, Unidad.activa.is_(True)).one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail="La unidad no existe o está desactivada.")
    return u


# ================================================================ CRUD de asambleas
@router.get("/", response_model=list[esq.AsambleaListaItem], summary="Ver las asambleas",
            description="**Administrador**: todas. **Residente**: las ya convocadas (y las canceladas que se habían convocado). **Guardia**: la convocada o en sesión, para acreditar en la puerta. Más recientes primero.")
def listar(db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    q = db.query(Asamblea)
    if usuario.rol == GUARDIA.value:
        q = q.filter(Asamblea.estado.in_([EstadoAsamblea.CONVOCADA.value, EstadoAsamblea.EN_SESION.value]))
    elif usuario.rol == RESIDENTE.value:
        q = q.filter((Asamblea.estado.in_(ESTADOS_VISIBLES_RESIDENTE)) | ((Asamblea.estado == EstadoAsamblea.CANCELADA.value) & Asamblea.fecha_convocatoria.isnot(None)))
    filas = q.order_by(Asamblea.fecha_sesion.desc(), Asamblea.id.desc()).limit(MAX_ASAMBLEAS_LISTA).all()
    return [esq.AsambleaListaItem(id=a.id, titulo=a.titulo, tipo=a.tipo, modalidad=a.modalidad, estado=a.estado, fecha_sesion=a.fecha_sesion,
                                  fecha_segunda=a.fecha_segunda, registro_abierto=reglas.registro_abierto(a)) for a in filas]


@router.post("/", response_model=esq.AsambleaResponse, status_code=status.HTTP_201_CREATED, summary="Crear una asamblea (borrador)",
             description="Solo **Administrador**. Nace en **Borrador**: los propietarios no la ven hasta que la convoques. Si no indicas la segunda convocatoria, se sugiere el "
                         "**tercer día hábil siguiente a las 8 p. m.** (Art. 41 de la Ley 675; con los festivos de Colombia).",
             responses={400: {"description": "Datos inválidos"}})
def crear(datos: esq.AsambleaCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    ahora = ahora_utc()
    if datos.fecha_sesion <= ahora:
        raise HTTPException(status_code=400, detail="La fecha de la asamblea debe ser futura.")
    segunda = datos.fecha_segunda or calendario_co.segunda_convocatoria(datos.fecha_sesion, config.ASAMBLEA_SABADO_HABIL)
    if segunda <= datos.fecha_sesion:
        raise HTTPException(status_code=400, detail="La segunda convocatoria debe ser después de la primera.")
    a = Asamblea(titulo=datos.titulo, tipo=datos.tipo.value, modalidad=datos.modalidad.value, estado=EstadoAsamblea.BORRADOR.value, orden_del_dia=datos.orden_del_dia,
                 fecha_sesion=datos.fecha_sesion, fecha_segunda=segunda, lugar=datos.lugar, url_videollamada=datos.url_videollamada,
                 instrucciones_virtual=datos.instrucciones_virtual, max_poderes=datos.max_poderes if datos.max_poderes is not None else config.ASAMBLEA_MAX_PODERES,
                 restringe_mora=datos.restringe_mora, creada_por=admin.id)
    db.add(a)
    db.flush()
    reglas.registrar_evento(db, a.id, "Creada", admin, detalle=f"{a.tipo} · {a.modalidad}")
    auditar(db, admin, "Creó una asamblea", "Asamblea", a.id, f"{a.titulo} · {a.tipo}")
    db.commit()
    return _vista(db, a, admin)


@router.get("/{asamblea_id}", response_model=esq.AsambleaResponse, summary="Ver el detalle de una asamblea",
            description="Roles: **Administrador**, **Residente** y **Guardia** (según el estado). Incluye documentos adjuntos y, para el residente, el estado de su unidad y de su poder. "
                        "La relación de morosos solo la ve el administrador.", responses={404: {"description": "No existe"}})
def detalle(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    return _vista(db, _con_acceso(db, asamblea_id, usuario), usuario)


@router.patch("/{asamblea_id}", response_model=esq.AsambleaResponse, summary="Editar una asamblea en borrador",
              description="Solo **Administrador** y solo en **Borrador**: una convocatoria ya enviada no se edita (se cancela y se crea otra), para que lo enviado y lo registrado coincidan.",
              responses={404: {"description": "No existe"}, 409: {"description": "Ya fue convocada"}})
def editar(asamblea_id: int, datos: esq.AsambleaUpdate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.BORRADOR, accion="editar")
    cambios = datos.model_dump(exclude_unset=True)
    for campo in ("tipo", "modalidad"):
        if campo in cambios and cambios[campo] is not None:
            cambios[campo] = cambios[campo].value
    nueva_fecha = "fecha_sesion" in cambios and cambios["fecha_sesion"] is not None
    for campo in ("titulo", "tipo", "modalidad", "orden_del_dia", "max_poderes", "restringe_mora", "fecha_sesion"):
        if campo in cambios and cambios[campo] is not None:
            setattr(a, campo, cambios[campo])
    for campo in ("lugar", "url_videollamada", "instrucciones_virtual"):
        if campo in cambios:
            setattr(a, campo, cambios[campo])
    if "fecha_segunda" in cambios and cambios["fecha_segunda"] is not None:
        a.fecha_segunda = cambios["fecha_segunda"]
    elif nueva_fecha:
        a.fecha_segunda = calendario_co.segunda_convocatoria(a.fecha_sesion, config.ASAMBLEA_SABADO_HABIL)
    if a.fecha_sesion <= ahora_utc():
        raise HTTPException(status_code=400, detail="La fecha de la asamblea debe ser futura.")
    if a.fecha_segunda <= a.fecha_sesion:
        raise HTTPException(status_code=400, detail="La segunda convocatoria debe ser después de la primera.")
    auditar(db, admin, "Editó una asamblea", "Asamblea", a.id, a.titulo)
    db.commit()
    return _vista(db, a, admin)


@router.post("/{asamblea_id}/documentos", response_model=esq.AsambleaResponse, status_code=status.HTTP_201_CREATED, summary="Adjuntar un documento a la convocatoria",
             description="Solo **Administrador**, en **Borrador**. Escoge un PDF ya subido en «Documentos» (estados financieros, informe de gestión, presupuesto…).",
             responses={404: {"description": "No existe la asamblea o el documento"}, 409: {"description": "Ya adjunto o asamblea ya convocada"}})
def adjuntar(asamblea_id: int, datos: esq.AdjuntarDocumento, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.BORRADOR, accion="adjuntar documentos")
    doc = db.query(Documento).filter(Documento.id == datos.documento_id).one_or_none()
    if doc is None:
        raise HTTPException(status_code=404, detail="El documento no existe.")
    if db.query(AsambleaDocumento.id).filter(AsambleaDocumento.asamblea_id == a.id, AsambleaDocumento.documento_id == doc.id).first():
        raise HTTPException(status_code=409, detail="Ese documento ya está adjunto.")
    db.add(AsambleaDocumento(asamblea_id=a.id, documento_id=doc.id))
    auditar(db, admin, "Adjuntó un documento a una asamblea", "Asamblea", a.id, doc.titulo)
    db.commit()
    return _vista(db, a, admin)


@router.delete("/{asamblea_id}/documentos/{documento_id}", response_model=esq.AsambleaResponse, summary="Quitar un documento de la convocatoria",
               description="Solo **Administrador**, en **Borrador**.", responses={404: {"description": "No estaba adjunto"}, 409: {"description": "Ya fue convocada"}})
def desadjuntar(asamblea_id: int, documento_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.BORRADOR, accion="quitar documentos")
    fila = db.query(AsambleaDocumento).filter(AsambleaDocumento.asamblea_id == a.id, AsambleaDocumento.documento_id == documento_id).one_or_none()
    if fila is None:
        raise HTTPException(status_code=404, detail="Ese documento no estaba adjunto.")
    db.delete(fila)
    db.commit()
    return _vista(db, a, admin)


# ================================================================ ciclo de vida
@router.post("/{asamblea_id}/convocar", response_model=esq.AdvertenciaResponse, summary="Enviar la convocatoria",
             description="Solo **Administrador**. Valida los plazos de la Ley 675 (Art. 39: **15 días calendario completos** en la ordinaria), exige el orden del día, los medios tecnológicos "
                         "si es virtual o mixta y —en la ordinaria— los **estados financieros** adjuntos. Guarda la **huella** del contenido enviado, la **relación de morosos** y deja en la bitácora "
                         "fecha y hora del aviso a cada propietario. Las unidades sin cuenta en la app quedan «pendientes»: hay que entregarles la convocatoria por escrito.",
             responses={400: {"description": "No cumple los requisitos"}, 409: {"description": "Ya fue convocada"}})
def convocar(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)                      # antes del candado: sincronizar hace commit
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.BORRADOR, accion="convocar")
    ahora = ahora_utc()
    if len((a.orden_del_dia or "").strip()) < 10:
        raise HTTPException(status_code=400, detail="Escribe el orden del día antes de convocar.")
    if a.modalidad in (ModalidadAsamblea.PRESENCIAL.value, ModalidadAsamblea.MIXTA.value) and not a.lugar:
        raise HTTPException(status_code=400, detail="Indica el lugar de la reunión.")
    if a.modalidad in (ModalidadAsamblea.VIRTUAL.value, ModalidadAsamblea.MIXTA.value) and not (a.url_videollamada or a.instrucciones_virtual):
        raise HTTPException(status_code=400, detail="En una reunión virtual o mixta la convocatoria debe indicar los medios tecnológicos: pon el enlace de la videollamada o las instrucciones de conexión.")
    reglas.validar_plazo(a, ahora)
    if a.fecha_segunda <= a.fecha_sesion:
        raise HTTPException(status_code=400, detail="La segunda convocatoria debe ser después de la primera.")
    docs = reglas.documentos_adjuntos(db, a.id)
    if a.tipo == TipoAsamblea.ORDINARIA.value and config.ASAMBLEA_EXIGE_FINANCIEROS and not any(d.categoria == CategoriaDocumento.FINANCIERO.value for d in docs):
        raise HTTPException(status_code=400, detail="La asamblea ordinaria revisa las cuentas del año: adjunta los estados financieros (documento de categoría «Financiero»).")
    resumen = reglas_unidades.resumen(db)
    advertencias = []
    if resumen.problema:
        advertencias.append(f"Base de coeficientes incompleta: {resumen.problema} No podrás instalar la asamblea hasta corregirlo.")
    lista_morosos = reglas.morosos(db)
    contenido = reglas.contenido_convocatoria(a, docs, lista_morosos)
    a.estado = EstadoAsamblea.CONVOCADA.value
    a.fecha_convocatoria = ahora
    a.morosos_snapshot = json.dumps(lista_morosos, ensure_ascii=False)
    a.convocatoria_hash = reglas.huella_convocatoria(contenido)

    cadena = reglas.Cadena(db, a.id)
    cadena.agregar("Convocada", admin, detalle=f"{a.tipo} · sesión {reglas.fmt_local(a.fecha_sesion)} · huella {a.convocatoria_hash[:12]}")
    por_unidad = reglas_unidades.residentes_por_unidad(db)
    con_correo = notificaciones.correo_activo()
    sin_cuenta = 0
    for u in db.query(Unidad).filter(Unidad.activa.is_(True)).order_by(Unidad.id).all():
        residentes = por_unidad.get(u.clave, [])
        if residentes:
            canal = "App" + (" + correo" if con_correo and any(r.email for r in residentes) else "")
            cadena.agregar("Notificada", admin, unidad_id=u.id, detalle=f"Canal: {canal}")
        else:
            sin_cuenta += 1
            cadena.agregar("SinCuenta", admin, unidad_id=u.id, detalle="Sin cuenta en la app: entregar la convocatoria por escrito")
    if sin_cuenta:
        advertencias.append(f"{sin_cuenta} unidad(es) no tienen cuenta en la app: entrégales la convocatoria (PDF) por escrito y regístralo en «Entregas».")
    todos = [r for rs in por_unidad.values() for r in rs]
    notificar(db, todos, f"Convocatoria: {a.titulo}", f"{a.tipo} · {reglas.fmt_local(a.fecha_sesion)} · {a.modalidad}. Revisa el orden del día en Asambleas.", "#/asambleas", correo=True)
    auditar(db, admin, "Convocó una asamblea", "Asamblea", a.id, f"{a.titulo} · {len(todos)} residentes avisados")
    db.commit()
    return esq.AdvertenciaResponse(asamblea=_vista(db, a, admin), advertencias=advertencias)


@router.get("/{asamblea_id}/entregas", response_model=list[esq.EntregaResponse], summary="Ver cómo se avisó a cada propietario",
            description="Solo **Administrador**. Por unidad: avisada por la **App**, entregada **Manual**mente o **Pendiente** (sin cuenta y sin entrega registrada).",
            responses={404: {"description": "No existe"}})
def entregas(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id)
    eventos = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a.id, AsambleaEvento.tipo.in_(["Notificada", "EntregaManual"]),
                                              AsambleaEvento.unidad_id.isnot(None)).order_by(AsambleaEvento.secuencia).all()
    estado: dict[int, tuple[str, Optional[str]]] = {}
    for e in eventos:
        estado[e.unidad_id] = ("App" if e.tipo == "Notificada" else "Manual", e.detalle)
    unidades = db.query(Unidad).filter(Unidad.activa.is_(True)).order_by(Unidad.apartamento).all() if a.estado != EstadoAsamblea.BORRADOR.value else []
    return [esq.EntregaResponse(unidad_id=u.id, apartamento=u.apartamento, propietario_nombre=u.propietario_nombre,
                                estado=estado.get(u.id, ("Pendiente", None))[0], detalle=estado.get(u.id, ("Pendiente", None))[1]) for u in unidades]


@router.post("/{asamblea_id}/entregas-manuales", response_model=MensajeResponse, status_code=status.HTTP_201_CREATED, summary="Registrar una entrega manual de la convocatoria",
             description="Solo **Administrador**. Para propietarios sin cuenta en la app: deja en la bitácora que se les entregó la convocatoria (por escrito, correo o WhatsApp) y cuándo.",
             responses={404: {"description": "No existe"}, 409: {"description": "La asamblea no está convocada"}})
def entrega_manual(asamblea_id: int, datos: esq.EntregaManual, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, accion="registrar entregas")
    u = _unidad_o_404(db, datos.unidad_id)
    reglas.registrar_evento(db, a.id, "EntregaManual", admin, unidad_id=u.id, detalle=f"Canal: {datos.canal}" + (f" · {datos.nota}" if datos.nota else ""))
    db.commit()
    return MensajeResponse(mensaje=f"Quedó registrada la entrega a {u.apartamento}.")


@router.post("/{asamblea_id}/sin-quorum", response_model=esq.AsambleaResponse, summary="Declarar que la primera convocatoria no logró quórum",
             description="Solo **Administrador**. Pasada la hora citada y sin más de la mitad de los coeficientes presentes, deja constancia y habilita la **segunda convocatoria** "
                         "(Art. 41: se delibera con cualquier número plural de propietarios). Los asistentes registrados se liberan: deben acreditarse de nuevo.",
             responses={409: {"description": "Aún no es la hora, ya hay quórum o ya se declaró"}})
def sin_quorum(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, accion="declarar sin quórum")
    ahora = ahora_utc()
    if a.sin_quorum_en:
        raise HTTPException(status_code=409, detail="Ya se declaró que la primera convocatoria no logró quórum.")
    if ahora < a.fecha_sesion:
        raise HTTPException(status_code=409, detail=f"Aún no es la hora de la primera convocatoria ({reglas.fmt_local(a.fecha_sesion)}).")
    q = reglas.quorum(db, a)
    if q["hay_quorum"]:
        raise HTTPException(status_code=409, detail=f"Ya hay quórum ({q['porcentaje']:g} %): instala la asamblea.")
    liberados = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.hora_salida.is_(None)).all()
    for p in liberados:
        p.hora_salida = ahora
    a.sin_quorum_en = ahora
    reglas.registrar_evento(db, a.id, "SinQuorum", admin, detalle=f"Quórum {q['porcentaje']:g} % ({q['unidades_presentes']} unidades). Segunda convocatoria: {reglas.fmt_local(a.fecha_segunda)}")
    notificar(db, _residentes_activos_lista(db), f"Sin quórum: segunda convocatoria de «{a.titulo}»",
              f"Se realizará el {reglas.fmt_local(a.fecha_segunda)} y se decidirá con los propietarios que asistan (Art. 41 Ley 675).", "#/asambleas", correo=True)
    auditar(db, admin, "Declaró sin quórum", "Asamblea", a.id, f"{q['porcentaje']:g} %")
    db.commit()
    return _vista(db, a, admin)


@router.post("/{asamblea_id}/instalar", response_model=esq.AsambleaResponse, summary="Instalar la asamblea",
             description="Solo **Administrador**. **Primera convocatoria**: exige más del 50 % de los coeficientes presentes. **Segunda**: exige haber declarado antes «sin quórum», que ya sea su "
                         "fecha y que haya un número plural de propietarios (2 o más unidades). Exige que los coeficientes sumen 100 %. Guarda el quórum inicial.",
             responses={409: {"description": "Aún no es la hora, no hay quórum o la base de coeficientes está incompleta"}})
def instalar(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, accion="instalar")
    ahora = ahora_utc()
    hito = a.fecha_segunda if a.sin_quorum_en else a.fecha_sesion
    if ahora < hito - reglas.TOLERANCIA_INSTALAR:
        raise HTTPException(status_code=409, detail=f"Aún no es la hora: la {'segunda' if a.sin_quorum_en else 'primera'} convocatoria es el {reglas.fmt_local(hito)}.")
    q = reglas.quorum(db, a)
    if not q["base_completa"]:
        raise HTTPException(status_code=409, detail=f"No se puede calcular el quórum: {q['problema_base']} Corrígelo en «Unidades y coeficientes».")
    if q["hay_quorum"]:
        numero = 2 if a.sin_quorum_en else 1
    elif not a.sin_quorum_en:
        raise HTTPException(status_code=409, detail=f"Sin quórum: hay {q['porcentaje']:g} % y se necesita más del 50 %. Si pasada la hora no se logra, declara «sin quórum» para pasar a la segunda convocatoria.")
    elif q["unidades_presentes"] < 2:
        raise HTTPException(status_code=409, detail="La segunda convocatoria necesita un número plural de propietarios: se requieren al menos 2 unidades presentes.")
    else:
        numero = 2
    a.estado = EstadoAsamblea.EN_SESION.value
    a.convocatoria_numero = numero
    a.instalada_en = ahora
    a.quorum_inicial = q["porcentaje"]
    reglas.registrar_evento(db, a.id, "Instalada", admin, detalle=f"{numero}.ª convocatoria · quórum {q['porcentaje']:g} % · {q['unidades_presentes']} unidades")
    auditar(db, admin, "Instaló una asamblea", "Asamblea", a.id, f"{numero}.ª convocatoria · {q['porcentaje']:g} %")
    db.commit()
    return _vista(db, a, admin)


@router.post("/{asamblea_id}/cerrar", response_model=esq.AsambleaResponse, summary="Cerrar la asamblea",
             description="Solo **Administrador**. Guarda el quórum final (los coeficientes presentes al cierre).", responses={409: {"description": "No está en sesión"}})
def cerrar(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.EN_SESION, accion="cerrar")
    q = reglas.quorum(db, a)
    a.estado = EstadoAsamblea.CERRADA.value
    a.cerrada_en = ahora_utc()
    a.quorum_final = q["porcentaje"]
    reglas.registrar_evento(db, a.id, "Cerrada", admin, detalle=f"Quórum final {q['porcentaje']:g} % · {q['unidades_presentes']} unidades")
    auditar(db, admin, "Cerró una asamblea", "Asamblea", a.id, f"quórum final {q['porcentaje']:g} %")
    db.commit()
    return _vista(db, a, admin)


@router.post("/{asamblea_id}/cancelar", response_model=esq.AsambleaResponse, summary="Cancelar la asamblea",
             description="Solo **Administrador**, antes de instalarla. Si ya estaba convocada, avisa a los propietarios.", responses={409: {"description": "Ya está en sesión o cerrada"}})
def cancelar(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.BORRADOR, EstadoAsamblea.CONVOCADA, accion="cancelar")
    estaba_convocada = a.estado == EstadoAsamblea.CONVOCADA.value
    a.estado = EstadoAsamblea.CANCELADA.value
    reglas.registrar_evento(db, a.id, "Cancelada", admin)
    if estaba_convocada:
        notificar(db, _residentes_activos_lista(db), f"Se canceló la asamblea «{a.titulo}»", "El administrador la canceló. Te avisaremos si se convoca de nuevo.", "#/asambleas", correo=True)
    auditar(db, admin, "Canceló una asamblea", "Asamblea", a.id, a.titulo)
    db.commit()
    return _vista(db, a, admin)


# ================================================================ quórum y acreditación de asistentes
@router.get("/{asamblea_id}/quorum", summary="Quórum en vivo",
            description="Roles: **Administrador**, **Residente** y **Guardia**. Suma del coeficiente de quienes están presentes sobre el 100 % del conjunto. Alimenta el «termómetro» de la pantalla grande. "
                        "Hay quórum deliberatorio con **más** del 50 % (Art. 45).", responses={404: {"description": "No existe"}})
def ver_quorum(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    a = _con_acceso(db, asamblea_id, usuario)
    reglas_unidades.sincronizar(db)
    q = reglas.quorum(db, a)
    q.update({"estado": a.estado, "convocatoria_numero": a.convocatoria_numero, "sin_quorum_en": a.sin_quorum_en, "registro_abierto": reglas.registro_abierto(a),
              "fecha_sesion": a.fecha_sesion, "fecha_segunda": a.fecha_segunda, "titulo": a.titulo})
    return q


def _vista_asistente(p: AsambleaAsistente, apartamento: str) -> esq.AsistenteResponse:
    return esq.AsistenteResponse(id=p.id, unidad_id=p.unidad_id, apartamento=apartamento, nombre=p.nombre, documento=p.documento, es_apoderado=p.es_apoderado,
                                 modalidad_ingreso=p.modalidad_ingreso, hora_ingreso=p.hora_ingreso, hora_salida=p.hora_salida, presente=p.hora_salida is None,
                                 coeficiente_acreditado=p.coeficiente_acreditado, en_mora=p.en_mora, con_voto=p.con_voto)


def _exige_registro_abierto(a: Asamblea) -> None:
    if reglas.registro_abierto(a):
        return
    if a.estado == EstadoAsamblea.CONVOCADA.value:
        hito = a.fecha_segunda if a.sin_quorum_en else a.fecha_sesion
        raise HTTPException(status_code=409, detail=f"El registro de asistentes abre 3 horas antes de la reunión ({reglas.fmt_local(hito - reglas.VENTANA_REGISTRO)}).")
    raise HTTPException(status_code=409, detail=f"No se puede registrar asistencia: la asamblea está «{a.estado}».")


def _acreditar(db: Session, a: Asamblea, u: Unidad, actor: Usuario, tipo: str, nombre: Optional[str], documento: Optional[str],
               poder: Optional[AsambleaPoder], modalidad: str, usuario_propio: Optional[Usuario] = None) -> tuple[AsambleaAsistente, dict]:
    """Registra (o reabre) la presencia de una unidad. Toma una «foto» del coeficiente y de la mora; deja el movimiento y el quórum resultante en la bitácora."""
    reglas.valida_modalidad_ingreso(a, modalidad)
    if u.coeficiente is None or u.coeficiente <= 0:
        raise HTTPException(status_code=400, detail=f"La unidad {u.apartamento} no tiene coeficiente: regístralo en «Unidades y coeficientes».")
    residentes = reglas_unidades.residentes_por_unidad(db).get(u.clave, [])
    es_apoderado = tipo == "Apoderado"
    usuario_id: Optional[int] = None
    if es_apoderado:
        if poder is None:
            raise HTTPException(status_code=400, detail="Para acreditar a un apoderado, escoge un poder aprobado.")
        if poder.estado != EstadoPoder.APROBADO.value or poder.asamblea_id != a.id or poder.unidad_id != u.id:
            raise HTTPException(status_code=400, detail="Ese poder no está aprobado para esta unidad en esta asamblea.")
        if reglas.usuario_es_personal(db, poder.apoderado_usuario_id):
            raise HTTPException(status_code=400, detail="El administrador y el personal del conjunto no pueden representar a otros propietarios.")
        usados = db.query(func.count(AsambleaAsistente.id)).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.es_apoderado.is_(True),
                                                                    AsambleaAsistente.documento == poder.apoderado_documento, AsambleaAsistente.unidad_id != u.id).scalar() or 0
        if usados >= a.max_poderes:
            raise HTTPException(status_code=400, detail=f"{poder.apoderado_nombre} ya representa a {usados} unidad(es): el máximo en esta asamblea es {a.max_poderes}.")
        nombre, documento, usuario_id = poder.apoderado_nombre, poder.apoderado_documento, poder.apoderado_usuario_id
    else:
        if usuario_propio is not None:
            nombre, usuario_id = usuario_propio.nombre_completo, usuario_propio.id
        else:
            if not nombre and not residentes:
                raise HTTPException(status_code=400, detail="Esta unidad no tiene residentes en la app: escribe el nombre de quien asiste.")
            if not nombre:
                nombre, usuario_id = residentes[0].nombre_completo, residentes[0].id
            else:
                coincide = next((r for r in residentes if r.nombre_completo.strip().casefold() == nombre.strip().casefold()), None)
                usuario_id = coincide.id if coincide else None
    mora = reglas_unidades.en_mora(residentes)
    con_voto = not (a.restringe_mora and mora)
    ahora = ahora_utc()
    fila = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.unidad_id == u.id).one_or_none()
    reingreso = fila is not None
    if fila is not None and fila.hora_salida is None:
        raise HTTPException(status_code=409, detail=f"La unidad {u.apartamento} ya está acreditada ({fila.nombre}).")
    if fila is None:
        fila = AsambleaAsistente(asamblea_id=a.id, unidad_id=u.id)
        db.add(fila)
    fila.usuario_id, fila.nombre, fila.documento, fila.es_apoderado, fila.poder_id = usuario_id, nombre[:120], (documento or None), es_apoderado, poder.id if poder else None
    fila.modalidad_ingreso, fila.hora_ingreso, fila.hora_salida = modalidad, ahora, None
    fila.coeficiente_acreditado, fila.en_mora, fila.con_voto, fila.registrado_por = u.coeficiente, mora, con_voto, actor.id
    db.flush()
    q = reglas.quorum(db, a)
    reglas.registrar_evento(db, a.id, "Reingreso" if reingreso else "Acreditó", actor, unidad_id=u.id,
                            detalle=f"{fila.nombre} · {'Apoderado' if es_apoderado else 'Propietario'} · {modalidad} · {u.coeficiente:g} % · quórum {q['porcentaje']:g} %"
                                    + ("" if con_voto else " · sin voto (mora)"))
    return fila, q


@router.get("/{asamblea_id}/unidades", response_model=list[esq.UnidadEstadoResponse], summary="Tablero de acreditación",
            description="Roles: **Administrador** y **Guardia**. Todas las unidades con su estado en esta asamblea (presente, ya estuvo, poder aprobado, mora): lo que se necesita en la puerta.",
            responses={404: {"description": "No existe"}})
def tablero(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    reglas_unidades.sincronizar(db)
    a = _con_acceso(db, asamblea_id, usuario)
    cuentas = reglas_unidades.residentes_por_unidad(db)
    filas = {p.unidad_id: p for p in db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id).all()}
    poderes = {p.unidad_id: p for p in db.query(AsambleaPoder).filter(AsambleaPoder.asamblea_id == a.id, AsambleaPoder.estado == EstadoPoder.APROBADO.value).all()}
    salida = []
    for u in db.query(Unidad).filter(Unidad.activa.is_(True)).order_by(Unidad.apartamento).all():
        p, pod = filas.get(u.id), poderes.get(u.id)
        salida.append(esq.UnidadEstadoResponse(unidad_id=u.id, apartamento=u.apartamento, coeficiente=u.coeficiente, propietario_nombre=u.propietario_nombre,
                                               tiene_cuenta=u.clave in cuentas, en_mora=reglas_unidades.en_mora(cuentas.get(u.clave, [])),
                                               presente=bool(p and p.hora_salida is None), ha_estado=p is not None,
                                               poder_id=pod.id if pod else None, apoderado_nombre=pod.apoderado_nombre if pod else None))
    return salida


@router.get("/{asamblea_id}/asistentes", response_model=list[esq.AsistenteResponse], summary="Ver los asistentes",
            description="Roles: **Administrador** y **Guardia**. Una fila por unidad que se ha acreditado (presentes primero).", responses={404: {"description": "No existe"}})
def asistentes(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    a = _con_acceso(db, asamblea_id, usuario)
    nombres = {u.id: u.apartamento for u in db.query(Unidad).all()}
    filas = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id).all()
    filas.sort(key=lambda p: (p.hora_salida is not None, nombres.get(p.unidad_id, "")))
    return [_vista_asistente(p, nombres.get(p.unidad_id, "?")) for p in filas]


@router.post("/{asamblea_id}/asistentes", response_model=esq.AcreditacionResponse, status_code=status.HTTP_201_CREATED, summary="Acreditar a un asistente (presencial o virtual)",
             description="Roles: **Administrador** y **Guardia**. Registra que una unidad está presente, sea el **propietario** o un **apoderado** con poder aprobado. Copia el coeficiente (así un cambio posterior no altera el quórum), "
                         "suma al quórum y deja la hora en la bitácora. Una unidad cuenta **una sola vez**. El registro abre 3 horas antes de la reunión.",
             responses={400: {"description": "Dato inválido o regla incumplida (poder, límite de poderes, personal del conjunto)"}, 409: {"description": "Ya acreditada o registro cerrado"}})
def acreditar(asamblea_id: int, datos: esq.AcreditarCreate, db: Session = Depends(get_db), actor: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    reglas_unidades.sincronizar(db)
    a = _con_acceso(db, asamblea_id, actor, bloquear=True)
    _exige_registro_abierto(a)
    u = _unidad_o_404(db, datos.unidad_id)
    poder = None
    if datos.tipo == "Apoderado":
        poder = db.query(AsambleaPoder).filter(AsambleaPoder.id == (datos.poder_id or 0)).one_or_none()
    fila, q = _acreditar(db, a, u, actor, datos.tipo, datos.nombre, datos.documento, poder, datos.modalidad)
    db.commit()
    return esq.AcreditacionResponse(asistente=_vista_asistente(fila, u.apartamento), quorum=q)


@router.post("/{asamblea_id}/asistentes/{asistente_id}/salida", response_model=esq.AcreditacionResponse, summary="Registrar la salida de un asistente",
             description="Roles: **Administrador** y **Guardia**. Si alguien se retira antes de terminar, su coeficiente deja de contar y el quórum baja.",
             responses={404: {"description": "No existe"}, 409: {"description": "Ya había salido"}})
def salida(asamblea_id: int, asistente_id: int, db: Session = Depends(get_db), actor: Usuario = Depends(requiere_roles(ADMIN, GUARDIA))):
    a = _con_acceso(db, asamblea_id, actor, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="registrar salidas")
    p = db.query(AsambleaAsistente).filter(AsambleaAsistente.id == asistente_id, AsambleaAsistente.asamblea_id == a.id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="Ese asistente no está en esta asamblea.")
    if p.hora_salida is not None:
        raise HTTPException(status_code=409, detail="Esa persona ya había salido.")
    p.hora_salida = ahora_utc()
    db.flush()
    q = reglas.quorum(db, a)
    apto = db.query(Unidad.apartamento).filter(Unidad.id == p.unidad_id).scalar() or "?"
    reglas.registrar_evento(db, a.id, "Salió", actor, unidad_id=p.unidad_id, detalle=f"{p.nombre} · quórum {q['porcentaje']:g} %")
    db.commit()
    return esq.AcreditacionResponse(asistente=_vista_asistente(p, apto), quorum=q)


@router.post("/{asamblea_id}/ingresar", response_model=esq.AcreditacionResponse, status_code=status.HTTP_201_CREATED, summary="Conectarme a la asamblea virtual",
             description="Solo **Residente**. Acredita a mi propia unidad como asistente **virtual** (solo en asambleas virtuales o mixtas, cuando el registro está abierto). "
                         "Queda guardada la hora de conexión.", responses={400: {"description": "La asamblea es presencial o mi unidad no tiene coeficiente"}, 409: {"description": "Mi unidad ya está acreditada o el registro está cerrado"}})
def ingresar(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE))):
    reglas_unidades.sincronizar(db)
    a = _con_acceso(db, asamblea_id, usuario, bloquear=True)
    _exige_registro_abierto(a)
    u = _unidad_de(db, usuario)
    if u is None or not u.activa:
        raise HTTPException(status_code=400, detail="Tu usuario no tiene una unidad registrada: pídele al administrador que complete tu apartamento.")
    fila, q = _acreditar(db, a, u, usuario, "Propietario", None, None, None, "Virtual", usuario_propio=usuario)
    db.commit()
    return esq.AcreditacionResponse(asistente=_vista_asistente(fila, u.apartamento), quorum=q)


@router.post("/{asamblea_id}/salir", response_model=esq.AcreditacionResponse, summary="Desconectarme de la asamblea virtual",
             description="Solo **Residente**. Registra mi salida (mi coeficiente deja de contar en el quórum). Solo puede salir quien se conectó con su propia cuenta.",
             responses={404: {"description": "No estás conectado"}})
def salir(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE))):
    a = _con_acceso(db, asamblea_id, usuario, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="registrar salidas")
    u = _unidad_de(db, usuario)
    p = (db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.unidad_id == u.id, AsambleaAsistente.usuario_id == usuario.id,
                                            AsambleaAsistente.hora_salida.is_(None)).one_or_none()) if u else None
    if p is None:
        raise HTTPException(status_code=404, detail="No estás conectado a esta asamblea con tu cuenta.")
    p.hora_salida = ahora_utc()
    db.flush()
    q = reglas.quorum(db, a)
    reglas.registrar_evento(db, a.id, "Salió", usuario, unidad_id=p.unidad_id, detalle=f"{p.nombre} · quórum {q['porcentaje']:g} %")
    db.commit()
    return esq.AcreditacionResponse(asistente=_vista_asistente(p, u.apartamento), quorum=q)


# ================================================================ poderes
def _vista_poder(db: Session, p: AsambleaPoder, a: Asamblea, aptos: dict[int, str], nombres: dict[int, str]) -> esq.PoderResponse:
    return esq.PoderResponse(id=p.id, asamblea_id=p.asamblea_id, unidad_id=p.unidad_id, apartamento=aptos.get(p.unidad_id, "?"), apoderado_nombre=p.apoderado_nombre,
                             apoderado_documento=p.apoderado_documento, apoderado_usuario_id=p.apoderado_usuario_id, tipo_archivo=p.tipo_archivo, estado=p.estado,
                             motivo=p.motivo, subido_por=nombres.get(p.subido_por), revisado_por=nombres.get(p.revisado_por), revisado_en=p.revisado_en,
                             fecha_creacion=p.fecha_creacion, poderes_del_apoderado=reglas.poderes_del_apoderado(db, a, p.apoderado_documento))


def _nombres_aptos(db: Session, poderes: list[AsambleaPoder]) -> tuple[dict[int, str], dict[int, str]]:
    aptos = {u.id: u.apartamento for u in db.query(Unidad).filter(Unidad.id.in_({p.unidad_id for p in poderes})).all()} if poderes else {}
    ids = {i for p in poderes for i in (p.subido_por, p.revisado_por) if i}
    nombres = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if ids else {}
    return aptos, nombres


@router.post("/{asamblea_id}/poderes", response_model=esq.PoderResponse, status_code=status.HTTP_201_CREATED, summary="Subir un poder",
             description="**Residente** (para su unidad) o **Administrador** (para cualquier unidad, indicando `unidad_id`). Archivo **PDF o foto** (JPG/PNG/WEBP) del poder escrito, firmado por el propietario. "
                         "Queda **Pendiente** hasta que el administrador lo apruebe, antes de la reunión: así no hay filas eternas en la puerta. Solo un poder activo por unidad.",
             responses={400: {"description": "Dato o archivo inválido"}, 409: {"description": "La unidad ya tiene un poder o la asamblea no admite poderes"}})
async def subir_poder(asamblea_id: int, apoderado_nombre: str = Form(..., min_length=3, max_length=120), apoderado_documento: str = Form(..., min_length=5, max_length=30),
                      unidad_id: Optional[int] = Form(None), archivo: UploadFile = File(..., description="PDF o foto del poder"),
                      db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE))):
    reglas_unidades.sincronizar(db)
    a = _con_acceso(db, asamblea_id, usuario, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="recibir poderes")
    if usuario.rol == ADMIN.value:
        if not unidad_id:
            raise HTTPException(status_code=400, detail="Indica la unidad que otorga el poder.")
        u = _unidad_o_404(db, unidad_id)
    else:
        u = _unidad_de(db, usuario)
        if u is None or not u.activa:
            raise HTTPException(status_code=400, detail="Tu usuario no tiene una unidad registrada: pídele al administrador que complete tu apartamento.")
    documento = reglas.normaliza_documento(apoderado_documento)
    nombre = " ".join(apoderado_nombre.split())
    if len(documento) < 5 or len(nombre) < 3:
        raise HTTPException(status_code=400, detail="Escribe el nombre completo y el número de documento del apoderado.")
    if db.query(AsambleaPoder.id).filter(AsambleaPoder.asamblea_id == a.id, AsambleaPoder.unidad_id == u.id,
                                         AsambleaPoder.estado.in_([EstadoPoder.PENDIENTE.value, EstadoPoder.APROBADO.value])).first():
        raise HTTPException(status_code=409, detail="Esta unidad ya tiene un poder pendiente o aprobado para esta asamblea.")
    if db.query(AsambleaAsistente.id).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.unidad_id == u.id, AsambleaAsistente.hora_salida.is_(None)).first():
        raise HTTPException(status_code=409, detail="Esta unidad ya está presente en la asamblea.")
    if archivo.content_type in ("application/pdf", "application/x-pdf"):
        guardado, _ = await guardar_pdf_validado(archivo)
        tipo_archivo = "pdf"
    else:
        guardado, tipo_archivo = await guardar_imagen_validada(archivo), "imagen"     # valida que sea una imagen real o responde 400
    p = AsambleaPoder(asamblea_id=a.id, unidad_id=u.id, apoderado_nombre=nombre, apoderado_documento=documento, archivo=guardado, tipo_archivo=tipo_archivo,
                      estado=EstadoPoder.PENDIENTE.value, subido_por=usuario.id)
    db.add(p)
    db.flush()
    reglas.registrar_evento(db, a.id, "PoderRecibido", usuario, unidad_id=u.id, detalle=f"Apoderado: {nombre}")
    admins = notificaciones.usuarios_activos(db, [ADMIN])
    if admins:
        notificar(db, admins, "Poder por revisar", f"{u.apartamento} subió un poder para «{a.titulo}».", "#/asambleas")
    db.commit()
    aptos, nombres = _nombres_aptos(db, [p])
    return _vista_poder(db, p, a, aptos, nombres)


@router.get("/{asamblea_id}/poderes", response_model=list[esq.PoderResponse], summary="Ver los poderes",
            description="**Administrador**: todos. **Residente**: los de su unidad. **Guardia**: solo los aprobados (para identificar al apoderado en la puerta).", responses={404: {"description": "No existe"}})
def listar_poderes(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    a = _con_acceso(db, asamblea_id, usuario)
    q = db.query(AsambleaPoder).filter(AsambleaPoder.asamblea_id == a.id)
    if usuario.rol == GUARDIA.value:
        q = q.filter(AsambleaPoder.estado == EstadoPoder.APROBADO.value)
    elif usuario.rol == RESIDENTE.value:
        u = _unidad_de(db, usuario)
        if u is None:
            return []
        q = q.filter(AsambleaPoder.unidad_id == u.id)
    filas = q.order_by(AsambleaPoder.id.desc()).all()
    aptos, nombres = _nombres_aptos(db, filas)
    return [_vista_poder(db, p, a, aptos, nombres) for p in filas]


def _poder_de(db: Session, a: Asamblea, poder_id: int) -> AsambleaPoder:
    p = db.query(AsambleaPoder).filter(AsambleaPoder.id == poder_id, AsambleaPoder.asamblea_id == a.id).one_or_none()
    if p is None:
        raise HTTPException(status_code=404, detail="El poder no existe.")
    return p


def _avisar_unidad(db: Session, unidad_id: int, titulo: str, mensaje: str) -> None:
    u = db.query(Unidad).filter(Unidad.id == unidad_id).one_or_none()
    if u:
        notificar(db, reglas_unidades.residentes_por_unidad(db).get(u.clave, []), titulo, mensaje, "#/asambleas")


@router.post("/{asamblea_id}/poderes/{poder_id}/aprobar", response_model=esq.PoderResponse, summary="Aprobar un poder",
             description="Solo **Administrador**. Verifica el límite de poderes por persona y que el apoderado no sea personal del conjunto (si indicas su cuenta). Avisa al propietario.",
             responses={400: {"description": "Supera el límite de poderes o el apoderado es personal del conjunto"}, 409: {"description": "El poder no está pendiente"}})
def aprobar_poder(asamblea_id: int, poder_id: int, datos: esq.PoderAprobar, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="aprobar poderes")
    p = _poder_de(db, a, poder_id)
    if p.estado != EstadoPoder.PENDIENTE.value:
        raise HTTPException(status_code=409, detail=f"Este poder ya está «{p.estado}».")
    if datos.apoderado_usuario_id:
        if not db.query(Usuario.id).filter(Usuario.id == datos.apoderado_usuario_id).first():
            raise HTTPException(status_code=400, detail="La cuenta del apoderado no existe.")
        p.apoderado_usuario_id = datos.apoderado_usuario_id
    if reglas.usuario_es_personal(db, p.apoderado_usuario_id):
        raise HTTPException(status_code=400, detail="El administrador y el personal del conjunto no pueden recibir poderes de otros propietarios.")
    ya = reglas.poderes_del_apoderado(db, a, p.apoderado_documento, excluir_poder_id=p.id)
    if ya >= a.max_poderes:
        raise HTTPException(status_code=400, detail=f"{p.apoderado_nombre} ya tiene {ya} poder(es) aprobado(s): el máximo en esta asamblea es {a.max_poderes}.")
    p.estado, p.revisado_por, p.revisado_en, p.motivo = EstadoPoder.APROBADO.value, admin.id, ahora_utc(), None
    reglas.registrar_evento(db, a.id, "PoderAprobado", admin, unidad_id=p.unidad_id, detalle=f"Apoderado: {p.apoderado_nombre} ({ya + 1}/{a.max_poderes})")
    _avisar_unidad(db, p.unidad_id, "Tu poder fue aprobado", f"{p.apoderado_nombre} podrá representarte en «{a.titulo}».")
    db.commit()
    aptos, nombres = _nombres_aptos(db, [p])
    return _vista_poder(db, p, a, aptos, nombres)


@router.post("/{asamblea_id}/poderes/{poder_id}/rechazar", response_model=esq.PoderResponse, summary="Rechazar (o revocar) un poder",
             description="Solo **Administrador**. Indica el motivo. Un poder ya aprobado solo se revoca si su apoderado aún no ha sido acreditado.",
             responses={409: {"description": "Ya fue rechazado o ya se usó en la asamblea"}})
def rechazar_poder(asamblea_id: int, poder_id: int, datos: esq.PoderRechazar, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="rechazar poderes")
    p = _poder_de(db, a, poder_id)
    if p.estado == EstadoPoder.RECHAZADO.value:
        raise HTTPException(status_code=409, detail="Este poder ya fue rechazado.")
    if p.estado == EstadoPoder.APROBADO.value and db.query(AsambleaAsistente.id).filter(AsambleaAsistente.poder_id == p.id).first():
        raise HTTPException(status_code=409, detail="El apoderado ya fue acreditado con este poder: no se puede revocar.")
    p.estado, p.motivo, p.revisado_por, p.revisado_en = EstadoPoder.RECHAZADO.value, datos.motivo, admin.id, ahora_utc()
    reglas.registrar_evento(db, a.id, "PoderRechazado", admin, unidad_id=p.unidad_id, detalle=f"Apoderado: {p.apoderado_nombre} · {datos.motivo}")
    _avisar_unidad(db, p.unidad_id, "Tu poder no fue aprobado", f"Motivo: {datos.motivo}. Puedes subir uno nuevo.")
    db.commit()
    aptos, nombres = _nombres_aptos(db, [p])
    return _vista_poder(db, p, a, aptos, nombres)


@router.get("/{asamblea_id}/poderes/{poder_id}/archivo", summary="Ver el archivo del poder",
            description="**Administrador** y el **propietario de esa unidad**. Devuelve el PDF o la foto tal como se subió.", responses={403: {"description": "No es tu poder"}, 404: {"description": "No existe"}})
def archivo_poder(asamblea_id: int, poder_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE))):
    a = _con_acceso(db, asamblea_id, usuario)
    p = _poder_de(db, a, poder_id)
    if usuario.rol != ADMIN.value:
        u = _unidad_de(db, usuario)
        if p.subido_por != usuario.id and not (u and u.id == p.unidad_id):
            raise HTTPException(status_code=403, detail="Este poder no es de tu unidad.")
    if p.tipo_archivo == "pdf":
        datos, tipo = leer_documento(p.archivo), "application/pdf"
    else:
        r = leer_imagen(p.archivo)
        datos, tipo = (r if r else (None, None))
    if datos is None:
        raise HTTPException(status_code=404, detail="El archivo ya no está disponible.")
    return Response(content=datos, media_type=tipo, headers={"Cache-Control": "private, no-store", "Content-Disposition": f'inline; filename="poder-{p.id}.{"pdf" if p.tipo_archivo == "pdf" else "jpg"}"'})


# ================================================================ bitácora de evidencia y PDF de la convocatoria
@router.get("/{asamblea_id}/bitacora", response_model=esq.BitacoraResponse, summary="Bitácora de evidencia",
            description="Solo **Administrador**. Cada movimiento (convocatoria, aviso a cada propietario, acreditaciones, poderes, instalación, cierre) con fecha y hora. "
                        "Las huellas están **encadenadas**: `integra` dice si la cadena completa sigue intacta (si alguien la alterara en la base de datos, se rompe y se señala la secuencia dañada).",
            responses={404: {"description": "No existe"}})
def bitacora(asamblea_id: int, limite: int = Query(200, ge=1, le=reglas.MAX_EVENTOS_VISTA, description="Cuántos eventos recientes mostrar"),
             db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id)
    integra, danada, total = reglas.verificar_bitacora(db, a.id)
    eventos = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a.id).order_by(AsambleaEvento.secuencia.desc()).limit(limite).all()
    aptos = {u.id: u.apartamento for u in db.query(Unidad).filter(Unidad.id.in_({e.unidad_id for e in eventos if e.unidad_id})).all()} if eventos else {}
    actores = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_({e.actor_id for e in eventos if e.actor_id})).all()} if eventos else {}
    return esq.BitacoraResponse(integra=integra, secuencia_danada=danada, total=total, eventos=[
        esq.EventoResponse(secuencia=e.secuencia, tipo=e.tipo, unidad=aptos.get(e.unidad_id), actor=actores.get(e.actor_id), detalle=e.detalle, creado_en=e.creado_en, hash=e.hash) for e in eventos])


def _cop(valor: float) -> str:
    return "$ " + f"{int(round(valor or 0)):,}".replace(",", ".")


@router.get("/{asamblea_id}/convocatoria.pdf", summary="Descargar la convocatoria en PDF",
            description="Solo **Administrador**, una vez enviada la convocatoria. Documento para entregar por escrito a quien no usa la app: fecha y hora, medios, segunda convocatoria (Art. 41), orden del día, "
                        "documentos adjuntos y relación de morosos (Art. 39, parágrafo 2). Lleva la huella (SHA-256) del contenido enviado.", responses={409: {"description": "Aún es un borrador"}})
def convocatoria_pdf(asamblea_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id)
    if a.estado == EstadoAsamblea.BORRADOR.value or not a.fecha_convocatoria:
        raise HTTPException(status_code=409, detail="La convocatoria solo se descarga una vez enviada.")
    from xml.sax.saxutils import escape
    docs = reglas.documentos_adjuntos(db, a.id)
    lista = json.loads(a.morosos_snapshot) if a.morosos_snapshot else []
    est = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=est["Normal"], fontSize=10.5, leading=15)
    titulo = ParagraphStyle("t", parent=est["Title"], fontSize=16, leading=20, spaceAfter=4)
    sub = ParagraphStyle("s", parent=est["Heading3"], fontSize=11.5, spaceBefore=12, spaceAfter=4)
    pequeno = ParagraphStyle("p", parent=normal, fontSize=8.5, leading=11, textColor=colors.HexColor("#555555"))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm, title=f"Convocatoria · {a.titulo}")
    partes = [Paragraph(escape(marca.nombre()), pequeno), Paragraph(f"CONVOCATORIA A ASAMBLEA GENERAL {a.tipo.upper()} DE COPROPIETARIOS", titulo),
              Paragraph(escape(a.titulo), ParagraphStyle("st", parent=normal, alignment=1, fontSize=12)), Spacer(1, 10),
              Paragraph(f"Fecha de esta convocatoria: <b>{reglas.fmt_local(a.fecha_convocatoria)}</b>.", normal), Spacer(1, 6),
              Paragraph(f"Se convoca a los propietarios a la reunión de la asamblea general, en modalidad <b>{a.modalidad.lower()}</b>, el <b>{reglas.fmt_local(a.fecha_sesion)}</b>.", normal)]
    if a.lugar:
        partes.append(Paragraph(f"<b>Lugar:</b> {escape(a.lugar)}", normal))
    if a.url_videollamada:
        partes.append(Paragraph(f"<b>Enlace de la videollamada:</b> {escape(a.url_videollamada)}", normal))
    if a.instrucciones_virtual:
        partes.append(Paragraph(f"<b>Cómo conectarse:</b> {escape(a.instrucciones_virtual)}", normal))
    partes += [Paragraph("Segunda convocatoria", sub),
               Paragraph(f"Si el día y la hora citados no se reúne el quórum (más de la mitad de los coeficientes de copropiedad), la asamblea se reunirá el <b>{reglas.fmt_local(a.fecha_segunda)}</b>, "
                         "y entonces sesionará y decidirá válidamente con un número plural de propietarios, cualquiera sea el porcentaje de coeficientes representados (Art. 41, Ley 675 de 2001).", normal),
               Paragraph("Orden del día", sub)]
    for linea in [l for l in a.orden_del_dia.splitlines() if l.strip()]:
        partes.append(Paragraph(escape(linea.strip()), normal))
    if docs:
        partes.append(Paragraph("Documentos que acompañan la convocatoria", sub))
        partes += [Paragraph("• " + escape(d.titulo) + f" ({escape(d.categoria)})", normal) for d in docs]
    partes += [Paragraph("Representación", sub),
               Paragraph(f"Quien no pueda asistir puede hacerse representar mediante poder escrito. Cada persona puede representar hasta {a.max_poderes} unidad(es). "
                         "El administrador y el personal del conjunto no pueden recibir poderes." + (" Conforme al reglamento, las unidades en mora no tendrán derecho a voto." if a.restringe_mora else ""), normal),
               Paragraph("Propietarios en mora al momento de la convocatoria", sub)]
    if lista:
        filas = [["Unidad", "Saldo adeudado"]] + [[escape(f["apartamento"]), _cop(f["saldo"])] for f in lista]
        t = Table(filas, colWidths=[8 * cm, 5 * cm], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EEF1")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2C8")),
                               ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        partes.append(t)
    else:
        partes.append(Paragraph("Ninguna unidad figura en mora a la fecha de la convocatoria.", normal))
    partes += [Spacer(1, 28), Paragraph("_______________________________<br/>Administrador(a)", normal), Spacer(1, 14),
               Paragraph(f"Huella de verificación (SHA-256) del contenido enviado: {a.convocatoria_hash}", pequeno)]
    doc.build(partes)
    return Response(content=buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="convocatoria-asamblea-{a.id}.pdf"', "Cache-Control": "private, no-store"})
