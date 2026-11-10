# tests/test_comercio.py — Fase 2: directorio comercial con anuncios de pago.
import io
from datetime import timedelta

from PIL import Image

from app.models import Publicidad, ahora_utc

DATOS = {"nombre_negocio": "Arepas Doña Rosa", "categoria": "Comida", "titulo": "Arepas rellenas a domicilio",
         "descripcion": "Arepas de queso, pollo y carne. Domicilio dentro del conjunto.", "whatsapp": "3001234567",
         "plan": "Mensual", "precio_texto": "Desde $6.000"}


def png() -> bytes:
    b = io.BytesIO(); Image.new("RGB", (30, 30), "orange").save(b, format="PNG"); return b.getvalue()


def crear(client, auth, quien="ana@conjunto.com", con_imagen=False, **cambios):
    archivos = {"imagen": ("foto.png", png(), "image/png")} if con_imagen else None
    r = client.post("/comercio/", data={**DATOS, **cambios}, files=archivos, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def activar(client, auth, a):
    client.post(f"/comercio/{a['id']}/informar-pago", json={"referencia": "Nequi M123"}, headers=auth("ana@conjunto.com"))
    r = client.post(f"/comercio/{a['id']}/aprobar", headers=auth("admin@conjunto.com"))
    assert r.status_code == 200, r.text
    return r.json()


def test_planes_visibles_para_todos(client, auth):
    r = client.get("/comercio/planes", headers=auth("celador@conjunto.com")).json()
    assert {p["plan"] for p in r["planes"]} == {"Semanal", "Mensual", "Trimestral"} and r["instrucciones_pago"]


def test_anuncio_nuevo_queda_pendiente_de_pago_y_no_sale_en_el_directorio(client, auth):
    a = crear(client, auth)
    assert a["estado"] == "Pendiente de pago" and a["valor"] == 45000 and a["contactos"] == 0
    assert client.get("/comercio/", headers=auth("luis@conjunto.com")).json() == []
    assert [x["id"] for x in client.get("/comercio/mios", headers=auth("ana@conjunto.com")).json()] == [a["id"]]


def test_flujo_completo_pago_revision_activa_y_directorio(client, auth):
    a = crear(client, auth)
    r = client.post(f"/comercio/{a['id']}/informar-pago", json={"referencia": "Nequi M123"}, headers=auth("ana@conjunto.com")).json()
    assert r["estado"] == "En revision"
    assert client.get("/comercio/resumen", headers=auth("admin@conjunto.com")).json()["por_revisar"] == 1
    act = client.post(f"/comercio/{a['id']}/aprobar", headers=auth("admin@conjunto.com")).json()
    assert act["estado"] == "Activa" and act["fecha_fin"] > act["fecha_inicio"]
    lista = client.get("/comercio/", headers=auth("luis@conjunto.com")).json()
    assert [x["id"] for x in lista] == [a["id"]] and lista[0]["apartamento"] == "Torre 1 Apt 101"
    res = client.get("/comercio/resumen", headers=auth("admin@conjunto.com")).json()
    assert res["activas"] == 1 and res["ingresos_confirmados"] == 45000


def test_permisos(client, auth):
    a = crear(client, auth)
    assert client.post("/comercio/", data=DATOS, headers=auth("celador@conjunto.com")).status_code == 403
    assert client.post(f"/comercio/{a['id']}/aprobar", headers=auth("ana@conjunto.com")).status_code == 403
    assert client.post(f"/comercio/{a['id']}/informar-pago", json={"referencia": "abc"}, headers=auth("luis@conjunto.com")).status_code == 403
    assert client.delete(f"/comercio/{a['id']}", headers=auth("luis@conjunto.com")).status_code == 403
    assert client.get("/comercio/gestion", headers=auth("ana@conjunto.com")).status_code == 403
    assert client.get("/comercio/").status_code == 401


def test_rechazo_con_motivo_y_renovacion(client, auth):
    a = crear(client, auth)
    client.post(f"/comercio/{a['id']}/informar-pago", json={"referencia": "comprobante 9"}, headers=auth("ana@conjunto.com"))
    r = client.post(f"/comercio/{a['id']}/rechazar", json={"motivo": "El comprobante no coincide."}, headers=auth("admin@conjunto.com")).json()
    assert r["estado"] == "Rechazada" and r["motivo_rechazo"] == "El comprobante no coincide."
    n = client.post(f"/comercio/{a['id']}/renovar", json={"plan": "Semanal"}, headers=auth("ana@conjunto.com")).json()
    assert n["estado"] == "Pendiente de pago" and n["valor"] == 15000 and n["motivo_rechazo"] is None
    assert client.post(f"/comercio/{a['id']}/renovar", json={"plan": "Semanal"}, headers=auth("ana@conjunto.com")).status_code == 400   # ya no está vencido/rechazado


def test_anuncio_vence_solo_y_desaparece_del_directorio(client, auth, db):
    a = activar(client, auth, crear(client, auth))
    db.query(Publicidad).filter(Publicidad.id == a["id"]).update({"fecha_fin": ahora_utc() - timedelta(minutes=1)})
    db.commit()
    assert client.get("/comercio/", headers=auth("luis@conjunto.com")).json() == []
    assert client.get("/comercio/mios", headers=auth("ana@conjunto.com")).json()[0]["estado"] == "Vencida"
    assert client.post(f"/comercio/{a['id']}/contacto", headers=auth("luis@conjunto.com")).status_code == 400


def test_contacto_cuenta_clics_de_otros_y_arma_el_enlace_de_whatsapp(client, auth):
    a = activar(client, auth, crear(client, auth))
    r = client.post(f"/comercio/{a['id']}/contacto", headers=auth("luis@conjunto.com")).json()
    assert r["whatsapp_url"].startswith("https://wa.me/573001234567?text=")
    client.post(f"/comercio/{a['id']}/contacto", headers=auth("ana@conjunto.com"))      # el dueño no suma
    assert client.get("/comercio/mios", headers=auth("ana@conjunto.com")).json()[0]["contactos"] == 1


def test_filtros_y_validaciones(client, auth):
    activar(client, auth, crear(client, auth))
    assert len(client.get("/comercio/?categoria=Comida", headers=auth("luis@conjunto.com")).json()) == 1
    assert client.get("/comercio/?categoria=Belleza", headers=auth("luis@conjunto.com")).json() == []
    assert len(client.get("/comercio/?q=arepas", headers=auth("luis@conjunto.com")).json()) == 1
    h = auth("ana@conjunto.com")
    assert client.post("/comercio/", data={**DATOS, "whatsapp": "12345"}, headers=h).status_code == 422
    assert client.post("/comercio/", data={**DATOS, "plan": "Eterno"}, headers=h).status_code == 422
    assert client.post("/comercio/", data={**DATOS, "categoria": "Armas"}, headers=h).status_code == 422
    mala = client.post("/comercio/", data=DATOS, files={"imagen": ("x.png", b"no soy imagen", "image/png")}, headers=h)
    assert mala.status_code == 400


def test_imagen_privada_hasta_que_se_activa(client, auth):
    a = crear(client, auth, con_imagen=True)
    assert a["tiene_imagen"] is True
    assert client.get(f"/comercio/{a['id']}/imagen", headers=auth("ana@conjunto.com")).status_code == 200
    assert client.get(f"/comercio/{a['id']}/imagen", headers=auth("luis@conjunto.com")).status_code == 403
    activar(client, auth, a)
    assert client.get(f"/comercio/{a['id']}/imagen", headers=auth("luis@conjunto.com")).status_code == 200


def test_eliminar_activo_solo_el_admin_y_limite_de_anuncios(client, auth):
    a = activar(client, auth, crear(client, auth))
    assert client.delete(f"/comercio/{a['id']}", headers=auth("ana@conjunto.com")).status_code == 400
    assert client.delete(f"/comercio/{a['id']}", headers=auth("admin@conjunto.com")).status_code == 200
    for _ in range(5):
        crear(client, auth)
    assert client.post("/comercio/", data=DATOS, headers=auth("ana@conjunto.com")).status_code == 400
