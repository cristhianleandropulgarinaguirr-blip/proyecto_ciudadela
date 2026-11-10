# tests/test_v27.py — Versión 2.7: sesión del guarda, visita de un día, política de datos, pagos con comprobante y calendario.
from datetime import date, datetime, timedelta, timezone

import jwt

from app.config import GUARDIA_TOKEN_HORAS
from app.models import VisitanteAutorizado
from app.security import decodificar_token

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
CLAVE = "claveSegura123"


def vida_del_token(client, email):
    t = client.post("/auth/login", data={"username": email, "password": CLAVE}).json()["access_token"]
    return (datetime.fromtimestamp(decodificar_token(t)["exp"], timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600


def id_de(client, auth, email):
    return next(u["id"] for u in client.get("/usuarios/", headers=auth(ADM)).json() if u["email"] == email)


# ------------------------------------------------------------ sesión larga solo para portería
def test_la_sesion_del_guarda_dura_un_turno_y_la_de_los_demas_no(client):
    assert GUARDIA_TOKEN_HORAS - 0.1 < vida_del_token(client, CEL) <= GUARDIA_TOKEN_HORAS
    assert vida_del_token(client, ANA) < 1.01 and vida_del_token(client, ADM) < 1.01


# ------------------------------------------------------------ visita de un solo día
def hoy():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def test_visita_de_hoy_vence_sola_y_se_puede_renovar(client, auth, db):
    cuerpo = {"nombre": "Pedro Gómez", "documento": "80123456", "tipo": "Amigo", "vigente_hasta": hoy().isoformat(), "notas": "Visita de hoy"}
    v = client.post("/visitantes-autorizados/", json=cuerpo, headers=auth(ANA)).json()
    assert v["vigente"] is True and v["vigente_hasta"] == hoy().isoformat()
    assert client.post("/visitantes-autorizados/", json=cuerpo, headers=auth(ANA)).status_code == 400              # aún vigente: duplicado
    db.query(VisitanteAutorizado).update({"vigente_hasta": datetime.combine(date.today() - timedelta(days=3), datetime.min.time())}); db.commit()
    assert client.get("/visitantes-autorizados/buscar?q=80123456", headers=auth(CEL)).json()[0]["vigente"] is False   # ya venció
    nuevo = client.post("/visitantes-autorizados/", json=cuerpo, headers=auth(ANA))                                # venció: se puede volver a invitar
    assert nuevo.status_code == 201 and nuevo.json()["id"] == v["id"] and nuevo.json()["vigente"] is True


def test_las_visitas_vencidas_no_ocupan_cupo(client, auth, db):
    for i in range(20):
        client.post("/visitantes-autorizados/", json={"nombre": f"Persona {i:02d}", "documento": f"DOC{i:05d}", "vigente_hasta": hoy().isoformat()}, headers=auth(ANA))
    extra = {"nombre": "Una más", "documento": "ZZZ99999"}
    assert client.post("/visitantes-autorizados/", json=extra, headers=auth(ANA)).status_code == 400                # lleno
    db.query(VisitanteAutorizado).update({"vigente_hasta": datetime.combine(date.today() - timedelta(days=3), datetime.min.time())}); db.commit()
    assert client.post("/visitantes-autorizados/", json=extra, headers=auth(ANA)).status_code == 201                # las vencidas liberaron el cupo


# ------------------------------------------------------------ política de datos
def test_aceptar_la_politica_de_datos(client, auth):
    assert client.get("/usuarios/me", headers=auth(ANA)).json()["politica_aceptada"] is False
    assert client.post("/auth/aceptar-politica-datos").status_code == 401
    assert client.post("/auth/aceptar-politica-datos", headers=auth(ANA)).status_code == 200
    assert client.post("/auth/aceptar-politica-datos", headers=auth(ANA)).status_code == 200                       # idempotente
    assert client.get("/usuarios/me", headers=auth(ANA)).json()["politica_aceptada"] is True
    assert client.get("/usuarios/me", headers=auth(LUIS)).json()["politica_aceptada"] is False                     # cada quien la suya
    assert [x["accion"] for x in client.get("/auditoria/?entidad=Seguridad", headers=auth(ADM)).json()].count("Aceptó la política de datos") == 1


# ------------------------------------------------------------ pagos y comprobantes
def deuda(client, auth, email, valor):
    client.patch(f"/administracion/registrar-deuda/{id_de(client, auth, email)}?saldo_pendiente={valor}", headers=auth(ADM))


def test_cada_pago_genera_un_comprobante_descargable(client, auth):
    deuda(client, auth, ANA, 300000)
    r = client.post("/administracion/simular-pago-pasarela?valor_pagado=100000", headers=auth(ANA)).json()
    assert r["saldo_pendiente"] == 200000 and r["pago_id"]
    client.post("/administracion/simular-pago-pasarela?valor_pagado=200000", headers=auth(ANA))
    pagos = client.get("/administracion/mis-pagos", headers=auth(ANA)).json()
    assert [(p["valor"], p["saldo_anterior"], p["saldo_posterior"]) for p in pagos] == [(200000, 200000, 0), (100000, 300000, 200000)]
    assert pagos[1]["comprobante"].startswith("REC-") and client.get("/administracion/mis-pagos", headers=auth(LUIS)).json() == []   # cada uno ve los suyos
    assert len(client.get(f"/administracion/mis-pagos?usuario_id={id_de(client, auth, ANA)}", headers=auth(ADM)).json()) == 2
    assert len(client.get(f"/administracion/mis-pagos?usuario_id={id_de(client, auth, ANA)}", headers=auth(LUIS)).json()) == 0    # un residente no puede espiar
    assert client.get("/administracion/mis-pagos", headers=auth(CEL)).status_code == 403
    pdf = client.get(f"/reportes/recibo/{pagos[0]['id']}.pdf", headers=auth(ANA))
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and "comprobante_REC-" in pdf.headers["content-disposition"]
    assert client.get(f"/reportes/recibo/{pagos[0]['id']}.pdf", headers=auth(ADM)).status_code == 200
    assert client.get(f"/reportes/recibo/{pagos[0]['id']}.pdf", headers=auth(LUIS)).status_code == 403
    assert client.get(f"/reportes/recibo/{pagos[0]['id']}.pdf").status_code == 401
    assert client.get("/reportes/recibo/9999.pdf", headers=auth(ADM)).status_code == 404


# ------------------------------------------------------------ calendario de reservas
def reservar(client, auth, email, dias, zona="Salon Comunal"):
    f = (datetime.now() + timedelta(days=dias)).replace(hour=14, minute=0, second=0, microsecond=0).isoformat()
    return client.post("/reservas/registrar", json={"zona_comun": zona, "fecha_reserva": f}, headers=auth(email)).json()["id"]


def test_ocupacion_no_revela_quien_reservo(client, auth):
    f = datetime.now() + timedelta(days=10)
    mes = f"{f:%Y-%m}"
    a = reservar(client, auth, ANA, 10)
    ocupado = client.get("/reservas/ocupacion", params={"zona": "Salon Comunal", "mes": mes}, headers=auth(LUIS)).json()
    assert ocupado == [{"dia": f"{f:%Y-%m-%d}", "estado": "Pendiente"}]                                          # Luis ve el día, no a Ana
    assert "Ana" not in str(ocupado) and set(ocupado[0]) == {"dia", "estado"}
    reservar(client, auth, LUIS, 10)                                                                              # otra pendiente el mismo día
    client.patch(f"/reservas/cambiar-estado/{a}?nuevo_estado=Aprobada", headers=auth(ADM))
    assert client.get("/reservas/ocupacion", params={"zona": "Salon Comunal", "mes": mes}, headers=auth(CEL)).json()[0]["estado"] == "Aprobada"
    assert client.get("/reservas/ocupacion", params={"zona": "Piscina", "mes": mes}, headers=auth(ANA)).json() == []   # otra zona
    assert client.get("/reservas/ocupacion", params={"zona": "Salon Comunal", "mes": "2026-13"}, headers=auth(ANA)).status_code == 422
    assert client.get("/reservas/ocupacion", params={"zona": "Salon Comunal", "mes": mes}).status_code == 401
    client.patch(f"/reservas/{a}/cancelar", headers=auth(ANA))
    assert client.get("/reservas/ocupacion", params={"zona": "Salon Comunal", "mes": mes}, headers=auth(ANA)).json()[0]["estado"] == "Pendiente"   # la cancelada ya no cuenta
