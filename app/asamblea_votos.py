# app/asamblea_votos.py
# Reglas de negocio de las VOTACIONES DENTRO DE UNA ASAMBLEA (Ley 675 de 2001) — V5.2, Fase 3. Los endpoints (routers/asamblea_votos.py) solo traducen HTTP a estas funciones.
#
# Decisiones de diseño (y por qué):
#  · Es un motor APARTE del de «Votaciones» del conjunto. Aquel vota por apartamentos con cuenta; la asamblea cuenta también a propietarios sin cuenta,
#    apoderados y el coeficiente «fotografiado» al acreditar. Mezclarlos habría puesto en riesgo lo que ya funciona.
#  · PADRÓN CONGELADO al abrir cada pregunta: pueden votar las unidades presentes y con derecho a voto en ESE momento, cada una con su coeficiente acreditado.
#    Quien llega después no vota esa pregunta (evita que el quórum «se mueva» mientras se vota). Quien se va antes de votar ya no puede votar, pero su coeficiente
#    sigue en la base de la mayoría simple (la lectura más exigente).
#  · UN voto por unidad y por pregunta (restricción única en la base de datos). Una sola pregunta abierta por asamblea (índice único parcial).
#  · Asistente VIRTUAL → vota él mismo desde la app y el voto es SECRETO (la tabla de votos no guarda qué votó; los contadores no se unen a nadie).
#    Asistente PRESENCIAL → el administrador registra su voto; queda NOMINAL (a nombre de la unidad). Nadie vota «por» un asistente virtual.
#  · Mientras la pregunta está abierta NO se muestran resultados parciales (ni al administrador): no se influye en quien aún no vota.
#  · Al cerrar se valida el quórum de ese momento, se calcula el resultado y se CONGELA con su huella SHA-256, que también queda en la bitácora encadenada.
#
# Qué NO hace: no reemplaza al presidente y al secretario de la asamblea ni a un abogado. Las reglas de mayoría y los bloqueos del 70 % son las lecturas
# prudentes de la ley que se documentan en PASOS_V5.2.md; si tu reglamento de propiedad horizontal dice otra cosa, el reglamento manda.
import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import asambleas as reglas, config
from app.constantes import EstadoAsamblea, EstadoVotacionAsamblea, MayoriaAsamblea, ModalidadAsamblea, TipoVotacionAsamblea
from app.models import (Asamblea, AsambleaAsistente, AsambleaVotacion, AsambleaVotacionOpcion, AsambleaVoto, Unidad, Usuario, ahora_utc)

FAVOR, CONTRA, ABSTENCION = "A favor", "En contra", "Abstención"
OPCIONES_DECISION = (FAVOR, CONTRA, ABSTENCION)
UMBRAL_SIMPLE = 50.0            # más de la mitad del coeficiente presente con derecho a voto
UMBRAL_CALIFICADA = 70.0        # 70 % o más del coeficiente de todo el conjunto
TOLERANCIA = 1e-9               # los coeficientes son decimales: se compara con una tolerancia mínima, nunca con ==
DECIMALES = 4


# ---------------------------------------------------------------- acceso
def obtener(db: Session, asamblea_id: int, votacion_id: int) -> AsambleaVotacion:
    v = db.query(AsambleaVotacion).filter(AsambleaVotacion.id == votacion_id, AsambleaVotacion.asamblea_id == asamblea_id).one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="La votación no existe en esta asamblea.")
    return v


def opciones_de(db: Session, votacion_id: int) -> list[AsambleaVotacionOpcion]:
    return db.query(AsambleaVotacionOpcion).filter(AsambleaVotacionOpcion.votacion_id == votacion_id).order_by(AsambleaVotacionOpcion.orden).all()


def padron_de(v: AsambleaVotacion) -> list[dict]:
    return json.loads(v.padron) if v.padron else []


def exige_estado(v: AsambleaVotacion, *permitidos: EstadoVotacionAsamblea, accion: str) -> None:
    if v.estado not in {e.value for e in permitidos}:
        raise HTTPException(status_code=409, detail=f"No se puede {accion}: la votación está «{v.estado}».")


def requisito(v: AsambleaVotacion) -> str:
    """La regla que decide esta pregunta, en palabras que entienda un propietario."""
    if v.tipo == TipoVotacionAsamblea.ELECCION.value:
        return "Gana la opción con más coeficiente. Si tu reglamento exige una mayoría específica para elegir, el presidente y el secretario deben verificarla con el resultado."
    if v.mayoria == MayoriaAsamblea.CALIFICADA.value:
        return f"Mayoría calificada: se aprueba con el {UMBRAL_CALIFICADA:g} % o más del coeficiente de TODO el conjunto (no solo de quienes están presentes)."
    return f"Mayoría simple: se aprueba con más del {UMBRAL_SIMPLE:g} % del coeficiente presente con derecho a voto cuando se abrió la votación. La abstención no suma a favor."


# ---------------------------------------------------------------- bloqueo del 70 %
def motivo_bloqueo_70(a: Asamblea, mayoria: str) -> Optional[str]:
    """Decisiones de mayoría calificada (70 %) no se toman en reuniones no presenciales ni en segunda convocatoria (lectura prudente de los Art. 41, 45 y 46 de la Ley 675).
    Cada bloqueo se puede apagar con una variable de entorno si el abogado del conjunto lo indica (ver PASOS_V5.2.md)."""
    if mayoria != MayoriaAsamblea.CALIFICADA.value:
        return None
    if config.ASAMBLEA_BLOQUEA_70_VIRTUAL and a.modalidad == ModalidadAsamblea.VIRTUAL.value:
        return "Las decisiones de mayoría calificada (70 %) no se pueden tomar en una reunión no presencial (virtual). Cítala presencial o usa una votación de mayoría simple si la ley lo permite para ese tema."
    if config.ASAMBLEA_BLOQUEA_70_MIXTA and a.modalidad == ModalidadAsamblea.MIXTA.value:
        return "Las decisiones de mayoría calificada (70 %) no se toman en reuniones con participación a distancia (mixtas). Cita la asamblea presencial para este tema."
    if config.ASAMBLEA_BLOQUEA_70_SEGUNDA and a.convocatoria_numero == 2:
        return "Esta asamblea se instaló en segunda convocatoria: ahí no se pueden tomar decisiones de mayoría calificada (70 %). Hay que citar una nueva asamblea."
    return None


# ---------------------------------------------------------------- quórum de la pregunta
def quorum_suficiente(a: Asamblea, q: dict) -> tuple[bool, Optional[str]]:
    """Para deliberar y decidir: 1.ª convocatoria → más del 50 % de los coeficientes; 2.ª → número plural de propietarios (2 o más unidades)."""
    if a.convocatoria_numero == 2:
        if q["unidades_presentes"] < 2:
            return False, "En segunda convocatoria se necesita un número plural de propietarios: hay menos de 2 unidades presentes."
        return True, None
    if not q["hay_quorum"]:
        return False, f"No hay quórum: hay {q['porcentaje']:g} % y se necesita más del 50 % del coeficiente."
    return True, None


# ---------------------------------------------------------------- padrón
def construir_padron(db: Session, a: Asamblea) -> list[dict]:
    """Unidades presentes (sin hora de salida) y con derecho a voto, con el coeficiente acreditado (la «foto»). Vía: App si se conectó virtual, Manual si está presencial."""
    filas = (db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id, AsambleaAsistente.hora_salida.is_(None),
                                                 AsambleaAsistente.con_voto.is_(True), AsambleaAsistente.coeficiente_acreditado > 0)
             .order_by(AsambleaAsistente.unidad_id).all())
    return [{"unidad_id": f.unidad_id, "asistente_id": f.id, "usuario_id": f.usuario_id, "coef": round(f.coeficiente_acreditado, 6),
             "via": "App" if f.modalidad_ingreso == "Virtual" else "Manual", "nombre": f.nombre} for f in filas]


def entrada_de_padron(v: AsambleaVotacion, unidad_id: int) -> Optional[dict]:
    return next((p for p in padron_de(v) if p["unidad_id"] == unidad_id), None)


def asistente_vigente(db: Session, a: Asamblea, entrada: dict) -> Optional[AsambleaAsistente]:
    """La fila de acreditación que respalda esa entrada del padrón, solo si SIGUE presente y es la misma persona/acreditación de cuando se abrió la votación."""
    f = db.query(AsambleaAsistente).filter(AsambleaAsistente.id == entrada["asistente_id"], AsambleaAsistente.asamblea_id == a.id).one_or_none()
    if f is None or f.hora_salida is not None or not f.con_voto or f.unidad_id != entrada["unidad_id"] or f.usuario_id != entrada.get("usuario_id"):
        return None
    return f


# ---------------------------------------------------------------- ciclo de vida
def siguiente_numero(db: Session, asamblea_id: int) -> int:
    return (db.query(func.coalesce(func.max(AsambleaVotacion.numero), 0)).filter(AsambleaVotacion.asamblea_id == asamblea_id).scalar() or 0) + 1


def abrir(db: Session, a: Asamblea, v: AsambleaVotacion, actor: Usuario, q: dict) -> list[str]:
    """Valida y abre la votación. `q` es el quórum calculado justo antes (con la asamblea bloqueada). Devuelve advertencias para el administrador."""
    if a.estado != EstadoAsamblea.EN_SESION.value:
        raise HTTPException(status_code=409, detail=f"Primero instala la asamblea: solo se puede votar con la asamblea en sesión (ahora está «{a.estado}»).")
    exige_estado(v, EstadoVotacionAsamblea.BORRADOR, accion="abrir")
    if db.query(AsambleaVotacion.id).filter(AsambleaVotacion.asamblea_id == a.id, AsambleaVotacion.estado == EstadoVotacionAsamblea.ABIERTA.value).first():
        raise HTTPException(status_code=409, detail="Ya hay una votación abierta en esta asamblea: ciérrala o anúlala antes de abrir otra.")
    bloqueo = motivo_bloqueo_70(a, v.mayoria)
    if bloqueo:
        raise HTTPException(status_code=409, detail=bloqueo)
    if not q["base_completa"]:
        raise HTTPException(status_code=409, detail=f"No se puede calcular el quórum: {q['problema_base']} Corrígelo en «Unidades y coeficientes».")
    ok, motivo = quorum_suficiente(a, q)
    if not ok:
        raise HTTPException(status_code=409, detail=f"No se puede abrir la votación. {motivo}")
    padron = construir_padron(db, a)
    if not padron:
        raise HTTPException(status_code=409, detail="No hay ninguna unidad presente con derecho a voto.")
    ahora = ahora_utc()
    v.estado, v.abierta_en, v.abierta_por = EstadoVotacionAsamblea.ABIERTA.value, ahora, actor.id
    v.padron = json.dumps(padron, ensure_ascii=False)
    v.coef_padron = round(sum(p["coef"] for p in padron), 6)
    v.coef_total = q["coeficiente_total"]
    v.quorum_apertura = q["porcentaje"]
    sin_medio = [p for p in padron if p["via"] == "App" and not p["usuario_id"]]
    advertencias = []
    if sin_medio:
        nombres = db.query(Unidad.apartamento).filter(Unidad.id.in_([p["unidad_id"] for p in sin_medio])).all()
        advertencias.append("Estas unidades están conectadas de forma virtual pero sin cuenta en la app, así que NO podrán votar (su coeficiente sí cuenta como presente): "
                            + ", ".join(n for (n,) in nombres) + ".")
    reglas.registrar_evento(db, a.id, "VotacionAbierta", actor,
                            detalle=f"#{v.numero} «{v.titulo[:80]}» · {v.tipo} · mayoría {v.mayoria.lower()} · quórum {q['porcentaje']:g} % · padrón {len(padron)} unidades ({v.coef_padron:g} %)")
    return advertencias


def registrar_voto(db: Session, a: Asamblea, v: AsambleaVotacion, entrada: dict, opcion: AsambleaVotacionOpcion, via: str, actor: Usuario) -> None:
    """Guarda el voto de UNA unidad. Con la asamblea bloqueada por quien llama. App: secreto (no se guarda qué votó). Manual: nominal (se guarda la opción)."""
    voto = AsambleaVoto(votacion_id=v.id, unidad_id=entrada["unidad_id"], asistente_id=entrada["asistente_id"], peso=entrada["coef"], via=via, emitido_por=actor.id,
                        opcion_id=opcion.id if via == "Manual" else None)
    db.add(voto)
    try:
        db.flush()                                   # si la unidad ya había votado, la restricción única lo rechaza aquí, antes de sumar nada
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Esa unidad ya votó en esta votación.")
    db.execute(update(AsambleaVotacionOpcion).where(AsambleaVotacionOpcion.id == opcion.id)
               .values(conteo=AsambleaVotacionOpcion.conteo + 1, peso=AsambleaVotacionOpcion.peso + entrada["coef"]))   # incremento atómico en la base de datos
    if via == "App":
        reglas.registrar_evento(db, a.id, "VotoEmitido", actor, unidad_id=entrada["unidad_id"], detalle=f"«{v.titulo[:80]}» · {entrada['coef']:g} % · por la app (voto secreto)")
    else:
        reglas.registrar_evento(db, a.id, "VotoRegistrado", actor, unidad_id=entrada["unidad_id"],
                                detalle=f"«{v.titulo[:60]}» · {entrada['coef']:g} % · {opcion.texto[:60]} · voto presencial registrado por el administrador")


# ---------------------------------------------------------------- resultado
def _pct(parte: float, base: float) -> float:
    return round(parte * 100.0 / base, DECIMALES) if base > 0 else 0.0


def calcular_resultado(db: Session, a: Asamblea, v: AsambleaVotacion, q: dict) -> dict:
    """Resultado de la pregunta. Se calcula UNA vez, al cerrar, y se congela. La base de la mayoría simple es el coeficiente del padrón; la de la calificada, el 100 % del conjunto."""
    opciones = opciones_de(db, v.id)
    n_votos, peso_votos = db.query(func.count(AsambleaVoto.id), func.coalesce(func.sum(AsambleaVoto.peso), 0.0)).filter(AsambleaVoto.votacion_id == v.id).one()
    peso_votos = float(peso_votos or 0.0)
    por_via = dict(db.query(AsambleaVoto.via, func.count(AsambleaVoto.id)).filter(AsambleaVoto.votacion_id == v.id).group_by(AsambleaVoto.via).all())
    suma_conteo, suma_peso = sum(o.conteo for o in opciones), sum(o.peso for o in opciones)
    integra = suma_conteo == n_votos and abs(suma_peso - peso_votos) < 1e-6          # lo contado en las opciones coincide con las unidades que votaron
    ok_quorum, motivo_quorum = quorum_suficiente(a, q)
    coef_padron, coef_total = float(v.coef_padron or 0.0), float(v.coef_total or 0.0)
    padron = padron_de(v)

    motivos: list[str] = []
    if not ok_quorum:
        motivos.append(f"Se perdió el quórum antes de cerrar la votación. {motivo_quorum}")
    if not integra:
        motivos.append("Los votos contados no coinciden con las unidades que votaron: no se debe usar este resultado.")
    valida = not motivos

    res = {
        "tipo": v.tipo, "mayoria": v.mayoria, "regla": requisito(v),
        "unidades_padron": len(padron), "unidades_votaron": int(n_votos), "votos_app": int(por_via.get("App", 0)), "votos_presenciales": int(por_via.get("Manual", 0)),
        "coeficiente_padron": round(coef_padron, DECIMALES), "coeficiente_votaron": round(peso_votos, DECIMALES), "coeficiente_total": round(coef_total, DECIMALES),
        "coeficiente_sin_votar": round(max(0.0, coef_padron - peso_votos), DECIMALES),
        "quorum_apertura": v.quorum_apertura, "quorum_cierre": q["porcentaje"],
        "valida": valida, "motivos": motivos,
        "opciones": [{"id": o.id, "texto": o.texto, "votos": o.conteo, "coeficiente": round(o.peso, DECIMALES),
                      "porcentaje_presentes": _pct(o.peso, coef_padron), "porcentaje_conjunto": _pct(o.peso, coef_total)} for o in opciones],
        "integridad": {"votos_en_opciones": suma_conteo, "unidades_que_votaron": int(n_votos), "coincide": integra},
        "aprobada": None, "ganadora": None, "empate": False,
    }
    if v.tipo == TipoVotacionAsamblea.DECISION.value:
        favor = next(o for o in opciones if o.orden == 0)                              # «A favor» siempre es la primera opción de una decisión
        if v.mayoria == MayoriaAsamblea.CALIFICADA.value:
            cumple = _pct(favor.peso, coef_total) >= UMBRAL_CALIFICADA - TOLERANCIA
            res.update(umbral=UMBRAL_CALIFICADA, base="conjunto", porcentaje_a_favor=_pct(favor.peso, coef_total))
        else:
            cumple = favor.peso * 100.0 / coef_padron > UMBRAL_SIMPLE + TOLERANCIA if coef_padron > 0 else False
            res.update(umbral=UMBRAL_SIMPLE, base="presentes", porcentaje_a_favor=_pct(favor.peso, coef_padron))
        res["aprobada"] = bool(valida and cumple)
        if valida and not cumple:
            res["motivos"].append("No alcanzó la mayoría exigida.")
    else:
        ordenadas = sorted(opciones, key=lambda o: (-o.peso, o.orden))
        if ordenadas and ordenadas[0].peso > 0:
            empate = len(ordenadas) > 1 and abs(ordenadas[0].peso - ordenadas[1].peso) < TOLERANCIA
            res["empate"] = empate
            res["ganadora"] = None if empate else ordenadas[0].id
        if res["empate"]:
            res["motivos"].append("Hay empate en el primer lugar: la asamblea debe decidir cómo desempatar según su reglamento.")
    return res


def huella_resultado(res: dict) -> str:
    return hashlib.sha256(json.dumps(res, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def titular_resultado(v: AsambleaVotacion, res: dict) -> str:
    if not res["valida"]:
        return "SIN VALIDEZ"
    if v.tipo == TipoVotacionAsamblea.DECISION.value:
        return "APROBADA" if res["aprobada"] else "NO APROBADA"
    if res["empate"]:
        return "EMPATE"
    ganadora = next((o["texto"] for o in res["opciones"] if o["id"] == res["ganadora"]), None)
    return f"Gana {ganadora}" if ganadora else "Sin votos"


def cerrar(db: Session, a: Asamblea, v: AsambleaVotacion, actor: Usuario, q: dict) -> dict:
    exige_estado(v, EstadoVotacionAsamblea.ABIERTA, accion="cerrar")
    res = calcular_resultado(db, a, v, q)
    h = huella_resultado(res)
    v.estado, v.cerrada_en, v.cerrada_por, v.quorum_cierre = EstadoVotacionAsamblea.CERRADA.value, ahora_utc(), actor.id, q["porcentaje"]
    v.resultado, v.resultado_hash = json.dumps(res, ensure_ascii=False), h
    reglas.registrar_evento(db, a.id, "VotacionCerrada", actor,
                            detalle=f"#{v.numero} «{v.titulo[:70]}» · {titular_resultado(v, res)} · votaron {res['unidades_votaron']} de {res['unidades_padron']} unidades · huella {h[:16]}")
    return res


def anular(db: Session, a: Asamblea, v: AsambleaVotacion, actor: Usuario, motivo: str) -> None:
    exige_estado(v, EstadoVotacionAsamblea.BORRADOR, EstadoVotacionAsamblea.ABIERTA, accion="anular")
    estaba_abierta = v.estado == EstadoVotacionAsamblea.ABIERTA.value
    v.estado, v.cerrada_en, v.cerrada_por, v.motivo_anulacion = EstadoVotacionAsamblea.ANULADA.value, ahora_utc(), actor.id, motivo
    reglas.registrar_evento(db, a.id, "VotacionAnulada", actor, detalle=f"#{v.numero} «{v.titulo[:60]}» · {'estaba abierta · ' if estaba_abierta else ''}motivo: {motivo[:120]}")
