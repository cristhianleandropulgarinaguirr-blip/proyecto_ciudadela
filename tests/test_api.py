# tests/test_api.py
import io
from datetime import datetime, timedelta

import jwt
from PIL import Image

from app.config import ALGORITHM
from app.models import Usuario
from app.security import SECRET_KEY, encriptar_password, es_hash_antiguo, verificar_password
from tests.conftest import CLAVE

FUTURO = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%dT14:00:00")


def png_bytes(formato="PNG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buf, format=formato)
    return buf.getvalue()


def id_de(db, email: str) -> int:
    return db.query(Usuario).filter(Usuario.email == email).one().id


# ---------- Autenticación ----------
def test_login_correcto_devuelve_token_y_rol(client):
    r = client.post("/auth/login", data={"username": "ana@conjunto.com", "password": CLAVE})
    assert r.status_code == 200
    assert r.json()["rol"] == "Residente" and r.json()["token_type"] == "bearer"


def test_login_incorrecto_da_401(client):
    assert client.post("/auth/login", data={"username": "ana@conjunto.com", "password": "mala"}).status_code == 401
    assert client.post("/auth/login", data={"username": "nadie@x.com", "password": CLAVE}).status_code == 401


def test_password_se_guarda_con_bcrypt(db):
    hash_ = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one().password_encriptada
    assert hash_.startswith("$2") and hash_ != CLAVE


def test_registro_publico_esta_cerrado_solo_el_admin_crea_cuentas(client, auth):
    cuerpo = {"nombre_completo": "Intruso", "email": "x@x.com", "password": "claveSegura123", "rol": "Administrador"}
    assert client.post("/auth/registrar", json=cuerpo).status_code in (404, 405)       # ya no existe
    assert client.post("/usuarios/", json=cuerpo).status_code == 401                   # sin token
    assert client.post("/usuarios/", json=cuerpo, headers=auth("ana@conjunto.com")).status_code == 403   # residente
    r = client.post("/usuarios/", json=cuerpo, headers=auth("admin@conjunto.com"))
    assert r.status_code == 201 and "password_encriptada" not in r.text and "claveSegura123" not in r.text


def test_hash_antiguo_sha256_se_actualiza_a_bcrypt_al_iniciar_sesion(client, db):
    import hashlib
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    ana.password_encriptada = hashlib.sha256(CLAVE.encode()).hexdigest()
    db.commit()
    assert es_hash_antiguo(ana.password_encriptada)
    assert client.post("/auth/login", data={"username": "ana@conjunto.com", "password": CLAVE}).status_code == 200
    db.refresh(ana)
    assert ana.password_encriptada.startswith("$2") and verificar_password(CLAVE, ana.password_encriptada)


# ---------- 401 / 403 ----------
def test_sin_token_da_401(client):
    for ruta in ["/usuarios/me", "/reservas/listar", "/porteria/vehiculos-dentro", "/mantenimiento/listar-danios"]:
        assert client.get(ruta).status_code == 401, ruta


def test_token_falso_o_manipulado_da_401(client):
    falso = jwt.encode({"usuario_id": 1, "exp": datetime.now() + timedelta(hours=1)}, "otra-clave-cualquiera-de-32-caracteres!!", algorithm=ALGORITHM)
    assert client.get("/usuarios/me", headers={"Authorization": f"Bearer {falso}"}).status_code == 401
    assert client.get("/usuarios/me", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_token_expirado_da_401(client):
    viejo = jwt.encode({"usuario_id": 1, "exp": datetime.now() - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM)
    assert client.get("/usuarios/me", headers={"Authorization": f"Bearer {viejo}"}).status_code == 401


def test_residente_no_puede_usar_rutas_de_admin_ni_porteria_da_403(client, auth):
    h = auth("ana@conjunto.com")
    assert client.get("/usuarios/", headers=h).status_code == 403
    assert client.patch("/reservas/cambiar-estado/1?nuevo_estado=Aprobada", headers=h).status_code == 403
    assert client.post("/porteria/vehiculo-ingreso?placa=ABC123&apartamento=T1", headers=h).status_code == 403


def test_guardia_no_puede_reservar_ni_ver_usuarios(client, auth):
    h = auth("celador@conjunto.com")
    assert client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=h).status_code == 403
    assert client.get("/usuarios/", headers=h).status_code == 403


def test_usuario_desactivado_pierde_acceso_aunque_tenga_token(client, auth, db):
    h = auth("ana@conjunto.com")
    assert client.get("/usuarios/me", headers=h).status_code == 200
    ana = db.query(Usuario).filter(Usuario.email == "ana@conjunto.com").one()
    ana.esta_activo = False
    db.commit()
    assert client.get("/usuarios/me", headers=h).status_code == 401


def test_admin_crea_guardia(client, auth):
    h = auth("admin@conjunto.com")
    r = client.post("/usuarios/", headers=h, json={"nombre_completo": "Nuevo Guardia", "email": "g2@conjunto.com",
                                                    "password": "claveSegura123", "rol": "Guardia"})
    assert r.status_code == 201 and r.json()["rol"] == "Guardia"


# ---------- Reservas ----------
def test_flujo_de_reservas_y_doble_reserva(client, auth):
    ana, luis, admin = auth("ana@conjunto.com"), auth("luis@conjunto.com"), auth("admin@conjunto.com")
    r = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=ana)
    assert r.status_code == 201 and r.json()["estado"] == "Pendiente"
    rid = r.json()["id"]
    assert client.patch(f"/reservas/cambiar-estado/{rid}?nuevo_estado=Aprobada", headers=admin).status_code == 200
    # Otro residente intenta el mismo salón el mismo día -> rechazado
    r2 = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=luis)
    assert r2.status_code == 400
    # Cada residente solo ve las suyas
    assert len(client.get("/reservas/mis-reservas", headers=ana).json()) == 1
    assert client.get("/reservas/mis-reservas", headers=luis).json() == []


def test_estado_de_reserva_invalido_da_422(client, auth):
    assert client.patch("/reservas/cambiar-estado/1?nuevo_estado=Inventado", headers=auth("admin@conjunto.com")).status_code == 422


def test_reserva_en_el_pasado_da_422(client, auth):
    r = client.post("/reservas/registrar", json={"zona_comun": "Zona BBQ", "fecha_reserva": "2020-01-01T10:00:00"}, headers=auth("ana@conjunto.com"))
    assert r.status_code == 422


def test_residente_no_puede_cancelar_reserva_ajena(client, auth):
    ana, luis = auth("ana@conjunto.com"), auth("luis@conjunto.com")
    rid = client.post("/reservas/registrar", json={"zona_comun": "Zona BBQ", "fecha_reserva": FUTURO}, headers=ana).json()["id"]
    assert client.patch(f"/reservas/{rid}/cancelar", headers=luis).status_code == 403
    assert client.patch(f"/reservas/{rid}/cancelar", headers=ana).json()["estado"] == "Cancelada"


# ---------- Mora y pagos ----------
def test_mora_bloquea_reservas_y_el_pago_las_habilita(client, auth, db):
    admin, ana = auth("admin@conjunto.com"), auth("ana@conjunto.com")
    uid = id_de(db, "ana@conjunto.com")
    assert client.patch(f"/administracion/registrar-deuda/{uid}?saldo_pendiente=300000", headers=admin).json()["esta_al_dia"] is False
    reserva = {"zona_comun": "Zona BBQ", "fecha_reserva": FUTURO}
    assert client.post("/reservas/registrar", json=reserva, headers=ana).status_code == 403

    r = client.post("/administracion/simular-pago-pasarela?valor_pagado=100000", headers=ana).json()
    assert r["saldo_pendiente"] == 200000 and r["esta_al_dia"] is False       # pago parcial: sigue en mora
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=999999", headers=ana).status_code == 400  # excede
    assert client.post("/administracion/simular-pago-pasarela?valor_pagado=-5", headers=ana).status_code == 422     # negativo
    r = client.post("/administracion/simular-pago-pasarela?valor_pagado=200000", headers=ana).json()
    assert r["esta_al_dia"] is True
    assert client.post("/reservas/registrar", json=reserva, headers=ana).status_code == 201


def test_estado_de_cuenta_solo_propio_o_admin(client, auth, db):
    ana, admin = auth("ana@conjunto.com"), auth("admin@conjunto.com")
    luis_id = id_de(db, "luis@conjunto.com")
    assert client.get(f"/administracion/estado-cuenta/{luis_id}", headers=ana).status_code == 403
    assert client.get(f"/administracion/estado-cuenta/{luis_id}", headers=admin).status_code == 200


# ---------- Daños y archivos ----------
def test_subida_de_foto_valida_y_acceso_restringido(client, auth, db):
    ana, luis, admin = auth("ana@conjunto.com"), auth("luis@conjunto.com"), auth("admin@conjunto.com")
    datos = {"titulo": "Ascensor trabado", "descripcion": "Se detiene entre el piso 4 y 5"}
    r = client.post("/mantenimiento/reportar-danio", data=datos, headers=ana,
                    files={"archivo_foto": ("mi foto ../../x.png", png_bytes(), "image/png")})
    assert r.status_code == 201
    foto = r.json()["foto_url"]
    assert foto.endswith(".png") and "/" not in foto and "x.png" not in foto   # nombre aleatorio, sin path traversal
    rid = r.json()["id"]
    assert client.get(f"/mantenimiento/danios/{rid}/foto", headers=ana).status_code == 200
    assert client.get(f"/mantenimiento/danios/{rid}/foto", headers=admin).status_code == 200
    assert client.get(f"/mantenimiento/danios/{rid}/foto", headers=luis).status_code == 403
    assert client.get(f"/mantenimiento/danios/{rid}/foto").status_code == 401


def test_archivo_que_no_es_imagen_se_rechaza(client, auth):
    h = auth("ana@conjunto.com")
    datos = {"titulo": "Ascensor trabado", "descripcion": "Se detiene entre el piso 4 y 5"}
    # Texto/ejecutable disfrazado de imagen
    r = client.post("/mantenimiento/reportar-danio", data=datos, headers=h,
                    files={"archivo_foto": ("virus.png", b"MZ\x90\x00 esto no es una imagen", "image/png")})
    assert r.status_code == 400
    # Tipo MIME no permitido
    r = client.post("/mantenimiento/reportar-danio", data=datos, headers=h,
                    files={"archivo_foto": ("doc.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 400


def test_imagen_demasiado_grande_da_413(client, auth, monkeypatch):
    import app.archivos as archivos
    monkeypatch.setattr(archivos, "MAX_UPLOAD_MB", 0)  # límite de 0 MB para forzar el error
    r = client.post("/mantenimiento/reportar-danio", headers=auth("ana@conjunto.com"),
                    data={"titulo": "Ascensor trabado", "descripcion": "Se detiene entre el piso 4 y 5"},
                    files={"archivo_foto": ("a.png", png_bytes(), "image/png")})
    assert r.status_code == 413


def test_reporte_sin_foto_y_visibilidad_por_rol(client, auth):
    ana, luis, admin = auth("ana@conjunto.com"), auth("luis@conjunto.com"), auth("admin@conjunto.com")
    datos = {"titulo": "Bombillo dañado", "descripcion": "Pasillo del piso 3 sin luz desde ayer"}
    assert client.post("/mantenimiento/reportar-danio", data=datos, headers=ana).status_code == 201
    assert len(client.get("/mantenimiento/listar-danios", headers=ana).json()) == 1
    assert client.get("/mantenimiento/listar-danios", headers=luis).json() == []
    assert len(client.get("/mantenimiento/listar-danios", headers=admin).json()) == 1


def test_solo_admin_cambia_estado_de_danio(client, auth):
    ana, admin = auth("ana@conjunto.com"), auth("admin@conjunto.com")
    rid = client.post("/mantenimiento/reportar-danio", headers=ana,
                      data={"titulo": "Bombillo dañado", "descripcion": "Pasillo del piso 3 sin luz"}).json()["id"]
    assert client.patch(f"/mantenimiento/cambiar-estado/{rid}?nuevo_estado=Solucionado", headers=ana).status_code == 403
    assert client.patch(f"/mantenimiento/cambiar-estado/{rid}?nuevo_estado=Solucionado", headers=admin).json()["estado"] == "Solucionado"


# ---------- Portería ----------
def test_porteria_ingreso_salida_y_validaciones(client, auth):
    g = auth("celador@conjunto.com")
    r = client.post("/porteria/vehiculo-ingreso?placa=xyz123&apartamento=Torre 1 Apt 101", headers=g)
    assert r.status_code == 201 and r.json()["placa"] == "XYZ123"
    vid = r.json()["id"]
    assert client.post("/porteria/vehiculo-ingreso?placa=XYZ123&apartamento=Torre 1", headers=g).status_code == 400  # ya está dentro
    assert client.post("/porteria/vehiculo-ingreso?placa=PLACA-MALA&apartamento=Torre 1", headers=g).status_code == 422
    assert len(client.get("/porteria/vehiculos-dentro", headers=g).json()) == 1
    assert client.patch(f"/porteria/vehiculo-salida/{vid}", headers=g).status_code == 200
    assert client.patch(f"/porteria/vehiculo-salida/{vid}", headers=g).status_code == 400  # ya salió
    assert client.get("/porteria/vehiculos-dentro", headers=g).json() == []


# ---------- Historial de portería ----------
def test_historial_guarda_entrada_salida_y_quien_registro(client, auth):
    g, a = auth("celador@conjunto.com"), auth("admin@conjunto.com")
    vid = client.post("/porteria/vehiculo-ingreso?placa=xyz123&apartamento=Torre 1 Apt 101", headers=g).json()["id"]
    assert client.patch(f"/porteria/vehiculo-salida/{vid}", headers=a).status_code == 200
    client.post("/porteria/vehiculo-ingreso?placa=ABC12D&apartamento=Torre 2 Apt 202", headers=g)

    r = client.get("/porteria/historial", headers=g).json()
    assert r["total"] == 2 and r["items"][0]["placa"] == "ABC12D"          # más reciente primero
    salido = next(i for i in r["items"] if i["placa"] == "XYZ123")
    assert salido["estado"] == "Salido" and salido["fecha_salida"] and salido["duracion_minutos"] == 0
    assert salido["ingreso_registrado_por"] == "Celador Uno" and salido["salida_registrada_por"] == "Admin"

    # Filtros y paginación
    assert client.get("/porteria/historial?placa=xyz", headers=g).json()["total"] == 1
    assert client.get("/porteria/historial?estado=Dentro", headers=g).json()["total"] == 1
    assert client.get("/porteria/historial?apartamento=torre 2", headers=g).json()["total"] == 1
    assert len(client.get("/porteria/historial?limite=1&pagina=2", headers=g).json()["items"]) == 1
    assert client.get("/porteria/historial?desde=2999-01-01T00:00:00Z", headers=g).json()["total"] == 0
    assert client.get("/porteria/historial?estado=Otro", headers=g).status_code == 422


def test_historial_solo_personal_y_exportacion_solo_admin(client, auth):
    assert client.get("/porteria/historial", headers=auth("ana@conjunto.com")).status_code == 403
    assert client.get("/porteria/historial").status_code == 401
    assert client.get("/porteria/historial/exportar", headers=auth("celador@conjunto.com")).status_code == 403


def test_exportar_historial_csv_con_bom_y_sin_inyeccion_de_formulas(client, auth):
    g, a = auth("celador@conjunto.com"), auth("admin@conjunto.com")
    client.post("/porteria/vehiculo-ingreso?placa=XYZ123&apartamento==SUMA(1;1)", headers=g)
    r = client.get("/porteria/historial/exportar", headers=a)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    texto = r.content.decode("utf-8")
    assert texto.startswith("\ufeffPlaca;") and "XYZ123" in texto and "'=SUMA(1;1)" in texto


# ---------- Anuncios ----------
def test_anuncios_admin_publica_todos_leen_y_residente_no_publica(client, auth):
    a, r = auth("admin@conjunto.com"), auth("ana@conjunto.com")
    cuerpo = {"titulo": "Asamblea general", "contenido": "Se tratará el presupuesto.", "tipo": "Reunion",
              "fecha_evento": FUTURO, "lugar": "Salón comunal"}
    assert client.post("/anuncios/", json=cuerpo, headers=r).status_code == 403
    creado = client.post("/anuncios/", json=cuerpo, headers=a)
    assert creado.status_code == 201 and creado.json()["autor_nombre"] == "Admin"
    client.post("/anuncios/", json={"titulo": "Corte de agua", "contenido": "Sábado de 8 a 12.", "tipo": "Urgente", "fijado": True}, headers=a)

    lista = client.get("/anuncios/", headers=r).json()
    assert [x["titulo"] for x in lista] == ["Corte de agua", "Asamblea general"]       # fijados primero
    assert client.post("/anuncios/", json={**cuerpo, "tipo": "Inventado"}, headers=a).status_code == 422
    assert client.post("/anuncios/", json={**cuerpo, "titulo": "ab"}, headers=a).status_code == 422
    assert client.get("/anuncios/").status_code == 401


def test_anuncios_confirmar_asistencia_es_idempotente_y_admin_ve_quien_va(client, auth):
    a, ana, luis = auth("admin@conjunto.com"), auth("ana@conjunto.com"), auth("luis@conjunto.com")
    aid = client.post("/anuncios/", json={"titulo": "Asamblea", "contenido": "Todos invitados.", "tipo": "Reunion", "fecha_evento": FUTURO}, headers=a).json()["id"]
    sin_fecha = client.post("/anuncios/", json={"titulo": "Aviso general", "contenido": "Sin fecha de evento."}, headers=a).json()["id"]

    assert client.put(f"/anuncios/{aid}/asistencia?asistire=true", headers=ana).json()["asistire"] is True
    assert client.put(f"/anuncios/{aid}/asistencia?asistire=true", headers=ana).json()["asistentes"] == 1   # no se duplica
    client.put(f"/anuncios/{aid}/asistencia?asistire=true", headers=luis)
    assert next(x for x in client.get("/anuncios/", headers=luis).json() if x["id"] == aid)["asistentes"] == 2
    quienes = client.get(f"/anuncios/{aid}/asistentes", headers=a).json()
    assert [q["nombre_completo"] for q in quienes] == ["Ana Residente", "Luis Residente"]
    assert client.get(f"/anuncios/{aid}/asistentes", headers=ana).status_code == 403
    assert client.put(f"/anuncios/{aid}/asistencia?asistire=false", headers=ana).json()["asistentes"] == 1
    assert client.put(f"/anuncios/{sin_fecha}/asistencia?asistire=true", headers=ana).status_code == 400
    assert client.put("/anuncios/9999/asistencia?asistire=true", headers=ana).status_code == 404


def test_anuncios_editar_fijar_y_eliminar(client, auth):
    a, ana = auth("admin@conjunto.com"), auth("ana@conjunto.com")
    aid = client.post("/anuncios/", json={"titulo": "Fiesta", "contenido": "Bazar navideño.", "tipo": "Evento", "fecha_evento": FUTURO}, headers=a).json()["id"]
    client.put(f"/anuncios/{aid}/asistencia?asistire=true", headers=ana)
    editado = client.patch(f"/anuncios/{aid}", json={"fijado": True, "lugar": "Parque central"}, headers=a).json()
    assert editado["fijado"] is True and editado["lugar"] == "Parque central" and editado["titulo"] == "Fiesta"
    assert client.patch(f"/anuncios/{aid}", json={"fijado": False}, headers=ana).status_code == 403
    assert client.delete(f"/anuncios/{aid}", headers=ana).status_code == 403
    assert client.delete(f"/anuncios/{aid}", headers=a).status_code == 200      # borra también las asistencias
    assert client.get("/anuncios/", headers=a).json() == []
    assert client.delete(f"/anuncios/{aid}", headers=a).status_code == 404
