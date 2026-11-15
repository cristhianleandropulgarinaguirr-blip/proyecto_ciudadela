# tests/test_v36_paz_kpis.py — Versión 3.6, Fase 2: paz y salvo con QR de verificación e indicadores (KPIs) del administrador.
from datetime import timedelta

from sqlalchemy import event

from app import config, limitador
from app.database import engine
from app.models import AccesoVisitante, Auditoria, Notificacion, PazSalvo, PQRS, Reserva, Usuario, VehiculoVisitante, ahora_utc
from tests.test_arrendamientos import ADM, ANA, CEL, LUIS, inquilino_activo
from tests.test_delegaciones import delegar, id_de


def pedir(client, auth, quien=ANA, **cuerpo):
    return client.post("/paz-y-salvo", json=cuerpo, headers=auth(quien))


def codigo_de(p):
    return p["enlace"].rsplit("/", 1)[1]


def poner_saldo(db, email, saldo):
    u = db.query(Usuario).filter(Usuario.email == email).one()
    u.saldo_pendiente, u.esta_al_dia = saldo, saldo == 0
    db.commit()


# ================================================================ PAZ Y SALVO · emisión
def test_el_residente_al_dia_genera_su_paz_y_salvo(client, auth, db):
    r = pedir(client, auth, destino="  Trámite   bancario ")
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["folio"] == f"PS-{p['id']:06d}" and p["estado"] == "Vigente" and p["destino"] == "Trámite bancario"
    assert p["titular"] == "Ana Residente" and p["apartamento"] == "Torre 1 Apt 101" and p["enlace"].startswith("/verificar/")
    dias = (config.PAZ_Y_SALVO_DIAS)
    guardado = db.query(PazSalvo).one()
    assert abs((guardado.valido_hasta - guardado.fecha_emision) - timedelta(days=dias)) < timedelta(seconds=5)
    assert db.query(Auditoria).filter(Auditoria.accion == "Emitió paz y salvo").count() == 1


def test_con_saldo_pendiente_no_se_emite(client, auth, db):
    poner_saldo(db, ANA, 250000)
    r = pedir(client, auth)
    assert r.status_code == 400 and "saldo pendiente" in r.json()["detail"] and db.query(PazSalvo).count() == 0


def test_el_administrador_emite_para_un_residente_y_este_se_entera(client, auth, db):
    ana = id_de(db, ANA)
    r = pedir(client, auth, ADM, usuario_id=ana)
    assert r.status_code == 201 and r.json()["titular"] == "Ana Residente"
    assert "Se generó un paz y salvo de tu apartamento" in [n.titulo for n in db.query(Notificacion).filter(Notificacion.usuario_id == ana).all()]
    assert pedir(client, auth, ADM).status_code == 400                    # sin usuario_id emitiría para sí mismo: el administrador no tiene apartamento
    assert pedir(client, auth, ADM, usuario_id=99999).status_code == 404
    assert pedir(client, auth, ADM, usuario_id=id_de(db, CEL)).status_code == 400       # un guardia no es propietario


def test_permisos_de_emision(client, auth, db):
    assert pedir(client, auth, CEL).status_code == 403
    assert client.post("/paz-y-salvo", json={}).status_code == 401
    assert pedir(client, auth, ANA, usuario_id=id_de(db, LUIS)).status_code == 403          # no se pide el de otro
    assert pedir(client, auth, ANA, usuario_id=id_de(db, ANA)).status_code == 201           # el propio sí


def test_el_inquilino_solo_con_permiso_de_pagar_y_el_certificado_es_del_propietario(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    assert client.post("/paz-y-salvo", json={}, headers=h).status_code == 403              # por defecto, nada
    assert delegar(client, auth, cid, pagar=True).status_code == 200
    r = client.post("/paz-y-salvo", json={"destino": "Mudanza"}, headers=h)
    assert r.status_code == 201 and r.json()["titular"] == "Ana Residente"
    assert len(client.get("/paz-y-salvo", headers=h).json()) == 1 and len(client.get("/paz-y-salvo", headers=auth(ANA)).json()) == 1
    assert client.get(f"/paz-y-salvo/{r.json()['id']}/pdf", headers=h).status_code == 200


def test_maximo_10_por_dia(client, auth):
    for _ in range(10):
        assert pedir(client, auth).status_code == 201
    r = pedir(client, auth)
    assert r.status_code == 429 and "10" in r.json()["detail"]


def test_listar_cada_quien_ve_lo_suyo_y_el_administrador_todo(client, auth, db):
    pedir(client, auth, ANA); pedir(client, auth, LUIS)
    assert [p["titular"] for p in client.get("/paz-y-salvo", headers=auth(ANA)).json()] == ["Ana Residente"]
    assert len(client.get("/paz-y-salvo", headers=auth(ADM)).json()) == 2
    assert len(client.get("/paz-y-salvo", params={"usuario_id": id_de(db, LUIS)}, headers=auth(ADM)).json()) == 1
    assert client.get("/paz-y-salvo", headers=auth(CEL)).status_code == 403


# ================================================================ PAZ Y SALVO · PDF
def test_el_pdf_se_descarga_solo_el_dueno_o_el_administrador(client, auth):
    p = pedir(client, auth).json()
    for quien, codigo in ((ANA, 200), (ADM, 200), (LUIS, 403), (CEL, 403)):
        assert client.get(f"/paz-y-salvo/{p['id']}/pdf", headers=auth(quien)).status_code == codigo, quien
    r = client.get(f"/paz-y-salvo/{p['id']}/pdf", headers=auth(ANA))
    assert r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-" and len(r.content) > 3000
    assert f"PS-{p['id']:06d}" in r.headers["content-disposition"] and "no-store" in r.headers["cache-control"]
    assert client.get("/paz-y-salvo/9999/pdf", headers=auth(ANA)).status_code == 404
    assert client.get(f"/paz-y-salvo/{p['id']}/pdf").status_code == 401


# ================================================================ PAZ Y SALVO · verificación pública
def test_verificacion_publica_vigente_y_con_solo_lo_necesario(client, auth):
    p = pedir(client, auth, destino="Mudanza").json()
    r = client.get(f"/verificacion-publica/{codigo_de(p)}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()["documento"]
    assert d["valido"] is True and d["estado"] == "Vigente" and d["folio"] == p["folio"] and d["titular"] == "Ana Residente" and d["destino"] == "Mudanza"
    for prohibido in ("saldo", "mora", "ana@conjunto.com", "password", "valor_administracion"):
        assert prohibido not in r.text.lower()


def test_el_certificado_deja_de_ser_vigente_si_vence_se_revoca_o_el_apartamento_vuelve_a_deber(client, auth, db):
    p = pedir(client, auth).json()
    url = f"/verificacion-publica/{codigo_de(p)}"
    assert client.get(url).json()["documento"]["estado"] == "Vigente"
    poner_saldo(db, ANA, 100000)
    d = client.get(url).json()["documento"]
    assert d["estado"] == "No vigente" and d["valido"] is False
    assert "100" not in client.get(url).text and "mora" not in client.get(url).text.lower()      # no se revela por qué
    poner_saldo(db, ANA, 0)
    assert client.get(url).json()["documento"]["estado"] == "Vigente"                           # al pagar, vuelve a valer
    db.query(PazSalvo).update({"valido_hasta": ahora_utc() - timedelta(days=1)}); db.commit()
    assert client.get(url).json()["documento"]["estado"] == "Vencido"


def test_revocar_es_solo_del_administrador_y_se_ve_como_no_vigente(client, auth, db):
    p = pedir(client, auth).json()
    assert client.post(f"/paz-y-salvo/{p['id']}/revocar", headers=auth(ANA)).status_code == 403
    r = client.post(f"/paz-y-salvo/{p['id']}/revocar", headers=auth(ADM))
    assert r.status_code == 200 and r.json()["estado"] == "Revocado"
    assert client.get(f"/verificacion-publica/{codigo_de(p)}").json()["documento"]["estado"] == "No vigente"      # sin distinguir el motivo
    assert db.query(Auditoria).filter(Auditoria.accion == "Revocó paz y salvo").count() == 1
    assert client.post("/paz-y-salvo/9999/revocar", headers=auth(ADM)).status_code == 404


def test_codigo_falso_404_y_tope_de_consultas_por_ip(client, auth):
    assert client.get("/verificacion-publica/codigo-que-no-existe").status_code == 404
    p = pedir(client, auth).json()
    for _ in range(limitador.LECTURAS_PUBLICAS.maximo - 1):
        assert client.get(f"/verificacion-publica/{codigo_de(p)}").status_code == 200
    assert client.get(f"/verificacion-publica/{codigo_de(p)}").status_code == 429


def test_pagina_publica_de_verificacion_con_cabeceras_estrictas(client):
    r = client.get("/verificar/cualquiera")
    assert r.status_code == 200 and "script-src 'self'" in r.headers["content-security-policy"] and r.headers["cache-control"] == "no-store"
    assert "<script>" not in r.text and ' style="' not in r.text
    assert client.get("/app/verificar/verificar.js").status_code == 200 and client.get("/app/verificar/verificar.css").status_code == 200
    assert "verificar" not in client.get("/app/sw.js").text.replace("verificacion", "")


def test_la_migracion_crea_la_tabla_de_paz_y_salvo():
    import os, sqlite3, tempfile
    from alembic import command
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = os.path.join(tempfile.mkdtemp(), "m.db")
    cfg = Config(os.path.join(raiz, "alembic.ini")); cfg.set_main_option("script_location", os.path.join(raiz, "alembic")); cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ruta}")
    command.upgrade(cfg, "head"); command.upgrade(cfg, "head")                  # y es idempotente
    con = sqlite3.connect(ruta)
    assert {c[1] for c in con.execute("PRAGMA table_info(paz_y_salvos)")} >= {"codigo", "valido_hasta", "revocado", "usuario_id", "destino"}
    assert "ix_paz_y_salvos_codigo" in {i[1] for i in con.execute("SELECT * FROM sqlite_master WHERE type='index'")}
    command.downgrade(cfg, "0017")
    assert not list(sqlite3.connect(ruta).execute("SELECT name FROM sqlite_master WHERE name='paz_y_salvos'"))


# ================================================================ KPIs
def test_kpis_solo_para_el_administrador(client, auth):
    for quien in (ANA, CEL, LUIS):
        assert client.get("/dashboard/kpis", headers=auth(quien)).status_code == 403
    assert client.get("/dashboard/kpis").status_code == 401


def test_kpis_con_datos_reales(client, auth, db):
    poner_saldo(db, LUIS, 300000)
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    ahora = ahora_utc()
    # reservas: 3 aprobadas en BBQ, 1 en piscina, 1 aprobada hace 200 días (fuera de la ventana), 2 pendientes
    local = ahora - timedelta(hours=5)
    db.add_all([Reserva(usuario_id=ana.id, zona_comun="Zona BBQ", fecha_reserva=local - timedelta(days=d), estado="Aprobada") for d in (1, 2, 3)]
               + [Reserva(usuario_id=ana.id, zona_comun="Piscina", fecha_reserva=local - timedelta(days=5), estado="Aprobada"),
                  Reserva(usuario_id=ana.id, zona_comun="Piscina", fecha_reserva=local - timedelta(days=200), estado="Aprobada")]
               + [Reserva(usuario_id=ana.id, zona_comun="Salón", fecha_reserva=local + timedelta(days=4), estado="Pendiente") for _ in range(2)])
    # PQRS: una respondida en 6 h, otra en 12 h → promedio 9; una abierta
    db.add_all([PQRS(usuario_id=ana.id, tipo="Queja", asunto="A", descripcion="x" * 20, estado="Respondida", fecha_creacion=ahora - timedelta(days=3), fecha_respuesta=ahora - timedelta(days=3) + timedelta(hours=6)),
                PQRS(usuario_id=ana.id, tipo="Queja", asunto="B", descripcion="x" * 20, estado="Respondida", fecha_creacion=ahora - timedelta(days=2), fecha_respuesta=ahora - timedelta(days=2) + timedelta(hours=12)),
                PQRS(usuario_id=ana.id, tipo="Queja", asunto="C", descripcion="x" * 20, estado="Radicada")])
    # visitantes: 2 vehículos a las 15:00 UTC (=10:00 en Colombia) y 1 a pie a las 03:00 UTC (=22:00 del día anterior)
    base = (ahora - timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    db.add_all([VehiculoVisitante(placa="AAA111", apartamento_destino="x", fecha_ingreso=base.replace(hour=15), estado="Dentro"),
                VehiculoVisitante(placa="BBB222", apartamento_destino="x", fecha_ingreso=base.replace(hour=15), estado="Salido"),
                VehiculoVisitante(placa="CCC333", apartamento_destino="x", fecha_ingreso=ahora - timedelta(days=60), estado="Salido")])    # fuera de la ventana
    db.commit()
    acceso = db.query(AccesoVisitante).count()
    j = client.get("/dashboard/kpis", headers=auth(ADM)).json()
    assert j["cartera"] == {"unidades": 2, "al_dia": 1, "en_mora": 1, "pct_al_dia": 50.0, "saldo_total": 300000}
    assert j["reservas"]["por_zona"] == [{"zona": "Zona BBQ", "total": 3}, {"zona": "Piscina", "total": 1}] and j["reservas"]["pendientes"] == 2
    assert j["pqrs"]["abiertas"] == 1 and j["pqrs"]["respondidas"] == 2 and j["pqrs"]["horas_promedio_respuesta"] == 9.0
    assert len(j["visitantes"]["por_hora"]) == 24 and j["visitantes"]["por_hora"][10] == 2 and j["visitantes"]["hora_pico"] == 10 and j["visitantes"]["total"] == 2 + acceso
    assert j["operacion"]["vehiculos_dentro"] == 1


def test_kpis_sin_datos_no_revientan(client, auth, db):
    db.query(Usuario).filter(Usuario.email.in_([ANA, LUIS])).delete(synchronize_session=False); db.commit()
    j = client.get("/dashboard/kpis", headers=auth(ADM)).json()
    assert j["cartera"] == {"unidades": 0, "al_dia": 0, "en_mora": 0, "pct_al_dia": 0.0, "saldo_total": 0}
    assert j["pqrs"]["horas_promedio_respuesta"] is None and j["visitantes"]["hora_pico"] is None and j["reservas"]["por_zona"] == []


def test_kpis_se_guardan_60_segundos_y_se_pueden_refrescar(client, auth, db):
    h = auth(ADM)
    a = client.get("/dashboard/kpis", headers=h).json()
    poner_saldo(db, LUIS, 500000)
    assert client.get("/dashboard/kpis", headers=h).json() == a                                  # sigue el valor guardado
    b = client.get("/dashboard/kpis", params={"refrescar": "true"}, headers=h).json()
    assert b["cartera"]["en_mora"] == a["cartera"]["en_mora"] + 1 and b["cartera"]["saldo_total"] == 500000


def test_kpis_usan_pocas_consultas(client, auth):
    h = auth(ADM)
    n = []
    registrar = lambda *_: n.append(1)                                                           # noqa: E731
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        assert client.get("/dashboard/kpis", params={"refrescar": "true"}, headers=h).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", registrar)
    assert len(n) <= 16, len(n)                  # sesión + cartera + reservas + pqrs + visitantes + operación: una cantidad fija, no depende de cuántos datos haya


# ================================================================ Cartera del administrador en UNA petición
def test_cartera_completa_trae_todos_los_residentes_en_una_sola_respuesta(client, auth, db):
    poner_saldo(db, LUIS, 300000)
    r = client.get("/administracion/cartera", headers=auth(ADM))
    assert r.status_code == 200
    filas = r.json()
    assert [f["nombre_completo"] for f in filas] == ["Ana Residente", "Luis Residente"] and [f["saldo_pendiente"] for f in filas] == [0, 300000]
    assert filas[0]["esta_al_dia"] is True and filas[1]["esta_al_dia"] is False and filas[0]["apartamento"] == "Torre 1 Apt 101"
    assert {"usuario_id", "valor_administracion", "esta_activo"} <= filas[0].keys() and "email" not in filas[0] and "password" not in r.text
    for quien in (ANA, CEL):
        assert client.get("/administracion/cartera", headers=auth(quien)).status_code == 403
    assert client.get("/administracion/cartera").status_code == 401


def test_cartera_completa_no_hace_una_consulta_por_residente(client, auth, db):
    rol = db.query(Usuario).filter(Usuario.email == ANA).one().rol_id
    db.add_all([Usuario(nombre_completo=f"Vecino {i}", email=f"v{i}@x.com", password_encriptada="x", rol_id=rol, apartamento=f"Apt {i}") for i in range(150)])
    db.commit()
    h = auth(ADM)                                    # el inicio de sesión se hace ANTES de contar
    n = []
    registrar = lambda *_: n.append(1)                                                           # noqa: E731
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        r = client.get("/administracion/cartera", headers=h)
    finally:
        event.remove(engine, "before_cursor_execute", registrar)
    assert len(r.json()) == 152 and len(n) <= 5, len(n)
