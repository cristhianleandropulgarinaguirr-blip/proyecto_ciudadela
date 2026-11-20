# tests/test_v46_asambleas.py — Versión 4.6: asambleas de copropietarios (Ley 675 de 2001).
# Cubre: calendario colombiano, unidades/coeficientes, plazos de convocatoria, bitácora encadenada, acreditación y quórum,
# segunda convocatoria, poderes, ingreso virtual, mora, permisos y la migración 0022.
import io
import os
import sqlite3
import tempfile
from datetime import date, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config

from app import calendario_co, config
from app.models import (Asamblea, AsambleaAsistente, AsambleaEvento, AsambleaPoder, Documento, Notificacion, Unidad, Usuario, ahora_utc)

PDF = b"%PDF-1.4\n% poder de prueba\n"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN, ANA, LUIS, CELADOR = "admin@conjunto.com", "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com"


# ------------------------------------------------------------------ ayudantes
def _coef(db, email: str, valor):
    u = db.query(Usuario).filter(Usuario.email == email).one()
    u.coeficiente = valor
    db.commit()


def base(client, auth, db, ana=40.0, luis=35.0, manual=25.0):
    """Tres unidades: Ana y Luis (con cuenta) y «Torre 3 Apt 303» (propietario sin cuenta). Suman 100 %."""
    _coef(db, ANA, ana)
    _coef(db, LUIS, luis)
    r = client.post("/unidades/", json={"apartamento": "Torre 3 Apt 303", "coeficiente": manual, "propietario_nombre": "Marta Sin Cuenta"}, headers=auth(ADMIN))
    assert r.status_code == 201, r.text
    resp = client.get("/unidades/", headers=auth(ADMIN)).json()
    assert resp["completo"] is True, resp
    return {u["apartamento"]: u["id"] for u in resp["items"]}


def datos_asamblea(dias=20, **extra):
    d = {"titulo": "Asamblea general de prueba", "tipo": "Extraordinaria", "modalidad": "Mixta", "fecha_sesion": (ahora_utc() + timedelta(days=dias)).isoformat() + "Z",
         "orden_del_dia": "1. Verificación del quórum\n2. Elección de presidente y secretario\n3. Proposiciones y varios", "lugar": "Salón comunal",
         "url_videollamada": "https://meet.example.com/asamblea"}
    d.update(extra)
    return d


def crear(client, auth, **kw):
    r = client.post("/asambleas/", json=datos_asamblea(**kw), headers=auth(ADMIN))
    assert r.status_code == 201, r.text
    return r.json()


def convocar(client, auth, aid):
    r = client.post(f"/asambleas/{aid}/convocar", headers=auth(ADMIN))
    assert r.status_code == 200, r.text
    return r.json()


def lista_para_sesion(client, auth, db, **kw):
    """Asamblea convocada y con la hora de la reunión «ahora» (se mueven las fechas en la base: no se puede esperar 20 días)."""
    a = crear(client, auth, **kw)
    convocar(client, auth, a["id"])
    acercar(db, a["id"])
    return a["id"]


def acercar(db, aid, minutos=0, segunda_en_horas=72):
    fila = db.query(Asamblea).filter(Asamblea.id == aid).one()
    fila.fecha_sesion = ahora_utc() + timedelta(minutes=minutos)
    fila.fecha_segunda = fila.fecha_sesion + timedelta(hours=segunda_en_horas)
    db.commit()


def acreditar(client, auth, aid, unidad_id, quien=ADMIN, **extra):
    return client.post(f"/asambleas/{aid}/asistentes", json={"unidad_id": unidad_id, **extra}, headers=auth(quien))


def quorum(client, auth, aid, quien=ADMIN):
    return client.get(f"/asambleas/{aid}/quorum", headers=auth(quien)).json()


def subir_poder(client, auth, aid, quien=ANA, nombre="Pedro Apoderado", doc="1.234.567", unidad_id=None, contenido=PDF, tipo="application/pdf", nombre_archivo="poder.pdf"):
    datos = {"apoderado_nombre": nombre, "apoderado_documento": doc}
    if unidad_id:
        datos["unidad_id"] = str(unidad_id)
    return client.post(f"/asambleas/{aid}/poderes", data=datos, files={"archivo": (nombre_archivo, contenido, tipo)}, headers=auth(quien))


# ================================================================ calendario colombiano
def test_festivos_2026_coinciden_con_el_calendario_oficial():
    esperado = {date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2), date(2026, 4, 3), date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8),
                date(2026, 6, 15), date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7), date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16),
                date(2026, 12, 8), date(2026, 12, 25)}
    assert calendario_co.festivos(2026) == esperado


def test_tercer_dia_habil_salta_festivos_y_fines_de_semana():
    assert calendario_co.tercer_dia_habil(date(2026, 12, 4)) == date(2026, 12, 10)       # el lunes 7, (martes 8 festivo), mié 9, jue 10
    assert calendario_co.tercer_dia_habil(date(2026, 11, 13)) == date(2026, 11, 19)      # lunes 16 festivo
    assert calendario_co.tercer_dia_habil(date(2026, 11, 19), sabado_habil=True) == date(2026, 11, 23)    # vie 20 (1), sáb 21 (2, cuenta el sábado), domingo no, lun 23 (3)
    assert calendario_co.es_dia_habil(date(2026, 11, 21)) is False and calendario_co.es_dia_habil(date(2026, 11, 21), sabado_habil=True) is True


def test_segunda_convocatoria_es_a_las_8pm_hora_colombia():
    s = calendario_co.segunda_convocatoria(datetime(2026, 12, 5, 15, 0))          # sábado 10 a. m. en Colombia
    assert s == datetime(2026, 12, 11, 1, 0)                                      # jueves 10 de diciembre, 8 p. m. (01:00 UTC del 11)


# ================================================================ unidades y coeficientes
def test_unidades_se_sincronizan_desde_los_residentes(client, auth, db):
    _coef(db, ANA, 12.5)
    r = client.get("/unidades/", headers=auth(ADMIN)).json()
    por_apto = {u["apartamento"]: u for u in r["items"]}
    assert set(por_apto) == {"Torre 1 Apt 101", "Torre 2 Apt 202"}
    assert por_apto["Torre 1 Apt 101"]["coeficiente"] == 12.5 and por_apto["Torre 1 Apt 101"]["tiene_cuenta"] is True
    assert por_apto["Torre 2 Apt 202"]["coeficiente"] is None
    assert r["completo"] is False and "Faltan coeficientes" in r["problema"]
    _coef(db, ANA, 20.0)                                                          # el cambio en «Usuarios» se refleja solo
    assert next(u for u in client.get("/unidades/", headers=auth(ADMIN)).json()["items"] if u["apartamento"] == "Torre 1 Apt 101")["coeficiente"] == 20.0


def test_unidad_manual_y_limites_del_coeficiente(client, auth, db):
    ids = base(client, auth, db)
    assert client.post("/unidades/", json={"apartamento": "torre 3  apt 303", "coeficiente": 1}, headers=auth(ADMIN)).status_code == 409      # misma unidad, otra escritura
    r = client.post("/unidades/", json={"apartamento": "Torre 4 Apt 404", "coeficiente": 5}, headers=auth(ADMIN))
    assert r.status_code == 400 and "100" in r.json()["detail"]                    # ya suman 100
    # la unidad con cuenta no se edita aquí; la manual sí
    assert client.patch(f"/unidades/{ids['Torre 1 Apt 101']}", json={"coeficiente": 30}, headers=auth(ADMIN)).status_code == 409
    assert client.patch(f"/unidades/{ids['Torre 3 Apt 303']}", json={"coeficiente": 30}, headers=auth(ADMIN)).status_code == 400   # 40+35+30 > 100
    assert client.patch(f"/unidades/{ids['Torre 3 Apt 303']}", json={"coeficiente": 20}, headers=auth(ADMIN)).status_code == 200
    assert client.get("/unidades/", headers=auth(ADMIN)).json()["completo"] is False                              # 95 %


def test_unidades_solo_para_el_administrador(client, auth, db):
    for quien in (ANA, CELADOR):
        assert client.get("/unidades/", headers=auth(quien)).status_code == 403
        assert client.post("/unidades/", json={"apartamento": "X1", "coeficiente": 1}, headers=auth(quien)).status_code == 403


# ================================================================ crear, ver y editar
def test_crear_asamblea_sugiere_la_segunda_convocatoria(client, auth, db):
    a = crear(client, auth)
    assert a["estado"] == "Borrador" and a["max_poderes"] == config.ASAMBLEA_MAX_PODERES and a["restringe_mora"] is False
    sesion = datetime.fromisoformat(a["fecha_sesion"])
    assert a["fecha_segunda"] == calendario_co.segunda_convocatoria(sesion, config.ASAMBLEA_SABADO_HABIL).isoformat()


def test_crear_valida_fechas_y_enlace(client, auth, db):
    h = auth(ADMIN)
    assert client.post("/asambleas/", json=datos_asamblea(dias=-1), headers=h).status_code == 400
    assert client.post("/asambleas/", json=datos_asamblea(url_videollamada="javascript:alert(1)"), headers=h).status_code == 422
    sesion = ahora_utc() + timedelta(days=20)
    assert client.post("/asambleas/", json=datos_asamblea(fecha_segunda=(sesion - timedelta(days=1)).isoformat() + "Z"), headers=h).status_code == 400


def test_borrador_es_invisible_para_residentes_y_guardia(client, auth, db):
    a = crear(client, auth)
    for quien in (ANA, CELADOR):
        assert client.get("/asambleas/", headers=auth(quien)).json() == []
        assert client.get(f"/asambleas/{a['id']}", headers=auth(quien)).status_code == 404
    assert len(client.get("/asambleas/", headers=auth(ADMIN)).json()) == 1


def test_solo_el_administrador_crea_y_edita(client, auth, db):
    a = crear(client, auth)
    assert client.post("/asambleas/", json=datos_asamblea(), headers=auth(ANA)).status_code == 403
    assert client.patch(f"/asambleas/{a['id']}", json={"titulo": "Otro título"}, headers=auth(ANA)).status_code == 403
    r = client.patch(f"/asambleas/{a['id']}", json={"titulo": "Otro título largo", "lugar": None}, headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["titulo"] == "Otro título largo" and r.json()["lugar"] is None


def test_cambiar_la_fecha_recalcula_la_segunda(client, auth, db):
    a = crear(client, auth)
    nueva = (ahora_utc() + timedelta(days=40)).replace(microsecond=0)
    r = client.patch(f"/asambleas/{a['id']}", json={"fecha_sesion": nueva.isoformat() + "Z"}, headers=auth(ADMIN)).json()
    assert r["fecha_segunda"] == calendario_co.segunda_convocatoria(nueva, config.ASAMBLEA_SABADO_HABIL).isoformat()


# ================================================================ convocar: plazos y requisitos
def test_ordinaria_exige_15_dias_completos(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth, tipo="Ordinaria", dias=15)                               # 15 días «justos»: no alcanzan (no se cuentan el envío ni la reunión)
    r = client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN))
    assert r.status_code == 400 and "15 días" in r.json()["detail"]


def test_ordinaria_exige_estados_financieros_adjuntos(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth, tipo="Ordinaria", dias=20)
    r = client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN))
    assert r.status_code == 400 and "estados financieros" in r.json()["detail"]
    otro = Documento(titulo="Circular", categoria="Circular", archivo="x.pdf", nombre_original="x.pdf", tamano=1)
    fin = Documento(titulo="Estados financieros 2026", categoria="Financiero", archivo="y.pdf", nombre_original="y.pdf", tamano=1)
    db.add_all([otro, fin])
    db.commit()
    assert client.post(f"/asambleas/{a['id']}/documentos", json={"documento_id": otro.id}, headers=auth(ADMIN)).status_code == 201
    assert client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN)).status_code == 400            # un documento de otra categoría no sirve
    assert client.post(f"/asambleas/{a['id']}/documentos", json={"documento_id": fin.id}, headers=auth(ADMIN)).status_code == 201
    assert client.post(f"/asambleas/{a['id']}/documentos", json={"documento_id": fin.id}, headers=auth(ADMIN)).status_code == 409   # ya adjunto
    r = client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN))
    assert r.status_code == 200 and {d["titulo"] for d in r.json()["asamblea"]["documentos"]} == {"Circular", "Estados financieros 2026"}


def test_extraordinaria_respeta_el_minimo_configurado(client, auth, db):
    base(client, auth, db)
    assert client.post(f"/asambleas/{crear(client, auth, dias=config.ASAMBLEA_DIAS_EXTRAORDINARIA)['id']}/convocar", headers=auth(ADMIN)).status_code == 400
    assert client.post(f"/asambleas/{crear(client, auth, dias=config.ASAMBLEA_DIAS_EXTRAORDINARIA + 2)['id']}/convocar", headers=auth(ADMIN)).status_code == 200


def test_virtual_exige_medios_tecnologicos_y_presencial_exige_lugar(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth, modalidad="Virtual", url_videollamada=None)
    assert "medios tecnológicos" in client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN)).json()["detail"]
    client.patch(f"/asambleas/{a['id']}", json={"instrucciones_virtual": "Entra con tu cuenta y pulsa «Conectarme»."}, headers=auth(ADMIN))
    assert client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN)).status_code == 200
    p = crear(client, auth, modalidad="Presencial", lugar=None)
    assert "lugar" in client.post(f"/asambleas/{p['id']}/convocar", headers=auth(ADMIN)).json()["detail"]


def test_convocar_deja_evidencia_y_avisa_a_cada_propietario(client, auth, db):
    _coef(db, LUIS, 35.0)
    luis = db.query(Usuario).filter(Usuario.email == LUIS).one()
    luis.esta_al_dia, luis.saldo_pendiente = False, 250000                           # Luis está en mora
    db.commit()
    ids = base(client, auth, db)
    a = crear(client, auth)
    r = convocar(client, auth, a["id"])
    asm = r["asamblea"]
    assert asm["estado"] == "Convocada" and len(asm["convocatoria_hash"]) == 64 and asm["fecha_convocatoria"]
    assert asm["morosos"] == [{"apartamento": "Torre 2 Apt 202", "saldo": 250000}]
    assert any("1 unidad(es) no tienen cuenta" in w for w in r["advertencias"])
    # una constancia por unidad: App para las que tienen cuenta, «sin cuenta» para la manual
    tipos = {(e.tipo, e.unidad_id) for e in db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a["id"]).all()}
    assert ("Notificada", ids["Torre 1 Apt 101"]) in tipos and ("Notificada", ids["Torre 2 Apt 202"]) in tipos and ("SinCuenta", ids["Torre 3 Apt 303"]) in tipos
    assert db.query(Notificacion).filter(Notificacion.titulo.like("Convocatoria:%")).count() == 2
    entregas = {e["apartamento"]: e["estado"] for e in client.get(f"/asambleas/{a['id']}/entregas", headers=auth(ADMIN)).json()}
    assert entregas == {"Torre 1 Apt 101": "App", "Torre 2 Apt 202": "App", "Torre 3 Apt 303": "Pendiente"}
    r = client.post(f"/asambleas/{a['id']}/entregas-manuales", json={"unidad_id": ids["Torre 3 Apt 303"], "canal": "Físico", "nota": "Recibió Marta"}, headers=auth(ADMIN))
    assert r.status_code == 201
    entregas = {e["apartamento"]: e["estado"] for e in client.get(f"/asambleas/{a['id']}/entregas", headers=auth(ADMIN)).json()}
    assert entregas["Torre 3 Apt 303"] == "Manual"


def test_una_asamblea_convocada_ya_no_se_edita_ni_se_convoca_otra_vez(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    assert client.patch(f"/asambleas/{a['id']}", json={"titulo": "Cambio posterior"}, headers=auth(ADMIN)).status_code == 409
    assert client.post(f"/asambleas/{a['id']}/convocar", headers=auth(ADMIN)).status_code == 409
    assert client.post(f"/asambleas/{a['id']}/documentos", json={"documento_id": 1}, headers=auth(ADMIN)).status_code == 409


def test_los_residentes_ven_la_convocada_pero_no_los_morosos(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    assert [x["id"] for x in client.get("/asambleas/", headers=auth(ANA)).json()] == [a["id"]]
    d = client.get(f"/asambleas/{a['id']}", headers=auth(ANA)).json()
    assert d["morosos"] is None and d["mi_unidad"]["apartamento"] == "Torre 1 Apt 101" and d["mi_unidad"]["presente"] is False
    assert [x["id"] for x in client.get("/asambleas/", headers=auth(CELADOR)).json()] == [a["id"]]


def test_pdf_de_la_convocatoria(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    assert client.get(f"/asambleas/{a['id']}/convocatoria.pdf", headers=auth(ADMIN)).status_code == 409        # aún es borrador
    convocar(client, auth, a["id"])
    r = client.get(f"/asambleas/{a['id']}/convocatoria.pdf", headers=auth(ADMIN))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert client.get(f"/asambleas/{a['id']}/convocatoria.pdf", headers=auth(ANA)).status_code == 403


def test_cancelar_avisa_y_no_se_puede_en_sesion(client, auth, db):
    ids = base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    antes = db.query(Notificacion).count()
    assert client.post(f"/asambleas/{a['id']}/cancelar", headers=auth(ADMIN)).json()["estado"] == "Cancelada"
    assert db.query(Notificacion).count() == antes + 2
    assert client.post(f"/asambleas/{a['id']}/cancelar", headers=auth(ADMIN)).status_code == 409
    # una cancelada que se había convocado sigue visible (con su estado); una en sesión no se cancela
    assert client.get(f"/asambleas/{a['id']}", headers=auth(ANA)).json()["estado"] == "Cancelada"
    aid = lista_para_sesion(client, auth, db)
    for u in ("Torre 1 Apt 101", "Torre 2 Apt 202"):
        assert acreditar(client, auth, aid, ids[u]).status_code == 201
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).status_code == 200
    assert client.post(f"/asambleas/{aid}/cancelar", headers=auth(ADMIN)).status_code == 409


# ================================================================ bitácora encadenada
def test_la_bitacora_detecta_cualquier_alteracion(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    r = client.get(f"/asambleas/{a['id']}/bitacora", headers=auth(ADMIN)).json()
    assert r["integra"] is True and r["total"] >= 5 and r["secuencia_danada"] is None
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a["id"], AsambleaEvento.secuencia == 2).one()
    ev.detalle = "Canal: Alterado a mano"                                           # alguien edita la base de datos
    db.commit()
    r = client.get(f"/asambleas/{a['id']}/bitacora", headers=auth(ADMIN)).json()
    assert r["integra"] is False and r["secuencia_danada"] == 2
    assert client.get(f"/asambleas/{a['id']}/bitacora", headers=auth(ANA)).status_code == 403


def test_borrar_un_evento_tambien_rompe_la_cadena(client, auth, db):
    base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a["id"], AsambleaEvento.secuencia == 3).delete()
    db.commit()
    r = client.get(f"/asambleas/{a['id']}/bitacora", headers=auth(ADMIN)).json()
    assert r["integra"] is False and r["secuencia_danada"] == 4


# ================================================================ acreditación y quórum
def test_el_registro_abre_tres_horas_antes(client, auth, db):
    ids = base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    r = acreditar(client, auth, a["id"], ids["Torre 1 Apt 101"])
    assert r.status_code == 409 and "abre 3 horas antes" in r.json()["detail"]
    acercar(db, a["id"], minutos=150)                                               # faltan 2 h 30 min: ya está abierto
    assert acreditar(client, auth, a["id"], ids["Torre 1 Apt 101"]).status_code == 201


def test_acreditar_suma_al_quorum_y_la_salida_lo_baja(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    r = acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    assert r.status_code == 201
    body = r.json()
    assert body["asistente"]["nombre"] == "Ana Residente" and body["asistente"]["coeficiente_acreditado"] == 40.0 and body["quorum"]["porcentaje"] == 40.0
    assert body["quorum"]["hay_quorum"] is False and body["quorum"]["faltan_para_quorum"] == 10.0
    r2 = acreditar(client, auth, aid, ids["Torre 2 Apt 202"], quien=CELADOR)         # el guardia también acredita en la puerta
    assert r2.status_code == 201 and r2.json()["quorum"]["porcentaje"] == 75.0 and r2.json()["quorum"]["hay_quorum"] is True
    asist = client.get(f"/asambleas/{aid}/asistentes", headers=auth(ADMIN)).json()
    luis = next(x for x in asist if x["apartamento"] == "Torre 2 Apt 202")
    out = client.post(f"/asambleas/{aid}/asistentes/{luis['id']}/salida", headers=auth(CELADOR))
    assert out.status_code == 200 and out.json()["quorum"]["porcentaje"] == 40.0
    assert client.post(f"/asambleas/{aid}/asistentes/{luis['id']}/salida", headers=auth(ADMIN)).status_code == 409   # ya había salido


def test_una_unidad_cuenta_una_sola_vez_y_puede_reingresar(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    u = ids["Torre 1 Apt 101"]
    primera = acreditar(client, auth, aid, u).json()
    assert acreditar(client, auth, aid, u).status_code == 409
    client.post(f"/asambleas/{aid}/asistentes/{primera['asistente']['id']}/salida", headers=auth(ADMIN))
    assert quorum(client, auth, aid)["porcentaje"] == 0
    again = acreditar(client, auth, aid, u)
    assert again.status_code == 201 and again.json()["asistente"]["id"] == primera["asistente"]["id"] and quorum(client, auth, aid)["porcentaje"] == 40.0
    tipos = [e.tipo for e in db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.unidad_id == u).order_by(AsambleaEvento.secuencia)]
    assert tipos == ["Notificada", "Acreditó", "Salió", "Reingreso"]


def test_el_coeficiente_acreditado_es_una_foto(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 3 Apt 303"], nombre="Marta Sin Cuenta")           # unidad manual: 25 %
    unidad = db.query(Unidad).filter(Unidad.id == ids["Torre 3 Apt 303"]).one()
    unidad.coeficiente = 10.0                                                                  # alguien la edita después
    db.commit()
    asist = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == aid).one()
    assert asist.coeficiente_acreditado == 25.0
    assert quorum(client, auth, aid)["coeficiente_presente"] == 25.0


def test_unidad_sin_cuenta_exige_nombre_y_sin_coeficiente_no_se_acredita(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    assert acreditar(client, auth, aid, ids["Torre 3 Apt 303"]).status_code == 400            # ¿quién asiste por esa unidad?
    r = acreditar(client, auth, aid, ids["Torre 3 Apt 303"], nombre="Marta Sin Cuenta", documento="52123456")
    assert r.status_code == 201 and r.json()["asistente"]["documento"] == "52123456"
    db.query(Unidad).filter(Unidad.id == ids["Torre 3 Apt 303"]).one().coeficiente = None
    db.commit()
    asist = db.query(AsambleaAsistente).one()
    client.post(f"/asambleas/{aid}/asistentes/{asist.id}/salida", headers=auth(ADMIN))
    assert acreditar(client, auth, aid, ids["Torre 3 Apt 303"], nombre="Marta").status_code == 400


def test_la_modalidad_de_ingreso_debe_coincidir_con_la_asamblea(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db, modalidad="Presencial", url_videollamada=None)
    assert acreditar(client, auth, aid, ids["Torre 1 Apt 101"], modalidad="Virtual").status_code == 400
    assert acreditar(client, auth, aid, ids["Torre 1 Apt 101"], modalidad="Presencial").status_code == 201


def test_solo_administrador_y_guardia_acreditan(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    assert acreditar(client, auth, aid, ids["Torre 1 Apt 101"], quien=ANA).status_code == 403
    assert client.get(f"/asambleas/{aid}/unidades", headers=auth(ANA)).status_code == 403
    assert client.get(f"/asambleas/{aid}/asistentes", headers=auth(ANA)).status_code == 403


def test_tablero_de_acreditacion(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    t = {x["apartamento"]: x for x in client.get(f"/asambleas/{aid}/unidades", headers=auth(CELADOR)).json()}
    assert t["Torre 1 Apt 101"]["presente"] is True and t["Torre 2 Apt 202"]["presente"] is False
    assert t["Torre 3 Apt 303"]["tiene_cuenta"] is False and t["Torre 3 Apt 303"]["coeficiente"] == 25.0


# ================================================================ instalar, sin quórum, segunda convocatoria y cierre
def test_instalar_en_primera_convocatoria_exige_mas_del_50(client, auth, db):
    ids = base(client, auth, db, ana=30.0, luis=20.0, manual=50.0)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    acreditar(client, auth, aid, ids["Torre 2 Apt 202"])                                       # 50 % exacto: NO es «más de la mitad»
    assert quorum(client, auth, aid)["hay_quorum"] is False
    r = client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    assert r.status_code == 409 and "Sin quórum" in r.json()["detail"]
    acreditar(client, auth, aid, ids["Torre 3 Apt 303"], nombre="Marta")
    r = client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["estado"] == "En sesión" and r.json()["convocatoria_numero"] == 1 and r.json()["quorum_inicial"] == 100.0
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).status_code == 409


def test_no_se_instala_antes_de_la_hora_ni_con_coeficientes_incompletos(client, auth, db):
    ids = base(client, auth, db)
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    assert "Aún no es la hora" in client.post(f"/asambleas/{a['id']}/instalar", headers=auth(ADMIN)).json()["detail"]
    acercar(db, a["id"])
    acreditar(client, auth, a["id"], ids["Torre 1 Apt 101"])
    acreditar(client, auth, a["id"], ids["Torre 2 Apt 202"])
    db.query(Unidad).filter(Unidad.id == ids["Torre 3 Apt 303"]).one().coeficiente = 10.0     # ahora suman 85 %
    db.commit()
    r = client.post(f"/asambleas/{a['id']}/instalar", headers=auth(ADMIN))
    assert r.status_code == 409 and "No se puede calcular el quórum" in r.json()["detail"]


def test_segunda_convocatoria_completa(client, auth, db):
    ids = base(client, auth, db, ana=20.0, luis=20.0, manual=60.0)
    aid = lista_para_sesion(client, auth, db, minutos=0)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    acreditar(client, auth, aid, ids["Torre 2 Apt 202"])                                       # 40 %: no hay quórum
    assert client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).status_code == 409
    # no se puede declarar «sin quórum» antes de la hora citada
    futura = db.query(Asamblea).filter(Asamblea.id == aid).one()
    futura.fecha_sesion = ahora_utc() + timedelta(hours=1)
    db.commit()
    assert "Aún no es la hora" in client.post(f"/asambleas/{aid}/sin-quorum", headers=auth(ADMIN)).json()["detail"]
    acercar(db, aid, minutos=-5)
    r = client.post(f"/asambleas/{aid}/sin-quorum", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["sin_quorum_en"]
    assert client.post(f"/asambleas/{aid}/sin-quorum", headers=auth(ADMIN)).status_code == 409
    assert quorum(client, auth, aid)["unidades_presentes"] == 0                               # se liberaron: deben acreditarse de nuevo
    # aún falta para la segunda convocatoria (en 72 h)
    assert "segunda convocatoria" in client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN)).json()["detail"]
    f = db.query(Asamblea).filter(Asamblea.id == aid).one()
    f.fecha_segunda = ahora_utc()
    db.commit()
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    r = client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    assert r.status_code == 409 and "número plural" in r.json()["detail"]                    # una sola unidad no es «plural»
    acreditar(client, auth, aid, ids["Torre 2 Apt 202"])
    r = client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["convocatoria_numero"] == 2 and r.json()["quorum_inicial"] == 40.0


def test_no_se_declara_sin_quorum_si_ya_lo_hay(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    acreditar(client, auth, aid, ids["Torre 2 Apt 202"])
    assert "Ya hay quórum" in client.post(f"/asambleas/{aid}/sin-quorum", headers=auth(ADMIN)).json()["detail"]


def test_cerrar_guarda_el_quorum_final_y_bloquea_cambios(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    acreditar(client, auth, aid, ids["Torre 2 Apt 202"])
    client.post(f"/asambleas/{aid}/instalar", headers=auth(ADMIN))
    luis = next(x for x in client.get(f"/asambleas/{aid}/asistentes", headers=auth(ADMIN)).json() if x["apartamento"] == "Torre 2 Apt 202")
    client.post(f"/asambleas/{aid}/asistentes/{luis['id']}/salida", headers=auth(ADMIN))      # se retira antes del cierre
    r = client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["estado"] == "Cerrada" and r.json()["quorum_inicial"] == 75.0 and r.json()["quorum_final"] == 40.0
    assert acreditar(client, auth, aid, ids["Torre 3 Apt 303"], nombre="Marta").status_code == 409
    assert client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN)).status_code == 409
    integra = client.get(f"/asambleas/{aid}/bitacora", headers=auth(ADMIN)).json()
    assert integra["integra"] is True and integra["eventos"][0]["tipo"] == "Cerrada"


# ================================================================ poderes
def test_flujo_de_un_poder(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    r = subir_poder(client, auth, aid)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["estado"] == "Pendiente" and p["apartamento"] == "Torre 1 Apt 101" and p["apoderado_documento"] == "1234567" and p["tipo_archivo"] == "pdf"
    assert subir_poder(client, auth, aid).status_code == 409                                   # un solo poder activo por unidad
    # no se puede acreditar al apoderado mientras esté pendiente
    assert acreditar(client, auth, aid, ids["Torre 1 Apt 101"], tipo="Apoderado", poder_id=p["id"]).status_code == 400
    ok = client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={}, headers=auth(ADMIN))
    assert ok.status_code == 200 and ok.json()["estado"] == "Aprobado"
    assert client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={}, headers=auth(ADMIN)).status_code == 409
    r = acreditar(client, auth, aid, ids["Torre 1 Apt 101"], tipo="Apoderado", poder_id=p["id"])
    assert r.status_code == 201 and r.json()["asistente"]["es_apoderado"] is True and r.json()["asistente"]["nombre"] == "Pedro Apoderado"
    assert r.json()["quorum"]["porcentaje"] == 40.0
    assert client.post(f"/asambleas/{aid}/poderes/{p['id']}/rechazar", json={"motivo": "Ya no"}, headers=auth(ADMIN)).status_code == 409   # ya se usó
    avisos = db.query(Notificacion).filter(Notificacion.titulo == "Tu poder fue aprobado").count()
    assert avisos == 1


def test_poder_rechazado_permite_subir_otro(client, auth, db):
    base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    pid = subir_poder(client, auth, aid).json()["id"]
    assert client.post(f"/asambleas/{aid}/poderes/{pid}/rechazar", json={"motivo": "x"}, headers=auth(ADMIN)).status_code == 422       # el motivo es obligatorio
    r = client.post(f"/asambleas/{aid}/poderes/{pid}/rechazar", json={"motivo": "Falta la firma"}, headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["estado"] == "Rechazado" and r.json()["motivo"] == "Falta la firma"
    assert subir_poder(client, auth, aid, nombre="Otra Persona", doc="7654321").status_code == 201


def test_limite_de_poderes_por_persona(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)                                                   # máximo 2 por defecto
    mismos = {"nombre": "Pedro Apoderado", "doc": "1.234.567"}
    p1 = subir_poder(client, auth, aid, quien=ANA, **mismos).json()
    p2 = subir_poder(client, auth, aid, quien=LUIS, **mismos).json()
    p3 = subir_poder(client, auth, aid, quien=ADMIN, unidad_id=ids["Torre 3 Apt 303"], **mismos).json()
    for p in (p1, p2):
        assert client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={}, headers=auth(ADMIN)).status_code == 200
    r = client.post(f"/asambleas/{aid}/poderes/{p3['id']}/aprobar", json={}, headers=auth(ADMIN))
    assert r.status_code == 400 and "máximo" in r.json()["detail"]
    # el administrador puede subir un poder por una unidad sin cuenta, pero debe indicar la unidad
    assert subir_poder(client, auth, aid, quien=ADMIN, doc="999999").status_code == 400


def test_el_personal_del_conjunto_no_recibe_poderes(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    celador = db.query(Usuario).filter(Usuario.email == CELADOR).one()
    pid = subir_poder(client, auth, aid).json()["id"]
    r = client.post(f"/asambleas/{aid}/poderes/{pid}/aprobar", json={"apoderado_usuario_id": celador.id}, headers=auth(ADMIN))
    assert r.status_code == 400 and "personal" in r.json()["detail"]


def test_poder_de_otra_unidad_o_sin_poder_no_acredita(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    pid = subir_poder(client, auth, aid, quien=ANA).json()["id"]
    client.post(f"/asambleas/{aid}/poderes/{pid}/aprobar", json={}, headers=auth(ADMIN))
    assert acreditar(client, auth, aid, ids["Torre 2 Apt 202"], tipo="Apoderado", poder_id=pid).status_code == 400    # el poder es de Ana, no de Luis
    assert acreditar(client, auth, aid, ids["Torre 1 Apt 101"], tipo="Apoderado").status_code == 400                    # sin poder


def test_archivos_de_poderes_validan_el_contenido(client, auth, db):
    base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    assert subir_poder(client, auth, aid, contenido=b"no soy un pdf", tipo="application/pdf").status_code == 400
    assert subir_poder(client, auth, aid, contenido=b"MZ...", tipo="application/octet-stream", nombre_archivo="virus.exe").status_code == 400
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    r = subir_poder(client, auth, aid, contenido=buf.getvalue(), tipo="image/png", nombre_archivo="poder.png")
    assert r.status_code == 201 and r.json()["tipo_archivo"] == "imagen"
    arch = client.get(f"/asambleas/{aid}/poderes/{r.json()['id']}/archivo", headers=auth(ANA))
    assert arch.status_code == 200 and arch.headers["content-type"].startswith("image/")


def test_privacidad_de_los_poderes(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    p = subir_poder(client, auth, aid, quien=ANA).json()
    assert client.get(f"/asambleas/{aid}/poderes/{p['id']}/archivo", headers=auth(ADMIN)).content == PDF
    assert client.get(f"/asambleas/{aid}/poderes/{p['id']}/archivo", headers=auth(ANA)).status_code == 200
    assert client.get(f"/asambleas/{aid}/poderes/{p['id']}/archivo", headers=auth(LUIS)).status_code == 403               # el de otra unidad
    assert client.get(f"/asambleas/{aid}/poderes/{p['id']}/archivo", headers=auth(CELADOR)).status_code == 403
    assert client.get(f"/asambleas/{aid}/poderes", headers=auth(LUIS)).json() == []                                       # solo ve los suyos
    assert len(client.get(f"/asambleas/{aid}/poderes", headers=auth(ANA)).json()) == 1
    assert client.get(f"/asambleas/{aid}/poderes", headers=auth(CELADOR)).json() == []                                    # el guardia solo ve los aprobados
    client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={}, headers=auth(ADMIN))
    assert len(client.get(f"/asambleas/{aid}/poderes", headers=auth(CELADOR)).json()) == 1
    assert client.post(f"/asambleas/{aid}/poderes/{p['id']}/aprobar", json={}, headers=auth(ANA)).status_code == 403


def test_no_se_suben_poderes_a_un_borrador_ni_estando_presente(client, auth, db):
    ids = base(client, auth, db)
    a = crear(client, auth)
    assert subir_poder(client, auth, a["id"]).status_code == 404                                # el residente ni siquiera ve el borrador
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"])
    assert subir_poder(client, auth, aid).status_code == 409                                    # Ana ya está presente: no necesita poder


# ================================================================ ingreso virtual
def test_ingreso_virtual_propio(client, auth, db):
    base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    r = client.post(f"/asambleas/{aid}/ingresar", headers=auth(ANA))
    assert r.status_code == 201 and r.json()["asistente"]["modalidad_ingreso"] == "Virtual" and r.json()["quorum"]["virtuales"] == 1
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(ANA)).status_code == 409
    assert client.get(f"/asambleas/{aid}", headers=auth(ANA)).json()["mi_unidad"]["presente"] is True
    q = client.get(f"/asambleas/{aid}/quorum", headers=auth(ANA)).json()
    assert q["porcentaje"] == 40.0
    out = client.post(f"/asambleas/{aid}/salir", headers=auth(ANA))
    assert out.status_code == 200 and out.json()["quorum"]["porcentaje"] == 0
    assert client.post(f"/asambleas/{aid}/salir", headers=auth(ANA)).status_code == 404
    assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(CELADOR)).status_code == 403      # solo residentes se conectan por sí mismos


def test_ingreso_virtual_no_aplica_a_presenciales_ni_fuera_de_ventana(client, auth, db):
    base(client, auth, db)
    pres = lista_para_sesion(client, auth, db, modalidad="Presencial", url_videollamada=None)
    assert client.post(f"/asambleas/{pres}/ingresar", headers=auth(ANA)).status_code == 400
    a = crear(client, auth)
    convocar(client, auth, a["id"])
    assert "abre 3 horas antes" in client.post(f"/asambleas/{a['id']}/ingresar", headers=auth(ANA)).json()["detail"]


def test_solo_sale_quien_se_conecto_con_su_cuenta(client, auth, db):
    ids = base(client, auth, db)
    aid = lista_para_sesion(client, auth, db)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"], modalidad="Virtual")                   # lo acreditó el administrador
    assert client.post(f"/asambleas/{aid}/salir", headers=auth(ANA)).status_code == 200          # coincide con su cuenta (usuario_id)
    acreditar(client, auth, aid, ids["Torre 1 Apt 101"], nombre="Una Tercera Persona", modalidad="Virtual")
    assert client.post(f"/asambleas/{aid}/salir", headers=auth(ANA)).status_code == 404          # ya no es ella


# ================================================================ mora
def test_mora_sin_restriccion_vota_con_restriccion_no(client, auth, db):
    ids = base(client, auth, db)
    luis = db.query(Usuario).filter(Usuario.email == LUIS).one()
    luis.esta_al_dia, luis.saldo_pendiente = False, 100000
    db.commit()
    libre = lista_para_sesion(client, auth, db)
    r = acreditar(client, auth, libre, ids["Torre 2 Apt 202"]).json()
    assert r["asistente"]["en_mora"] is True and r["asistente"]["con_voto"] is True              # la ley no le quita el voto; solo el reglamento
    estricta = lista_para_sesion(client, auth, db, restringe_mora=True)
    r = acreditar(client, auth, estricta, ids["Torre 2 Apt 202"]).json()
    assert r["asistente"]["con_voto"] is False and r["quorum"]["porcentaje"] == 35.0 and r["quorum"]["coeficiente_con_voto"] == 0.0     # cuenta para el quórum, no para votar


# ================================================================ documentos adjuntos
def test_un_documento_de_una_convocatoria_enviada_no_se_borra(client, auth, db):
    base(client, auth, db)
    d1 = Documento(titulo="Presupuesto", categoria="Financiero", archivo="a.pdf", nombre_original="a.pdf", tamano=1)
    d2 = Documento(titulo="Borrador de informe", categoria="Otros", archivo="b.pdf", nombre_original="b.pdf", tamano=1)
    db.add_all([d1, d2])
    db.commit()
    enviada, borrador = crear(client, auth), crear(client, auth)
    client.post(f"/asambleas/{enviada['id']}/documentos", json={"documento_id": d1.id}, headers=auth(ADMIN))
    client.post(f"/asambleas/{borrador['id']}/documentos", json={"documento_id": d2.id}, headers=auth(ADMIN))
    convocar(client, auth, enviada["id"])
    r = client.delete(f"/documentos/{d1.id}", headers=auth(ADMIN))
    assert r.status_code == 409 and "evidencia" in r.json()["detail"]
    assert client.delete(f"/documentos/{d2.id}", headers=auth(ADMIN)).status_code == 200         # solo estaba en un borrador
    assert client.get(f"/asambleas/{borrador['id']}", headers=auth(ADMIN)).json()["documentos"] == []


def test_se_puede_quitar_un_documento_de_un_borrador(client, auth, db):
    d = Documento(titulo="Informe", categoria="Otros", archivo="a.pdf", nombre_original="a.pdf", tamano=1)
    db.add(d)
    db.commit()
    a = crear(client, auth)
    client.post(f"/asambleas/{a['id']}/documentos", json={"documento_id": d.id}, headers=auth(ADMIN))
    assert client.delete(f"/asambleas/{a['id']}/documentos/{d.id}", headers=auth(ADMIN)).json()["documentos"] == []
    assert client.delete(f"/asambleas/{a['id']}/documentos/{d.id}", headers=auth(ADMIN)).status_code == 404


# ================================================================ migración 0022
def _config_alembic(url: str) -> Config:
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _tablas(ruta: str) -> set[str]:
    con = sqlite3.connect(ruta)
    try:
        return {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


NUEVAS = {"unidades", "asambleas", "asamblea_documentos", "asamblea_eventos", "asamblea_poderes", "asamblea_asistentes"}


def test_migracion_0022_crea_y_revierte_las_tablas():
    with tempfile.TemporaryDirectory() as tmp:
        ruta = os.path.join(tmp, "m.db")
        cfg = _config_alembic(f"sqlite:///{ruta}")
        command.upgrade(cfg, "head")
        assert NUEVAS <= _tablas(ruta)
        command.upgrade(cfg, "head")                                                              # correrla otra vez no rompe nada
        command.downgrade(cfg, "0021")
        assert not (NUEVAS & _tablas(ruta)) and "usuarios" in _tablas(ruta)
        command.upgrade(cfg, "head")                                                              # y se puede volver a subir
        assert NUEVAS <= _tablas(ruta)
