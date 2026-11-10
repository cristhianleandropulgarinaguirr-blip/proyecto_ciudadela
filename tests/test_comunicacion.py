# tests/test_comunicacion.py — Bloque 3: notificaciones, PQRS, documentos y reportes.
import io
from datetime import datetime, timedelta

import pytest
from openpyxl import load_workbook

from app import notificaciones

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
FUTURO = (datetime.now() + timedelta(days=10)).replace(hour=12, minute=0, second=0, microsecond=0).isoformat()


def id_de(client, auth, email):
    return next(u["id"] for u in client.get("/usuarios/", headers=auth(ADM)).json() if u["email"] == email)


def sin_leer(client, auth, email):
    return client.get("/notificaciones/conteo", headers=auth(email)).json()["no_leidas"]


def radicar(client, auth, quien=ANA, **extra):
    r = client.post("/pqrs/", json={"tipo": "Queja", "asunto": "Ruido en el parqueadero", "descripcion": "Música alta todas las noches en el sótano.", **extra}, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()


def subir(client, auth, contenido=PDF, nombre="reglamento.pdf", mime="application/pdf", quien=ADM, **datos):
    return client.post("/documentos/", data={"titulo": "Reglamento interno", "categoria": "Reglamento", **datos},
                       files={"archivo": (nombre, io.BytesIO(contenido), mime)}, headers=auth(quien))


@pytest.fixture()
def correos(monkeypatch):
    """Simula un servidor de correo configurado y captura lo que se enviaría."""
    enviados = []
    monkeypatch.setattr(notificaciones.config, "SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setattr(notificaciones.config, "SMTP_FROM", "app@prueba.local")
    monkeypatch.setattr(notificaciones, "enviar_correos", lambda msgs: enviados.extend(msgs))
    return enviados


# ------------------------------------------------------------ notificaciones
def test_cada_usuario_ve_solo_sus_notificaciones(client, auth):
    dest = id_de(client, auth, ANA)
    client.post("/paquetes/", json={"destinatario_id": dest, "remitente": "Servientrega"}, headers=auth(CEL))
    assert sin_leer(client, auth, ANA) == 1 and sin_leer(client, auth, LUIS) == 0
    n = client.get("/notificaciones/", headers=auth(ANA)).json()
    assert n[0]["titulo"] == "Tienes un paquete en portería" and "Servientrega" in n[0]["mensaje"] and n[0]["enlace"] == "#/paquetes" and n[0]["leida"] is False
    assert client.post(f"/notificaciones/{n[0]['id']}/leer", headers=auth(LUIS)).status_code == 404     # ajena: no existe para Luis
    assert client.post(f"/notificaciones/{n[0]['id']}/leer", headers=auth(ANA)).status_code == 200
    assert sin_leer(client, auth, ANA) == 0 and client.get("/notificaciones/?solo_no_leidas=true", headers=auth(ANA)).json() == []
    assert client.get("/notificaciones/").status_code == 401


def test_marcar_todas_como_leidas(client, auth):
    for _ in range(3):
        client.post("/paquetes/", json={"destinatario_id": id_de(client, auth, ANA)}, headers=auth(CEL))
    assert sin_leer(client, auth, ANA) == 3
    assert client.post("/notificaciones/leer-todas", headers=auth(ANA)).status_code == 200
    assert sin_leer(client, auth, ANA) == 0


def test_anuncio_y_reserva_avisan_a_los_usuarios(client, auth):
    client.post("/anuncios/", json={"titulo": "Corte de agua", "contenido": "Sábado de 8 a 12.", "tipo": "Aviso"}, headers=auth(ADM))
    assert sin_leer(client, auth, ANA) == 1 and sin_leer(client, auth, CEL) == 1 and sin_leer(client, auth, ADM) == 0   # el autor no se avisa a sí mismo
    rid = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=auth(ANA)).json()["id"]
    client.patch(f"/reservas/cambiar-estado/{rid}?nuevo_estado=Aprobada", headers=auth(ADM))
    titulos = [n["titulo"] for n in client.get("/notificaciones/", headers=auth(ANA)).json()]
    assert "Tu reserva fue aprobada" in titulos


def test_correos_solo_si_hay_smtp_y_solo_tras_el_commit(client, auth, correos):
    client.post("/paquetes/", json={"destinatario_id": id_de(client, auth, ANA), "remitente": "Rappi"}, headers=auth(CEL))
    assert [(c[0], c[1]) for c in correos] == [("ana@conjunto.com", "Tienes un paquete en portería")]
    correos.clear()
    client.post("/anuncios/", json={"titulo": "Fiesta", "contenido": "Sábado en el salón.", "tipo": "Evento"}, headers=auth(ADM))
    assert correos == []                                                                              # un evento normal no genera correos
    client.post("/anuncios/", json={"titulo": "Fuga de gas", "contenido": "Evacuar la torre 2.", "tipo": "Urgente"}, headers=auth(ADM))
    assert {c[0] for c in correos} == {"ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com"}
    correos.clear()
    assert client.post("/paquetes/", json={"destinatario_id": 9999}, headers=auth(CEL)).status_code == 400   # operación fallida: nada se envía
    assert correos == []


def test_sin_smtp_no_se_envian_correos(client, auth, monkeypatch):
    llamados = []
    monkeypatch.setattr(notificaciones, "_enviar_ahora", lambda m: llamados.append(m))
    client.post("/paquetes/", json={"destinatario_id": id_de(client, auth, ANA)}, headers=auth(CEL))
    assert llamados == [] and sin_leer(client, auth, ANA) == 1                                        # el aviso en la app sí existe


# ------------------------------------------------------------ PQRS
def test_residente_radica_y_solo_ve_las_suyas(client, auth):
    p = radicar(client, auth)
    assert p["radicado"] == f"PQRS-{datetime.now().year}-{p['id']:04d}" and p["estado"] == "Radicada" and p["apartamento"] == "Torre 1 Apt 101"
    radicar(client, auth, LUIS, tipo="Sugerencia", asunto="Más bancas en el parque")
    assert [x["id"] for x in client.get("/pqrs/", headers=auth(ANA)).json()] == [p["id"]]
    assert len(client.get("/pqrs/", headers=auth(ADM)).json()) == 2
    assert client.get("/pqrs/", headers=auth(CEL)).status_code == 403
    assert client.post("/pqrs/", json={"tipo": "Queja", "asunto": "Algo", "descripcion": "x"}, headers=auth(ANA)).status_code == 422
    assert client.post("/pqrs/", json={"tipo": "Otra", "asunto": "Asunto largo", "descripcion": "Descripción suficiente"}, headers=auth(ANA)).status_code == 422
    assert sin_leer(client, auth, ADM) == 2                                                           # el admin recibe aviso de cada una


def test_limite_de_pqrs_abiertas(client, auth):
    for i in range(5):
        radicar(client, auth, asunto=f"Solicitud número {i}")
    assert client.post("/pqrs/", json={"tipo": "Queja", "asunto": "Una más", "descripcion": "Descripción suficiente"}, headers=auth(ANA)).status_code == 400
    radicar(client, auth, LUIS)    # el límite es por persona


def test_admin_responde_y_el_residente_es_avisado(client, auth, correos):
    p = radicar(client, auth)
    assert client.patch(f"/pqrs/{p['id']}", json={"estado": "En tramite"}, headers=auth(ANA)).status_code == 403
    assert client.patch(f"/pqrs/{p['id']}", json={}, headers=auth(ADM)).status_code == 400
    assert client.patch(f"/pqrs/{p['id']}", json={"estado": "Resuelta"}, headers=auth(ADM)).status_code == 400   # sin respuesta
    r = client.patch(f"/pqrs/{p['id']}", json={"estado": "En tramite"}, headers=auth(ADM)).json()
    assert r["estado"] == "En tramite" and correos == []                                              # cambio de estado: aviso en app, sin correo
    assert client.patch(f"/pqrs/{p['id']}", json={"estado": "En tramite"}, headers=auth(ADM)).status_code == 400  # sin cambio
    r = client.patch(f"/pqrs/{p['id']}", json={"respuesta": "Reforzamos la ronda nocturna."}, headers=auth(ADM)).json()
    assert r["estado"] == "Resuelta" and r["respondido_por"] == "Admin" and r["fecha_respuesta"]
    assert [c[0] for c in correos] == [ANA]                                                           # la respuesta sí va por correo
    assert "Reforzamos" in client.get("/notificaciones/", headers=auth(ANA)).json()[0]["mensaje"]
    assert client.get("/pqrs/?estado=Resuelta", headers=auth(ANA)).json()[0]["respuesta"].startswith("Reforzamos")
    assert client.patch("/pqrs/9999", json={"estado": "Cerrada"}, headers=auth(ADM)).status_code == 404
    assert {x["accion"] for x in client.get("/auditoria/?entidad=PQRS", headers=auth(ADM)).json()} == {"Radicó PQRS", "Gestionó PQRS"}


# ------------------------------------------------------------ documentos
def test_admin_sube_pdf_y_todos_lo_descargan(client, auth):
    assert subir(client, auth, quien=ANA).status_code == 403
    assert subir(client, auth, quien=CEL).status_code == 403
    d = subir(client, auth).json()
    assert d["titulo"] == "Reglamento interno" and d["categoria"] == "Reglamento" and d["tamano"] == len(PDF) and d["subido_por"] == "Admin"
    for quien in (ANA, CEL, ADM):
        r = client.get(f"/documentos/{d['id']}/descargar", headers=auth(quien))
        assert r.status_code == 200 and r.content == PDF and r.headers["content-type"] == "application/pdf"
    assert "reglamento.pdf" in r.headers["content-disposition"]
    assert client.get(f"/documentos/{d['id']}/descargar").status_code == 401                          # sin sesión no hay descarga
    assert client.get("/documentos/9999/descargar", headers=auth(ANA)).status_code == 404
    assert [x["id"] for x in client.get("/documentos/?categoria=Reglamento", headers=auth(ANA)).json()] == [d["id"]]
    assert client.get("/documentos/?categoria=Acta", headers=auth(ANA)).json() == []
    assert sin_leer(client, auth, ANA) == 1                                                           # avisó a todos


def test_documentos_rechaza_lo_que_no_es_pdf(client, auth):
    assert subir(client, auth, contenido=b"MZ\x90\x00 programa", nombre="virus.pdf").status_code == 400        # firma falsa
    assert subir(client, auth, mime="image/png", nombre="foto.png").status_code == 400                         # tipo equivocado
    assert subir(client, auth, contenido=PDF + b"0" * (10 * 1024 * 1024)).status_code == 413                   # pesa más de 10 MB
    assert subir(client, auth, titulo="ab").status_code == 422
    assert client.get("/documentos/", headers=auth(ANA)).json() == []


def test_nombre_de_descarga_no_permite_rutas_y_eliminar_borra_el_archivo(client, auth):
    d = subir(client, auth, nombre="../../etc/pass wd?.pdf").json()
    assert ".." not in d["nombre_original"] and "/" not in d["nombre_original"] and d["nombre_original"].endswith(".pdf")
    assert client.delete(f"/documentos/{d['id']}", headers=auth(ANA)).status_code == 403
    assert client.delete(f"/documentos/{d['id']}", headers=auth(ADM)).status_code == 200
    assert client.get(f"/documentos/{d['id']}/descargar", headers=auth(ANA)).status_code == 404
    assert client.delete(f"/documentos/{d['id']}", headers=auth(ADM)).status_code == 404


# ------------------------------------------------------------ reportes
def abrir(r):
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    return load_workbook(io.BytesIO(r.content)).active


@pytest.mark.parametrize("ruta", ["cartera", "pqrs", "paquetes", "visitantes", "auditoria"])
def test_excel_solo_para_el_administrador(client, auth, ruta):
    for quien in (ANA, CEL):
        assert client.get(f"/reportes/{ruta}.xlsx", headers=auth(quien)).status_code == 403
    assert client.get(f"/reportes/{ruta}.xlsx").status_code == 401
    assert abrir(client.get(f"/reportes/{ruta}.xlsx", headers=auth(ADM))).max_row >= 4              # título, fecha, vacío y encabezado


def test_excel_de_cartera_con_totales(client, auth):
    client.patch(f"/administracion/registrar-deuda/{id_de(client, auth, ANA)}?saldo_pendiente=300000", headers=auth(ADM))
    ws = abrir(client.get("/reportes/cartera.xlsx", headers=auth(ADM)))
    filas = [[c.value for c in f] for f in ws.iter_rows(min_row=5)]
    assert filas[0][:2] == ["Torre 1 Apt 101", "Ana Residente"] and filas[0][4] == 300000 and filas[0][5] == "En mora"
    assert filas[1][5] == "Al día" and filas[-1][0] == "TOTAL" and filas[-1][4] == 300000 and filas[-1][3] == 300000


def test_excel_neutraliza_formulas(client, auth):
    radicar(client, auth, asunto='=HYPERLINK("http://malo.example","clic")')
    ws = abrir(client.get("/reportes/pqrs.xlsx", headers=auth(ADM)))
    asunto = ws["F5"].value
    assert asunto.startswith("'=") and ws["F5"].data_type == "s"


def test_excel_de_auditoria_deja_rastro_del_reporte(client, auth):
    abrir(client.get("/reportes/cartera.xlsx", headers=auth(ADM)))
    acc = [x["detalle"] for x in client.get("/auditoria/?entidad=Reporte", headers=auth(ADM)).json()]
    assert any(d.startswith("Cartera") for d in acc)


def test_pdf_estado_de_cuenta(client, auth):
    ana = id_de(client, auth, ANA)
    r = client.get(f"/reportes/estado-cuenta/{ana}.pdf", headers=auth(ANA))
    assert r.status_code == 200 and r.content.startswith(b"%PDF") and r.headers["content-type"] == "application/pdf"
    assert client.get(f"/reportes/estado-cuenta/{ana}.pdf", headers=auth(ADM)).status_code == 200      # el admin puede el de cualquiera
    assert client.get(f"/reportes/estado-cuenta/{ana}.pdf", headers=auth(LUIS)).status_code == 403      # otro vecino no
    assert client.get(f"/reportes/estado-cuenta/{ana}.pdf").status_code == 401
    assert client.get("/reportes/estado-cuenta/9999.pdf", headers=auth(ADM)).status_code == 404
