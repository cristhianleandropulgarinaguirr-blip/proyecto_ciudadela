# tests/test_v52_votaciones_asamblea.py — Versión 5.2: votaciones dentro de la asamblea (Fase 3, Ley 675 de 2001).
# Cubre: creación y permisos, bloqueo del 70 % (virtual, mixta, 2.ª convocatoria), apertura (quórum, una sola abierta, padrón congelado), voto secreto desde la app,
# voto presencial nominal, apoderados, mayoría simple y calificada (incluidos los límites exactos), elecciones, quórum perdido, integridad, resultado congelado,
# anulación, bitácora encadenada y la migración 0023.
import hashlib
import json
import os
import tempfile

import pytest
from alembic import command
from sqlalchemy.exc import IntegrityError

from app.models import (Asamblea, AsambleaAsistente, AsambleaVotacion, AsambleaVotacionOpcion, AsambleaVoto, Auditoria, Notificacion, Usuario, ahora_utc)
from tests.test_v46_asambleas import (ADMIN, ANA, CELADOR, LUIS, NUEVAS, _config_alembic, _tablas, acercar, acreditar, base, convocar, crear, lista_para_sesion, quorum, subir_poder)

APTO_ANA, APTO_LUIS, MARTA = "Torre 1 Apt 101", "Torre 2 Apt 202", "Torre 3 Apt 303"
FAVOR, CONTRA, ABST = "A favor", "En contra", "Abstención"


# ------------------------------------------------------------------ ayudantes
def sesion(client, auth, db, modalidad="Mixta", virtuales=(), presenciales=(), coef=None, **kw):
    """Asamblea INSTALADA: los `virtuales` se conectan solos desde la app y los `presenciales` los acredita el administrador. Devuelve (id de la asamblea, ids de unidades)."""
    ids = base(client, auth, db, **(coef or {}))
    aid = lista_para_sesion(client, auth, db, modalidad=modalidad, **kw)
    for email in virtuales:
        r = client.post(f"/asambleas/{aid}/ingresar", headers=auth(email))
        assert r.status_code == 201, r.text
    for apto in presenciales:
        r = acreditar(client, auth, aid, ids[apto], **({"nombre": "Marta Sin Cuenta"} if apto == MARTA else {}))
        assert r.status_code == 201, r.text
    r = client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    assert r.status_code == 200, r.text
    return aid, ids


def nueva(client, auth, aid, titulo="¿Aprueba el presupuesto 2027?", **extra):
    return client.post(f"/asambleas/{aid}/votaciones", json={"titulo": titulo, **extra}, headers=auth(ADMIN))


def abierta(client, auth, aid, titulo="¿Aprueba el presupuesto 2027?", **extra):
    """Crea y abre una votación; devuelve su JSON ya abierto."""
    v = nueva(client, auth, aid, titulo, **extra)
    assert v.status_code == 201, v.text
    r = client.post(f"/asambleas/{aid}/votaciones/{v.json()['id']}/abrir", headers=auth(ADMIN))
    assert r.status_code == 200, r.text
    return r.json()


def op(v, texto):
    return next(o["id"] for o in v["opciones"] if o["texto"] == texto)


def votar(client, auth, aid, v, quien, texto, **extra):
    return client.post(f"/asambleas/{aid}/votaciones/{v['id']}/votar", json={"opcion_id": op(v, texto), **extra}, headers=auth(quien))


def presencial(client, auth, aid, v, unidad_id, texto, quien=ADMIN):
    return client.post(f"/asambleas/{aid}/votaciones/{v['id']}/votos-presenciales", json={"unidad_id": unidad_id, "opcion_id": op(v, texto)}, headers=auth(quien))


def cerrar(client, auth, aid, v):
    r = client.post(f"/asambleas/{aid}/votaciones/{v['id']}/cerrar", headers=auth(ADMIN))
    assert r.status_code == 200, r.text
    return r.json()


def ver(client, auth, aid, v, quien=ADMIN):
    r = client.get(f"/asambleas/{aid}/votaciones/{v['id']}", headers=auth(quien))
    assert r.status_code == 200, r.text
    return r.json()


# ================================================================ crear
def test_decision_tiene_opciones_fijas_y_se_numera(client, auth, db):
    aid, _ = sesion(client, auth, db, virtuales=(ANA, LUIS))
    v1 = nueva(client, auth, aid)
    assert v1.status_code == 201, v1.text
    d = v1.json()
    assert d["estado"] == "Borrador" and d["numero"] == 1 and d["tipo"] == "Decisión" and d["mayoria"] == "Simple"
    assert [o["texto"] for o in d["opciones"]] == [FAVOR, CONTRA, ABST]
    assert nueva(client, auth, aid, "Segundo punto").json()["numero"] == 2
    assert "más del 50 %" in d["requisito"]


def test_validaciones_de_la_creacion(client, auth, db):
    aid, _ = sesion(client, auth, db, virtuales=(ANA, LUIS))
    assert nueva(client, auth, aid, "ab").status_code == 422                                              # título muy corto
    assert nueva(client, auth, aid, opciones=["Sí", "No"]).status_code == 422                             # una decisión no lleva opciones escritas
    assert nueva(client, auth, aid, tipo="Elección", opciones=["Solo una"]).status_code == 422
    assert nueva(client, auth, aid, tipo="Elección", opciones=["Pedro", "pedro"]).status_code == 422      # repetidas
    assert nueva(client, auth, aid, tipo="Elección", opciones=["Pedro", "Juana"], mayoria="Calificada").status_code == 422   # el 70 % es para decisiones
    ok = nueva(client, auth, aid, "Consejo de administración", tipo="Elección", opciones=["Pedro", "Juana", "Rosa"])
    assert ok.status_code == 201 and [o["texto"] for o in ok.json()["opciones"]] == ["Pedro", "Juana", "Rosa"]


def test_solo_el_administrador_crea_abre_cierra_y_anula(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS))
    for quien in (ANA, CELADOR):
        assert client.post(f"/asambleas/{aid}/votaciones", json={"titulo": "Intento"}, headers=auth(quien)).status_code == 403
    v = nueva(client, auth, aid).json()
    for quien in (ANA, CELADOR):
        assert client.post(f"/asambleas/{aid}/votaciones/{v['id']}/abrir", headers=auth(quien)).status_code == 403
        assert client.post(f"/asambleas/{aid}/votaciones/{v['id']}/cerrar", headers=auth(quien)).status_code == 403
        assert client.post(f"/asambleas/{aid}/votaciones/{v['id']}/anular", json={"motivo": "Sin permiso"}, headers=auth(quien)).status_code == 403
    assert client.post(f"/asambleas/{aid}/votaciones").status_code in (401, 403)                          # sin sesión


def test_el_residente_no_ve_borradores_y_el_guardia_solo_mira(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS))
    borrador = nueva(client, auth, aid, "Todavía no").json()
    abierta_ = abierta(client, auth, aid, "Ya se vota")
    assert [x["titulo"] for x in client.get(f"/asambleas/{aid}/votaciones", headers=auth(ADMIN)).json()] == ["Todavía no", "Ya se vota"]
    assert [x["titulo"] for x in client.get(f"/asambleas/{aid}/votaciones", headers=auth(ANA)).json()] == ["Ya se vota"]
    assert client.get(f"/asambleas/{aid}/votaciones/{borrador['id']}", headers=auth(ANA)).status_code == 404
    assert client.get(f"/asambleas/{aid}/votaciones", headers=auth(CELADOR)).status_code == 200
    assert votar(client, auth, aid, abierta_, CELADOR, FAVOR).status_code == 403                          # el guardia no vota


# ================================================================ bloqueo del 70 %
@pytest.mark.parametrize("modalidad,texto", [("Virtual", "no presencial"), ("Mixta", "mixtas")])
def test_no_se_crea_votacion_de_70_en_asamblea_virtual_ni_mixta(client, auth, db, modalidad, texto):
    base(client, auth, db)
    a = crear(client, auth, modalidad=modalidad)
    convocar(client, auth, a["id"])
    r = nueva(client, auth, a["id"], mayoria="Calificada")
    assert r.status_code == 400 and texto in r.json()["detail"]
    assert nueva(client, auth, a["id"], mayoria="Simple").status_code == 201                              # la simple sí


def test_si_el_abogado_lo_permite_el_bloqueo_se_apaga(client, auth, db, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "ASAMBLEA_BLOQUEA_70_MIXTA", False)
    base(client, auth, db)
    a = crear(client, auth, modalidad="Mixta")
    convocar(client, auth, a["id"])
    assert nueva(client, auth, a["id"], mayoria="Calificada").status_code == 201


def test_70_bloqueado_si_la_asamblea_se_instalo_en_segunda_convocatoria(client, auth, db):
    ids = base(client, auth, db, ana=20.0, luis=20.0, manual=60.0)
    aid = lista_para_sesion(client, auth, db, modalidad="Presencial")
    pendiente = nueva(client, auth, aid, "Reforma del reglamento", mayoria="Calificada")                  # presencial y aún sin instalar: se puede preparar
    assert pendiente.status_code == 201
    acreditar(client, auth, aid, ids[APTO_ANA])
    acreditar(client, auth, aid, ids[APTO_LUIS])                                                          # 40 %: no hay quórum en la primera
    acercar(db, aid, minutos=-5)
    assert client.post(f"/asambleas/{aid}/sin-quorum", headers=auth(ADMIN)).status_code == 200
    db.query(Asamblea).filter(Asamblea.id == aid).one().fecha_segunda = ahora_utc()
    db.commit()
    acreditar(client, auth, aid, ids[APTO_ANA])
    acreditar(client, auth, aid, ids[APTO_LUIS])
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).json()["convocatoria_numero"] == 2
    r = client.post(f"/asambleas/{aid}/votaciones/{pendiente.json()['id']}/abrir", headers=auth(ADMIN))
    assert r.status_code == 409 and "segunda convocatoria" in r.json()["detail"]
    assert nueva(client, auth, aid, "Otra del 70", mayoria="Calificada").status_code == 400
    # una decisión de mayoría simple sí se puede tomar en segunda convocatoria (basta un número plural de propietarios)
    assert abierta(client, auth, aid, "Mayoría simple")["estado"] == "Abierta"


# ================================================================ abrir
def test_no_se_abre_con_la_asamblea_sin_instalar(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    v = nueva(client, auth, a["id"]).json()                                                               # se puede preparar
    r = client.post(f"/asambleas/{a['id']}/votaciones/{v['id']}/abrir", headers=auth(ADMIN))
    assert r.status_code == 409 and "instala la asamblea" in r.json()["detail"]


def test_no_se_abre_sin_quorum(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS))
    v = nueva(client, auth, aid).json()
    client.post(f"/asambleas/{aid}/salir", headers=auth(LUIS))                                            # queda Ana sola: 40 %
    r = client.post(f"/asambleas/{aid}/votaciones/{v['id']}/abrir", headers=auth(ADMIN))
    assert r.status_code == 409 and "quórum" in r.json()["detail"]


def test_solo_una_votacion_abierta_a_la_vez(client, auth, db):
    aid, _ = sesion(client, auth, db, virtuales=(ANA, LUIS))
    primera = abierta(client, auth, aid, "Primera")
    segunda = nueva(client, auth, aid, "Segunda").json()
    r = client.post(f"/asambleas/{aid}/votaciones/{segunda['id']}/abrir", headers=auth(ADMIN))
    assert r.status_code == 409 and "Ya hay una votación abierta" in r.json()["detail"]
    cerrar(client, auth, aid, primera)
    assert client.post(f"/asambleas/{aid}/votaciones/{segunda['id']}/abrir", headers=auth(ADMIN)).status_code == 200
    assert client.post(f"/asambleas/{aid}/votaciones/{segunda['id']}/abrir", headers=auth(ADMIN)).status_code == 409   # ya está abierta


def test_la_base_de_datos_tambien_impide_dos_abiertas_y_dos_votos(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid)
    db.add(AsambleaVotacion(asamblea_id=aid, numero=99, titulo="Intruso", tipo="Decisión", mayoria="Simple", estado="Abierta"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert votar(client, auth, aid, v, ANA, FAVOR).status_code == 200
    fila = db.query(AsambleaVoto).filter(AsambleaVoto.votacion_id == v["id"]).one()
    db.add(AsambleaVoto(votacion_id=v["id"], unidad_id=fila.unidad_id, asistente_id=fila.asistente_id, peso=1.0, via="App"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_abrir_avisa_a_quienes_votan_desde_la_app(client, auth, db):
    aid, _ = sesion(client, auth, db, virtuales=(ANA, LUIS), presenciales=(MARTA,))
    abierta(client, auth, aid, "Cambio de portería")
    avisos = db.query(Notificacion).filter(Notificacion.titulo.like("Se abrió una votación%")).count()
    assert avisos == 2                                                                                    # Ana y Luis (Marta es presencial y no tiene cuenta)


def test_advertencia_si_un_virtual_no_tiene_cuenta(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db, modalidad="Virtual")
    for email in (ANA, LUIS):
        client.post(f"/asambleas/{aid}/ingresar", headers=auth(email))
    assert acreditar(client, auth, aid, ids[MARTA], nombre="Marta Sin Cuenta", modalidad="Virtual").status_code == 201
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).status_code == 200
    v = abierta(client, auth, aid)
    assert any(MARTA in w and "NO podrán votar" in w for w in v["advertencias"])
    fila = next(p for p in v["padron"] if p["apartamento"] == MARTA)
    assert fila["sin_medio"] is True
    assert presencial(client, auth, aid, v, ids[MARTA], FAVOR).status_code == 409                         # nadie vota «por» un asistente virtual


# ================================================================ voto secreto desde la app
def test_voto_virtual_es_secreto_y_se_cuenta(client, auth, db):
    aid, ids = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid, "Aprobación del presupuesto")
    assert v["estado"] == "Abierta" and v["quorum_apertura"] == 75.0 and v["participacion"]["unidades_padron"] == 2
    r = votar(client, auth, aid, v, ANA, FAVOR)
    assert r.status_code == 200, r.text
    assert r.json()["mis_unidades"][0]["ya_voto"] is True and "ya quedó registrado" in r.json()["mensaje_votante"]
    assert votar(client, auth, aid, v, ANA, CONTRA).status_code == 409                                    # no se cambia ni se repite
    # --- secreto: no queda guardado qué votó, ni en la tabla de votos, ni en la bitácora, ni en la auditoría
    voto = db.query(AsambleaVoto).filter(AsambleaVoto.votacion_id == v["id"]).one()
    assert voto.via == "App" and voto.opcion_id is None and voto.peso == 40.0
    bit = client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()
    emitido = [e for e in bit["eventos"] if e["tipo"] == "VotoEmitido"]
    assert len(emitido) == 1 and not any(t in emitido[0]["detalle"] for t in (FAVOR, CONTRA, ABST))
    assert not any(t in (a.detalle or "") for a in db.query(Auditoria).filter(Auditoria.accion == "Votó en una asamblea") for t in (FAVOR, CONTRA, ABST))
    # --- mientras está abierta nadie ve resultados parciales, ni el administrador
    for quien in (ADMIN, ANA, LUIS):
        d = ver(client, auth, aid, v, quien)
        assert d["resultado"] is None and all(o["votos"] is None and o["coeficiente"] is None for o in d["opciones"])
    parcial = ver(client, auth, aid, v)["participacion"]
    assert parcial["unidades_votaron"] == 1 and parcial["porcentaje"] == pytest.approx(53.33, abs=0.01)
    assert votar(client, auth, aid, v, LUIS, CONTRA).status_code == 200
    r = cerrar(client, auth, aid, v)
    res = r["resultado"]
    assert res["valida"] is True and res["aprobada"] is True and res["votos_app"] == 2 and res["votos_presenciales"] == 0
    assert res["porcentaje_a_favor"] == pytest.approx(53.3333, abs=0.001) and res["base"] == "presentes"
    assert {o["texto"]: o["coeficiente"] for o in r["opciones"]} == {FAVOR: 40.0, CONTRA: 35.0, ABST: 0.0}
    assert res["integridad"]["coincide"] is True


def test_el_resultado_queda_congelado_con_su_huella(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    votar(client, auth, aid, v, LUIS, FAVOR)
    cerrada = cerrar(client, auth, aid, v)
    esperado = hashlib.sha256(json.dumps(cerrada["resultado"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    assert cerrada["resultado_hash"] == esperado and len(esperado) == 64
    bit = client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()
    assert bit["integra"] is True
    cierre = next(e for e in bit["eventos"] if e["tipo"] == "VotacionCerrada")
    assert esperado[:16] in cierre["detalle"] and "APROBADA" in cierre["detalle"]
    # los residentes ven el mismo resultado; no se puede votar ni cerrar de nuevo
    assert ver(client, auth, aid, v, ANA)["resultado"] == cerrada["resultado"]
    assert votar(client, auth, aid, v, ANA, FAVOR).status_code == 409
    assert client.post(f"/asambleas/{aid}/votaciones/{v['id']}/cerrar", headers=auth(ADMIN)).status_code == 409
    assert client.post(f"/asambleas/{aid}/votaciones/{v['id']}/anular", json={"motivo": "Ya cerrada"}, headers=auth(ADMIN)).status_code == 409


def test_opcion_de_otra_votacion_y_unidad_ajena(client, auth, db):
    aid, ids = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    otra = nueva(client, auth, aid, "Otra pregunta").json()
    v = abierta(client, auth, aid, "La que se vota")
    r = client.post(f"/asambleas/{aid}/votaciones/{v['id']}/votar", json={"opcion_id": op(otra, FAVOR)}, headers=auth(ANA))
    assert r.status_code == 400 and "no pertenece" in r.json()["detail"]
    r = client.post(f"/asambleas/{aid}/votaciones/{v['id']}/votar", json={"opcion_id": op(v, FAVOR), "unidad_id": ids[APTO_LUIS]}, headers=auth(ANA))
    assert r.status_code == 403                                                                           # nadie vota por la unidad de otro


# ================================================================ padrón congelado y salidas
def test_quien_llega_despues_de_abrir_no_vota_esa_pregunta(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(MARTA,))                         # 65 %
    v = abierta(client, auth, aid)
    assert v["participacion"]["unidades_padron"] == 2
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(LUIS)).status_code == 201              # llega tarde
    r = votar(client, auth, aid, v, LUIS, FAVOR)
    assert r.status_code == 403 and "padrón" in r.json()["detail"]
    assert "No estás en el padrón" in ver(client, auth, aid, v, LUIS)["mensaje_votante"]
    assert quorum(client, auth, aid)["unidades_presentes"] == 3                                           # pero sí cuenta para el quórum


def test_quien_sale_antes_de_votar_ya_no_puede_votar(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(MARTA,))
    v = abierta(client, auth, aid)
    client.post(f"/asambleas/{aid}/salir", headers=auth(ANA))
    r = votar(client, auth, aid, v, ANA, FAVOR)
    assert r.status_code == 403 and "Ya no estás conectado" in r.json()["detail"]
    marta = next(a for a in client.get(f"/asambleas/{aid}/asistentes", headers=auth(ADMIN)).json() if a["apartamento"] == MARTA)
    assert client.post(f"/asambleas/{aid}/asistentes/{marta['id']}/salida", headers=auth(ADMIN)).status_code == 200
    r = presencial(client, auth, aid, v, ids[MARTA], FAVOR)
    assert r.status_code == 409 and "ya salió" in r.json()["detail"]
    # quien se reconecta (misma acreditación) vuelve a poder votar
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(ANA)).status_code == 201
    assert votar(client, auth, aid, v, ANA, FAVOR).status_code == 200


def test_si_otra_persona_ocupa_la_acreditacion_el_antiguo_ya_no_vota(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(MARTA,))
    v = abierta(client, auth, aid)
    fila = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == aid, AsambleaAsistente.unidad_id == ids[APTO_ANA]).one()
    fila.usuario_id = None                                                                                # la acreditación cambió de manos
    db.commit()
    assert votar(client, auth, aid, v, ANA, FAVOR).status_code == 403


def test_asistente_en_mora_con_restriccion_no_entra_al_padron(client, auth, db):
    luis = db.query(Usuario).filter(Usuario.email == LUIS).one()
    luis.esta_al_dia, luis.saldo_pendiente = False, 100000
    db.commit()
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS), presenciales=(MARTA,), restringe_mora=True)
    v = abierta(client, auth, aid)
    assert v["participacion"]["unidades_padron"] == 2 and v["participacion"]["coeficiente_padron"] == 65.0   # Luis cuenta para el quórum, no para votar
    assert votar(client, auth, aid, v, LUIS, FAVOR).status_code == 403
    votar(client, auth, aid, v, ANA, FAVOR)
    presencial(client, auth, aid, v, ids[MARTA], FAVOR)
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["aprobada"] is True and res["coeficiente_padron"] == 65.0                                  # 100 % del coeficiente con derecho a voto


# ================================================================ voto presencial
def test_voto_presencial_lo_registra_el_administrador_y_es_nominal(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(MARTA,))
    v = abierta(client, auth, aid, "Cambio de portería")
    assert presencial(client, auth, aid, v, ids[MARTA], FAVOR, quien=ANA).status_code == 403              # un residente no registra votos
    assert presencial(client, auth, aid, v, ids[MARTA], FAVOR, quien=CELADOR).status_code == 403          # ni el guardia
    assert presencial(client, auth, aid, v, ids[APTO_LUIS], FAVOR).status_code == 404                     # Luis no está en el padrón
    assert presencial(client, auth, aid, v, ids[APTO_ANA], FAVOR).status_code == 409                      # Ana es virtual: solo ella vota
    r = presencial(client, auth, aid, v, ids[MARTA], FAVOR)
    assert r.status_code == 200, r.text
    fila = next(p for p in r.json()["padron"] if p["apartamento"] == MARTA)
    assert fila["ya_voto"] is True and fila["opcion_registrada"] == FAVOR and fila["via"] == "Manual"      # nominal: consta lo que votó
    assert presencial(client, auth, aid, v, ids[MARTA], CONTRA).status_code == 409                        # una sola vez
    voto = db.query(AsambleaVoto).filter(AsambleaVoto.unidad_id == ids[MARTA]).one()
    assert voto.via == "Manual" and voto.opcion_id is not None and voto.emitido_por is not None
    ev = next(e for e in client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()["eventos"] if e["tipo"] == "VotoRegistrado")
    assert FAVOR in ev["detalle"] and "presencial" in ev["detalle"]


# ================================================================ mayorías
def test_mayoria_simple_no_alcanza_y_si_alcanza(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS), presenciales=(MARTA,))                     # 40 / 35 / 25
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    votar(client, auth, aid, v, LUIS, CONTRA)
    presencial(client, auth, aid, v, ids[MARTA], ABST)                                                    # la abstención no suma a favor
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["valida"] is True and res["aprobada"] is False and res["porcentaje_a_favor"] == 40.0 and "No alcanzó la mayoría exigida." in res["motivos"]
    v2 = abierta(client, auth, aid, "Segunda pregunta")
    votar(client, auth, aid, v2, ANA, FAVOR)
    votar(client, auth, aid, v2, LUIS, CONTRA)
    presencial(client, auth, aid, v2, ids[MARTA], FAVOR)
    assert cerrar(client, auth, aid, v2)["resultado"]["aprobada"] is True                                 # 65 % a favor de lo presente


def test_exactamente_la_mitad_no_es_mayoria_simple(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS), presenciales=(MARTA,), coef={"ana": 50.0, "luis": 30.0, "manual": 20.0})
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    votar(client, auth, aid, v, LUIS, CONTRA)
    presencial(client, auth, aid, v, ids[MARTA], CONTRA)
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["porcentaje_a_favor"] == 50.0 and res["aprobada"] is False                                 # «más de la mitad»: el 50 % justo no basta


def test_mayoria_calificada_se_mide_sobre_todo_el_conjunto_no_sobre_los_presentes(client, auth, db):
    aid, ids = sesion(client, auth, db, modalidad="Presencial", presenciales=(APTO_ANA, MARTA))           # 65 % presente
    v = abierta(client, auth, aid, "Reforma del reglamento", mayoria="Calificada")
    presencial(client, auth, aid, v, ids[APTO_ANA], FAVOR)
    presencial(client, auth, aid, v, ids[MARTA], FAVOR)                                                   # 100 % de los presentes, pero solo 65 % del conjunto
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["valida"] is True and res["base"] == "conjunto" and res["umbral"] == 70.0
    assert res["porcentaje_a_favor"] == 65.0 and res["aprobada"] is False


def test_mayoria_calificada_aprueba_con_el_70_o_mas(client, auth, db):
    aid, ids = sesion(client, auth, db, modalidad="Presencial", presenciales=(APTO_ANA, APTO_LUIS, MARTA))
    v = abierta(client, auth, aid, "Cambio de destinación", mayoria="Calificada")
    presencial(client, auth, aid, v, ids[APTO_ANA], FAVOR)
    presencial(client, auth, aid, v, ids[APTO_LUIS], FAVOR)
    presencial(client, auth, aid, v, ids[MARTA], CONTRA)
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["porcentaje_a_favor"] == 75.0 and res["aprobada"] is True


def test_el_70_justo_cuenta_aunque_los_decimales_estorben(client, auth, db):
    aid, ids = sesion(client, auth, db, modalidad="Presencial", presenciales=(APTO_ANA, APTO_LUIS, MARTA), coef={"ana": 44.9, "luis": 25.1, "manual": 30.0})
    v = abierta(client, auth, aid, "Límite exacto", mayoria="Calificada")
    presencial(client, auth, aid, v, ids[APTO_ANA], FAVOR)
    presencial(client, auth, aid, v, ids[APTO_LUIS], FAVOR)
    presencial(client, auth, aid, v, ids[MARTA], CONTRA)
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["porcentaje_a_favor"] == 70.0 and res["aprobada"] is True


# ================================================================ apoderados
def test_apoderado_virtual_vota_por_cada_unidad_que_representa(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db, modalidad="Mixta")
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    p = subir_poder(client, auth, aid, quien=LUIS, nombre="Ana Residente", doc="52.111.222").json()      # Luis le da poder a Ana
    assert client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={"apoderado_usuario_id": ana.id}, headers=auth(ADMIN)).status_code == 200
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(ANA)).status_code == 201               # Ana, por su unidad
    assert acreditar(client, auth, aid, ids[APTO_LUIS], tipo="Apoderado", poder_id=p["id"], modalidad="Virtual").status_code == 201   # y por la de Luis
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).status_code == 200
    v = abierta(client, auth, aid)
    mis = ver(client, auth, aid, v, ANA)["mis_unidades"]
    assert {m["apartamento"] for m in mis} == {APTO_ANA, APTO_LUIS} and all(m["puede_votar"] for m in mis)
    r = votar(client, auth, aid, v, ANA, FAVOR)
    assert r.status_code == 400 and "más de una unidad" in r.json()["detail"]                             # debe decir por cuál
    assert votar(client, auth, aid, v, ANA, FAVOR, unidad_id=ids[APTO_LUIS]).status_code == 200
    assert votar(client, auth, aid, v, ANA, CONTRA).status_code == 200                                    # queda una sola pendiente: la suya
    assert votar(client, auth, aid, v, ANA, CONTRA).status_code == 409
    assert db.query(AsambleaVoto).filter(AsambleaVoto.votacion_id == v["id"]).count() == 2
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(LUIS)).status_code == 409              # la unidad de Luis ya está representada: nadie más vota por ella
    assert votar(client, auth, aid, v, LUIS, FAVOR).status_code == 403


# ================================================================ elecciones
def test_eleccion_gana_la_opcion_con_mas_coeficiente(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA, LUIS), presenciales=(MARTA,))
    v = abierta(client, auth, aid, "Consejo de administración", tipo="Elección", opciones=["Pedro", "Juana"])
    votar(client, auth, aid, v, ANA, "Pedro")                                                             # 40
    votar(client, auth, aid, v, LUIS, "Juana")                                                            # 35
    presencial(client, auth, aid, v, ids[MARTA], "Juana")                                                 # 25 → Juana 60
    r = cerrar(client, auth, aid, v)
    res = r["resultado"]
    assert res["aprobada"] is None and res["empate"] is False and res["ganadora"] == op(v, "Juana")
    assert next(o for o in r["opciones"] if o["texto"] == "Juana")["porcentaje_presentes"] == 60.0


def test_eleccion_empatada_no_declara_ganador(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS), coef={"ana": 30.0, "luis": 30.0, "manual": 40.0})
    v = abierta(client, auth, aid, "Comité de convivencia", tipo="Elección", opciones=["Pedro", "Juana"])
    votar(client, auth, aid, v, ANA, "Pedro")
    votar(client, auth, aid, v, LUIS, "Juana")
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["empate"] is True and res["ganadora"] is None and any("empate" in m for m in res["motivos"])


# ================================================================ quórum e integridad al cerrar
def test_si_se_pierde_el_quorum_el_resultado_no_tiene_validez(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    votar(client, auth, aid, v, LUIS, FAVOR)
    client.post(f"/asambleas/{aid}/salir", headers=auth(LUIS))                                            # queda 40 %: se perdió el quórum
    r = cerrar(client, auth, aid, v)
    res = r["resultado"]
    assert res["valida"] is False and res["aprobada"] is False and res["quorum_apertura"] == 75.0 and res["quorum_cierre"] == 40.0
    assert any("quórum" in m for m in res["motivos"])
    cierre = next(e for e in client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()["eventos"] if e["tipo"] == "VotacionCerrada")
    assert "SIN VALIDEZ" in cierre["detalle"]


def test_si_los_contadores_no_cuadran_con_los_votos_el_resultado_se_marca_sin_validez(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    votar(client, auth, aid, v, LUIS, FAVOR)
    o = db.get(AsambleaVotacionOpcion, op(v, FAVOR))
    o.conteo += 1                                                                                         # alguien tocó la base de datos a mano
    db.commit()
    res = cerrar(client, auth, aid, v)["resultado"]
    assert res["valida"] is False and res["aprobada"] is False and res["integridad"]["coincide"] is False
    assert any("no coinciden" in m for m in res["motivos"])


def test_no_se_cierra_la_asamblea_con_una_votacion_abierta(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    v = abierta(client, auth, aid)
    r = client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN))
    assert r.status_code == 409 and "votación abierta" in r.json()["detail"]
    cerrar(client, auth, aid, v)
    assert client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN)).status_code == 200
    assert nueva(client, auth, aid, "Tarde").status_code == 409                                           # asamblea cerrada: no se crean más


# ================================================================ anular
def test_anular_exige_motivo_y_deja_constancia(client, auth, db):
    aid, _ = sesion(client, auth, db, modalidad="Virtual", virtuales=(ANA, LUIS))
    borrador = nueva(client, auth, aid, "Se me fue un punto").json()
    assert client.post(f"/asambleas/{aid}/votaciones/{borrador['id']}/anular", json={"motivo": "no"}, headers=auth(ADMIN)).status_code == 422
    r = client.post(f"/asambleas/{aid}/votaciones/{borrador['id']}/anular", json={"motivo": "Error de redacción"}, headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["estado"] == "Anulada" and r.json()["motivo_anulacion"] == "Error de redacción"
    v = abierta(client, auth, aid, "Mal planteada")
    votar(client, auth, aid, v, ANA, FAVOR)
    anulada = client.post(f"/asambleas/{aid}/votaciones/{v['id']}/anular", json={"motivo": "La pregunta estaba mal formulada"}, headers=auth(ADMIN)).json()
    assert anulada["estado"] == "Anulada" and anulada["resultado"] is None and all(o["votos"] is None for o in anulada["opciones"])
    assert votar(client, auth, aid, v, LUIS, FAVOR).status_code == 409
    assert abierta(client, auth, aid, "Bien planteada")["estado"] == "Abierta"                            # al anular se libera el «una sola abierta»
    tipos = [e["tipo"] for e in client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()["eventos"]]
    assert tipos.count("VotacionAnulada") == 2


# ================================================================ bitácora
def test_todo_el_ciclo_queda_en_la_bitacora_encadenada(client, auth, db):
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(MARTA,))
    v = abierta(client, auth, aid)
    votar(client, auth, aid, v, ANA, FAVOR)
    presencial(client, auth, aid, v, ids[MARTA], FAVOR)
    cerrar(client, auth, aid, v)
    bit = client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()
    tipos = [e["tipo"] for e in bit["eventos"]]
    for t in ("VotacionCreada", "VotacionAbierta", "VotoEmitido", "VotoRegistrado", "VotacionCerrada"):
        assert t in tipos
    assert bit["integra"] is True


# ================================================================ no se rompe lo anterior
def test_las_votaciones_del_conjunto_siguen_independientes(client, auth, db):
    aid, _ = sesion(client, auth, db, virtuales=(ANA, LUIS))
    abierta(client, auth, aid)
    r = client.get("/votaciones/", headers=auth(ANA))                                                      # el motor del conjunto no ve las de asamblea
    assert r.status_code == 200 and r.json() == []
    assert client.get("/votaciones/pendientes", headers=auth(ANA)).json() == {"pendientes": 0}


# ================================================================ migración 0023
NUEVAS_0023 = {"asamblea_votaciones", "asamblea_votacion_opciones", "asamblea_votos"}


def test_migracion_0023_crea_y_revierte_solo_sus_tablas():
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "m.db")
        cfg = _config_alembic(f"sqlite:///{ruta}")
        command.upgrade(cfg, "head")
        assert NUEVAS_0023 <= _tablas(ruta) and NUEVAS <= _tablas(ruta)
        command.upgrade(cfg, "head")                                                                       # correrla otra vez no rompe nada
        command.downgrade(cfg, "0022")
        assert not (NUEVAS_0023 & _tablas(ruta)) and NUEVAS <= _tablas(ruta)                              # la 0022 queda intacta
        command.upgrade(cfg, "head")
        assert NUEVAS_0023 <= _tablas(ruta)
