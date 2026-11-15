# tests/test_v35.py — Versión 3.5: Fase 0 (filtros de reservas, índices) y Fase 1 (PIN, página pública del pase, avisos).
from datetime import datetime, timedelta

import pytest

from app import config, limitador
from app.models import CodigoQR, Notificacion, Reserva, Usuario, ahora_utc

PASE = {"nombre_visitante": "Carlos Pérez", "placa": "xyz123", "horas_validez": 6}


def crear_pase(client, auth, quien="ana@conjunto.com"):
    r = client.post("/qr/visitantes", json=PASE, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def token_de(pase: dict) -> str:
    return pase["payload"][len("CD1:"):]


def pin(client, auth, numero, quien="celador@conjunto.com"):
    return client.post("/qr/escanear-pin", json={"pin": numero}, headers=auth(quien))


# ================================================================ FASE 0 · reservas con filtros
def _reservas(db):
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    hoy = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    filas = [("Zona BBQ", hoy - timedelta(days=200), "Aprobada"), ("Piscina", hoy - timedelta(days=5), "Cancelada"),
             ("Zona BBQ", hoy, "Aprobada"), ("Salón Comunal", hoy + timedelta(days=3), "Pendiente"), ("Piscina", hoy + timedelta(days=9), "Pendiente")]
    db.add_all([Reserva(usuario_id=ana.id, zona_comun=z, fecha_reserva=f, estado=e) for z, f, e in filas])
    db.commit()
    return hoy


def test_listar_reservas_sin_filtros_devuelve_todo_como_siempre(client, auth, db):
    _reservas(db)
    assert len(client.get("/reservas/listar", headers=auth("admin@conjunto.com")).json()) == 5


def test_listar_reservas_filtra_por_estado_fecha_y_limite(client, auth, db):
    hoy = _reservas(db)
    h = auth("admin@conjunto.com")
    pend = client.get("/reservas/listar", params={"estado": "Pendiente"}, headers=h).json()
    assert len(pend) == 2 and {r["estado"] for r in pend} == {"Pendiente"}
    # «hasta» incluye TODO ese día (la reserva de hoy a las 10:00 entra aunque «hasta» sea hoy)
    de_hoy = client.get("/reservas/listar", params={"desde": hoy.date().isoformat(), "hasta": hoy.date().isoformat(), "estado": "Aprobada"}, headers=h).json()
    assert [r["zona_comun"] for r in de_hoy] == ["Zona BBQ"]
    recientes = client.get("/reservas/listar", params={"desde": (hoy - timedelta(days=90)).date().isoformat()}, headers=h).json()
    assert len(recientes) == 4          # la de hace 200 días queda fuera
    assert len(client.get("/reservas/listar", params={"limite": 2}, headers=h).json()) == 2


def test_listar_reservas_valida_parametros_y_permisos(client, auth, db):
    h = auth("admin@conjunto.com")
    assert client.get("/reservas/listar", params={"estado": "Inventado"}, headers=h).status_code == 422
    assert client.get("/reservas/listar", params={"desde": "ayer"}, headers=h).status_code == 422
    assert client.get("/reservas/listar", params={"limite": 0}, headers=h).status_code == 422
    assert client.get("/reservas/listar", headers=auth("ana@conjunto.com")).status_code == 403     # el residente no ve las de todos
    assert client.get("/reservas/listar", headers=auth("celador@conjunto.com")).status_code == 200


# ================================================================ FASE 1 · PIN
def test_cada_pase_trae_un_pin_de_6_digitos_y_un_enlace_y_el_carnet_no(client, auth):
    p = crear_pase(client, auth)
    assert len(p["pin"]) == 6 and p["pin"].isdigit()
    assert p["enlace"] == f"/pase/{token_de(p)}"
    carnet = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    assert carnet["pin"] is None and carnet["enlace"] is None
    assert client.get("/qr/visitantes", headers=auth("ana@conjunto.com")).json()[0]["pin"] == p["pin"]    # ella puede volver a verlo


def test_los_pin_de_pases_vigentes_no_se_repiten(client, auth):
    pines = [crear_pase(client, auth, q)["pin"] for q in ("ana@conjunto.com", "luis@conjunto.com") for _ in range(10)]
    assert len(set(pines)) == 20


def test_guardia_registra_ingreso_y_salida_con_el_pin(client, auth):
    p = crear_pase(client, auth)
    entra = pin(client, auth, p["pin"]).json()
    assert entra["ok"] and entra["resultado"] == "Ingreso registrado" and entra["visitante"]["placa"] == "XYZ123"
    sale = pin(client, auth, p["pin"]).json()
    assert sale["ok"] and sale["resultado"] == "Salida registrada"
    # pase ya usado: el PIN deja de servir
    assert pin(client, auth, p["pin"]).json()["ok"] is False
    # y todo queda en la bitácora, sin guardar el número probado
    detalles = " ".join(f["detalle"] or "" for f in client.get("/qr/escaneos", headers=auth("admin@conjunto.com")).json())
    assert p["pin"] not in detalles


def test_el_pin_y_el_qr_comparten_estado(client, auth):
    p = crear_pase(client, auth)
    assert client.post("/qr/escanear", json={"codigo": p["payload"]}, headers=auth("celador@conjunto.com")).json()["resultado"] == "Ingreso registrado"
    assert pin(client, auth, p["pin"]).json()["resultado"] == "Salida registrada"     # entró con el QR, sale con el PIN


def test_pin_incorrecto_se_rechaza_y_a_los_8_fallos_se_bloquea_al_guardia(client, auth):
    for _ in range(limitador.PIN_FALLIDOS.maximo):
        r = pin(client, auth, "000000")
        assert r.status_code == 200 and r.json()["ok"] is False
    assert pin(client, auth, "000000").status_code == 429
    # el bloqueo es por guardia: el administrador sigue pudiendo trabajar
    assert pin(client, auth, "000000", "admin@conjunto.com").status_code == 200


def test_pin_de_un_pase_vencido_da_un_mensaje_claro_y_no_cuenta_como_fallo(client, auth, db):
    p = crear_pase(client, auth)
    db.query(CodigoQR).filter(CodigoQR.token == token_de(p)).update({"valido_hasta": ahora_utc() - timedelta(hours=1)})
    db.commit()
    for _ in range(limitador.PIN_FALLIDOS.maximo + 2):
        r = pin(client, auth, p["pin"])
        assert r.status_code == 200 and r.json()["ok"] is False and "venció" in r.json()["mensaje"]


def test_pin_de_un_pase_revocado_no_funciona(client, auth):
    p = crear_pase(client, auth)
    assert client.post(f"/qr/visitantes/{p['id']}/revocar", headers=auth("ana@conjunto.com")).status_code == 200
    assert pin(client, auth, p["pin"]).json()["ok"] is False


def test_el_pin_solo_lo_usa_la_porteria_y_debe_tener_6_digitos(client, auth):
    p = crear_pase(client, auth)
    assert pin(client, auth, p["pin"], "ana@conjunto.com").status_code == 403
    assert client.post("/qr/escanear-pin", json={"pin": p["pin"]}).status_code == 401
    for malo in ("12345", "1234567", "12345a", ""):
        assert pin(client, auth, malo).status_code == 422


def test_un_pase_cerrado_no_bloquea_los_pin_de_los_pases_nuevos(client, auth):
    p = crear_pase(client, auth)
    pin(client, auth, p["pin"]); pin(client, auth, p["pin"])                   # ingreso + salida: el pase queda Usado
    otro = crear_pase(client, auth, "luis@conjunto.com")
    assert pin(client, auth, otro["pin"]).json()["visitante"]["autorizado_por"] == "Luis Residente"


# ================================================================ FASE 1 · página pública del pase
def test_la_pagina_publica_se_sirve_con_cabeceras_estrictas_y_sin_scripts_inline(client):
    r = client.get("/pase/cualquier-cosa")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "script-src 'self'" in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and r.headers["referrer-policy"] == "no-referrer" and "noindex" in r.headers["x-robots-tag"]
    assert "<script>" not in r.text and ' style="' not in r.text and "onclick=" not in r.text       # la CSP los bloquearía
    assert client.get("/app/pase/pase.css").status_code == 200 and client.get("/app/pase/pase.js").status_code == 200


def test_la_api_publica_muestra_solo_lo_que_el_visitante_ya_conoce(client, auth):
    p = crear_pase(client, auth)
    r = client.get(f"/pase-publico/{token_de(p)}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    assert j["pase"]["visitante"] == "Carlos Pérez" and j["pase"]["placa"] == "XYZ123" and j["pase"]["apartamento"] == "Torre 1 Apt 101"
    assert j["pase"]["estado"] == "Activo" and j["pase"]["sirve"] and j["pase"]["pin"] == p["pin"] and j["pase"]["puede_avisar"]
    texto = r.text.lower()
    for prohibido in ("ana residente", "ana@conjunto.com", "saldo", "propietario", "password"):
        assert prohibido not in texto


def test_token_falso_o_de_carnet_da_404_igual_que_uno_inexistente(client, auth):
    carnet = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    for token in ("no-existe-0123456789", token_de(carnet)):
        assert client.get(f"/pase-publico/{token}").status_code == 404
        assert client.get(f"/pase-publico/{token}/imagen").status_code == 404
        assert client.post(f"/pase-publico/{token}/aviso", json={"tipo": "llegue"}).status_code == 404


def test_la_imagen_publica_es_un_png_y_desaparece_si_el_pase_se_revoca(client, auth):
    p = crear_pase(client, auth)
    r = client.get(f"/pase-publico/{token_de(p)}/imagen")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n"
    client.post(f"/qr/visitantes/{p['id']}/revocar", headers=auth("ana@conjunto.com"))
    assert client.get(f"/pase-publico/{token_de(p)}/imagen").status_code == 404
    j = client.get(f"/pase-publico/{token_de(p)}").json()["pase"]
    assert j["estado"] == "Revocado" and j["sirve"] is False and j["pin"] is None and j["puede_avisar"] is False


def test_el_pase_dentro_sigue_mostrando_el_qr_para_salir_pero_ya_no_deja_avisar(client, auth):
    p = crear_pase(client, auth)
    pin(client, auth, p["pin"])                                                     # ingresa
    j = client.get(f"/pase-publico/{token_de(p)}").json()["pase"]
    assert j["estado"] == "Dentro" and j["sirve"] and j["pin"] == p["pin"] and j["puede_avisar"] is False
    assert client.get(f"/pase-publico/{token_de(p)}/imagen").status_code == 200
    assert client.post(f"/pase-publico/{token_de(p)}/aviso", json={"tipo": "llegue"}).status_code == 400


def test_el_titular_desactivado_deja_el_pase_inservible(client, auth, db):
    p = crear_pase(client, auth)
    db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").update({"esta_activo": False})
    db.commit()
    j = client.get(f"/pase-publico/{token_de(p)}").json()["pase"]
    assert j["sirve"] is False and j["estado"] == "Revocado"
    assert client.get(f"/pase-publico/{token_de(p)}/imagen").status_code == 404


# ================================================================ FASE 1 · «Estoy en camino» / «Llegué»
def _notis(db, email):
    u = db.query(Usuario).filter(Usuario.email == email).one()
    return [n.titulo for n in db.query(Notificacion).filter(Notificacion.usuario_id == u.id).all()]


def test_en_camino_avisa_al_residente(client, auth, db):
    p = crear_pase(client, auth)
    r = client.post(f"/pase-publico/{token_de(p)}/aviso", json={"tipo": "en_camino"})
    assert r.status_code == 200 and r.json()["ok"]
    assert "Tu visita va en camino" in _notis(db, "ana@conjunto.com")
    assert _notis(db, "celador@conjunto.com") == []                                  # «en camino» no molesta a portería
    assert client.get(f"/pase-publico/{token_de(p)}").json()["pase"]["en_camino"] is True


def test_llegue_avisa_a_la_porteria_y_al_residente(client, auth, db):
    p = crear_pase(client, auth)
    assert client.post(f"/pase-publico/{token_de(p)}/aviso", json={"tipo": "llegue"}).status_code == 200
    assert "Visita en portería" in _notis(db, "celador@conjunto.com")
    assert "Tu visita llegó" in _notis(db, "ana@conjunto.com")
    assert _notis(db, "luis@conjunto.com") == []                                      # otros residentes no se enteran


def test_el_mismo_aviso_no_se_repite_antes_de_5_minutos(client, auth, db):
    p = crear_pase(client, auth)
    url = f"/pase-publico/{token_de(p)}/aviso"
    assert client.post(url, json={"tipo": "en_camino"}).status_code == 200
    assert client.post(url, json={"tipo": "en_camino"}).status_code == 429
    assert client.post(url, json={"tipo": "llegue"}).status_code == 200               # otro tipo de aviso sí
    assert _notis(db, "ana@conjunto.com").count("Tu visita va en camino") == 1       # el spam no llegó al residente
    db.query(CodigoQR).filter(CodigoQR.token == token_de(p)).update({"aviso_camino": ahora_utc() - timedelta(minutes=6)})
    db.commit()
    assert client.post(url, json={"tipo": "en_camino"}).status_code == 200


def test_aviso_valida_el_tipo_y_rechaza_pases_revocados_o_vencidos(client, auth, db):
    p = crear_pase(client, auth)
    url = f"/pase-publico/{token_de(p)}/aviso"
    assert client.post(url, json={"tipo": "sorpresa"}).status_code == 422
    db.query(CodigoQR).filter(CodigoQR.token == token_de(p)).update({"valido_hasta": ahora_utc() - timedelta(minutes=1)})
    db.commit()
    assert client.post(url, json={"tipo": "llegue"}).status_code == 400
    q = crear_pase(client, auth)
    client.post(f"/qr/visitantes/{q['id']}/revocar", headers=auth("ana@conjunto.com"))
    assert client.post(f"/pase-publico/{token_de(q)}/aviso", json={"tipo": "llegue"}).status_code == 400


# ================================================================ FASE 1 · límites, mapas y configuración
def test_las_lecturas_publicas_tienen_tope_por_ip(client, auth):
    p = crear_pase(client, auth)
    for _ in range(limitador.LECTURAS_PUBLICAS.maximo):
        assert client.get(f"/pase-publico/{token_de(p)}").status_code == 200
    assert client.get(f"/pase-publico/{token_de(p)}").status_code == 429


def test_los_avisos_tienen_un_tope_por_ip_aunque_el_token_sea_falso(client):
    for _ in range(limitador.AVISOS_PUBLICOS.maximo):
        assert client.post("/pase-publico/falso-0123456789/aviso", json={"tipo": "llegue"}).status_code == 404
    assert client.post("/pase-publico/falso-0123456789/aviso", json={"tipo": "llegue"}).status_code == 429


def test_los_mapas_usan_coordenadas_o_direccion_o_no_aparecen(client, auth, monkeypatch):
    p = crear_pase(client, auth)
    url = f"/pase-publico/{token_de(p)}"
    assert client.get(url).json()["conjunto"]["mapas"] is None                       # sin configurar: no hay botones
    monkeypatch.setattr(config, "CONJUNTO_DIRECCION", "Calle 10 # 5-20, Facatativá")
    m = client.get(url).json()["conjunto"]["mapas"]
    assert "Calle%2010" in m["google"] and "waze.com/ul?q=" in m["waze"]
    monkeypatch.setattr(config, "CONJUNTO_LATITUD", 4.8133)
    monkeypatch.setattr(config, "CONJUNTO_LONGITUD", -74.3541)
    m = client.get(url).json()["conjunto"]["mapas"]
    assert "destination=4.8133,-74.3541" in m["google"] and "ll=4.8133,-74.3541" in m["waze"]


def test_el_service_worker_no_guarda_la_pagina_publica(client):
    sw = client.get("/app/sw.js").text
    assert "pase/pase" not in sw and "pase.html" not in sw


def test_la_migracion_agrega_pin_avisos_e_indices():
    import os, sqlite3, tempfile
    from alembic import command
    from alembic.config import Config
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = os.path.join(tempfile.mkdtemp(), "m.db")
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(raiz, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ruta}")
    command.upgrade(cfg, "head")
    con = sqlite3.connect(ruta)
    cols = {c[1] for c in con.execute("PRAGMA table_info(codigos_qr)")}
    idx = {i[1] for i in con.execute("SELECT * FROM sqlite_master WHERE type='index'")}
    assert {"pin", "aviso_camino", "aviso_llegada"} <= cols
    assert {"ix_codigos_qr_pin", "ix_usuarios_rol_id", "ix_vehiculos_visitantes_estado", "ix_vehiculos_visitantes_fecha_ingreso"} <= idx
    command.upgrade(cfg, "head")                  # correrla otra vez no rompe nada (idempotente)
    command.downgrade(cfg, "0015")                # y se puede devolver
    con2 = sqlite3.connect(ruta)
    assert "pin" not in {c[1] for c in con2.execute("PRAGMA table_info(codigos_qr)")}
