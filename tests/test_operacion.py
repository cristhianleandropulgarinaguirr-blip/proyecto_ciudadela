# tests/test_operacion.py — Bloque 2: visitantes autorizados, paquetes y contactos de emergencia.
from datetime import date, timedelta

from app.models import VisitanteAutorizado

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
VISITA = {"nombre": "María Gómez", "documento": "1.020.304-050", "tipo": "Servicio domestico", "notas": "Martes y jueves"}


def autorizar(client, auth, quien=ANA, **extra):
    r = client.post("/visitantes-autorizados/", json={**VISITA, **extra}, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def id_de(client, auth, email):
    return next(u["id"] for u in client.get("/usuarios/", headers=auth(ADM)).json() if u["email"] == email)


# ------------------------------------------------------------ visitantes autorizados
def test_residente_autoriza_y_el_documento_se_normaliza(client, auth):
    v = autorizar(client, auth)
    assert v["documento"] == "1020304050" and v["vigente"] is True and v["dentro"] is False and v["apartamento"] == "Torre 1 Apt 101"
    assert client.post("/visitantes-autorizados/", json=VISITA, headers=auth(ANA)).status_code == 400   # duplicado
    assert client.post("/visitantes-autorizados/", json={**VISITA, "documento": "12"}, headers=auth(ANA)).status_code == 422
    assert client.post("/visitantes-autorizados/", json=VISITA, headers=auth(CEL)).status_code == 403
    assert client.post("/visitantes-autorizados/", json=VISITA).status_code == 401


def test_cada_residente_solo_ve_los_suyos_y_el_admin_todos(client, auth):
    autorizar(client, auth, ANA)
    autorizar(client, auth, LUIS, nombre="Pedro Ruiz", documento="99887766")
    assert [v["nombre"] for v in client.get("/visitantes-autorizados/", headers=auth(ANA)).json()] == ["María Gómez"]
    assert len(client.get("/visitantes-autorizados/?todos=true", headers=auth(ANA)).json()) == 1       # todos=true no sirve a un residente
    assert len(client.get("/visitantes-autorizados/?todos=true", headers=auth(ADM)).json()) == 2


def test_limite_de_20_y_fecha_pasada_rechazada(client, auth):
    for i in range(20):
        autorizar(client, auth, documento=f"DOC{i:05d}", nombre=f"Persona {i:02d}")
    assert client.post("/visitantes-autorizados/", json={**VISITA, "documento": "ZZZ99999"}, headers=auth(ANA)).status_code == 400
    ayer = (date.today() - timedelta(days=2)).isoformat()
    assert client.post("/visitantes-autorizados/", json={**VISITA, "documento": "ZZZ99999", "vigente_hasta": ayer}, headers=auth(LUIS)).status_code == 422


def test_editar_retirar_y_reautorizar(client, auth):
    v = autorizar(client, auth)
    assert client.patch(f"/visitantes-autorizados/{v['id']}", json={"notas": "x"}, headers=auth(LUIS)).status_code == 403
    r = client.patch(f"/visitantes-autorizados/{v['id']}", json={"nombre": "María G. Gómez", "notas": None}, headers=auth(ANA)).json()
    assert r["nombre"] == "María G. Gómez" and r["notas"] is None
    assert client.delete(f"/visitantes-autorizados/{v['id']}", headers=auth(LUIS)).status_code == 403
    assert client.delete(f"/visitantes-autorizados/{v['id']}", headers=auth(ANA)).status_code == 200
    assert client.get("/visitantes-autorizados/", headers=auth(ANA)).json() == []
    assert client.get("/visitantes-autorizados/buscar?q=1020304", headers=auth(CEL)).json() == []      # retirada: ya no aparece
    nuevo = autorizar(client, auth, nombre="María Gómez Nueva")                                        # se reactiva, mismo registro
    assert nuevo["id"] == v["id"] and nuevo["nombre"] == "María Gómez Nueva"


def test_guardia_busca_registra_ingreso_y_salida(client, auth):
    v = autorizar(client, auth)
    assert client.get("/visitantes-autorizados/buscar?q=ab", headers=auth(CEL)).status_code == 422     # mínimo 3 caracteres
    assert client.get("/visitantes-autorizados/buscar?q=maría", headers=auth(ANA)).status_code == 403
    for q in ("maría", "1020304"):
        hallado = client.get("/visitantes-autorizados/buscar", params={"q": q}, headers=auth(CEL)).json()
        assert [h["id"] for h in hallado] == [v["id"]] and hallado[0]["anfitrion_nombre"] == "Ana Residente"
    assert client.get("/visitantes-autorizados/buscar?q=nadie", headers=auth(CEL)).json() == []

    assert client.post(f"/visitantes-autorizados/{v['id']}/ingreso", headers=auth(ANA)).status_code == 403
    ing = client.post(f"/visitantes-autorizados/{v['id']}/ingreso", headers=auth(CEL)).json()
    assert ing["dentro"] is True and ing["acceso_id"]
    assert client.post(f"/visitantes-autorizados/{v['id']}/ingreso", headers=auth(CEL)).status_code == 400   # ya está dentro
    assert client.get("/visitantes-autorizados/", headers=auth(ANA)).json()[0]["dentro"] is True            # la residente lo ve
    dentro = client.get("/visitantes-autorizados/dentro", headers=auth(CEL)).json()
    assert [d["nombre"] for d in dentro] == ["María Gómez"] and dentro[0]["ingreso_registrado_por"] == "Celador Uno"

    sal = client.patch(f"/visitantes-autorizados/accesos/{ing['acceso_id']}/salida", headers=auth(CEL)).json()
    assert sal["fecha_salida"] and sal["salida_registrada_por"] == "Celador Uno"
    assert client.patch(f"/visitantes-autorizados/accesos/{ing['acceso_id']}/salida", headers=auth(CEL)).status_code == 400
    assert client.get("/visitantes-autorizados/dentro", headers=auth(CEL)).json() == []
    assert client.get("/visitantes-autorizados/accesos", headers=auth(ADM)).json()[0]["nombre"] == "María Gómez"


def test_autorizacion_vencida_o_anfitrion_desactivado_no_ingresa(client, auth, db):
    v = autorizar(client, auth)
    db.query(VisitanteAutorizado).update({"vigente_hasta": date.today() - timedelta(days=2)})
    db.commit()   # 2 días de margen: el servidor va en UTC y la app mide en hora de Colombia
    hallado = client.get("/visitantes-autorizados/buscar?q=maría", headers=auth(CEL)).json()[0]
    assert hallado["vigente"] is False
    assert "venció" in client.post(f"/visitantes-autorizados/{v['id']}/ingreso", headers=auth(CEL)).json()["detail"]
    db.query(VisitanteAutorizado).update({"vigente_hasta": None}); db.commit()
    client.patch(f"/usuarios/{id_de(client, auth, ANA)}/activo", params={"esta_activo": False}, headers=auth(ADM))
    assert client.get("/visitantes-autorizados/buscar?q=maría", headers=auth(CEL)).json() == []


# ------------------------------------------------------------ paquetes
def registrar(client, auth, email=ANA, quien=CEL, **extra):
    dest = id_de(client, auth, email)
    r = client.post("/paquetes/", json={"destinatario_id": dest, "tipo": "Paquete", "remitente": "Servientrega", **extra}, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def test_guardia_registra_paquete_y_solo_el_dueno_lo_ve(client, auth):
    p = registrar(client, auth, descripcion="Caja frágil")
    assert p["estado"] == "En porteria" and p["destinatario_nombre"] == "Ana Residente" and p["recibido_por"] == "Celador Uno"
    assert [x["id"] for x in client.get("/paquetes/", headers=auth(ANA)).json()] == [p["id"]]
    assert client.get("/paquetes/", headers=auth(LUIS)).json() == []                   # otro vecino no ve el paquete de Ana
    assert len(client.get("/paquetes/", headers=auth(CEL)).json()) == 1
    assert client.post("/paquetes/", json={"destinatario_id": 1}, headers=auth(ANA)).status_code == 403
    assert client.post("/paquetes/", json={"destinatario_id": id_de(client, auth, CEL)}, headers=auth(CEL)).status_code == 400   # no es residente
    assert client.post("/paquetes/", json={"destinatario_id": 9999}, headers=auth(CEL)).status_code == 400


def test_destinatarios_solo_para_portería_sin_datos_sensibles(client, auth):
    lista = client.get("/paquetes/destinatarios", headers=auth(CEL)).json()
    assert {d["nombre_completo"] for d in lista} == {"Ana Residente", "Luis Residente"}
    assert set(lista[0]) == {"id", "nombre_completo", "apartamento"}
    assert [d["nombre_completo"] for d in client.get("/paquetes/destinatarios?q=202", headers=auth(CEL)).json()] == ["Luis Residente"]
    assert client.get("/paquetes/destinatarios", headers=auth(ANA)).status_code == 403


def test_entregar_y_anular(client, auth):
    p1, p2 = registrar(client, auth), registrar(client, auth, tipo="Correspondencia")
    assert client.patch(f"/paquetes/{p1['id']}/entregar", headers=auth(ANA)).status_code == 403
    e = client.patch(f"/paquetes/{p1['id']}/entregar", json={"entregado_a": "  Pedro   Gómez (hermano) "}, headers=auth(CEL)).json()
    assert e["estado"] == "Entregado" and e["entregado_a"] == "Pedro Gómez (hermano)" and e["entregado_por"] == "Celador Uno" and e["fecha_entrega"]
    assert client.patch(f"/paquetes/{p1['id']}/entregar", headers=auth(CEL)).status_code == 400      # ya entregado
    assert client.patch(f"/paquetes/{p1['id']}/anular", headers=auth(CEL)).status_code == 400
    e2 = client.patch(f"/paquetes/{p2['id']}/entregar", headers=auth(ADM)).json()                    # sin cuerpo: lo recibe el dueño
    assert e2["entregado_a"] == "Ana Residente"
    p3 = registrar(client, auth)
    assert client.patch(f"/paquetes/{p3['id']}/anular", headers=auth(CEL)).json()["estado"] == "Anulado"
    assert client.patch("/paquetes/9999/entregar", headers=auth(CEL)).status_code == 404
    assert [x["id"] for x in client.get("/paquetes/?estado=Entregado", headers=auth(ANA)).json()] == [p2["id"], p1["id"]]


def test_paquetes_quedan_en_la_auditoria(client, auth):
    p = registrar(client, auth)
    client.patch(f"/paquetes/{p['id']}/entregar", headers=auth(CEL))
    log = client.get("/auditoria/?entidad=Paquete", headers=auth(ADM)).json()
    assert [(x["accion"], x["actor"]) for x in log] == [("Entregó paquete", "Celador Uno"), ("Registró paquete", "Celador Uno")]


# ------------------------------------------------------------ emergencias
def test_todos_ven_emergencias_y_solo_admin_edita(client, auth):
    assert client.get("/emergencias/").status_code == 401
    for quien in (ANA, CEL, ADM):
        assert client.get("/emergencias/", headers=auth(quien)).status_code == 200
    nuevo = {"nombre": "Clínica San Rafael", "telefono": "601 234 5678", "categoria": "Salud", "orden": 10}
    for quien in (ANA, CEL):
        assert client.post("/emergencias/", json=nuevo, headers=auth(quien)).status_code == 403
    c = client.post("/emergencias/", json=nuevo, headers=auth(ADM)).json()
    assert client.get("/emergencias/", headers=auth(ANA)).json()[0]["nombre"] == "Clínica San Rafael"   # orden 10 va primero (la BD de pruebas no trae las líneas base)
    assert client.patch(f"/emergencias/{c['id']}", json={"telefono": "+57 300 123 4567"}, headers=auth(ADM)).json()["telefono"] == "+57 300 123 4567"
    assert client.patch(f"/emergencias/{c['id']}", json={"telefono": "abc"}, headers=auth(ADM)).status_code == 422
    assert client.post("/emergencias/", json={**nuevo, "telefono": "12"}, headers=auth(ADM)).status_code == 422
    assert client.delete(f"/emergencias/{c['id']}", headers=auth(CEL)).status_code == 403
    assert client.delete(f"/emergencias/{c['id']}", headers=auth(ADM)).status_code == 200
    assert client.delete(f"/emergencias/{c['id']}", headers=auth(ADM)).status_code == 404
    assert {x["accion"] for x in client.get("/auditoria/?entidad=Emergencia", headers=auth(ADM)).json()} == {
        "Agregó contacto de emergencia", "Editó contacto de emergencia", "Eliminó contacto de emergencia"}
