# tests/test_v42_pagos_simulados.py — v4.2: pasarela de pagos de PRUEBAS (tipo Wompi / PSE).
from datetime import timedelta

import pytest

from app import config
from app.models import IntentoPago, Pago, Usuario, ahora_utc
from app.routers import pagos_simulados as ps
from tests.test_arrendamientos import ADM, ANA, LUIS, MARTA, inquilino_activo
from tests.test_delegaciones import con_deuda, delegar, id_de

BASE = "/pagos-simulados"


@pytest.fixture(autouse=True)
def modo_pruebas(monkeypatch):
    monkeypatch.setattr(config, "PAGOS_SIMULADOS", True)


def saldo(db, email):
    db.expire_all()
    return db.query(Usuario).filter(Usuario.email == email).one().saldo_pendiente


def iniciar(client, auth, valor=100000, quien=ANA):
    return client.post(BASE, json={"valor": valor}, headers=auth(quien))


def pagar(client, auth, ref, quien=ANA, **datos):
    return client.post(f"{BASE}/{ref}/pagar", json=datos, headers=auth(quien))


# ------------------------------------------------------------------ recorrido completo
def test_pago_aprobado_con_tarjeta_descuenta_el_saldo_una_sola_vez(client, auth, db):
    con_deuda(client, auth, db, 300000)
    r = iniciar(client, auth, 100000)
    assert r.status_code == 201 and r.json()["estado"] == "Creado" and r.json()["referencia"].startswith("SIM-") and r.json()["modo_pruebas"] is True
    assert saldo(db, ANA) == 300000                                         # crear el intento NO cobra nada
    ref = r.json()["referencia"]
    ok = pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242")
    assert ok.status_code == 200 and ok.json()["estado"] == "Aprobado" and ok.json()["pago_id"] and ok.json()["saldo_pendiente"] == 200000
    assert saldo(db, ANA) == 200000
    # idempotente: repetir el pago (doble clic, reintento de red) devuelve lo mismo y NO cobra de nuevo
    otra = pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242")
    assert otra.json()["estado"] == "Aprobado" and saldo(db, ANA) == 200000
    assert db.query(Pago).filter(Pago.usuario_id == id_de(db, ANA)).count() == 1


def test_el_pago_aprobado_deja_comprobante_y_queda_al_dia_al_pagar_todo(client, auth, db):
    con_deuda(client, auth, db, 80000)
    ref = iniciar(client, auth, 80000).json()["referencia"]
    r = pagar(client, auth, ref, metodo="PSE", banco="aprueba").json()
    assert r["estado"] == "Aprobado" and r["esta_al_dia"] is True
    assert client.get("/administracion/mis-pagos", headers=auth(ANA)).json()[0]["valor"] == 80000
    assert client.get(f"/reportes/recibo/{r['pago_id']}.pdf", headers=auth(ANA)).status_code == 200


@pytest.mark.parametrize("datos, estado", [
    ({"metodo": "Tarjeta", "terminacion": "4111"}, "Rechazado"),
    ({"metodo": "Tarjeta", "terminacion": "1234"}, "Rechazado"),
    ({"metodo": "PSE", "banco": "rechaza"}, "Rechazado"),
    ({"metodo": "Nequi", "celular": "3001234561"}, "Rechazado"),
])
def test_los_pagos_rechazados_no_descuentan_nada(client, auth, db, datos, estado):
    con_deuda(client, auth, db, 200000)
    ref = iniciar(client, auth, 50000).json()["referencia"]
    r = pagar(client, auth, ref, **datos).json()
    assert r["estado"] == estado and r["pago_id"] is None and r["mensaje"]
    assert saldo(db, ANA) == 200000


def test_un_pago_rechazado_no_se_puede_reintentar_con_la_misma_referencia(client, auth, db):
    con_deuda(client, auth, db, 200000)
    ref = iniciar(client, auth, 50000).json()["referencia"]
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4111").json()["estado"] == "Rechazado"
    # como en una pasarela real: para volver a intentar se crea un intento nuevo; este ya terminó y no se puede «aprobar» después
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242").json()["estado"] == "Rechazado"
    assert saldo(db, ANA) == 200000


# ------------------------------------------------------------------ pendiente → confirmación posterior («webhook»)
def test_un_pago_pendiente_se_confirma_solo_despues_de_unos_segundos(client, auth, db):
    con_deuda(client, auth, db, 200000)
    ref = iniciar(client, auth, 60000).json()["referencia"]
    r = pagar(client, auth, ref, metodo="PSE", banco="pendiente").json()
    assert r["estado"] == "Pendiente" and r["segundos_para_confirmar"] >= 1 and saldo(db, ANA) == 200000
    assert client.get(f"{BASE}/{ref}", headers=auth(ANA)).json()["estado"] == "Pendiente"      # aún no le toca
    i = db.query(IntentoPago).filter(IntentoPago.referencia == ref).one()
    i.resuelve_en = ahora_utc() - timedelta(seconds=1)                                         # «pasaron los segundos»
    db.commit()
    c = client.get(f"{BASE}/{ref}", headers=auth(ANA)).json()
    assert c["estado"] == "Aprobado" and c["saldo_pendiente"] == 140000 and saldo(db, ANA) == 140000
    assert client.get(f"{BASE}/{ref}", headers=auth(ANA)).json()["saldo_pendiente"] == 140000  # y no se cobra dos veces
    assert db.query(Pago).filter(Pago.usuario_id == id_de(db, ANA)).count() == 1


def test_un_intento_que_nadie_paga_expira(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    i = db.query(IntentoPago).filter(IntentoPago.referencia == ref).one()
    i.fecha_creacion = ahora_utc() - timedelta(minutes=ps.MINUTOS_PARA_PAGAR + 1)
    db.commit()
    assert client.get(f"{BASE}/{ref}", headers=auth(ANA)).json()["estado"] == "Expirado"
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242").json()["estado"] == "Expirado"
    assert saldo(db, ANA) == 100000


# ------------------------------------------------------------------ validaciones y seguridad
def test_no_se_puede_pagar_mas_que_el_saldo_ni_sin_saldo(client, auth, db):
    con_deuda(client, auth, db, 50000)
    assert iniciar(client, auth, 50001).status_code == 400
    assert iniciar(client, auth, 0).status_code == 422
    assert iniciar(client, auth, -5).status_code == 422
    assert iniciar(client, auth, 100000, quien=LUIS).status_code == 400                         # Luis no debe nada


def test_si_el_saldo_cambia_mientras_tanto_el_pago_se_rechaza_en_vez_de_dejar_saldo_negativo(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 100000).json()["referencia"]
    assert client.post(f"/administracion/registrar-pago/{id_de(db, ANA)}?valor_pagado=60000", headers=auth(ADM)).status_code == 200   # el admin registró una transferencia
    r = pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242").json()
    assert r["estado"] == "Rechazado" and "saldo" in r["mensaje"].lower()
    assert saldo(db, ANA) == 40000


def test_cada_persona_solo_ve_sus_intentos_ni_el_administrador(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    for quien in (LUIS, ADM):
        assert client.get(f"{BASE}/{ref}", headers=auth(quien)).status_code == 404
        assert pagar(client, auth, ref, quien=quien, metodo="Tarjeta", terminacion="4242").status_code == 404
    assert saldo(db, ANA) == 100000


def test_en_produccion_la_pasarela_de_pruebas_esta_apagada(client, auth, db, monkeypatch):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    monkeypatch.setattr(config, "PAGOS_SIMULADOS", False)
    assert iniciar(client, auth).status_code == 403
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242").status_code == 403
    assert client.get(f"{BASE}/{ref}", headers=auth(ANA)).status_code == 403
    assert saldo(db, ANA) == 100000


def test_sin_sesion_o_con_guardia_no_se_puede_usar(client, auth):
    assert client.post(BASE, json={"valor": 1000}).status_code == 401
    assert client.post(BASE, json={"valor": 1000}, headers=auth("celador@conjunto.com")).status_code == 403


def test_el_servidor_no_acepta_numeros_de_tarjeta_completos_ni_campos_extra(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242424242424242").status_code == 422   # solo los 4 últimos dígitos
    assert pagar(client, auth, ref, metodo="Tarjeta", terminacion="4242", cvc="123").status_code == 422     # ni CVC ni nada más
    assert saldo(db, ANA) == 100000


def test_faltan_los_datos_del_metodo(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    for datos in ({"metodo": "PSE"}, {"metodo": "Tarjeta"}, {"metodo": "Nequi"}, {"metodo": "Efecty"}):
        assert pagar(client, auth, ref, **datos).status_code == 422, datos


def test_nada_sensible_queda_guardado_en_el_intento(client, auth, db):
    con_deuda(client, auth, db, 100000)
    ref = iniciar(client, auth, 10000).json()["referencia"]
    pagar(client, auth, ref, metodo="Nequi", celular="3109876540")
    i = db.query(IntentoPago).filter(IntentoPago.referencia == ref).one()
    guardado = " ".join(str(getattr(i, c.name)) for c in IntentoPago.__table__.columns)
    assert "3109876540" not in guardado and "4242" not in guardado


def test_hay_un_tope_de_intentos_de_pago_por_persona(client, auth, db, monkeypatch):
    from app import limitador
    monkeypatch.setattr(limitador.PAGOS_SIMULADOS_USUARIO, "maximo", 3)
    con_deuda(client, auth, db, 100000)
    codigos = [iniciar(client, auth, 1000).status_code for _ in range(5)]
    assert codigos == [201, 201, 201, 429, 429]


# ------------------------------------------------------------------ inquilino: solo con el pago delegado
def test_el_inquilino_sin_delegacion_no_puede_pagar_y_con_delegacion_paga_la_deuda_del_propietario(client, auth, db):
    cid, _ = inquilino_activo(client, auth, db)
    con_deuda(client, auth, db, 200000)
    assert iniciar(client, auth, 50000, quien=MARTA).status_code == 403
    assert delegar(client, auth, cid, pagar=True).status_code == 200
    ref = iniciar(client, auth, 50000, quien=MARTA).json()["referencia"]
    assert pagar(client, auth, ref, quien=MARTA, metodo="PSE", banco="aprueba").json()["estado"] == "Aprobado"
    assert saldo(db, ANA) == 150000                                          # la deuda es del propietario
    assert client.get(f"{BASE}/{ref}", headers=auth(ANA)).status_code == 404 # pero el intento es de quien pagó


def test_la_migracion_crea_la_tabla_de_intentos():
    import os
    import sqlite3
    import tempfile
    from tests.test_migraciones import _config
    from alembic import command
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    command.upgrade(_config(f"sqlite:///{ruta}"), "head")
    con = sqlite3.connect(ruta)
    cols = {c[1] for c in con.execute("PRAGMA table_info(intentos_pago)")}
    con.close()
    assert {"referencia", "usuario_id", "titular_id", "valor", "metodo", "estado", "pago_id", "resuelve_en"} <= cols
    assert not {"numero_tarjeta", "cvc", "documento", "celular"} & cols       # nunca columnas con datos de pago
