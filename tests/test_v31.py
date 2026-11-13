# tests/test_v31.py — Versión 3.1: sesión segura, avisos push, votaciones y portería sin internet.
import base64
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import config, push, sesiones
from app.generar_vapid import generar
from app.main import app
from app.models import (AccesoVisitante, OperacionOffline, Paquete, Sesion, SuscripcionPush, Usuario, VehiculoVisitante, VisitanteAutorizado,
                        Votacion, ahora_utc)
from app.security import crear_token_acceso, encriptar_password

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
CLAVE = "claveSegura123"
CSRF = {"X-Requested-With": "ciudadela"}


def dispositivo() -> TestClient:
    """Un «celular» con su propio jar de cookies."""
    return TestClient(app)


def entrar(c: TestClient, email: str) -> dict:
    r = c.post("/auth/login", data={"username": email, "password": CLAVE})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _limpiar_cache():
    sesiones.invalidar_cache()
    yield
    sesiones.invalidar_cache()


def uid(db, email):
    return db.query(Usuario).filter(Usuario.email == email).one().id


# ======================================================================= SESIÓN SEGURA
def test_login_entrega_cookie_httponly_y_token_corto(client):
    r = client.post("/auth/login", data={"username": ANA, "password": CLAVE})
    assert r.status_code == 200 and r.json()["expira_en"] == config.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    cookie = r.headers["set-cookie"].lower()
    assert "ciudadela_rt=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/auth" in cookie
    assert "ciudadela_rt" not in json.dumps(r.json())       # el refresh token jamás viaja en el cuerpo
    assert r.headers["cache-control"] == "no-store"


def test_refresh_rota_la_cookie_y_entrega_un_token_valido(client):
    entrar(client, ANA)
    antes = client.cookies.get("ciudadela_rt")
    r = client.post("/auth/refresh", headers=CSRF)
    assert r.status_code == 200 and client.cookies.get("ciudadela_rt") != antes
    assert client.get("/usuarios/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_refresh_exige_cookie_y_encabezado_de_la_app(client):
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401           # sin cookie
    entrar(client, ANA)
    assert client.post("/auth/refresh").status_code == 403                          # sin encabezado (CSRF)


def test_reutilizar_un_refresh_viejo_revoca_la_sesion(client, db):
    h = entrar(client, ANA)
    viejo = client.cookies.get("ciudadela_rt")
    assert client.post("/auth/refresh", headers=CSRF).status_code == 200
    db.query(Sesion).update({"rotado_en": ahora_utc() - timedelta(minutes=5)}); db.commit()     # fuera de la gracia
    ladron = dispositivo()
    ladron.cookies.set("ciudadela_rt", viejo, path="/auth")
    assert ladron.post("/auth/refresh", headers=CSRF).status_code == 401
    assert client.get("/usuarios/me", headers=h).status_code == 401                 # la sesión entera quedó revocada
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_dos_pestanas_que_renuevan_a_la_vez_no_cierran_la_sesion(client):
    entrar(client, ANA)
    viejo = client.cookies.get("ciudadela_rt")
    assert client.post("/auth/refresh", headers=CSRF).status_code == 200
    otra = dispositivo()
    otra.cookies.set("ciudadela_rt", viejo, path="/auth")
    r = otra.post("/auth/refresh", headers=CSRF)                                      # dentro de la gracia de rotación
    assert r.status_code == 200 and otra.get("/usuarios/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_logout_revoca_en_el_servidor(client):
    h = entrar(client, ANA)
    assert client.post("/auth/logout", headers=CSRF).status_code == 200
    assert client.get("/usuarios/me", headers=h).status_code == 401                 # el token de acceso deja de servir al instante
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_token_sin_id_de_sesion_no_sirve(client, db):
    t = crear_token_acceso({"sub": ANA, "usuario_id": uid(db, ANA), "rol": "Residente"})
    assert client.get("/usuarios/me", headers={"Authorization": f"Bearer {t}"}).status_code == 401


def test_sesion_vencida_o_con_tope_absoluto_no_renueva(client, db):
    entrar(client, ANA)
    db.query(Sesion).update({"maxima": ahora_utc() - timedelta(seconds=1)}); db.commit()
    assert client.post("/auth/refresh", headers=CSRF).status_code == 401


def test_ver_y_cerrar_sesiones_de_otros_dispositivos(db):
    a, b = dispositivo(), dispositivo()
    ha, hb = entrar(a, ANA), entrar(b, ANA)
    lista = a.get("/auth/sesiones", headers=ha).json()
    assert len(lista) == 2 and sum(s["actual"] for s in lista) == 1
    otra = next(s for s in lista if not s["actual"])
    assert a.delete(f"/auth/sesiones/{otra['id']}", headers=ha).status_code == 200
    assert b.get("/usuarios/me", headers=hb).status_code == 401 and a.get("/usuarios/me", headers=ha).status_code == 200
    # no se puede cerrar la sesión de otra persona
    c = dispositivo(); hl = entrar(c, LUIS)
    assert c.delete(f"/auth/sesiones/{lista[0]['id']}", headers=hl).status_code == 404


def test_cerrar_todas_las_demas_deja_solo_esta(db):
    a, b, c = dispositivo(), dispositivo(), dispositivo()
    ha, hb, hc = entrar(a, ANA), entrar(b, ANA), entrar(c, ANA)
    assert a.post("/auth/cerrar-otras-sesiones", headers=ha).status_code == 200
    assert b.get("/usuarios/me", headers=hb).status_code == 401 and c.get("/usuarios/me", headers=hc).status_code == 401
    assert a.get("/usuarios/me", headers=ha).status_code == 200


def test_cambiar_contrasena_cierra_las_otras_sesiones(db):
    a, b = dispositivo(), dispositivo()
    ha, hb = entrar(a, ANA), entrar(b, ANA)
    r = a.post("/auth/cambiar-password", json={"password_actual": CLAVE, "password_nueva": "OtraClave2026x"}, headers=ha)
    assert r.status_code == 200, r.text
    assert b.get("/usuarios/me", headers=hb).status_code == 401 and a.get("/usuarios/me", headers=ha).status_code == 200


def test_desactivar_o_restablecer_cierra_las_sesiones_del_usuario(db):
    adm, a = dispositivo(), dispositivo()
    h_adm, ha = entrar(adm, ADM), entrar(a, ANA)
    assert adm.patch(f"/usuarios/{uid(db, ANA)}/activo", params={"esta_activo": False}, headers=h_adm).status_code == 200
    assert a.get("/usuarios/me", headers=ha).status_code == 401
    assert a.post("/auth/refresh", headers=CSRF).status_code == 401
    b = dispositivo(); hl = entrar(b, LUIS)
    r = adm.post(f"/usuarios/{uid(db, LUIS)}/restablecer-password", headers=h_adm)
    assert r.status_code == 200, r.text
    assert b.get("/usuarios/me", headers=hl).status_code == 401


def test_la_base_solo_guarda_el_hash_del_refresh(client, db):
    entrar(client, ANA)
    token = client.cookies.get("ciudadela_rt")
    s = db.query(Sesion).one()
    assert s.token_hash != token and token not in (s.token_anterior_hash or "") and len(s.token_hash) == 64


def test_cabecera_csp_en_la_app(client):
    csp = client.get("/app/").headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp


# ======================================================================= AVISOS PUSH
SUB = {"endpoint": "https://fcm.googleapis.com/fcm/send/abc123abc123abc123abc123", "keys": {"p256dh": "B" * 87, "auth": "a" * 22}}


@pytest.fixture()
def vapid(monkeypatch):
    pub, priv = generar()
    monkeypatch.setattr(config, "VAPID_PUBLIC_KEY", pub)
    monkeypatch.setattr(config, "VAPID_PRIVATE_KEY", priv)
    return pub


def test_generar_vapid_produce_claves_validas():
    pub, priv = generar()
    p = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
    assert len(p) == 65 and p[0] == 4 and len(base64.urlsafe_b64decode(priv + "=" * (-len(priv) % 4))) == 32


def test_push_apagado_sin_claves(client, auth):
    c = client.get("/push/config", headers=auth(ANA)).json()
    assert c["activo"] is False and c["clave_publica"] is None
    assert client.post("/push/suscribir", json=SUB, headers=auth(ANA)).status_code == 503


def test_suscribir_reasignar_y_desuscribir(client, auth, db, vapid):
    assert client.get("/push/config", headers=auth(ANA)).json()["clave_publica"] == vapid
    assert client.post("/push/suscribir", json=SUB, headers=auth(ANA)).status_code == 200
    assert client.post("/push/suscribir", json=SUB, headers=auth(ANA)).status_code == 200            # repetir no duplica
    assert db.query(SuscripcionPush).count() == 1
    assert client.post("/push/suscribir", json=SUB, headers=auth(LUIS)).status_code == 200            # el celular pasó a otra persona
    assert db.query(SuscripcionPush).one().usuario_id == uid(db, LUIS)
    assert client.post("/push/desuscribir", json={"endpoint": SUB["endpoint"]}, headers=auth(ANA)).status_code == 200
    assert db.query(SuscripcionPush).count() == 1                                                      # Ana no puede borrar la de Luis
    assert client.post("/push/desuscribir", json={"endpoint": SUB["endpoint"]}, headers=auth(LUIS)).status_code == 200
    assert db.query(SuscripcionPush).count() == 0


def test_suscripcion_invalida_se_rechaza(client, auth, vapid):
    assert client.post("/push/suscribir", json={**SUB, "endpoint": "http://inseguro.com/xxxxxxxxxxxxxxxxxxxxxxx"}, headers=auth(ANA)).status_code == 422


def test_las_notificaciones_tambien_se_despachan_por_push(client, auth, db, vapid, monkeypatch):
    enviados = []

    class Inmediato:
        def submit(self, fn, *a):
            fn(*a)

    monkeypatch.setattr(push, "_pool", Inmediato())
    monkeypatch.setattr(push, "_enviar_una", lambda sub, carga: enviados.append((sub.usuario_id, json.loads(carga))) and None)
    client.post("/push/suscribir", json=SUB, headers=auth(ANA))
    r = client.post("/paquetes/", json={"destinatario_id": uid(db, ANA), "remitente": "Servientrega"}, headers=auth(CEL))
    assert r.status_code == 201
    assert len(enviados) == 1 and enviados[0][0] == uid(db, ANA)
    assert enviados[0][1]["titulo"] == "Tienes un paquete en portería" and enviados[0][1]["enlace"] == "#/paquetes"


def test_suscripcion_expirada_se_elimina(client, auth, db, vapid, monkeypatch):
    client.post("/push/suscribir", json=SUB, headers=auth(ANA))
    monkeypatch.setattr(push, "_enviar_una", lambda sub, carga: 410)
    assert push.enviar_ahora([uid(db, ANA)], "x", "y", "#/") == 0
    db.expire_all()
    assert db.query(SuscripcionPush).count() == 0


def test_probar_sin_dispositivos_da_error_claro(client, auth, vapid):
    assert client.post("/push/probar", headers=auth(ANA)).status_code == 400


# ======================================================================= VOTACIONES
def nueva_votacion(client, auth, **extra):
    cuerpo = {"titulo": "¿Pintamos la fachada?", "opciones": ["Sí", "No", "Me abstengo"],
              "fecha_cierre": (ahora_utc() + timedelta(days=3)).isoformat() + "Z", **extra}
    return client.post("/votaciones/", json=cuerpo, headers=auth(ADM))


def votar(client, auth, quien, vid, opcion):
    return client.post(f"/votaciones/{vid}/votar", json={"opcion_id": opcion}, headers=auth(quien))


def ids_opciones(client, auth, vid):
    return {o["texto"]: o["id"] for o in client.get(f"/votaciones/{vid}", headers=auth(ADM)).json()["opciones"]}


def test_crear_votacion_avisa_a_los_residentes(client, auth):
    r = nueva_votacion(client, auth)
    assert r.status_code == 201 and r.json()["estado"] == "Abierta" and len(r.json()["opciones"]) == 3
    assert r.json()["elegibles"] == 2 and r.json()["participacion"] == 0
    n = client.get("/notificaciones/", headers=auth(ANA)).json()
    assert n[0]["titulo"].startswith("Nueva votación") and n[0]["enlace"] == "#/votaciones"
    assert client.get("/notificaciones/", headers=auth(CEL)).json() == []                 # el guarda no vota


def test_validaciones_al_crear(client, auth):
    assert nueva_votacion(client, auth, opciones=["Sí"]).status_code == 422
    assert nueva_votacion(client, auth, opciones=["Sí", "sí"]).status_code == 422
    assert nueva_votacion(client, auth, fecha_cierre="2020-01-01T00:00:00Z").status_code == 422
    assert nueva_votacion(client, auth, fecha_cierre=(ahora_utc() + timedelta(days=200)).isoformat() + "Z").status_code == 422
    assert client.post("/votaciones/", json={"titulo": "x" * 10, "opciones": ["a", "b"], "fecha_cierre": "2099-01-01T00:00:00Z"}, headers=auth(ANA)).status_code == 403


def test_voto_secreto_resultados_solo_al_cerrar(client, auth):
    vid = nueva_votacion(client, auth).json()["id"]
    op = ids_opciones(client, auth, vid)
    r = votar(client, auth, ANA, vid, op["Sí"])
    assert r.status_code == 200 and r.json()["ya_vote"] is True and r.json()["puede_votar"] is False
    assert all(o["votos"] is None for o in r.json()["opciones"]) and r.json()["total_votos"] is None
    assert all(o["votos"] is None for o in client.get(f"/votaciones/{vid}", headers=auth(ADM)).json()["opciones"])   # ni el admin ve parciales
    votar(client, auth, LUIS, vid, op["No"])
    cerrada = client.post(f"/votaciones/{vid}/cerrar", headers=auth(ADM)).json()
    assert cerrada["estado"] == "Cerrada" and cerrada["resultados_visibles"] and cerrada["total_votos"] == 2
    assert {o["texto"]: o["votos"] for o in cerrada["opciones"]} == {"Sí": 1, "No": 1, "Me abstengo": 0}
    assert votar(client, auth, ANA, vid, op["Sí"]).status_code == 400                    # ya terminó


def test_resultados_en_vivo_si_se_pidio(client, auth):
    vid = nueva_votacion(client, auth, resultados_en_vivo=True).json()["id"]
    votar(client, auth, ANA, vid, ids_opciones(client, auth, vid)["Sí"])
    assert client.get(f"/votaciones/{vid}", headers=auth(LUIS)).json()["total_votos"] == 1


def test_un_voto_por_apartamento_y_no_se_puede_repetir(client, auth, db):
    r = db.query(Usuario).filter(Usuario.email == ANA).one()
    db.add(Usuario(nombre_completo="Pareja de Ana", email="pareja@conjunto.com", password_encriptada=encriptar_password(CLAVE), rol_id=r.rol_id, apartamento="torre 1   apt 101"))
    db.commit()
    vid = nueva_votacion(client, auth).json()["id"]
    op = ids_opciones(client, auth, vid)
    assert votar(client, auth, ANA, vid, op["Sí"]).status_code == 200
    assert votar(client, auth, ANA, vid, op["No"]).status_code == 409                    # no cambia el voto
    r2 = votar(client, auth, "pareja@conjunto.com", vid, op["No"])
    assert r2.status_code == 409 and "apartamento" in r2.json()["detail"]                # mismo apto (aunque escrito distinto)
    assert client.get(f"/votaciones/{vid}", headers=auth("pareja@conjunto.com")).json()["puede_votar"] is False


def test_un_voto_por_persona_permite_a_ambos(client, auth, db):
    r = db.query(Usuario).filter(Usuario.email == ANA).one()
    db.add(Usuario(nombre_completo="Pareja de Ana", email="pareja@conjunto.com", password_encriptada=encriptar_password(CLAVE), rol_id=r.rol_id, apartamento="Torre 1 Apt 101"))
    db.commit()
    vid = nueva_votacion(client, auth, un_voto_por="persona").json()["id"]
    op = ids_opciones(client, auth, vid)
    assert votar(client, auth, ANA, vid, op["Sí"]).status_code == 200
    assert votar(client, auth, "pareja@conjunto.com", vid, op["No"]).status_code == 200


def test_quien_no_vota(client, auth):
    vid = nueva_votacion(client, auth).json()["id"]
    op = ids_opciones(client, auth, vid)
    assert votar(client, auth, CEL, vid, op["Sí"]).status_code == 403
    assert votar(client, auth, ADM, vid, op["Sí"]).status_code == 403
    assert votar(client, auth, ANA, vid, 99999).status_code == 400
    otra = nueva_votacion(client, auth, titulo="Otra consulta").json()["id"]
    assert votar(client, auth, ANA, vid, ids_opciones(client, auth, otra)["Sí"]).status_code == 400   # opción de otra votación
    assert client.get("/votaciones/", headers=auth(CEL)).status_code == 403


def test_exige_estar_al_dia(client, auth, db):
    db.query(Usuario).filter(Usuario.email == LUIS).update({"esta_al_dia": False}); db.commit()
    vid = nueva_votacion(client, auth, exige_al_dia=True).json()["id"]
    op = ids_opciones(client, auth, vid)
    assert votar(client, auth, LUIS, vid, op["Sí"]).status_code == 403
    assert client.get("/votaciones/pendientes", headers=auth(LUIS)).json()["pendientes"] == 0
    assert votar(client, auth, ANA, vid, op["Sí"]).status_code == 200


def test_cierra_sola_con_la_fecha_y_anular_oculta_resultados(client, auth, db):
    vid = nueva_votacion(client, auth).json()["id"]
    votar(client, auth, ANA, vid, ids_opciones(client, auth, vid)["Sí"])
    db.query(Votacion).update({"fecha_cierre": ahora_utc() - timedelta(minutes=1)}); db.commit()
    v = client.get(f"/votaciones/{vid}", headers=auth(LUIS)).json()
    assert v["estado"] == "Cerrada" and v["total_votos"] == 1 and v["puede_votar"] is False
    v2 = nueva_votacion(client, auth, titulo="Consulta que se anula").json()["id"]
    votar(client, auth, ANA, v2, ids_opciones(client, auth, v2)["Sí"])
    a = client.post(f"/votaciones/{v2}/anular", headers=auth(ADM)).json()
    assert a["estado"] == "Anulada" and a["resultados_visibles"] is False and all(o["votos"] is None for o in a["opciones"])


def test_participacion_muestra_quien_voto_pero_no_que_voto(client, auth):
    vid = nueva_votacion(client, auth).json()["id"]
    votar(client, auth, ANA, vid, ids_opciones(client, auth, vid)["No"])
    p = client.get(f"/votaciones/{vid}/participacion", headers=auth(ADM)).json()
    assert p["participaron"] == ["Torre 1 Apt 101"] and p["pendientes"] == ["Torre 2 Apt 202"]
    assert "No" not in json.dumps(p)
    assert client.get(f"/votaciones/{vid}/participacion", headers=auth(ANA)).status_code == 403


def test_no_hay_forma_de_unir_voto_y_votante(client, auth, db):
    from app.models import VotacionOpcion, VotacionParticipacion
    vid = nueva_votacion(client, auth).json()["id"]
    votar(client, auth, ANA, vid, ids_opciones(client, auth, vid)["Sí"])
    assert not any("opcion" in c.name for c in VotacionParticipacion.__table__.columns)          # quién votó no apunta a qué votó
    assert not any("usuario" in c.name for c in VotacionOpcion.__table__.columns)
    log = " ".join((a["detalle"] or "") for a in client.get("/auditoria/", headers=auth(ADM)).json() if a["accion"] == "Votó")
    assert "Sí" not in log


def test_pendientes_cuenta_las_que_faltan(client, auth):
    assert client.get("/votaciones/pendientes", headers=auth(ANA)).json()["pendientes"] == 0
    a = nueva_votacion(client, auth).json()["id"]
    nueva_votacion(client, auth, titulo="Segunda consulta")
    assert client.get("/votaciones/pendientes", headers=auth(ANA)).json()["pendientes"] == 2
    votar(client, auth, ANA, a, ids_opciones(client, auth, a)["Sí"])
    assert client.get("/votaciones/pendientes", headers=auth(ANA)).json()["pendientes"] == 1


# ======================================================================= PORTERÍA SIN INTERNET
def op(uuid, tipo, datos, hace_min=None):
    d = {"uuid": uuid, "tipo": tipo, "datos": datos}
    if hace_min is not None:
        d["ocurrido_en"] = (ahora_utc() - timedelta(minutes=hace_min)).isoformat() + "Z"
    return d


def sincronizar(client, auth, ops, quien=CEL):
    return client.post("/porteria/sincronizar", json={"operaciones": ops}, headers=auth(quien))


def test_ingreso_y_salida_sin_internet_conservan_la_hora_real(client, auth, db):
    r = sincronizar(client, auth, [op("op-ing-0001", "vehiculo_ingreso", {"placa": "abc123", "apartamento": "Torre 1 Apt 101"}, hace_min=90),
                                   op("op-sal-0001", "vehiculo_salida", {"ref": "op-ing-0001"}, hace_min=30)])
    assert r.status_code == 200 and [x["estado"] for x in r.json()["resultados"]] == ["ok", "ok"]
    v = db.query(VehiculoVisitante).one()
    assert v.placa == "ABC123" and v.estado == "Salido"
    assert 85 < (ahora_utc() - v.fecha_ingreso).total_seconds() / 60 < 95 and 25 < (ahora_utc() - v.fecha_salida).total_seconds() / 60 < 35


def test_reenviar_no_duplica_nada(client, auth, db):
    ops = [op("op-ing-0002", "vehiculo_ingreso", {"placa": "XYZ123", "apartamento": "Torre 2"})]
    assert sincronizar(client, auth, ops).json()["resultados"][0]["estado"] == "ok"
    r = sincronizar(client, auth, ops).json()["resultados"][0]
    assert r["estado"] == "duplicada" and r["id"] is not None
    assert db.query(VehiculoVisitante).count() == 1 and db.query(OperacionOffline).count() == 1


def test_operaciones_invalidas_se_rechazan_sin_romper_las_demas(client, auth, db):
    r = sincronizar(client, auth, [op("op-mala-001", "vehiculo_ingreso", {"placa": "12", "apartamento": "x"}),
                                   op("op-buena-01", "vehiculo_ingreso", {"placa": "DEF456", "apartamento": "Torre 3"}),
                                   op("op-repe-001", "vehiculo_ingreso", {"placa": "DEF456", "apartamento": "Torre 3"})]).json()["resultados"]
    assert [x["estado"] for x in r] == ["rechazada", "ok", "rechazada"] and "ya figura dentro" in r[2]["mensaje"]
    assert db.query(VehiculoVisitante).count() == 1


def test_salida_por_placa_si_el_ingreso_original_ya_estaba_dentro(client, auth, db):
    client.post("/porteria/vehiculo-ingreso", params={"placa": "GHI789", "apartamento": "Torre 1"}, headers=auth(CEL))
    r = sincronizar(client, auth, [op("op-ing-0003", "vehiculo_ingreso", {"placa": "GHI789", "apartamento": "Torre 1"}),
                                   op("op-sal-0003", "vehiculo_salida", {"ref": "op-ing-0003", "placa": "GHI789"})]).json()["resultados"]
    assert [x["estado"] for x in r] == ["rechazada", "ok"] and db.query(VehiculoVisitante).one().estado == "Salido"


def test_la_hora_se_acota(client, auth, db):
    sincronizar(client, auth, [op("op-fut-0001", "vehiculo_ingreso", {"placa": "JKL012", "apartamento": "T1"}, hace_min=-600),
                               op("op-vie-0001", "vehiculo_ingreso", {"placa": "MNO345", "apartamento": "T1"}, hace_min=60 * 24 * 30)])
    for v in db.query(VehiculoVisitante).all():
        assert v.fecha_ingreso <= ahora_utc() and v.fecha_ingreso >= ahora_utc() - timedelta(days=7, minutes=1)


def test_visitante_a_pie_sin_internet(client, auth, db):
    vid = client.post("/visitantes-autorizados/", json={"nombre": "Pedro Gómez", "documento": "80123456", "tipo": "Amigo"}, headers=auth(ANA)).json()["id"]
    r = sincronizar(client, auth, [op("op-vis-0001", "visitante_ingreso", {"visitante_id": vid}, hace_min=20),
                                   op("op-vis-0002", "visitante_salida", {"ref": "op-vis-0001"}, hace_min=5)]).json()["resultados"]
    assert [x["estado"] for x in r] == ["ok", "ok"]
    a = db.query(AccesoVisitante).one()
    assert a.fecha_salida is not None and a.ingreso_registrado_por == uid(db, CEL)
    r = sincronizar(client, auth, [op("op-vis-0003", "visitante_salida", {"visitante_id": vid})]).json()["resultados"][0]
    assert r["estado"] == "rechazada"                                                    # ya había salido


def test_paquete_registrado_y_entregado_sin_internet(client, auth, db):
    dest = uid(db, ANA)
    r = sincronizar(client, auth, [op("op-paq-0001", "paquete_registro", {"destinatario_id": dest, "tipo": "Paquete", "remitente": "Servientrega"}, hace_min=45),
                                   op("op-paq-0002", "paquete_entrega", {"ref": "op-paq-0001", "entregado_a": "Su hermano"}, hace_min=10)]).json()["resultados"]
    assert [x["estado"] for x in r] == ["ok", "ok"]
    p = db.query(Paquete).one()
    assert p.estado == "Entregado" and p.entregado_a == "Su hermano" and 40 < (ahora_utc() - p.fecha_recepcion).total_seconds() / 60 < 50
    assert client.get("/notificaciones/conteo", headers=auth(ANA)).json()["no_leidas"] == 1     # el residente sí recibe su aviso al sincronizar


def test_solo_el_personal_sincroniza_y_hay_tope(client, auth):
    assert sincronizar(client, auth, [], quien=ANA).status_code == 403
    assert sincronizar(client, auth, [op(f"op-{i:08d}", "vehiculo_ingreso", {"placa": "ABC123", "apartamento": "x"}) for i in range(101)]).status_code == 422
    assert sincronizar(client, auth, [op("x", "vehiculo_ingreso", {})]).status_code == 422                  # uuid demasiado corto
    assert sincronizar(client, auth, [{"uuid": "op-tipo-0001", "tipo": "borrar_todo", "datos": {}}]).status_code == 422


def test_lista_liviana_de_visitantes_para_la_porteria(client, auth, db):
    vid = client.post("/visitantes-autorizados/", json={"nombre": "Pedro Gómez", "documento": "80123456", "tipo": "Amigo"}, headers=auth(ANA)).json()["id"]
    client.post(f"/visitantes-autorizados/{vid}/ingreso", headers=auth(CEL))
    lista = client.get("/visitantes-autorizados/sincronizacion", headers=auth(CEL)).json()
    assert len(lista) == 1 and lista[0]["dentro"] is True and lista[0]["acceso_id"] is not None and lista[0]["anfitrion_nombre"] == "Ana Residente"
    assert client.get("/visitantes-autorizados/sincronizacion", headers=auth(ANA)).status_code == 403
