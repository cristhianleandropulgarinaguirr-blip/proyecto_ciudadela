# tests/test_delegaciones.py — Fase 3 del rol Inquilino: lo que el propietario puede delegarle (pagar la administración y votar).
from datetime import timedelta

from app.models import Notificacion, Usuario, ahora_utc
from tests.test_arrendamientos import ADM, ANA, CEL, LUIS, MARTA, contrato, inquilino_activo


def delegar(client, auth, cid, pagar=False, votar=False, quien=ANA):
    return client.patch(f"/arrendamientos/{cid}/permisos", json={"puede_pagar": pagar, "puede_votar": votar}, headers=auth(quien))


def id_de(db, email):
    return db.query(Usuario).filter(Usuario.email == email).one().id


def con_deuda(client, auth, db, saldo=300000):
    assert client.patch(f"/administracion/registrar-deuda/{id_de(db, ANA)}?saldo_pendiente={saldo}", headers=auth(ADM)).status_code == 200


def nueva_votacion(client, auth, **extra):
    cuerpo = {"titulo": "¿Pintamos la fachada?", "opciones": ["Sí", "No"], "fecha_cierre": (ahora_utc() + timedelta(days=3)).isoformat() + "Z", **extra}
    r = client.post("/votaciones/", json=cuerpo, headers=auth(ADM))
    assert r.status_code == 201, r.text
    return r.json()["id"], {o["texto"]: o["id"] for o in r.json()["opciones"]}


def titulos(db, email):
    return [n.titulo for n in db.query(Notificacion).filter(Notificacion.usuario_id == id_de(db, email)).all()]


# ---------------------------------------------------------------- por defecto, nada
def test_por_defecto_el_inquilino_no_puede_ni_pagar_ni_votar(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    con_deuda(client, auth, db)
    nueva_votacion(client, auth)
    assert client.get("/usuarios/me", headers=h).json()["delegaciones"] == []
    ana = id_de(db, ANA)
    assert client.get(f"/administracion/estado-cuenta/{ana}", headers=h).status_code == 403
    assert client.get("/administracion/mis-pagos", headers=h).status_code == 403
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=100000", headers=h).status_code == 403
    assert client.get(f"/reportes/estado-cuenta/{ana}.pdf", headers=h).status_code == 403
    for ruta in ("/votaciones/", "/votaciones/pendientes", "/votaciones/1"):
        assert client.get(ruta, headers=h).status_code == 403, ruta
    assert client.post("/votaciones/1/votar", json={"opcion_id": 1}, headers=h).status_code == 403
    assert client.get("/usuarios/me", headers=auth(ANA)).json()["delegaciones"] == []     # los demás roles nunca traen delegaciones


# ---------------------------------------------------------------- quién puede delegar
def test_solo_el_propietario_del_contrato_delega(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    assert delegar(client, auth, cid, quien=LUIS).status_code == 403          # otro propietario
    assert delegar(client, auth, cid, quien=ADM).status_code == 403           # ni el administrador: es decisión del propietario
    assert delegar(client, auth, cid, quien=CEL).status_code == 403
    assert client.patch(f"/arrendamientos/{cid}/permisos", json={"puede_pagar": True, "puede_votar": True}, headers=h).status_code == 403   # ni él mismo
    assert client.patch(f"/arrendamientos/{cid}/permisos", json={"puede_pagar": True}, headers=auth(ANA)).status_code == 422             # faltan datos
    assert client.get("/usuarios/me", headers=h).json()["delegaciones"] == []
    r = delegar(client, auth, cid, pagar=True, votar=True)
    assert r.status_code == 200 and r.json()["puede_pagar"] is True and r.json()["puede_votar"] is True
    assert sorted(client.get("/usuarios/me", headers=h).json()["delegaciones"]) == ["pagar", "votar"]
    assert any("cambió tus permisos" in t for t in titulos(db, MARTA))        # el inquilino se entera
    lista = client.get("/arrendamientos/", headers=auth(ANA)).json()
    assert lista[0]["puede_pagar"] is True and lista[0]["puede_votar"] is True


def test_no_se_delegan_permisos_en_un_contrato_terminado(client, auth, db):
    cid, _ = inquilino_activo(client, auth, db)
    client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(ANA))
    assert delegar(client, auth, cid, pagar=True).status_code == 400


# ---------------------------------------------------------------- pagar
def test_con_el_pago_delegado_el_inquilino_paga_la_deuda_del_propietario(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    con_deuda(client, auth, db, 300000)
    delegar(client, auth, cid, pagar=True)
    ana, luis = id_de(db, ANA), id_de(db, LUIS)
    cuenta = client.get(f"/administracion/estado-cuenta/{ana}", headers=h)
    assert cuenta.status_code == 200 and cuenta.json()["saldo_pendiente"] == 300000
    assert client.get(f"/administracion/estado-cuenta/{luis}", headers=h).status_code == 403          # solo SU apartamento
    pago = client.post("/administracion/simular-pago-pasarela?valor_pagado=100000", headers=h)
    assert pago.status_code == 200 and pago.json()["saldo_pendiente"] == 200000 and pago.json()["esta_al_dia"] is False
    db.expire_all()
    assert db.query(Usuario).filter(Usuario.email == ANA).one().saldo_pendiente == 200000              # bajó la deuda del propietario
    # el pago queda a nombre del apartamento: lo ven el propietario y el inquilino, y el comprobante lo descargan ambos
    mios, suyos = client.get("/administracion/mis-pagos", headers=auth(ANA)).json(), client.get("/administracion/mis-pagos", headers=h).json()
    assert len(mios) == len(suyos) == 1 and mios[0]["valor"] == 100000
    assert client.get(f"/reportes/recibo/{mios[0]['id']}.pdf", headers=h).status_code == 200
    assert client.get(f"/reportes/recibo/{mios[0]['id']}.pdf", headers=auth(ANA)).status_code == 200
    assert client.get(f"/reportes/recibo/{mios[0]['id']}.pdf", headers=auth(LUIS)).status_code == 403   # otro apartamento
    assert client.get(f"/reportes/estado-cuenta/{ana}.pdf", headers=h).status_code == 200
    assert client.get(f"/reportes/estado-cuenta/{luis}.pdf", headers=h).status_code == 403
    assert any("pagó la administración" in t for t in titulos(db, ANA))                                  # el propietario se entera
    # pagar el resto deja el apartamento al día → vuelven las reservas
    fin = client.post("/administracion/simular-pago-pasarela?valor_pagado=200000", headers=h)
    assert fin.json()["esta_al_dia"] is True
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=1000", headers=h).status_code == 400   # ya no hay saldo


def test_el_inquilino_no_puede_ver_pagos_de_otro_apartamento(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, pagar=True)
    con_deuda(client, auth, db)
    client.post("/administracion/simular-pago-pasarela?valor_pagado=50000", headers=auth(LUIS))   # Luis no tiene deuda → 400, no crea pago
    r = client.get(f"/administracion/mis-pagos?usuario_id={id_de(db, LUIS)}", headers=h)            # `usuario_id` solo lo respeta el administrador
    assert r.status_code == 200 and r.json() == []


def test_quitar_el_pago_delegado_rige_al_instante(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    con_deuda(client, auth, db)
    delegar(client, auth, cid, pagar=True)
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=10000", headers=h).status_code == 200
    delegar(client, auth, cid, pagar=False)
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=10000", headers=h).status_code == 403
    assert client.get(f"/administracion/estado-cuenta/{id_de(db, ANA)}", headers=h).status_code == 403


def test_delegar_el_pago_no_da_el_voto_ni_al_reves(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    nueva_votacion(client, auth)
    delegar(client, auth, cid, pagar=True, votar=False)
    assert client.get("/votaciones/", headers=h).status_code == 403
    delegar(client, auth, cid, pagar=False, votar=True)
    assert client.get("/votaciones/", headers=h).status_code == 200
    assert client.get("/administracion/mis-pagos", headers=h).status_code == 403


# ---------------------------------------------------------------- votar
def test_el_inquilino_vota_por_el_apartamento_y_el_propietario_ya_no_puede(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, votar=True)
    vid, op = nueva_votacion(client, auth)
    assert any("Nueva votación" in t for t in titulos(db, MARTA))                                    # se le avisa porque tiene el voto
    v = client.get(f"/votaciones/{vid}", headers=h).json()
    assert v["puede_votar"] is True and v["ya_vote"] is False
    assert client.get("/votaciones/pendientes", headers=h).json()["pendientes"] == 1
    r = client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=h)
    assert r.status_code == 200 and r.json()["ya_vote"] is True and r.json()["puede_votar"] is False
    # el propietario ve que su apartamento ya votó y no puede votar de nuevo (un voto por apartamento)
    de_ana = client.get(f"/votaciones/{vid}", headers=auth(ANA)).json()
    assert de_ana["ya_vote"] is True and de_ana["puede_votar"] is False and "ya votó" in de_ana["motivo_no_puede"]
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["No"]}, headers=auth(ANA)).status_code == 409
    assert any("votó por tu apartamento" in t for t in titulos(db, ANA))
    # el administrador ve al apartamento como participante, sin saber qué votó
    part = client.get(f"/votaciones/{vid}/participacion", headers=auth(ADM)).json()
    assert part["participaron"] == ["Torre 1 Apt 101"] and "Torre 1 Apt 101" not in part["pendientes"]    # el apartamento de Ana figura como participante
    # y el voto cuenta una sola vez en el resultado
    cerrada = client.post(f"/votaciones/{vid}/cerrar", headers=auth(ADM)).json()
    assert cerrada["total_votos"] == 1 and {o["texto"]: o["votos"] for o in cerrada["opciones"]} == {"Sí": 1, "No": 0}


def test_si_el_propietario_vota_primero_el_inquilino_no_puede(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, votar=True)
    vid, op = nueva_votacion(client, auth)
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=auth(ANA)).status_code == 200
    v = client.get(f"/votaciones/{vid}", headers=h).json()
    assert v["puede_votar"] is False and v["ya_vote"] is True
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["No"]}, headers=h).status_code == 409
    assert client.get("/votaciones/pendientes", headers=h).json()["pendientes"] == 0


def test_votacion_por_persona_el_voto_delegado_tambien_es_del_propietario(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, votar=True)
    vid, op = nueva_votacion(client, auth, un_voto_por="persona")
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=h).status_code == 200
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=auth(ANA)).status_code == 409   # no se duplica


def test_el_inquilino_hereda_la_mora_para_votar(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, votar=True)
    vid, op = nueva_votacion(client, auth, exige_al_dia=True)
    con_deuda(client, auth, db)
    v = client.get(f"/votaciones/{vid}", headers=h).json()
    assert v["puede_votar"] is False and "al día" in v["motivo_no_puede"]
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=h).status_code == 403
    client.patch(f"/administracion/registrar-deuda/{id_de(db, ANA)}?saldo_pendiente=0", headers=auth(ADM))
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=h).status_code == 200


def test_quitar_el_voto_delegado_rige_al_instante_y_no_se_avisa_a_quien_no_lo_tiene(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    vid, op = nueva_votacion(client, auth)
    assert not any("Nueva votación" in t for t in titulos(db, MARTA))                                 # sin delegación no recibe el aviso
    delegar(client, auth, cid, votar=True)
    delegar(client, auth, cid, votar=False)
    assert client.post(f"/votaciones/{vid}/votar", json={"opcion_id": op["Sí"]}, headers=h).status_code == 403


def test_el_inquilino_no_puede_crear_ni_cerrar_votaciones(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, pagar=True, votar=True)
    vid, _ = nueva_votacion(client, auth)
    assert client.post("/votaciones/", json={"titulo": "x" * 10, "opciones": ["a", "b"], "fecha_cierre": "2099-01-01T00:00:00Z"}, headers=h).status_code == 403
    assert client.post(f"/votaciones/{vid}/cerrar", headers=h).status_code == 403
    assert client.get(f"/votaciones/{vid}/participacion", headers=h).status_code == 403
    assert client.post(f"/administracion/registrar-pago/{id_de(db, ANA)}?valor_pagado=1000", headers=h).status_code == 403
    assert client.patch(f"/administracion/registrar-deuda/{id_de(db, ANA)}?saldo_pendiente=0", headers=h).status_code == 403


def test_al_terminar_el_contrato_las_delegaciones_dejan_de_servir(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    delegar(client, auth, cid, pagar=True, votar=True)
    client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(ANA))
    assert client.get("/votaciones/", headers=h).status_code == 401
    assert client.get("/administracion/mis-pagos", headers=h).status_code == 401
