# tests/test_arrendamientos.py — Rol Inquilino: registro por el propietario, aprobación, permisos acotados, mora heredada y vencimiento.
from datetime import datetime, timedelta

import pytest

from app import arrendamientos as reglas
from app.models import Arrendamiento, CodigoQR, Documento, Notificacion, Paquete, Usuario, VisitanteAutorizado

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
MARTA = "marta@correo.com"
CLAVE = "claveSegura123"
FUTURO = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%dT14:00:00")
HOY = reglas.ahora_local().date()


def contrato(client, h, email=MARTA, nombre="Marta Rojas", dias=365, **extra):
    cuerpo = {"nombre_completo": nombre, "email": email, "fecha_inicio": str(HOY), "fecha_fin": str(HOY + timedelta(days=dias)), **extra}
    return client.post("/arrendamientos/", json=cuerpo, headers=h)


def inquilino_activo(client, auth, db, propietario=ANA, email=MARTA):
    """Ana registra, el administrador aprueba y la inquilina entra con la clave temporal (que cambia por una conocida)."""
    r = contrato(client, auth(propietario), email=email)
    assert r.status_code == 201, r.text
    a = client.post(f"/arrendamientos/{r.json()['id']}/aprobar", headers=auth(ADM))
    assert a.status_code == 200, a.text
    temporal = a.json()["password_temporal"]
    login = client.post("/auth/login", data={"username": email, "password": temporal})
    assert login.status_code == 200, login.text
    u = db.query(Usuario).filter(Usuario.email == email).one()
    from app.security import encriptar_password
    u.password_encriptada, u.debe_cambiar_password = encriptar_password(CLAVE), False
    db.commit()
    return r.json()["id"], auth(email)


# ---------------------------------------------------------------- registro y aprobación
def test_el_inquilino_no_entra_hasta_que_el_administrador_aprueba(client, auth, db):
    r = contrato(client, auth(ANA))
    assert r.status_code == 201
    c = r.json()
    assert c["estado"] == "Pendiente" and c["apartamento"] == "Torre 1 Apt 101" and c["propietario_nombre"] == "Ana Residente"
    # Pendiente: no puede iniciar sesión, ni siquiera adivinando una clave
    p = client.post("/auth/login", data={"username": MARTA, "password": CLAVE})
    assert p.status_code == 401 or "pendiente" in p.json()["detail"].lower()
    assert not db.query(Usuario).filter(Usuario.email == MARTA).one().esta_activo
    a = client.post(f"/arrendamientos/{c['id']}/aprobar", headers=auth(ADM))
    assert a.status_code == 200 and a.json()["arrendamiento"]["estado"] == "Activo" and len(a.json()["password_temporal"]) >= 10
    ok = client.post("/auth/login", data={"username": MARTA, "password": a.json()["password_temporal"]})
    assert ok.status_code == 200 and ok.json()["rol"] == "Inquilino" and ok.json()["debe_cambiar_password"] is True


def test_login_pendiente_avisa_que_espera_aprobacion(client, auth, db):
    contrato(client, auth(ANA))
    from app.security import encriptar_password
    u = db.query(Usuario).filter(Usuario.email == MARTA).one()
    u.password_encriptada = encriptar_password(CLAVE)       # solo para ver el mensaje de acceso pendiente
    db.commit()
    r = client.post("/auth/login", data={"username": MARTA, "password": CLAVE})
    assert r.status_code == 403 and "pendiente" in r.json()["detail"].lower()


def test_solo_el_administrador_aprueba_y_rechaza(client, auth):
    cid = contrato(client, auth(ANA)).json()["id"]
    for quien in (ANA, LUIS, CEL):
        assert client.post(f"/arrendamientos/{cid}/aprobar", headers=auth(quien)).status_code == 403
        assert client.post(f"/arrendamientos/{cid}/rechazar", headers=auth(quien)).status_code == 403
    r = client.post(f"/arrendamientos/{cid}/rechazar", json={"motivo": "Documentos incompletos"}, headers=auth(ADM))
    assert r.status_code == 200 and r.json()["estado"] == "Rechazado" and r.json()["motivo_cierre"] == "Documentos incompletos"
    assert client.post(f"/arrendamientos/{cid}/aprobar", headers=auth(ADM)).status_code == 400   # ya no está pendiente


def test_validaciones_del_registro(client, auth):
    h = auth(ANA)
    assert contrato(client, h, dias=-1).status_code == 400                                    # fin antes del inicio
    assert client.post("/arrendamientos/", json={"nombre_completo": "Marta Rojas", "email": MARTA, "fecha_inicio": str(HOY - timedelta(days=40)),
                                                 "fecha_fin": str(HOY - timedelta(days=5))}, headers=h).status_code == 400   # ya venció
    assert contrato(client, h, dias=365 * 6).status_code == 400                               # más de 5 años
    assert contrato(client, h, email=LUIS).status_code == 400                                 # correo ya usado
    for i in range(3):
        assert contrato(client, h, email=f"inq{i}@correo.com", nombre=f"Inquilino {i}").status_code == 201
    assert contrato(client, h, email="inq9@correo.com", nombre="Inquilino 9").status_code == 400   # máximo 3 abiertos


def test_propietario_ve_solo_sus_contratos_y_el_admin_todos(client, auth):
    contrato(client, auth(ANA))
    contrato(client, auth(LUIS), email="otro@correo.com", nombre="Otro Inquilino")
    assert [c["inquilino_email"] for c in client.get("/arrendamientos/", headers=auth(ANA)).json()] == [MARTA]
    assert len(client.get("/arrendamientos/", headers=auth(ADM)).json()) == 2
    assert client.get("/arrendamientos/", headers=auth(CEL)).status_code == 403


def test_el_admin_no_puede_crear_un_inquilino_sin_contrato(client, auth):
    r = client.post("/usuarios/", json={"nombre_completo": "Sin Contrato", "email": "sc@correo.com", "password": CLAVE, "rol": "Inquilino"}, headers=auth(ADM))
    assert r.status_code == 400


def test_el_admin_registra_un_contrato_a_nombre_del_propietario(client, auth, db):
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    assert contrato(client, auth(ADM)).status_code == 400                                      # falta propietario_id
    r = contrato(client, auth(ADM), propietario_id=ana.id)
    assert r.status_code == 201 and r.json()["propietario_id"] == ana.id


# ---------------------------------------------------------------- permisos acotados
def test_matriz_de_permisos_del_inquilino(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    yo = client.get("/usuarios/me", headers=h).json()
    # NO: cartera, votaciones, comercio propio, usuarios, auditoría, gestionar inquilinos, portería
    assert client.get("/votaciones/", headers=h).status_code == 403
    assert client.get("/votaciones/pendientes", headers=h).status_code == 403
    assert client.get("/administracion/mis-pagos", headers=h).status_code == 403
    assert client.get(f"/administracion/estado-cuenta/{yo['id']}", headers=h).status_code == 403
    assert client.get(f"/reportes/estado-cuenta/{yo['id']}.pdf", headers=h).status_code == 403
    assert client.get("/comercio/mios", headers=h).status_code == 403
    assert client.get("/usuarios/", headers=h).status_code == 403
    assert client.get("/auditoria/", headers=h).status_code == 403
    assert contrato(client, h, email="x@correo.com").status_code == 403
    assert client.get("/arrendamientos/", headers=h).status_code == 403
    assert client.get("/porteria/vehiculos-dentro", headers=h).status_code == 403
    # SÍ: reservas, daños, PQRS, visitas, paquetes, cartelera, emergencias, documentos, su contrato
    assert client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=h).status_code == 201
    assert client.post("/pqrs/", json={"tipo": "Sugerencia", "asunto": "Más luz en el parque", "descripcion": "Propongo poner más luces en el parque infantil."}, headers=h).status_code == 201
    assert client.post("/qr/visitantes", json={"nombre_visitante": "Carlos Pérez", "placa": "XYZ123"}, headers=h).status_code == 201
    for ruta in ("/paquetes/", "/anuncios/", "/emergencias/", "/documentos/", "/pqrs/", "/reservas/mis-reservas", "/visitantes-autorizados/"):
        assert client.get(ruta, headers=h).status_code == 200, ruta
    m = client.get("/arrendamientos/mio", headers=h).json()
    assert m["propietario_nombre"] == "Ana Residente" and m["estado"] == "Activo" and m["dias_restantes"] >= 364


def test_el_inquilino_solo_ve_reglamento_y_circulares(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    ids = {}
    for cat in ("Reglamento", "Circular", "Acta", "Financiero", "Otros"):
        d = Documento(titulo=f"Doc {cat}", categoria=cat, archivo=f"{cat}.pdf", nombre_original=f"{cat}.pdf", tamano=10)
        db.add(d)
        db.flush()
        ids[cat] = d.id
    db.commit()
    assert {d["categoria"] for d in client.get("/documentos/", headers=h).json()} == {"Reglamento", "Circular"}
    assert {d["categoria"] for d in client.get("/documentos/", headers=auth(ANA)).json()} == {"Reglamento", "Circular", "Acta", "Financiero", "Otros"}
    assert client.get(f"/documentos/{ids['Financiero']}/descargar", headers=h).status_code == 404   # ni por la URL directa
    assert client.get(f"/documentos/{ids['Acta']}/descargar", headers=h).status_code == 404


def test_el_inquilino_tiene_tope_de_visitas(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    for i in range(5):
        assert client.post("/qr/visitantes", json={"nombre_visitante": f"Visita Número {i}", "placa": f"AAA10{i}"}, headers=h).status_code == 201
    r = client.post("/qr/visitantes", json={"nombre_visitante": "Una Más", "placa": "BBB123"}, headers=h)
    assert r.status_code == 400 and "5" in r.json()["detail"]
    for i in range(5):
        assert client.post("/visitantes-autorizados/", json={"nombre": f"Persona Número {i}", "documento": f"10203040{i}0"}, headers=h).status_code == 201
    assert client.post("/visitantes-autorizados/", json={"nombre": "Persona Extra", "documento": "5555555555"}, headers=h).status_code == 400
    # el propietario conserva sus topes normales (10 pases)
    for i in range(6):
        assert client.post("/qr/visitantes", json={"nombre_visitante": f"Visita Dueña {i}", "placa": f"CCC10{i}"}, headers=auth(ANA)).status_code == 201


# ---------------------------------------------------------------- paquetes: privacidad
def test_paquetes_del_inquilino_son_solo_suyos(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    ids = {r["nombre_completo"]: r["id"] for r in client.get("/paquetes/destinatarios", headers=auth(CEL)).json()}
    assert "Marta Rojas" in ids                                      # portería puede elegirla como destinataria
    client.post("/paquetes/", json={"destinatario_id": ids["Marta Rojas"], "remitente": "Rappi"}, headers=auth(CEL))
    client.post("/paquetes/", json={"destinatario_id": ids["Ana Residente"], "remitente": "Amazon"}, headers=auth(CEL))
    mios = client.get("/paquetes/", headers=h).json()
    assert [p["remitente"] for p in mios] == ["Rappi"]               # no ve el paquete de Ana (apartamento ajeno... y del propietario)
    assert [p["remitente"] for p in client.get("/paquetes/", headers=auth(ANA)).json()] == ["Amazon"]
    ajeno = db.query(Paquete).filter(Paquete.remitente == "Amazon").one()
    assert client.get(f"/paquetes/{ajeno.id}/foto", headers=h).status_code == 403


# ---------------------------------------------------------------- mora heredada y avisos
def test_la_mora_del_propietario_bloquea_las_reservas_del_inquilino(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    ana.esta_al_dia = False
    db.commit()
    r = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=h)
    assert r.status_code == 403 and "mora" in r.json()["detail"]
    ana.esta_al_dia = True
    db.commit()
    assert client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=h).status_code == 201


def test_el_propietario_se_entera_de_lo_que_hace_su_inquilino(client, auth, db):
    _, h = inquilino_activo(client, auth, db)
    client.post("/reservas/registrar", json={"zona_comun": "Zona BBQ", "fecha_reserva": FUTURO}, headers=h)
    client.post("/mantenimiento/reportar-danio", data={"titulo": "Gotera en el pasillo", "descripcion": "Hay una gotera en el pasillo del piso 2."}, headers=h)
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    titulos = [n.titulo for n in db.query(Notificacion).filter(Notificacion.usuario_id == ana.id).all()]
    assert any("pidió una reserva" in t for t in titulos) and any("reportó un daño" in t for t in titulos)


# ---------------------------------------------------------------- cierre del acceso
def test_el_propietario_termina_el_contrato_y_el_acceso_se_cierra_al_instante(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    client.post("/qr/visitantes", json={"nombre_visitante": "Carlos Pérez", "placa": "XYZ123"}, headers=h)
    client.post("/visitantes-autorizados/", json={"nombre": "María Gómez", "documento": "1020304050"}, headers=h)
    assert client.get("/usuarios/me", headers=h).status_code == 200
    r = client.post(f"/arrendamientos/{cid}/finalizar", json={"motivo": "Se mudó"}, headers=auth(ANA))
    assert r.status_code == 200 and r.json()["estado"] == "Finalizado"
    assert client.get("/usuarios/me", headers=h).status_code == 401                              # el token ya no sirve
    assert client.post("/auth/login", data={"username": MARTA, "password": CLAVE}).status_code == 403
    inq = db.query(Usuario).filter(Usuario.email == MARTA).one()
    assert not inq.esta_activo
    assert all(c.estado == "Revocado" for c in db.query(CodigoQR).filter(CodigoQR.usuario_id == inq.id, CodigoQR.tipo == "Visitante"))
    assert not db.query(VisitanteAutorizado).filter(VisitanteAutorizado.usuario_id == inq.id, VisitanteAutorizado.activo.is_(True)).count()
    assert client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(ANA)).status_code == 400   # ya estaba cerrado


def test_solo_el_propietario_del_contrato_o_el_admin_lo_cierran(client, auth, db):
    cid, _ = inquilino_activo(client, auth, db)
    assert client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(LUIS)).status_code == 403
    assert client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(CEL)).status_code == 403
    assert client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(ADM)).status_code == 200


def test_cancelar_un_contrato_pendiente_lo_deja_rechazado(client, auth):
    cid = contrato(client, auth(ANA)).json()["id"]
    r = client.post(f"/arrendamientos/{cid}/finalizar", headers=auth(ANA))
    assert r.status_code == 200 and r.json()["estado"] == "Rechazado"


def test_el_contrato_vencido_cierra_el_acceso_solo(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    c = db.get(Arrendamiento, cid)
    c.fecha_fin = reglas.ahora_local() - timedelta(minutes=1)         # venció hace un instante
    db.commit()
    assert client.get("/usuarios/me", headers=h).status_code == 401
    db.expire_all()
    assert db.get(Arrendamiento, cid).estado == "Finalizado" and "fecha de fin" in db.get(Arrendamiento, cid).motivo_cierre
    assert not db.query(Usuario).filter(Usuario.email == MARTA).one().esta_activo
    r = client.post("/auth/login", data={"username": MARTA, "password": CLAVE})
    assert r.status_code == 403


def test_listar_cierra_los_contratos_vencidos_aunque_nadie_inicie_sesion(client, auth, db):
    cid, _ = inquilino_activo(client, auth, db)
    db.get(Arrendamiento, cid).fecha_fin = reglas.ahora_local() - timedelta(days=1)
    db.commit()
    lista = client.get("/arrendamientos/", headers=auth(ANA)).json()
    assert lista[0]["estado"] == "Finalizado"
    db.expire_all()
    assert not db.query(Usuario).filter(Usuario.email == MARTA).one().esta_activo


def test_ultimo_dia_del_contrato_aun_tiene_acceso(client, auth, db):
    cid, h = inquilino_activo(client, auth, db)
    c = db.get(Arrendamiento, cid)
    c.fecha_fin = datetime.combine(reglas.ahora_local().date(), datetime.max.time().replace(microsecond=0))   # hoy a las 23:59:59
    db.commit()
    assert client.get("/usuarios/me", headers=h).status_code == 200


def test_titular_de_un_inquilino_es_el_propietario(db, client, auth):
    inquilino_activo(client, auth, db)
    inq = db.query(Usuario).filter(Usuario.email == MARTA).one()
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    assert reglas.titular_de(db, inq).id == ana.id and reglas.titular_de(db, ana).id == ana.id
