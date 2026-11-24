# tests/test_v54_acta_asamblea.py — Versión 5.4: acta de la asamblea (Fase 4, Art. 47 de la Ley 675 de 2001).
# Cubre: permisos, borrador (editar, PDF con marca de agua), sellado y congelado con huella, contenido del acta, verificación de integridad
# (detecta cambios en asistentes, texto y bitácora), copia firmada, publicación y notificaciones, plazo de 20 días hábiles,
# asamblea inmutable tras el cierre, contraseña de nuevo (v5.3) en sellar/publicar y la migración 0025.
import hashlib
import json
import os
import tempfile
from datetime import date, timedelta

from alembic import command
from reportlab import rl_config

from app import asamblea_acta as acta_reglas, asambleas as reglas, calendario_co
from app.models import Asamblea, AsambleaActa, AsambleaAsistente, AsambleaEvento, Notificacion
from app.models import ahora_utc
from tests.test_v46_asambleas import ADMIN, ANA, CELADOR, LUIS, PDF, _config_alembic, _tablas, lista_para_sesion
from tests.test_v52_votaciones_asamblea import APTO_LUIS, CONTRA, FAVOR, MARTA, abierta, cerrar, nueva, presencial, sesion, votar

DATOS = {"presidente_nombre": "Carlos Presidente", "secretario_nombre": "Sofia Secretaria", "comision": "Pedro Perez y Lucia Gomez",
         "desarrollo": "Se aprobo el presupuesto.\nSe cerro la sesion."}


# ------------------------------------------------------------------ ayudantes
def reunion(client, auth, db, cerrar_asamblea=True):
    """Asamblea mixta con 3 unidades presentes (Ana virtual; Luis y Marta presenciales) y una votación cerrada. Por defecto, también la asamblea cerrada."""
    aid, ids = sesion(client, auth, db, virtuales=(ANA,), presenciales=(APTO_LUIS, MARTA))
    v = abierta(client, auth, aid)
    assert votar(client, auth, aid, v, ANA, FAVOR).status_code == 200
    assert presencial(client, auth, aid, v, ids[APTO_LUIS], CONTRA).status_code in (200, 201)
    cerrar(client, auth, aid, v)
    if cerrar_asamblea:
        assert client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN)).status_code == 200
    return aid, ids


def guardar(client, auth, aid, **extra):
    return client.put(f"/asambleas/{aid}/acta", json={**DATOS, **extra}, headers=auth(ADMIN))


def sellar(client, auth, aid):
    return client.post(f"/asambleas/{aid}/acta/sellar", headers=auth(ADMIN))


def acta_sellada(client, auth, db):
    aid, ids = reunion(client, auth, db)
    assert guardar(client, auth, aid).status_code == 200
    r = sellar(client, auth, aid)
    assert r.status_code == 200, r.text
    return aid, ids, r.json()


def verificar(client, auth, aid):
    r = client.get(f"/asambleas/{aid}/acta/verificar", headers=auth(ADMIN))
    assert r.status_code == 200, r.text
    return r.json()


def prueba(v, nombre):
    return next(c for c in v["comprobaciones"] if c["nombre"] == nombre)


def sin_comprimir(monkeypatch):
    """Los PDF sin comprimir dejan leer el texto con `in` sobre los bytes."""
    monkeypatch.setattr(rl_config, "pageCompression", 0)


def firmada(client, auth, aid, contenido=PDF, tipo="application/pdf"):
    return client.post(f"/asambleas/{aid}/acta/firmada", files={"archivo": ("firmada.pdf", contenido, tipo)}, headers=auth(ADMIN))


# ================================================================ calendario y plazo
def test_dia_habil_numero_salta_festivos_y_fines_de_semana():
    assert calendario_co.dia_habil_numero(date(2026, 11, 23), 0) == date(2026, 11, 23)
    assert calendario_co.dia_habil_numero(date(2026, 11, 23), 20) == date(2026, 12, 22)        # el 8 de diciembre (Inmaculada Concepción) es festivo
    assert calendario_co.dia_habil_numero(date(2026, 11, 27), 1) == date(2026, 11, 30)         # viernes → lunes
    assert calendario_co.tercer_dia_habil(date(2026, 12, 4)) == date(2026, 12, 10)             # sigue igual que antes de la refactorización


# ================================================================ acceso y permisos
def test_el_acta_no_existe_antes_de_instalar(client, auth, db):
    aid = lista_para_sesion(client, auth, db)
    assert client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).status_code == 409
    assert guardar(client, auth, aid).status_code == 409
    assert client.get(f"/asambleas/{aid}/acta/borrador.pdf", headers=auth(ADMIN)).status_code == 409


def test_solo_el_administrador_prepara_el_acta(client, auth, db):
    aid, _ = reunion(client, auth, db)
    for quien, esperado in ((ANA, 403), (CELADOR, 403)):
        h = auth(quien)
        assert client.put(f"/asambleas/{aid}/acta", json=DATOS, headers=h).status_code == esperado
        assert client.post(f"/asambleas/{aid}/acta/sellar", headers=h).status_code == esperado
        assert client.get(f"/asambleas/{aid}/acta/borrador.pdf", headers=h).status_code == esperado
        assert client.post(f"/asambleas/{aid}/acta/publicar", headers=h).status_code == esperado
        assert client.get(f"/asambleas/{aid}/acta/verificar", headers=h).status_code == esperado
        assert client.post(f"/asambleas/{aid}/acta/firmada", files={"archivo": ("f.pdf", PDF, "application/pdf")}, headers=h).status_code == esperado
    assert client.get(f"/asambleas/{aid}/acta", headers=auth(CELADOR)).status_code == 403
    assert client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(CELADOR)).status_code == 403
    assert client.get(f"/asambleas/{aid}/acta").status_code in (401, 403)


# ================================================================ borrador
def test_guardar_borrador_crea_y_actualiza_solo_lo_enviado(client, auth, db):
    aid, _ = reunion(client, auth, db)
    r = client.put(f"/asambleas/{aid}/acta", json={"presidente_nombre": "  Carlos   Presidente "}, headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["presidente_nombre"] == "Carlos Presidente" and r.json()["estado"] == "Borrador" and r.json()["editable"] is True
    r = client.put(f"/asambleas/{aid}/acta", json={"secretario_nombre": "Sofia Secretaria"}, headers=auth(ADMIN))
    assert r.json()["presidente_nombre"] == "Carlos Presidente" and r.json()["secretario_nombre"] == "Sofia Secretaria"        # lo no enviado no se pierde
    assert client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).json()["secretario_nombre"] == "Sofia Secretaria"


def test_validaciones_del_borrador(client, auth, db):
    aid, _ = reunion(client, auth, db)
    assert client.put(f"/asambleas/{aid}/acta", json={"presidente_nombre": "ab"}, headers=auth(ADMIN)).status_code == 422
    assert client.put(f"/asambleas/{aid}/acta", json={"desarrollo": "x" * 20001}, headers=auth(ADMIN)).status_code == 422
    guardar(client, auth, aid)
    r = client.put(f"/asambleas/{aid}/acta", json={"comision": ""}, headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["comision"] is None                      # un texto vacío borra el campo


def test_se_puede_redactar_durante_la_sesion_pero_no_sellar(client, auth, db):
    aid, _ = reunion(client, auth, db, cerrar_asamblea=False)
    assert guardar(client, auth, aid).status_code == 200
    pdf = client.get(f"/asambleas/{aid}/acta/borrador.pdf", headers=auth(ADMIN))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    r = sellar(client, auth, aid)
    assert r.status_code == 409 and "Cierra primero" in r.json()["detail"]
    assert client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).json()["puede_sellar"] is False


def test_borrador_pdf_lleva_marca_de_agua_y_los_datos(client, auth, db, monkeypatch):
    sin_comprimir(monkeypatch)
    aid, _ = reunion(client, auth, db)
    guardar(client, auth, aid)
    r = client.get(f"/asambleas/{aid}/acta/borrador.pdf", headers=auth(ADMIN))
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.headers["cache-control"] == "private, no-store"
    for texto in (b"BORRADOR", b"Carlos Presidente", b"Sofia Secretaria", b"Pedro Perez"):
        assert texto in r.content


# ================================================================ sellar
def test_sellar_exige_dignatarios(client, auth, db):
    aid, _ = reunion(client, auth, db)
    r = sellar(client, auth, aid)
    assert r.status_code == 400 and "presidente" in r.json()["detail"]
    client.put(f"/asambleas/{aid}/acta", json={"presidente_nombre": "Carlos Presidente"}, headers=auth(ADMIN))
    r = sellar(client, auth, aid)
    assert r.status_code == 400 and "secretario" in r.json()["detail"]


def test_sellar_congela_y_deja_huella_en_la_bitacora(client, auth, db):
    aid, _, acta = acta_sellada(client, auth, db)
    assert acta["estado"] == "Sellada" and acta["editable"] is False and acta["puede_sellar"] is False and len(acta["contenido_hash"]) == 64
    fila = db.query(AsambleaActa).filter(AsambleaActa.asamblea_id == aid).one()
    assert hashlib.sha256(fila.contenido.encode("utf-8")).hexdigest() == acta["contenido_hash"]
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "ActaSellada").one()
    assert acta["contenido_hash"] in ev.detalle
    assert reglas.verificar_bitacora(db, aid)[0] is True
    # ya nada cambia
    assert sellar(client, auth, aid).status_code == 409
    assert guardar(client, auth, aid, desarrollo="otro texto").status_code == 409
    assert client.get(f"/asambleas/{aid}/acta/borrador.pdf", headers=auth(ADMIN)).status_code == 409


def test_no_se_sella_con_la_bitacora_alterada(client, auth, db):
    aid, _ = reunion(client, auth, db)
    guardar(client, auth, aid)
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "Instalada").one()
    ev.detalle = "manipulado"
    db.commit()
    r = sellar(client, auth, aid)
    assert r.status_code == 409 and "bitácora" in r.json()["detail"]


def test_el_contenido_cumple_lo_que_pide_el_articulo_47(client, auth, db):
    aid, ids, _ = acta_sellada(client, auth, db)
    c = json.loads(db.query(AsambleaActa).filter(AsambleaActa.asamblea_id == aid).one().contenido)
    assert c["asamblea"]["tipo"] in ("Ordinaria", "Extraordinaria") and c["asamblea"]["modalidad"] == "Mixta" and c["asamblea"]["orden_del_dia"]       # clase y orden del día
    assert c["convocatoria"]["unidades_avisadas"] >= 0 and c["asamblea"]["fecha_convocatoria"]                                                         # forma de la convocatoria
    asistentes = c["evidencia"]["asistentes"]
    assert len(asistentes) == 3 and {x["calidad"] for x in asistentes} == {"Propietario"} and all(x["coeficiente"] > 0 for x in asistentes)             # nombre, calidad, coeficiente
    assert all("documento" not in x for x in asistentes)                                                                                              # no se publica la cédula
    assert round(sum(x["coeficiente"] for x in asistentes), 4) == round(c["quorum"]["coeficiente_presente"], 4) and c["quorum"]["unidades_presentes"] == 3
    v = c["evidencia"]["votaciones"][0]
    assert v["estado"] == "Cerrada" and v["resultado"]["votos_app"] == 1 and v["resultado"]["votos_presenciales"] == 1 and v["resultado_hash"]           # votos emitidos
    assert [n["unidad"] for n in v["votos_nominales"]] == [APTO_LUIS] and v["votos_nominales"][0]["voto"] == CONTRA                                 # el voto de la app sigue siendo secreto
    assert c["dignatarios"]["presidente"] == "Carlos Presidente" and c["desarrollo"].startswith("Se aprobo")


def test_la_misma_asamblea_siempre_da_la_misma_huella(client, auth, db):
    aid, _ = reunion(client, auth, db)
    guardar(client, auth, aid)
    a = db.query(Asamblea).filter(Asamblea.id == aid).one()
    acta = acta_reglas.acta_de(db, aid)
    assert acta_reglas.huella(acta_reglas.construir_contenido(db, a, acta)) == acta_reglas.huella(acta_reglas.construir_contenido(db, a, acta))


def test_votaciones_sin_votar_y_segunda_convocatoria_constan_en_el_acta(client, auth, db):
    aid, _ = reunion(client, auth, db, cerrar_asamblea=False)
    assert nueva(client, auth, aid, "Propuesta que no se alcanzó a votar").status_code == 201
    assert client.post(f"/asambleas/{aid}/cerrar", headers=auth(ADMIN)).status_code == 200
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "Cerrada").one()
    assert "1 cerrada(s)" in ev.detalle and "1 sin votar" in ev.detalle
    a = db.query(Asamblea).filter(Asamblea.id == aid).one()
    a.convocatoria_numero, a.sin_quorum_en = 2, ahora_utc()
    db.commit()
    c = acta_reglas.construir_contenido(db, a, None)
    assert c["asamblea"]["convocatoria_numero"] == 2 and c["asamblea"]["sin_quorum_en"]
    assert [v["estado"] for v in c["evidencia"]["votaciones"]] == ["Cerrada", "Borrador"]
    assert acta_reglas.render_pdf(c, borrador=True).startswith(b"%PDF")


# ================================================================ PDF definitivo
def test_acta_definitiva_solo_para_el_administrador_hasta_publicar(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    r = client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ADMIN))
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get(f"/asambleas/{aid}/acta", headers=auth(ANA)).status_code == 404
    assert client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ANA)).status_code == 404
    assert client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(CELADOR)).status_code == 403


def test_el_pdf_definitivo_sale_de_la_copia_congelada(client, auth, db, monkeypatch):
    sin_comprimir(monkeypatch)
    aid, _, _ = acta_sellada(client, auth, db)
    antes = client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ADMIN)).content
    fila = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == aid).first()
    fila.nombre = "Nombre Manipulado"
    db.commit()
    despues = client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ADMIN)).content
    assert b"Nombre Manipulado" not in despues and b"Carlos Presidente" in despues and b"Sofia Secretaria" in despues and b"BORRADOR" not in despues
    assert len(antes) == len(despues)


def test_el_pdf_definitivo_no_se_pide_si_no_esta_sellada(client, auth, db):
    aid, _ = reunion(client, auth, db)
    assert client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ADMIN)).status_code == 409


# ================================================================ verificar
def test_verificar_antes_de_sellar_es_409(client, auth, db):
    aid, _ = reunion(client, auth, db)
    assert client.get(f"/asambleas/{aid}/acta/verificar", headers=auth(ADMIN)).status_code == 409


def test_verificar_un_acta_intacta(client, auth, db):
    aid, _, acta = acta_sellada(client, auth, db)
    v = verificar(client, auth, aid)
    assert v["ok"] is True and v["huella"] == acta["contenido_hash"] and [c["nombre"] for c in v["comprobaciones"]] == ["Texto del acta", "Asistentes y votos", "Bitácora encadenada"]
    assert all(c["ok"] for c in v["comprobaciones"])


def test_verificar_sigue_ok_aunque_se_agreguen_eventos_posteriores(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    assert firmada(client, auth, aid).status_code == 200
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN)).status_code == 200            # firmar y publicar agregan eventos a la bitácora
    v = verificar(client, auth, aid)
    assert v["ok"] is True and prueba(v, "Copia firmada")["ok"] is True


def test_verificar_detecta_que_cambiaron_los_asistentes(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    fila = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == aid).first()
    fila.coeficiente_acreditado = fila.coeficiente_acreditado + 0.01
    db.commit()
    v = verificar(client, auth, aid)
    assert v["ok"] is False and prueba(v, "Asistentes y votos")["ok"] is False and "asistentes" in prueba(v, "Asistentes y votos")["detalle"]
    assert prueba(v, "Texto del acta")["ok"] is True


def test_verificar_detecta_que_cambio_el_texto_congelado(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    fila = db.query(AsambleaActa).filter(AsambleaActa.asamblea_id == aid).one()
    fila.contenido = fila.contenido.replace("Carlos Presidente", "Otra Persona")
    db.commit()
    v = verificar(client, auth, aid)
    assert v["ok"] is False and prueba(v, "Texto del acta")["ok"] is False


def test_verificar_detecta_la_bitacora_alterada(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "Instalada").one()
    ev.detalle = "manipulado"
    db.commit()
    v = verificar(client, auth, aid)
    assert v["ok"] is False and prueba(v, "Bitácora encadenada")["ok"] is False


# ================================================================ copia firmada
def test_copia_firmada_exige_acta_sellada_y_pdf_valido(client, auth, db):
    aid, _ = reunion(client, auth, db)
    assert firmada(client, auth, aid).status_code == 409                                              # aún no está sellada
    guardar(client, auth, aid)
    sellar(client, auth, aid)
    assert firmada(client, auth, aid, contenido=b"\x89PNG....", tipo="image/png").status_code == 400
    assert firmada(client, auth, aid, contenido=b"no soy un pdf", tipo="application/pdf").status_code == 400


def test_copia_firmada_guarda_huella_evento_y_se_puede_reemplazar_antes_de_publicar(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    r = firmada(client, auth, aid)
    assert r.status_code == 200 and r.json()["tiene_firmada"] is True and r.json()["firmada_hash"] == hashlib.sha256(PDF).hexdigest()
    assert client.get(f"/asambleas/{aid}/acta/firmada", headers=auth(ADMIN)).content == PDF
    nuevo = PDF + b"% version 2\n"
    assert firmada(client, auth, aid, contenido=nuevo).json()["firmada_hash"] == hashlib.sha256(nuevo).hexdigest()
    eventos = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "ActaFirmada").order_by(AsambleaEvento.secuencia).all()
    assert len(eventos) == 2 and "reemplazó" in eventos[1].detalle and hashlib.sha256(nuevo).hexdigest() in eventos[1].detalle
    assert client.get(f"/asambleas/{aid}/acta/firmada", headers=auth(ANA)).status_code == 404          # el residente no la ve hasta publicar


def test_verificar_detecta_una_copia_firmada_distinta(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    firmada(client, auth, aid)
    fila = db.query(AsambleaActa).filter(AsambleaActa.asamblea_id == aid).one()
    fila.firmada_hash = "0" * 64
    db.commit()
    v = verificar(client, auth, aid)
    assert v["ok"] is False and prueba(v, "Copia firmada")["ok"] is False


# ================================================================ publicar
def test_publicar_exige_acta_sellada(client, auth, db):
    aid, _ = reunion(client, auth, db)
    guardar(client, auth, aid)
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN)).status_code == 409


def test_publicar_avisa_a_los_propietarios_y_les_abre_el_acta(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    firmada(client, auth, aid)
    antes = db.query(Notificacion).filter(Notificacion.titulo.like("Acta disponible%")).count()
    r = client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN))
    assert r.status_code == 200 and r.json()["publicada"] is True and r.json()["publicada_en"]
    assert db.query(Notificacion).filter(Notificacion.titulo.like("Acta disponible%")).count() > antes
    assert db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "ActaPublicada").count() == 1
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN)).status_code == 409
    # el propietario ve que está publicada, pero no el texto del borrador ni los nombres: lee el PDF
    vista = client.get(f"/asambleas/{aid}/acta", headers=auth(ANA))
    assert vista.status_code == 200 and vista.json()["publicada"] is True and vista.json()["presidente_nombre"] is None and vista.json()["desarrollo"] is None
    assert vista.json()["tiene_firmada"] is True
    assert client.get(f"/asambleas/{aid}/acta.pdf", headers=auth(ANA)).content.startswith(b"%PDF")
    assert client.get(f"/asambleas/{aid}/acta/firmada", headers=auth(LUIS)).content == PDF
    # y ya no se puede cambiar la copia firmada
    assert firmada(client, auth, aid, contenido=PDF + b"%otra\n").status_code == 409
    # el residente sigue sin poder hacer nada más
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ANA)).status_code == 403
    assert client.get(f"/asambleas/{aid}/acta/verificar", headers=auth(ANA)).status_code == 403


def test_publicar_sin_copia_firmada_se_permite_pero_se_advierte(client, auth, db):
    aid, _, acta = acta_sellada(client, auth, db)
    assert any("copia firmada" in x for x in client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).json()["advertencias"])
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN)).status_code == 200
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "ActaPublicada").one()
    assert "SIN copia firmada" in ev.detalle


# ================================================================ plazo de 20 días hábiles
def test_el_plazo_son_20_dias_habiles_desde_la_reunion(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    a = db.query(Asamblea).filter(Asamblea.id == aid).one()
    esperado = calendario_co.dia_habil_numero(reglas.local(a.instalada_en).date(), 20)
    r = client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).json()
    assert r["limite_publicacion"] == esperado.isoformat() and r["plazo_vencido"] is False


def test_plazo_vencido_se_advierte_y_queda_constancia(client, auth, db):
    aid, _, _ = acta_sellada(client, auth, db)
    a = db.query(Asamblea).filter(Asamblea.id == aid).one()
    a.instalada_en = ahora_utc() - timedelta(days=60)
    db.commit()
    r = client.get(f"/asambleas/{aid}/acta", headers=auth(ADMIN)).json()
    assert r["plazo_vencido"] is True and any("venció" in x for x in r["advertencias"])
    assert client.post(f"/asambleas/{aid}/acta/publicar", headers=auth(ADMIN)).status_code == 200
    ev = db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == aid, AsambleaEvento.tipo == "ActaPublicada").one()
    assert "fuera del plazo legal" in ev.detalle


# ================================================================ cierre: la reunión queda congelada
def test_cerrada_la_asamblea_nada_se_puede_modificar(client, auth, db):
    aid, ids = reunion(client, auth, db)
    h = auth(ADMIN)
    asistente = client.get(f"/asambleas/{aid}/asistentes", headers=h).json()[0]["id"]
    intentos = [
        ("patch", f"/asambleas/{aid}", {"json": {"titulo": "Otro título"}}),
        ("post", f"/asambleas/{aid}/asistentes", {"json": {"unidad_id": ids[APTO_LUIS]}}),
        ("post", f"/asambleas/{aid}/asistentes/{asistente}/salida", {}),
        ("post", f"/asambleas/{aid}/cancelar", {}),
        ("post", f"/asambleas/{aid}/cerrar", {}),
        ("post", f"/asambleas/{aid}/convocar", {}),
        ("post", f"/asambleas/{aid}/instalar", {}),
        ("post", f"/asambleas/{aid}/sin-quorum", {}),
        ("post", f"/asambleas/{aid}/documentos", {"json": {"documento_id": 1}}),
        ("post", f"/asambleas/{aid}/entregas-manuales", {"json": {"unidad_id": ids[APTO_LUIS], "canal": "Físico"}}),
        ("post", f"/asambleas/{aid}/votaciones", {"json": {"titulo": "Nueva pregunta tardía"}}),
    ]
    for metodo, ruta, extra in intentos:
        r = getattr(client, metodo)(ruta, headers=h, **extra)
        assert r.status_code == 409, f"{metodo.upper()} {ruta} debería rechazarse con 409 y dio {r.status_code}: {r.text}"
    for quien in (ANA, LUIS):
        assert client.post(f"/asambleas/{aid}/ingresar", headers=auth(quien)).status_code == 409
        assert client.post(f"/asambleas/{aid}/salir", headers=auth(quien)).status_code == 409
    r = client.post(f"/asambleas/{aid}/poderes", data={"apoderado_nombre": "Pedro Apoderado", "apoderado_documento": "123456789"},
                    files={"archivo": ("p.pdf", PDF, "application/pdf")}, headers=auth(ANA))
    assert r.status_code == 409 and "Cerrada" in r.json()["detail"]                                       # tampoco se reciben poderes
    votacion = client.get(f"/asambleas/{aid}/votaciones", headers=h).json()[0]
    for ruta in ("abrir", "anular", "cerrar"):
        r = client.post(f"/asambleas/{aid}/votaciones/{votacion['id']}/{ruta}", headers=h, json={"motivo": "intento tardío de anular"} if ruta == "anular" else None)
        assert r.status_code == 409, f"{ruta}: {r.status_code} {r.text}"
    assert client.post(f"/asambleas/{aid}/votaciones/{votacion['id']}/votar", headers=auth(ANA), json={"opcion_id": votacion["opciones"][0]["id"]}).status_code == 409
    assert client.post(f"/asambleas/{aid}/votaciones/{votacion['id']}/votos-presenciales", headers=h, json={"unidad_id": ids[MARTA], "opcion_id": votacion["opciones"][0]["id"]}).status_code == 409
    # y el resultado de la votación sigue igual
    assert client.get(f"/asambleas/{aid}/votaciones/{votacion['id']}", headers=h).json()["estado"] == "Cerrada"


# ================================================================ migración 0024
def test_la_migracion_0025_sube_baja_y_se_puede_repetir():
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = os.path.join(carpeta, "m.db")
        cfg = _config_alembic(f"sqlite:///{ruta}")
        command.upgrade(cfg, "head")
        assert "asamblea_actas" in _tablas(ruta)
        command.upgrade(cfg, "head")                                                                  # repetir no rompe nada
        command.downgrade(cfg, "0024")
        assert "asamblea_actas" not in _tablas(ruta) and "asamblea_votaciones" in _tablas(ruta)       # solo se quita la tabla nueva (la de seguridad 0024 se queda)
        command.upgrade(cfg, "head")
        assert "asamblea_actas" in _tablas(ruta)
