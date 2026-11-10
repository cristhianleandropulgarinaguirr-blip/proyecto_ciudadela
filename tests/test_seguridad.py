# tests/test_seguridad.py — Bloque 1: reservas para portería, cambio/restablecimiento de contraseña, bloqueo de login y auditoría.
from datetime import timedelta

from app.models import IntentoLogin, ahora_utc

FECHA = "2030-06-15T14:00:00"


def login(client, email, clave="claveSegura123"):
    return client.post("/auth/login", data={"username": email, "password": clave})


def test_guardia_ve_quien_reservo_pero_no_su_correo(client, auth):
    client.post("/reservas/registrar", json={"zona_comun": "Zona BBQ", "fecha_reserva": FECHA}, headers=auth("ana@conjunto.com"))
    fila = client.get("/reservas/listar", headers=auth("celador@conjunto.com")).json()[0]
    assert fila["usuario_nombre"] == "Ana Residente" and fila["apartamento"] == "Torre 1 Apt 101"
    assert "ana@conjunto.com" not in str(fila)
    mia = client.get("/reservas/mis-reservas", headers=auth("ana@conjunto.com")).json()[0]
    assert mia["usuario_nombre"] == "Ana Residente"


def test_cambiar_password_exige_la_actual_y_la_nueva_funciona(client, auth):
    h = auth("ana@conjunto.com")
    assert client.post("/auth/cambiar-password", json={"password_actual": "mala", "password_nueva": "otraClave2026"}, headers=h).status_code == 400
    assert client.post("/auth/cambiar-password", json={"password_actual": "claveSegura123", "password_nueva": "claveSegura123"}, headers=h).status_code == 400
    assert client.post("/auth/cambiar-password", json={"password_actual": "claveSegura123", "password_nueva": "corta"}, headers=h).status_code == 422
    assert client.post("/auth/cambiar-password", json={"password_actual": "claveSegura123", "password_nueva": "otraClave2026"}, headers=h).status_code == 200
    assert login(client, "ana@conjunto.com").status_code == 401
    assert login(client, "ana@conjunto.com", "otraClave2026").status_code == 200
    assert client.post("/auth/cambiar-password", json={"password_actual": "x", "password_nueva": "otraClave2026"}).status_code == 401


def test_admin_restablece_clave_y_la_persona_debe_cambiarla(client, auth):
    admin = auth("admin@conjunto.com")
    uid = next(u["id"] for u in client.get("/usuarios/", headers=admin).json() if u["email"] == "ana@conjunto.com")
    assert client.post(f"/usuarios/{uid}/restablecer-password", headers=auth("luis@conjunto.com")).status_code == 403
    r = client.post(f"/usuarios/{uid}/restablecer-password", headers=admin).json()
    temporal = r["password_temporal"]
    assert len(temporal) >= 8 and client.post("/usuarios/1/restablecer-password", headers=admin).status_code in (200, 400)
    assert login(client, "ana@conjunto.com").status_code == 401                      # la vieja ya no sirve
    ok = login(client, "ana@conjunto.com", temporal)
    assert ok.status_code == 200 and ok.json()["debe_cambiar_password"] is True
    h = {"Authorization": f"Bearer {ok.json()['access_token']}"}
    assert client.get("/usuarios/me", headers=h).json()["debe_cambiar_password"] is True
    client.post("/auth/cambiar-password", json={"password_actual": temporal, "password_nueva": "miClavePropia99"}, headers=h)
    assert client.get("/usuarios/me", headers=h).json()["debe_cambiar_password"] is False


def test_admin_no_restablece_su_propia_clave(client, auth):
    yo = client.get("/usuarios/me", headers=auth("admin@conjunto.com")).json()["id"]
    assert client.post(f"/usuarios/{yo}/restablecer-password", headers=auth("admin@conjunto.com")).status_code == 400


def test_cinco_fallos_bloquean_y_el_acierto_resetea(client, db):
    for _ in range(4):
        assert login(client, "ana@conjunto.com", "mal").status_code == 401
    assert login(client, "ana@conjunto.com").status_code == 200                      # acierto: contador a cero
    for _ in range(5):
        login(client, "ana@conjunto.com", "mal")
    r = login(client, "ana@conjunto.com")                                            # aunque ahora acierte, sigue bloqueada
    assert r.status_code == 429 and "Intenta de nuevo" in r.json()["detail"] and r.headers["retry-after"]
    db.query(IntentoLogin).update({"bloqueado_hasta": ahora_utc() - timedelta(seconds=1)}); db.commit()
    assert login(client, "ana@conjunto.com").status_code == 200


def test_bloqueo_tambien_aplica_a_correos_inexistentes_sin_revelar_nada(client):
    for _ in range(5):
        assert login(client, "fantasma@x.com", "mal").status_code == 401
    assert login(client, "fantasma@x.com", "mal").status_code == 429


def test_auditoria_registra_acciones_y_solo_la_ve_el_admin(client, auth):
    h = auth("ana@conjunto.com")
    rid = client.post("/reservas/registrar", json={"zona_comun": "Zona BBQ", "fecha_reserva": FECHA}, headers=h).json()["id"]
    client.patch(f"/reservas/cambiar-estado/{rid}", params={"nuevo_estado": "Aprobada"}, headers=auth("admin@conjunto.com"))
    uid = next(u["id"] for u in client.get("/usuarios/", headers=auth("admin@conjunto.com")).json() if u["email"] == "ana@conjunto.com")
    client.patch(f"/administracion/registrar-deuda/{uid}", params={"saldo_pendiente": 50000}, headers=auth("admin@conjunto.com"))
    log = client.get("/auditoria/", headers=auth("admin@conjunto.com")).json()
    acciones = {(x["accion"], x["actor"]) for x in log}
    assert ("Solicitó reserva", "Ana Residente") in acciones and ("Reserva aprobada", "Admin") in acciones or any(a.startswith("Reserva aprobada") for a, _ in acciones)
    assert any(x["entidad"] == "Cartera" and "50000" in x["detalle"] for x in log)
    assert [x["entidad"] for x in client.get("/auditoria/?entidad=Cartera", headers=auth("admin@conjunto.com")).json()] == ["Cartera"]
    assert client.get("/auditoria/", headers=h).status_code == 403
    assert client.get("/auditoria/", headers=auth("celador@conjunto.com")).status_code == 403
    assert client.get("/auditoria/").status_code == 401


def test_bloqueo_queda_en_auditoria(client, auth):
    for _ in range(5):
        login(client, "luis@conjunto.com", "mal")
    log = client.get("/auditoria/?entidad=Seguridad", headers=auth("admin@conjunto.com")).json()
    assert log[0]["accion"] == "Bloqueó inicio de sesión" and log[0]["actor"] == "Sistema"
