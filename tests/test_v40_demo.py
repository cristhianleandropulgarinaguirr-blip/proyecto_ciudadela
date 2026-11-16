# tests/test_v40_demo.py — Fase 4: «Solicitar demo» (ruta pública que ESCRIBE en la base: debe ser difícil de abusar).
import pytest
from sqlalchemy import func

from app.models import Notificacion, SolicitudDemo, Usuario

BASE = {"nombre": "Marcela Rojas", "conjunto": "Conjunto Reserva del Sol", "celular": "310 000 0001", "acepto_datos": True}


def _enviar(client, **cambios):
    return client.post("/demo/solicitar", json={**BASE, **cambios})


def _filas(db):
    db.expire_all()
    return db.query(func.count(SolicitudDemo.id)).scalar()


# ------------------------------------------------------------------ enviar
def test_una_solicitud_valida_se_guarda_y_avisa_al_administrador(client, db):
    r = _enviar(client, correo="marcela@ejemplo.com", ciudad="Facatativá", apartamentos=120, mensaje="Quiero ver la portería")
    assert r.status_code == 201 and r.json()["ok"] is True and r.headers["cache-control"] == "no-store"
    s = db.query(SolicitudDemo).one()
    assert (s.nombre, s.conjunto, s.celular, s.correo, s.ciudad, s.apartamentos, s.estado, s.origen) == \
           ("Marcela Rojas", "Conjunto Reserva del Sol", "3100000001", "marcela@ejemplo.com", "Facatativá", 120, "Nueva", "formulario")
    assert s.acepto_datos is not None
    admin = db.query(Usuario).filter(Usuario.email == "admin@conjunto.com").one()
    avisos = db.query(Notificacion).filter(Notificacion.usuario_id == admin.id).all()
    assert len(avisos) == 1 and "demo" in avisos[0].titulo.lower() and avisos[0].enlace == "#/demos"
    assert "Conjunto Reserva del Sol" in avisos[0].mensaje


def test_solo_el_administrador_recibe_el_aviso(client, db):
    _enviar(client)
    otros = db.query(Notificacion).join(Usuario, Usuario.id == Notificacion.usuario_id).filter(Usuario.email != "admin@conjunto.com").count()
    assert otros == 0


def test_los_campos_opcionales_pueden_ir_vacios(client, db):
    r = _enviar(client, correo="", ciudad="", mensaje="", apartamentos=None)
    assert r.status_code == 201
    s = db.query(SolicitudDemo).one()
    assert s.correo is None and s.ciudad is None and s.mensaje is None and s.apartamentos is None


@pytest.mark.parametrize("crudo", ["310 000 0001", "310-000-0001", "+57 310 000 0001", "573100000001", "(310) 000 0001"])
def test_el_celular_se_normaliza_a_10_digitos(client, db, crudo):
    assert _enviar(client, celular=crudo).status_code == 201
    assert db.query(SolicitudDemo).one().celular == "3100000001"


@pytest.mark.parametrize("celular", ["", "12345", "2100000001", "310 000 000", "310 000 00011", "abcdefghij", "6011234567"])
def test_un_celular_invalido_se_rechaza(client, db, celular):
    assert _enviar(client, celular=celular).status_code == 422
    assert _filas(db) == 0


def test_sin_autorizar_el_tratamiento_de_datos_no_se_guarda_nada(client, db):
    assert _enviar(client, acepto_datos=False).status_code == 422
    body = {k: v for k, v in BASE.items() if k != "acepto_datos"}
    assert client.post("/demo/solicitar", json=body).status_code == 422
    assert _filas(db) == 0


@pytest.mark.parametrize("cambios", [{"nombre": "A"}, {"nombre": "   "}, {"conjunto": ""}, {"correo": "no-es-correo"}, {"apartamentos": 0}, {"apartamentos": 5001},
                                      {"mensaje": "x" * 501}, {"origen": "otro"}, {"nombre": "x" * 81}])
def test_datos_fuera_de_rango_se_rechazan(client, db, cambios):
    assert _enviar(client, **cambios).status_code == 422
    assert _filas(db) == 0


def test_los_espacios_y_saltos_de_linea_se_limpian(client, db):
    _enviar(client, nombre="  Marcela \n  Rojas ", mensaje="Hola\n\n   quiero   verla")
    s = db.query(SolicitudDemo).one()
    assert s.nombre == "Marcela Rojas" and s.mensaje == "Hola quiero verla"


def test_el_campo_trampa_de_robots_responde_ok_pero_no_guarda_ni_avisa(client, db):
    r = _enviar(client, sitio_web="http://spam.example")
    assert r.status_code == 201 and r.json()["ok"] is True          # el robot no debe enterarse de que lo descubrimos
    assert _filas(db) == 0 and db.query(Notificacion).count() == 0


def test_el_mismo_celular_no_se_duplica_en_24_horas_ni_avisa_dos_veces(client, db):
    assert _enviar(client).status_code == 201
    assert _enviar(client, nombre="Otra Persona", conjunto="Otro Conjunto").status_code == 201
    assert _filas(db) == 1 and db.query(Notificacion).count() == 1
    assert _enviar(client, celular="310 000 0002").status_code == 201
    assert _filas(db) == 2


def test_una_solicitud_descartada_permite_volver_a_pedir(client, db):
    _enviar(client)
    s = db.query(SolicitudDemo).one()
    s.estado = "Descartada"
    db.commit()
    assert _enviar(client).status_code == 201 and _filas(db) == 2


def test_tope_de_envios_por_conexion(client, db):
    codigos = [_enviar(client, celular=f"31000000{n:02d}").status_code for n in range(7)]
    assert codigos[:5] == [201] * 5 and codigos[5:] == [429, 429]
    assert _filas(db) == 5


def test_el_envio_whatsapp_se_guarda_marcado(client, db):
    assert _enviar(client, origen="whatsapp").status_code == 201
    s = db.query(SolicitudDemo).one()
    assert s.origen == "whatsapp"
    admin_aviso = db.query(Notificacion).one()
    assert "WhatsApp" in admin_aviso.mensaje


def test_no_se_guarda_la_ip_ni_datos_del_dispositivo():
    columnas = {c.name for c in SolicitudDemo.__table__.columns}
    assert not (columnas & {"ip", "ip_cliente", "user_agent", "agente", "dispositivo", "huella"})


# ------------------------------------------------------------------ administrar
def test_solo_el_administrador_ve_las_solicitudes(client, db, auth):
    _enviar(client)
    assert client.get("/demo/solicitudes").status_code == 401
    assert client.get("/demo/solicitudes", headers=auth("ana@conjunto.com")).status_code == 403
    assert client.get("/demo/solicitudes", headers=auth("celador@conjunto.com")).status_code == 403
    r = client.get("/demo/solicitudes", headers=auth("admin@conjunto.com"))
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["celular"] == "3100000001" and "acepto_datos" not in r.json()[0]


def test_las_mas_recientes_primero_y_filtro_por_estado(client, db, auth):
    for n in range(3):
        _enviar(client, celular=f"31000000{n:02d}", conjunto=f"Conjunto {n}")
    h = auth("admin@conjunto.com")
    nombres = [s["conjunto"] for s in client.get("/demo/solicitudes", headers=h).json()]
    assert nombres == ["Conjunto 2", "Conjunto 1", "Conjunto 0"]
    primero = client.get("/demo/solicitudes", headers=h).json()[0]["id"]
    client.patch(f"/demo/solicitudes/{primero}", json={"estado": "Contactada"}, headers=h)
    assert [s["id"] for s in client.get("/demo/solicitudes?estado=Contactada", headers=h).json()] == [primero]
    assert len(client.get("/demo/solicitudes?estado=Nueva", headers=h).json()) == 2
    assert client.get("/demo/solicitudes?estado=Inventado", headers=h).status_code == 422


def test_actualizar_estado_y_nota_queda_en_la_auditoria(client, db, auth):
    from app.models import Auditoria
    _enviar(client)
    h = auth("admin@conjunto.com")
    sid = client.get("/demo/solicitudes", headers=h).json()[0]["id"]
    r = client.patch(f"/demo/solicitudes/{sid}", json={"estado": "Agendada", "nota": "  Demo el martes 3 p. m.  "}, headers=h)
    assert r.status_code == 200 and r.json()["estado"] == "Agendada" and r.json()["nota"] == "Demo el martes 3 p. m."
    a = db.query(Auditoria).filter(Auditoria.entidad == "Demo").one()
    assert "Agendada" in a.detalle and "Conjunto Reserva del Sol" in a.detalle
    # sin cambios reales no se llena la auditoría
    client.patch(f"/demo/solicitudes/{sid}", json={"estado": "Agendada"}, headers=h)
    assert db.query(Auditoria).filter(Auditoria.entidad == "Demo").count() == 1


def test_la_nota_se_puede_borrar_y_un_estado_inventado_se_rechaza(client, db, auth):
    _enviar(client)
    h = auth("admin@conjunto.com")
    sid = client.get("/demo/solicitudes", headers=h).json()[0]["id"]
    client.patch(f"/demo/solicitudes/{sid}", json={"nota": "algo"}, headers=h)
    assert client.patch(f"/demo/solicitudes/{sid}", json={"nota": None}, headers=h).json()["nota"] is None
    assert client.patch(f"/demo/solicitudes/{sid}", json={"estado": "Vendida"}, headers=h).status_code == 422
    assert client.patch("/demo/solicitudes/999", json={"estado": "Contactada"}, headers=h).status_code == 404
    assert client.patch(f"/demo/solicitudes/{sid}", json={"estado": "Contactada"}, headers=auth("ana@conjunto.com")).status_code == 403
