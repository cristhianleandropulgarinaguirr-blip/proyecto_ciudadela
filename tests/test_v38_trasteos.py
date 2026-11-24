# tests/test_v38_trasteos.py — Versión 3.8, Fase 3 (operativo): trasteos con solicitud, validación de paz y salvo, aprobación y alerta al guardia.
from datetime import timedelta

from app.models import Auditoria, Notificacion, PazSalvo, Trasteo, ahora_utc
from tests.test_arrendamientos import ADM, ANA, CEL, LUIS, inquilino_activo
from tests.test_v36_paz_kpis import poner_saldo
from tests.test_delegaciones import id_de


def iso(horas):
    return (ahora_utc() + timedelta(hours=horas)).isoformat() + "Z"


def pedir(client, auth, quien=ANA, tipo="Salida", desde=1, hasta=5, **extra):
    cuerpo = {"tipo": tipo, "fecha_inicio": iso(desde), "fecha_fin": iso(hasta), "empresa": "Trasteos El Rápido", "placa": "abc-123", **extra}
    return client.post("/trasteos", json=cuerpo, headers=auth(quien))


def titulos(db, email):
    return [n.titulo for n in db.query(Notificacion).filter(Notificacion.usuario_id == id_de(db, email)).all()]


# ================================================================ solicitud
def test_una_salida_al_dia_se_solicita_y_enlaza_un_paz_y_salvo(client, auth, db):
    r = pedir(client, auth)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["estado"] == "Pendiente" and t["tipo"] == "Salida" and t["placa"] == "ABC123" and t["apartamento"] == "Torre 1 Apt 101"
    assert t["paz_salvo_estado"] == "Vigente" and t["paz_salvo_folio"].startswith("PS-")
    assert db.query(PazSalvo).one().destino == "Trasteo"
    assert "Nueva solicitud de trasteo (salida)" in titulos(db, ADM)
    assert db.query(Auditoria).filter(Auditoria.accion == "Solicitó un trasteo").count() == 1


def test_reutiliza_el_paz_y_salvo_vigente_que_ya_existe(client, auth, db):
    client.post("/paz-y-salvo", json={}, headers=auth(ANA))
    pedir(client, auth)
    assert db.query(PazSalvo).count() == 1


def test_una_salida_con_saldo_pendiente_se_rechaza(client, auth, db):
    poner_saldo(db, ANA, 250000)
    r = pedir(client, auth)
    assert r.status_code == 400 and "paz y salvo" in r.json()["detail"] and db.query(Trasteo).count() == 0


def test_una_entrada_no_exige_paz_y_salvo(client, auth, db):
    poner_saldo(db, ANA, 250000)
    r = pedir(client, auth, tipo="Entrada")
    assert r.status_code == 201 and r.json()["paz_salvo_folio"] is None


def test_validaciones_de_fecha(client, auth, db):
    assert pedir(client, auth, desde=-3, hasta=2).status_code == 422                # ya pasó
    assert pedir(client, auth, desde=5, hasta=3).status_code == 422                 # fin antes del inicio
    assert pedir(client, auth, desde=1, hasta=20).status_code == 422                # más de 12 horas
    assert pedir(client, auth, desde=24 * 70, hasta=24 * 70 + 3).status_code == 422 # muy lejos
    assert pedir(client, auth, tipo="Otro").status_code == 422


def test_maximo_dos_solicitudes_abiertas_por_apartamento(client, auth, db):
    assert pedir(client, auth, tipo="Entrada", desde=1, hasta=3).status_code == 201
    assert pedir(client, auth, tipo="Entrada", desde=30, hasta=32).status_code == 201
    r = pedir(client, auth, tipo="Entrada", desde=60, hasta=62)
    assert r.status_code == 429


def test_el_guardia_no_solicita_y_hay_que_iniciar_sesion(client, auth, db):
    assert pedir(client, auth, CEL).status_code == 403
    assert pedir(client, auth, ADM).status_code == 403
    assert client.post("/trasteos", json={}).status_code == 401


def test_el_inquilino_solicita_y_el_propietario_se_entera(client, auth, db):
    _, inq = inquilino_activo(client, auth, db)
    r = client.post("/trasteos", json={"tipo": "Entrada", "fecha_inicio": iso(2), "fecha_fin": iso(4)}, headers=inq)
    assert r.status_code == 201 and r.json()["titular"] == "Ana Residente" and r.json()["apartamento"] == "Torre 1 Apt 101"
    assert "Tu inquilino solicitó un trasteo" in titulos(db, ANA)
    assert len(client.get("/trasteos", headers=auth(ANA)).json()) == 1               # el propietario lo ve


def test_la_salida_del_inquilino_se_valida_con_la_cartera_del_propietario(client, auth, db):
    _, inq = inquilino_activo(client, auth, db)
    poner_saldo(db, ANA, 100000)
    r = client.post("/trasteos", json={"tipo": "Salida", "fecha_inicio": iso(2), "fecha_fin": iso(4)}, headers=inq)
    assert r.status_code == 400


# ================================================================ lectura por rol
def test_cada_rol_ve_lo_suyo(client, auth, db):
    pedir(client, auth, ANA, tipo="Entrada")
    pedir(client, auth, LUIS, tipo="Entrada")
    assert len(client.get("/trasteos", headers=auth(ANA)).json()) == 1
    assert len(client.get("/trasteos", headers=auth(LUIS)).json()) == 1
    assert len(client.get("/trasteos", headers=auth(ADM)).json()) == 2
    assert client.get("/trasteos", headers=auth(CEL)).json() == []                  # el guardia solo ve lo aprobado


# ================================================================ aprobación
def test_aprobar_avisa_a_la_porteria_y_al_solicitante(client, auth, db):
    tid = pedir(client, auth).json()["id"]
    r = client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM))
    assert r.status_code == 200 and r.json()["estado"] == "Aprobado"
    assert any(x.startswith("Trasteo aprobado: Torre 1 Apt 101") for x in titulos(db, CEL))
    assert "Tu trasteo fue aprobado" in titulos(db, ANA)
    ve = client.get("/trasteos", headers=auth(CEL)).json()
    assert [t["id"] for t in ve] == [tid] and ve[0]["empresa"] == "Trasteos El Rápido"


def test_solo_el_administrador_aprueba(client, auth, db):
    tid = pedir(client, auth).json()["id"]
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ANA)).status_code == 403
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(CEL)).status_code == 403
    assert client.post("/trasteos/9999/aprobar", headers=auth(ADM)).status_code == 404


def test_no_se_aprueba_una_salida_si_el_apartamento_volvio_a_deber(client, auth, db):
    tid = pedir(client, auth).json()["id"]
    poner_saldo(db, ANA, 300000)
    r = client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM))
    assert r.status_code == 400 and "paz y salvo" in r.json()["detail"]
    assert db.get(Trasteo, tid).estado == "Pendiente" and titulos(db, CEL) == []


def test_no_se_aprueba_dos_veces(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM)).status_code == 200
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM)).status_code == 400


def test_dos_trasteos_al_mismo_tiempo_piden_confirmacion(client, auth, db):
    a = pedir(client, auth, ANA, tipo="Entrada", desde=2, hasta=5).json()["id"]
    b = pedir(client, auth, LUIS, tipo="Entrada", desde=3, hasta=6).json()["id"]
    assert client.post(f"/trasteos/{a}/aprobar", headers=auth(ADM)).status_code == 200
    en_lista = {t["id"]: t for t in client.get("/trasteos", headers=auth(ADM)).json()}
    assert en_lista[b]["simultaneo_con"] == "Torre 1 Apt 101"                          # aviso para el administrador
    r = client.post(f"/trasteos/{b}/aprobar", headers=auth(ADM))
    assert r.status_code == 409 and "Torre 1 Apt 101" in r.json()["detail"]
    assert client.post(f"/trasteos/{b}/aprobar", json={"permitir_simultaneo": True}, headers=auth(ADM)).status_code == 200


def test_rechazar_exige_motivo_y_avisa(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    assert client.post(f"/trasteos/{tid}/rechazar", json={"motivo": "x"}, headers=auth(ADM)).status_code == 422
    r = client.post(f"/trasteos/{tid}/rechazar", json={"motivo": "Coincide con el mantenimiento del ascensor."}, headers=auth(ADM))
    assert r.status_code == 200 and r.json()["estado"] == "Rechazado" and "ascensor" in r.json()["motivo"]
    assert "Tu solicitud de trasteo no fue aprobada" in titulos(db, ANA)
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM)).status_code == 400   # ya no está pendiente


# ================================================================ cancelación
def test_cancelar_un_trasteo_aprobado_avisa_a_la_porteria(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM))
    r = client.post(f"/trasteos/{tid}/cancelar", headers=auth(ANA))
    assert r.status_code == 200 and r.json()["estado"] == "Cancelado"
    assert any(x.startswith("Trasteo cancelado") for x in titulos(db, CEL))
    assert client.get("/trasteos", headers=auth(CEL)).json() == []


def test_otro_apartamento_no_puede_cancelar(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    assert client.post(f"/trasteos/{tid}/cancelar", headers=auth(LUIS)).status_code == 403
    assert client.post(f"/trasteos/{tid}/cancelar", headers=auth(CEL)).status_code == 403


def test_cancelar_libera_el_cupo_de_solicitudes(client, auth, db):
    a = pedir(client, auth, tipo="Entrada", desde=1, hasta=3).json()["id"]
    pedir(client, auth, tipo="Entrada", desde=30, hasta=32)
    client.post(f"/trasteos/{a}/cancelar", headers=auth(ANA))
    assert pedir(client, auth, tipo="Entrada", desde=60, hasta=62).status_code == 201


# ================================================================ portería
def aprobado(client, auth, tipo="Salida", desde=1, hasta=5):
    tid = pedir(client, auth, tipo=tipo, desde=desde, hasta=hasta).json()["id"]
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM)).status_code == 200
    return tid


def test_el_guardia_inicia_y_finaliza_el_trasteo(client, auth, db):
    tid = aprobado(client, auth)
    assert client.get("/trasteos", headers=auth(CEL)).json()[0]["puede_iniciar"] is True
    r = client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL))
    assert r.status_code == 200 and r.json()["estado"] == "En curso" and r.json()["inicio_real"]
    assert db.get(Trasteo, tid).registrado_por == id_de(db, CEL)
    f = client.post(f"/trasteos/{tid}/finalizar", headers=auth(CEL))
    assert f.status_code == 200 and f.json()["estado"] == "Completado" and f.json()["fin_real"]
    assert {"Tu trasteo comenzó", "Tu trasteo terminó"} <= set(titulos(db, ANA))
    assert client.get("/trasteos", headers=auth(CEL)).json() == []                   # ya no aparece en la lista de portería
    assert client.get("/trasteos", headers=auth(ADM)).json()[0]["estado"] == "Completado"


def test_la_salida_no_inicia_si_el_paz_y_salvo_dejo_de_ser_vigente(client, auth, db):
    tid = aprobado(client, auth)
    poner_saldo(db, ANA, 90000)                                                      # entre la aprobación y el día del trasteo, vuelve a deber
    v = client.get("/trasteos", headers=auth(CEL)).json()[0]
    assert v["puede_iniciar"] is False and v["paz_salvo_estado"] == "No vigente" and "paz y salvo" in v["motivo_no_puede_iniciar"]
    r = client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL))
    assert r.status_code == 409 and db.get(Trasteo, tid).estado == "Aprobado"


def test_un_paz_y_salvo_revocado_tambien_frena_la_salida(client, auth, db):
    tid = aprobado(client, auth)
    db.query(PazSalvo).update({"revocado": True})
    db.commit()
    assert client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL)).status_code == 409


def test_una_entrada_inicia_aunque_haya_deuda(client, auth, db):
    tid = aprobado(client, auth, tipo="Entrada")
    poner_saldo(db, ANA, 90000)
    assert client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL)).status_code == 200


def test_no_se_inicia_antes_de_hora_ni_despues_de_la_ventana(client, auth, db):
    tid = aprobado(client, auth, tipo="Entrada", desde=6, hasta=9)                    # faltan 6 h: el guardia puede iniciar hasta 2 h antes
    r = client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL))
    assert r.status_code == 409 and "hora" in r.json()["detail"]
    t = db.get(Trasteo, tid)
    t.fecha_inicio, t.fecha_fin = ahora_utc() - timedelta(hours=5), ahora_utc() - timedelta(hours=1)
    db.commit()
    r = client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL))
    assert r.status_code == 409 and "terminó" in r.json()["detail"]


def test_solo_guardia_o_administrador_registran_el_movimiento(client, auth, db):
    tid = aprobado(client, auth)
    assert client.post(f"/trasteos/{tid}/iniciar", headers=auth(ANA)).status_code == 403
    assert client.post(f"/trasteos/{tid}/iniciar", headers=auth(LUIS)).status_code == 403
    assert client.post(f"/trasteos/{tid}/finalizar", headers=auth(CEL)).status_code == 400   # aún no está en curso


def test_no_se_inicia_un_trasteo_pendiente(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    assert client.post(f"/trasteos/{tid}/iniciar", headers=auth(CEL)).status_code == 409


def test_pendiente_que_pasa_de_fecha_se_muestra_vencido(client, auth, db):
    tid = pedir(client, auth, tipo="Entrada").json()["id"]
    t = db.get(Trasteo, tid)
    t.fecha_inicio, t.fecha_fin = ahora_utc() - timedelta(hours=5), ahora_utc() - timedelta(hours=1)
    db.commit()
    assert client.get("/trasteos", headers=auth(ANA)).json()[0]["estado"] == "Vencido"
    assert client.post(f"/trasteos/{tid}/aprobar", headers=auth(ADM)).status_code == 400
