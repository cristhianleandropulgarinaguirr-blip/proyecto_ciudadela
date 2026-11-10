# tests/test_qr.py — Fase 2: carnet QR, pases de visitante y escaneo en portería.
from datetime import timedelta

from app.models import CodigoQR, ahora_utc

PASE = {"nombre_visitante": "Carlos Pérez", "placa": "xyz123", "horas_validez": 6}


def crear_pase(client, auth, quien="ana@conjunto.com", **extra):
    r = client.post("/qr/visitantes", json={**PASE, **extra}, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def escanear(client, auth, payload, quien="celador@conjunto.com"):
    return client.post("/qr/escanear", json={"codigo": payload}, headers=auth(quien))


def test_carnet_se_crea_una_vez_y_el_qr_no_contiene_datos_personales(client, auth):
    a = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    b = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    assert a["id"] == b["id"] and a["payload"] == b["payload"] and a["payload"].startswith("CD1:")
    assert "Ana" not in a["payload"] and "101" not in a["payload"] and "@" not in a["payload"]
    assert client.get("/qr/mi-carnet").status_code == 401


def test_renovar_carnet_invalida_el_anterior(client, auth):
    viejo = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    nuevo = client.post("/qr/mi-carnet/renovar", headers=auth("ana@conjunto.com")).json()
    assert nuevo["payload"] != viejo["payload"]
    r = escanear(client, auth, viejo["payload"]).json()
    assert r["ok"] is False and "revocado" in r["mensaje"]
    assert escanear(client, auth, nuevo["payload"]).json()["ok"] is True


def test_guardia_escanea_carnet_y_ve_identidad_sin_datos_de_cartera(client, auth):
    c = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    r = escanear(client, auth, c["payload"]).json()
    assert r["ok"] and r["resultado"] == "Identidad verificada"
    assert r["persona"]["nombre_completo"] == "Ana Residente" and r["persona"]["apartamento"] == "Torre 1 Apt 101"
    assert "saldo" not in str(r).lower() and "mora" not in str(r).lower()


def test_solo_guardia_y_admin_pueden_escanear(client, auth):
    c = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    assert escanear(client, auth, c["payload"], "ana@conjunto.com").status_code == 403
    assert client.post("/qr/escanear", json={"codigo": c["payload"]}).status_code == 401
    assert escanear(client, auth, c["payload"], "admin@conjunto.com").status_code == 200


def test_pase_de_visitante_ingreso_salida_y_queda_en_el_historial(client, auth):
    p = crear_pase(client, auth)
    assert p["placa"] == "XYZ123" and p["estado"] == "Activo"
    ing = escanear(client, auth, p["payload"]).json()
    assert ing["ok"] and ing["resultado"] == "Ingreso registrado" and ing["visitante"]["apartamento_destino"] == "Torre 1 Apt 101"
    dentro = client.get("/porteria/vehiculos-dentro", headers=auth("celador@conjunto.com")).json()
    assert [v["placa"] for v in dentro] == ["XYZ123"]

    sal = escanear(client, auth, p["payload"]).json()
    assert sal["ok"] and sal["resultado"] == "Salida registrada"
    assert client.get("/porteria/vehiculos-dentro", headers=auth("celador@conjunto.com")).json() == []
    h = client.get("/porteria/historial", headers=auth("celador@conjunto.com")).json()["items"][0]
    assert h["placa"] == "XYZ123" and h["estado"] == "Salido" and h["ingreso_registrado_por"] == "Celador Uno" and h["salida_registrada_por"] == "Celador Uno"

    tercero = escanear(client, auth, p["payload"]).json()           # ya fue usado
    assert tercero["ok"] is False and "ya fue usado" in tercero["mensaje"]


def test_pase_vencido_se_rechaza_y_se_muestra_vencido(client, auth, db):
    p = crear_pase(client, auth)
    db.query(CodigoQR).filter(CodigoQR.id == p["id"]).update({"valido_hasta": ahora_utc() - timedelta(minutes=1)})
    db.commit()
    assert escanear(client, auth, p["payload"]).json()["ok"] is False
    assert client.get("/qr/visitantes", headers=auth("ana@conjunto.com")).json()[0]["estado"] == "Vencido"


def test_pase_revocado_no_sirve_y_no_se_revoca_con_el_visitante_adentro(client, auth):
    p1 = crear_pase(client, auth)
    assert client.post(f"/qr/visitantes/{p1['id']}/revocar", headers=auth("luis@conjunto.com")).status_code == 403   # no es de Luis
    assert client.post(f"/qr/visitantes/{p1['id']}/revocar", headers=auth("ana@conjunto.com")).json()["estado"] == "Revocado"
    assert escanear(client, auth, p1["payload"]).json()["ok"] is False

    p2 = crear_pase(client, auth, placa="ABC123")
    escanear(client, auth, p2["payload"])
    assert client.post(f"/qr/visitantes/{p2['id']}/revocar", headers=auth("ana@conjunto.com")).status_code == 400


def test_placa_ya_dentro_no_puede_ingresar_dos_veces(client, auth):
    a, b = crear_pase(client, auth), crear_pase(client, auth, quien="luis@conjunto.com")
    assert escanear(client, auth, a["payload"]).json()["ok"] is True
    r = escanear(client, auth, b["payload"]).json()
    assert r["ok"] is False and "ya figura dentro" in r["mensaje"]


def test_codigo_falso_se_rechaza_y_queda_en_la_bitacora(client, auth):
    r = escanear(client, auth, "CD1:token-inventado-que-no-existe").json()
    assert r["ok"] is False and "no reconocido" in r["mensaje"]
    log = client.get("/qr/escaneos", headers=auth("celador@conjunto.com")).json()
    assert log[0]["resultado"] == "Rechazado" and log[0]["escaneado_por"] == "Celador Uno"
    assert client.get("/qr/escaneos", headers=auth("ana@conjunto.com")).status_code == 403


def test_titular_desactivado_no_pasa(client, auth):
    c = client.get("/qr/mi-carnet", headers=auth("luis@conjunto.com")).json()
    luis = client.get("/usuarios/", headers=auth("admin@conjunto.com")).json()
    uid = next(u["id"] for u in luis if u["email"] == "luis@conjunto.com")
    client.patch(f"/usuarios/{uid}/activo", params={"esta_activo": False}, headers=auth("admin@conjunto.com"))
    assert escanear(client, auth, c["payload"]).json()["ok"] is False


def test_validaciones_del_pase_y_limite(client, auth):
    h = auth("ana@conjunto.com")
    assert client.post("/qr/visitantes", json={**PASE, "placa": "12"}, headers=h).status_code == 422
    assert client.post("/qr/visitantes", json={**PASE, "horas_validez": 500}, headers=h).status_code == 422
    assert client.post("/qr/visitantes", json=PASE, headers=auth("celador@conjunto.com")).status_code == 403
    for _ in range(10):
        crear_pase(client, auth)
    assert client.post("/qr/visitantes", json=PASE, headers=h).status_code == 400


def test_imagen_qr_solo_para_el_dueno_o_admin(client, auth):
    c = client.get("/qr/mi-carnet", headers=auth("ana@conjunto.com")).json()
    png = client.get(f"/qr/{c['id']}/imagen", headers=auth("ana@conjunto.com"))
    assert png.status_code == 200 and png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"
    svg = client.get(f"/qr/{c['id']}/imagen?formato=svg", headers=auth("admin@conjunto.com"))
    assert svg.status_code == 200 and b"<svg" in svg.content
    assert client.get(f"/qr/{c['id']}/imagen", headers=auth("luis@conjunto.com")).status_code == 403
    assert client.get(f"/qr/{c['id']}/imagen").status_code == 401
