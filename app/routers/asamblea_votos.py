# app/routers/asamblea_votos.py — Votaciones dentro de una asamblea de copropietarios (Ley 675 de 2001). V5.2, Fase 3.
#
# Flujo de cada pregunta: Borrador → Abierta → Cerrada (o Anulada). Solo UNA abierta por asamblea.
#   Abrir: valida que la asamblea esté en sesión, que haya quórum, el bloqueo del 70 % y congela el padrón (quién puede votar y con qué coeficiente).
#   Votar: el asistente VIRTUAL vota desde la app (voto secreto); el administrador registra el voto de los asistentes PRESENCIALES (voto nominal).
#   Cerrar: valida el quórum de ese momento, calcula el resultado, lo congela con su huella SHA-256 y lo deja en la bitácora encadenada.
# Las reglas viven en app/asamblea_votos.py; aquí solo se traduce HTTP a esas reglas.
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import asamblea_votos as reglas_votos, asambleas as reglas, unidades as reglas_unidades
from app.auditoria import auditar
from app.constantes import EstadoAsamblea, EstadoVotacionAsamblea, RolNombre, TipoVotacionAsamblea
from app.database import get_db
from app.dependencies import requiere_roles
from app.models import Asamblea, AsambleaAsistente, AsambleaVotacion, AsambleaVotacionOpcion, AsambleaVoto, Unidad, Usuario
from app.notificaciones import notificar
from app.routers.asambleas import _con_acceso, _unidad_de
from app.schemas import asamblea_votos as esq

TAG = "Votaciones de la Asamblea"
router = APIRouter(prefix="/asambleas", tags=[TAG])
ADMIN, RESIDENTE, GUARDIA = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.GUARDIA
MAX_VOTACIONES_POR_ASAMBLEA = 60


# ================================================================ vista
def _vista(db: Session, a: Asamblea, v: AsambleaVotacion, usuario: Usuario, advertencias: Optional[list[str]] = None) -> esq.VotacionAsambleaResponse:
    """Lo que ve cada rol. Mientras la pregunta está abierta NO hay resultados parciales para nadie (ni el administrador): solo la participación."""
    cerrada = v.estado == EstadoVotacionAsamblea.CERRADA.value and v.resultado
    res = json.loads(v.resultado) if cerrada else None
    por_id = {o["id"]: o for o in res["opciones"]} if res else {}
    opciones = [esq.OpcionAsambleaResponse(id=o.id, texto=o.texto, votos=por_id.get(o.id, {}).get("votos"), coeficiente=por_id.get(o.id, {}).get("coeficiente"),
                                           porcentaje_presentes=por_id.get(o.id, {}).get("porcentaje_presentes"), porcentaje_conjunto=por_id.get(o.id, {}).get("porcentaje_conjunto"))
                for o in reglas_votos.opciones_de(db, v.id)]
    padron = reglas_votos.padron_de(v)
    votos = {x.unidad_id: x for x in db.query(AsambleaVoto).filter(AsambleaVoto.votacion_id == v.id).all()} if padron else {}
    participacion = None
    if padron:
        coef_padron = float(v.coef_padron or 0.0)
        coef_votaron = round(sum(x.peso for x in votos.values()), 4)
        participacion = esq.ParticipacionResponse(unidades_padron=len(padron), unidades_votaron=len(votos), coeficiente_padron=round(coef_padron, 4), coeficiente_votaron=coef_votaron,
                                                  porcentaje=round(coef_votaron * 100.0 / coef_padron, 2) if coef_padron > 0 else 0.0)
    r = esq.VotacionAsambleaResponse(
        id=v.id, asamblea_id=v.asamblea_id, numero=v.numero, titulo=v.titulo, descripcion=v.descripcion, tipo=v.tipo, mayoria=v.mayoria, estado=v.estado, requisito=reglas_votos.requisito(v),
        opciones=opciones, abierta_en=v.abierta_en, cerrada_en=v.cerrada_en, quorum_apertura=v.quorum_apertura, quorum_cierre=v.quorum_cierre, participacion=participacion,
        resultado=res, resultado_hash=v.resultado_hash if cerrada else None, motivo_anulacion=v.motivo_anulacion, advertencias=advertencias or [])
    if v.estado != EstadoVotacionAsamblea.ABIERTA.value or not padron:
        return r
    ids_filas = [p["asistente_id"] for p in padron]
    filas = {f.id: f for f in db.query(AsambleaAsistente).filter(AsambleaAsistente.id.in_(ids_filas)).all()}
    aptos = {u.id: u.apartamento for u in db.query(Unidad).filter(Unidad.id.in_([p["unidad_id"] for p in padron])).all()}
    if usuario.rol == ADMIN.value:
        textos = {o.id: o.texto for o in reglas_votos.opciones_de(db, v.id)}
        r.padron = [esq.PadronFilaResponse(unidad_id=p["unidad_id"], apartamento=aptos.get(p["unidad_id"], "?"), nombre=p["nombre"], coeficiente=p["coef"], via=p["via"],
                                           ya_voto=p["unidad_id"] in votos, sin_medio=p["via"] == "App" and not p["usuario_id"],
                                           opcion_registrada=textos.get(votos[p["unidad_id"]].opcion_id) if p["unidad_id"] in votos and p["via"] == "Manual" else None,
                                           sigue_presente=bool(filas.get(p["asistente_id"]) and filas[p["asistente_id"]].hora_salida is None)) for p in padron]
    elif usuario.rol == RESIDENTE.value:
        propias = [p for p in padron if p["via"] == "App" and p["usuario_id"] == usuario.id]
        r.mis_unidades = []
        for p in propias:
            f = filas.get(p["asistente_id"])
            presente = bool(f and f.hora_salida is None and f.usuario_id == usuario.id)
            ya = p["unidad_id"] in votos
            r.mis_unidades.append(esq.UnidadVotanteResponse(unidad_id=p["unidad_id"], apartamento=aptos.get(p["unidad_id"], "?"), coeficiente=p["coef"], ya_voto=ya, puede_votar=presente and not ya))
        if not propias:
            u = _unidad_de(db, usuario)
            propia = next((p for p in padron if u and p["unidad_id"] == u.id), None)
            if propia is None:
                r.mensaje_votante = "No estás en el padrón de esta votación: solo votan las unidades presentes y con derecho a voto cuando el administrador la abrió."
            elif propia["via"] == "Manual":
                r.mensaje_votante = "Tu asistencia es presencial: el administrador registra tu voto en la reunión."
            else:
                r.mensaje_votante = "Tu unidad vota con otro asistente (un apoderado)."
        elif all(m.ya_voto for m in r.mis_unidades):
            r.mensaje_votante = "Tu voto ya quedó registrado. Es secreto y no se puede cambiar."
        elif not any(m.puede_votar for m in r.mis_unidades):
            r.mensaje_votante = "Ya no estás conectado a la asamblea: conéctate de nuevo para poder votar."
    return r


def _avisar(db: Session, v: AsambleaVotacion, titulo: str, mensaje: str) -> None:
    """Avisa (campana y, si lo activaron, push) a quienes votan desde la app en esta pregunta."""
    ids = {p["usuario_id"] for p in reglas_votos.padron_de(v) if p["via"] == "App" and p["usuario_id"]}
    if ids:
        notificar(db, db.query(Usuario).filter(Usuario.id.in_(ids)).all(), titulo, mensaje, "#/asambleas")


def _opcion_de(db: Session, v: AsambleaVotacion, opcion_id: int) -> AsambleaVotacionOpcion:
    o = db.get(AsambleaVotacionOpcion, opcion_id)
    if o is None or o.votacion_id != v.id:
        raise HTTPException(status_code=400, detail="Esa opción no pertenece a esta votación.")
    return o


# ================================================================ consultar
@router.get("/{asamblea_id}/votaciones", response_model=list[esq.VotacionAsambleaResponse], summary="Ver las votaciones de la asamblea",
            description="Roles: **Administrador**, **Residente** y **Guardia**. Los borradores solo los ve el administrador. Mientras una votación está abierta **nadie** ve resultados parciales; "
                        "al cerrarla aparece el resultado congelado con su huella.", responses={404: {"description": "La asamblea no existe"}})
def listar(asamblea_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    a = _con_acceso(db, asamblea_id, usuario)
    q = db.query(AsambleaVotacion).filter(AsambleaVotacion.asamblea_id == a.id)
    if usuario.rol != ADMIN.value:
        q = q.filter(AsambleaVotacion.estado != EstadoVotacionAsamblea.BORRADOR.value)
    return [_vista(db, a, v, usuario) for v in q.order_by(AsambleaVotacion.numero).all()]


@router.get("/{asamblea_id}/votaciones/{votacion_id}", response_model=esq.VotacionAsambleaResponse, summary="Ver una votación de la asamblea",
            responses={404: {"description": "No existe"}})
def detalle(asamblea_id: int, votacion_id: int, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(ADMIN, RESIDENTE, GUARDIA))):
    a = _con_acceso(db, asamblea_id, usuario)
    v = reglas_votos.obtener(db, a.id, votacion_id)
    if v.estado == EstadoVotacionAsamblea.BORRADOR.value and usuario.rol != ADMIN.value:
        raise HTTPException(status_code=404, detail="La votación no existe en esta asamblea.")
    return _vista(db, a, v, usuario)


# ================================================================ administrar
@router.post("/{asamblea_id}/votaciones", response_model=esq.VotacionAsambleaResponse, status_code=status.HTTP_201_CREATED, summary="Crear una votación (borrador)",
             description="Solo **Administrador**, con la asamblea **convocada** o **en sesión**. «Decisión»: opciones fijas (A favor, En contra, Abstención). «Elección»: de 2 a 12 opciones que escribes. "
                         "La mayoría **calificada (70 %)** se rechaza aquí si la asamblea es virtual o mixta (y al abrir, si se instaló en segunda convocatoria).",
             responses={400: {"description": "Mayoría calificada no permitida en esta asamblea"}, 409: {"description": "La asamblea no está convocada ni en sesión, o hay demasiadas votaciones"}})
def crear(asamblea_id: int, datos: esq.VotacionAsambleaCreate, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="crear votaciones")
    bloqueo = reglas_votos.motivo_bloqueo_70(a, datos.mayoria.value)
    if bloqueo:
        raise HTTPException(status_code=400, detail=bloqueo)
    if db.query(AsambleaVotacion.id).filter(AsambleaVotacion.asamblea_id == a.id).count() >= MAX_VOTACIONES_POR_ASAMBLEA:
        raise HTTPException(status_code=409, detail=f"Una asamblea admite hasta {MAX_VOTACIONES_POR_ASAMBLEA} votaciones.")
    v = AsambleaVotacion(asamblea_id=a.id, numero=reglas_votos.siguiente_numero(db, a.id), titulo=datos.titulo, descripcion=datos.descripcion, tipo=datos.tipo.value,
                         mayoria=datos.mayoria.value, estado=EstadoVotacionAsamblea.BORRADOR.value, creada_por=admin.id)
    db.add(v)
    db.flush()
    textos = list(reglas_votos.OPCIONES_DECISION) if datos.tipo == TipoVotacionAsamblea.DECISION else datos.opciones
    db.add_all([AsambleaVotacionOpcion(votacion_id=v.id, texto=t, orden=i) for i, t in enumerate(textos)])
    reglas.registrar_evento(db, a.id, "VotacionCreada", admin, detalle=f"#{v.numero} «{v.titulo[:80]}» · {v.tipo} · mayoría {v.mayoria.lower()}")
    auditar(db, admin, "Creó una votación de asamblea", "Asamblea", a.id, f"#{v.numero} {v.titulo[:100]}")
    db.commit()
    return _vista(db, a, v, admin)


@router.post("/{asamblea_id}/votaciones/{votacion_id}/abrir", response_model=esq.VotacionAsambleaResponse, summary="Abrir la votación",
             description="Solo **Administrador**. Exige asamblea **en sesión**, **quórum** vigente (1.ª convocatoria: más del 50 %; 2.ª: 2 o más unidades), que no haya otra votación abierta y el bloqueo del 70 %. "
                         "**Congela el padrón**: votan las unidades presentes y con derecho a voto en este momento, cada una con su coeficiente acreditado. Avisa a quienes votan desde la app.",
             responses={409: {"description": "No está en sesión, no hay quórum, ya hay otra abierta o el 70 % está bloqueado"}})
def abrir(asamblea_id: int, votacion_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    v = reglas_votos.obtener(db, a.id, votacion_id)
    q = reglas.quorum(db, a)
    advertencias = reglas_votos.abrir(db, a, v, admin, q)
    auditar(db, admin, "Abrió una votación de asamblea", "Asamblea", a.id, f"#{v.numero} {v.titulo[:100]}")
    _avisar(db, v, f"Se abrió una votación en la asamblea: {v.titulo[:80]}", "Entra a la asamblea y vota. Tu voto es secreto y no se puede cambiar.")
    db.commit()
    return _vista(db, a, v, admin, advertencias)


@router.post("/{asamblea_id}/votaciones/{votacion_id}/cerrar", response_model=esq.VotacionAsambleaResponse, summary="Cerrar la votación y publicar el resultado",
             description="Solo **Administrador**. Valida el quórum **de este momento**, calcula el resultado (mayoría simple sobre el coeficiente del padrón; calificada sobre el 100 % del conjunto), "
                         "lo **congela con su huella SHA-256** y lo deja en la bitácora encadenada. Si se perdió el quórum, el resultado queda **sin validez**.",
             responses={409: {"description": "La votación no está abierta"}})
def cerrar(asamblea_id: int, votacion_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    reglas_unidades.sincronizar(db)
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.EN_SESION, accion="cerrar una votación")
    v = reglas_votos.obtener(db, a.id, votacion_id)
    q = reglas.quorum(db, a)
    res = reglas_votos.cerrar(db, a, v, admin, q)
    auditar(db, admin, "Cerró una votación de asamblea", "Asamblea", a.id, f"#{v.numero} {v.titulo[:80]} · {reglas_votos.titular_resultado(v, res)}")
    _avisar(db, v, f"Resultado de la votación: {v.titulo[:80]}", "La votación terminó. Ya puedes ver el resultado en la asamblea.")
    db.commit()
    return _vista(db, a, v, admin)


@router.post("/{asamblea_id}/votaciones/{votacion_id}/anular", response_model=esq.VotacionAsambleaResponse, summary="Anular la votación",
             description="Solo **Administrador**. Una votación en borrador o abierta puede anularse con un **motivo** (queda en la bitácora). Su resultado no se publica. Una votación ya cerrada NO se puede anular.",
             responses={409: {"description": "Ya está cerrada o anulada"}})
def anular(asamblea_id: int, votacion_id: int, datos: esq.AnularIn, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.CONVOCADA, EstadoAsamblea.EN_SESION, accion="anular votaciones")
    v = reglas_votos.obtener(db, a.id, votacion_id)
    estaba_abierta = v.estado == EstadoVotacionAsamblea.ABIERTA.value
    reglas_votos.anular(db, a, v, admin, datos.motivo)
    auditar(db, admin, "Anuló una votación de asamblea", "Asamblea", a.id, f"#{v.numero} {v.titulo[:100]}")
    if estaba_abierta:
        _avisar(db, v, f"Se anuló la votación: {v.titulo[:80]}", "El administrador la anuló. Tu voto no se tendrá en cuenta.")
    db.commit()
    return _vista(db, a, v, admin)


# ================================================================ votar
@router.post("/{asamblea_id}/votaciones/{votacion_id}/votar", response_model=esq.VotacionAsambleaResponse, summary="Votar desde la app (asistente virtual)",
             description="Solo **Residente** conectado a la asamblea como asistente **virtual** (él mismo o, si es apoderado, la unidad que representa). El voto es **secreto** y **no se puede cambiar**: "
                         "no queda guardado qué opción escogió, solo que su unidad ya votó. Si representa a más de una unidad (poderes), se indica por cuál con `unidad_id`.",
             responses={400: {"description": "Opción inválida o falta indicar la unidad"}, 403: {"description": "No estás en el padrón o ya no estás conectado"}, 409: {"description": "No está abierta o la unidad ya votó"}})
def votar(asamblea_id: int, votacion_id: int, datos: esq.VotoAsambleaIn, db: Session = Depends(get_db), usuario: Usuario = Depends(requiere_roles(RESIDENTE))):
    a = _con_acceso(db, asamblea_id, usuario, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.EN_SESION, accion="votar")
    v = reglas_votos.obtener(db, a.id, votacion_id)
    reglas_votos.exige_estado(v, EstadoVotacionAsamblea.ABIERTA, accion="votar")
    propias = [p for p in reglas_votos.padron_de(v) if p["via"] == "App" and p["usuario_id"] == usuario.id]
    if not propias:
        raise HTTPException(status_code=403, detail="No puedes votar: tu unidad no está en el padrón de esta votación (debías estar conectado, con derecho a voto, cuando se abrió).")
    ya = {u for (u,) in db.query(AsambleaVoto.unidad_id).filter(AsambleaVoto.votacion_id == v.id).all()}
    if datos.unidad_id is not None:
        entrada = next((p for p in propias if p["unidad_id"] == datos.unidad_id), None)
        if entrada is None:
            raise HTTPException(status_code=403, detail="No puedes votar por esa unidad.")
    else:
        pendientes = [p for p in propias if p["unidad_id"] not in ya]
        if not pendientes:
            raise HTTPException(status_code=409, detail="Tu unidad ya votó en esta votación.")
        if len(pendientes) > 1:
            raise HTTPException(status_code=400, detail="Representas a más de una unidad: indica por cuál votas (unidad_id).")
        entrada = pendientes[0]
    if entrada["unidad_id"] in ya:
        raise HTTPException(status_code=409, detail="Tu unidad ya votó en esta votación.")
    if reglas_votos.asistente_vigente(db, a, entrada) is None:
        raise HTTPException(status_code=403, detail="Ya no estás conectado a la asamblea: conéctate de nuevo para votar. (Si te desconectaste después de abrirse la votación, tu unidad no puede votar en ella.)")
    opcion = _opcion_de(db, v, datos.opcion_id)
    reglas_votos.registrar_voto(db, a, v, entrada, opcion, "App", usuario)
    auditar(db, usuario, "Votó en una asamblea", "Asamblea", a.id, f"#{v.numero} {v.titulo[:100]}")        # se audita que votó, JAMÁS qué votó
    db.commit()
    return _vista(db, a, v, usuario)


@router.post("/{asamblea_id}/votaciones/{votacion_id}/votos-presenciales", response_model=esq.VotacionAsambleaResponse, summary="Registrar el voto de un asistente presencial",
             description="Solo **Administrador**. Registra el voto de una unidad cuyo asistente está **presente en el lugar** (no virtual). Este voto es **nominal**: queda a nombre de la unidad y de lo que votó, "
                         "y así consta en la bitácora. A un asistente virtual NO se le puede registrar el voto: solo él puede votar desde la app.",
             responses={404: {"description": "La unidad no está en el padrón"}, 409: {"description": "Ya votó, es virtual, ya salió o la votación no está abierta"}})
def voto_presencial(asamblea_id: int, votacion_id: int, datos: esq.VotoPresencialIn, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    a = reglas.obtener(db, asamblea_id, bloquear=True)
    reglas.exige_estado(a, EstadoAsamblea.EN_SESION, accion="registrar votos")
    v = reglas_votos.obtener(db, a.id, votacion_id)
    reglas_votos.exige_estado(v, EstadoVotacionAsamblea.ABIERTA, accion="registrar votos")
    entrada = reglas_votos.entrada_de_padron(v, datos.unidad_id)
    if entrada is None:
        raise HTTPException(status_code=404, detail="Esa unidad no está en el padrón de esta votación (debía estar presente y con derecho a voto cuando se abrió).")
    if entrada["via"] != "Manual":
        raise HTTPException(status_code=409, detail="Esa unidad está conectada de forma virtual: solo ella puede votar, desde la app.")
    if db.query(AsambleaVoto.id).filter(AsambleaVoto.votacion_id == v.id, AsambleaVoto.unidad_id == datos.unidad_id).first():
        raise HTTPException(status_code=409, detail="Esa unidad ya votó en esta votación.")
    if reglas_votos.asistente_vigente(db, a, entrada) is None:
        raise HTTPException(status_code=409, detail="Esa persona ya salió de la asamblea: no puede votar.")
    opcion = _opcion_de(db, v, datos.opcion_id)
    reglas_votos.registrar_voto(db, a, v, entrada, opcion, "Manual", admin)
    auditar(db, admin, "Registró un voto presencial", "Asamblea", a.id, f"#{v.numero} {v.titulo[:80]} · unidad {datos.unidad_id}")
    db.commit()
    return _vista(db, a, v, admin)
