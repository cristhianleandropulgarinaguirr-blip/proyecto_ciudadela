# tests/test_v57_notificaciones_gestion.py — v5.7 · «leída» NO es «gestionada».
# Un aviso que pide una acción (aprobar, responder, recoger…) sigue «por gestionar» aunque se abra, hasta que se gestione a mano
# o hasta que se resuelva lo que pedía. Así lo pendiente no se pierde si se abre el aviso y se olvida actuar.
import os
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config

from app.models import Notificacion
from tests.test_comunicacion import ADM, ANA, CEL, FUTURO, id_de
from tests.test_v56_enlace_tecnico import _enlace, _estado, _reporte

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _conteo(client, auth, quien):
    return client.get("/notificaciones/conteo", headers=auth(quien)).json()


def _lista(client, auth, quien, **params):
    return client.get("/notificaciones/", params=params, headers=auth(quien)).json()


def _reserva(client, auth, quien=ANA):
    r = client.post("/reservas/registrar", json={"zona_comun": "Salon Comunal", "fecha_reserva": FUTURO}, headers=auth(quien))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------- el corazón: abrir un aviso no lo gestiona
def test_abrir_o_leer_todas_no_gestiona_un_aviso_pendiente(client, auth):
    rid = _reserva(client, auth)
    c = _conteo(client, auth, ADM)
    assert c == {"no_leidas": 1, "por_gestionar": 1}
    aviso = _lista(client, auth, ADM)[0]
    assert aviso["titulo"] == "Reserva por aprobar" and aviso["estado_gestion"] == "por_gestionar" and aviso["requiere_gestion"] is True

    assert client.post(f"/notificaciones/{aviso['id']}/leer", headers=auth(ADM)).status_code == 200
    assert _conteo(client, auth, ADM) == {"no_leidas": 0, "por_gestionar": 1}          # leído, pero NO se pierde: sigue pendiente
    assert client.post("/notificaciones/leer-todas", headers=auth(ADM)).status_code == 200
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1
    assert _lista(client, auth, ADM)[0]["estado_gestion"] == "por_gestionar" and _lista(client, auth, ADM)[0]["leida"] is True
    assert rid


def test_se_gestiona_sola_cuando_se_resuelve_lo_que_pedia(client, auth):
    rid = _reserva(client, auth)
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1
    client.patch(f"/reservas/cambiar-estado/{rid}?nuevo_estado=Aprobada", headers=auth(ADM))
    aviso = _lista(client, auth, ADM)[0]
    assert aviso["estado_gestion"] == "gestionada" and aviso["gestionada_en"] is not None
    assert _conteo(client, auth, ADM) == {"no_leidas": 1, "por_gestionar": 0}      # se cerró solo y NO se marcó como leído (nadie lo había visto)
    assert [n["titulo"] for n in _lista(client, auth, ADM, gestion="gestionadas")] == ["Reserva por aprobar"]
    assert _lista(client, auth, ADM, gestion="por_gestionar") == []


def test_gestionar_a_mano_y_devolver_a_pendiente(client, auth):
    _reserva(client, auth)
    n = _lista(client, auth, ADM)[0]
    g = client.post(f"/notificaciones/{n['id']}/gestionar", headers=auth(ADM))
    assert g.status_code == 200 and g.json()["estado_gestion"] == "gestionada" and g.json()["leida"] is True
    assert _conteo(client, auth, ADM) == {"no_leidas": 0, "por_gestionar": 0}
    p = client.post(f"/notificaciones/{n['id']}/pendiente", headers=auth(ADM))               # por si se marcó por error
    assert p.status_code == 200 and p.json()["estado_gestion"] == "por_gestionar"
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1


def test_un_aviso_informativo_no_se_gestiona_ni_el_ajeno(client, auth):
    _reserva(client, auth)
    client.post("/anuncios/", json={"titulo": "Corte de agua", "contenido": "Sábado de 8 a 12.", "tipo": "Aviso"}, headers=auth(ADM))
    info = _lista(client, auth, ANA)[0]
    assert info["estado_gestion"] == "informativa"
    for ruta in ("gestionar", "pendiente"):
        assert client.post(f"/notificaciones/{info['id']}/{ruta}", headers=auth(ANA)).status_code == 400
    ajeno = _lista(client, auth, ADM)[0]
    assert client.post(f"/notificaciones/{ajeno['id']}/gestionar", headers=auth(CEL)).status_code == 404      # no revela si existe
    assert client.post(f"/notificaciones/{ajeno['id']}/gestionar").status_code == 401


def test_lo_pendiente_va_primero_aunque_sea_viejo(client, auth):
    _reserva(client, auth)                                                                          # id viejo, por gestionar
    client.post("/anuncios/", json={"titulo": "Reunión", "contenido": "Jueves a las 7 pm.", "tipo": "Reunion"}, headers=auth(ADM))
    client.post("/pqrs/", json={"tipo": "Queja", "asunto": "Ruido nocturno", "descripcion": "Música alta todas las noches."}, headers=auth(ANA))
    estados = [n["estado_gestion"] for n in _lista(client, auth, ADM)]
    assert estados[:2] == ["por_gestionar", "por_gestionar"]                                       # las dos pendientes primero


# ---------------------------------------------------------------- cada flujo del administrador
def test_pqrs_nueva_queda_por_gestionar_hasta_responder(client, auth):
    pid = client.post("/pqrs/", json={"tipo": "Queja", "asunto": "Ruido nocturno", "descripcion": "Música alta todas las noches."}, headers=auth(ANA)).json()["id"]
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1
    assert client.patch(f"/pqrs/{pid}", json={"respuesta": "Hablaremos con el vecino."}, headers=auth(ADM)).status_code == 200
    assert _conteo(client, auth, ADM)["por_gestionar"] == 0 and _lista(client, auth, ADM)[0]["estado_gestion"] == "gestionada"


def test_dano_nuevo_se_gestiona_al_crear_el_enlace_y_el_del_tecnico_al_aprobar(client, auth):
    rid = _reporte(client, auth)
    assert [n["titulo"] for n in _lista(client, auth, ADM, gestion="por_gestionar")] == ["Nuevo daño por atender"]
    e = _enlace(client, auth, rid)                                                                  # el administrador ya lo gestionó: generó el enlace
    assert _conteo(client, auth, ADM)["por_gestionar"] == 0
    assert _estado(client, e["token"], "En Reparacion", "Ya estoy en el sitio.").status_code == 200
    assert _conteo(client, auth, ADM)["por_gestionar"] == 0                                        # «El técnico actualizó» es solo informativo
    assert _estado(client, e["token"], "Solucionado", "Cambié el sifón y quedó seco.").status_code == 200
    pend = _lista(client, auth, ADM, gestion="por_gestionar")
    assert [n["titulo"] for n in pend] == ["Daño por aprobar: el técnico terminó"]                  # ahora SÍ falta algo del administrador
    client.post(f"/notificaciones/{pend[0]['id']}/leer", headers=auth(ADM))
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1                                         # lo abrió y se le olvidó: no se pierde
    client.patch(f"/mantenimiento/cambiar-estado/{rid}", params={"nuevo_estado": "Aprobado"}, headers=auth(ADM))
    assert _conteo(client, auth, ADM)["por_gestionar"] == 0


def test_paquete_del_residente_queda_por_gestionar_hasta_que_lo_recoge(client, auth):
    p = client.post("/paquetes/", json={"destinatario_id": id_de(client, auth, ANA), "remitente": "Rappi"}, headers=auth(CEL)).json()
    assert _conteo(client, auth, ANA)["por_gestionar"] == 1
    assert _lista(client, auth, ANA)[0]["titulo"] == "Tienes un paquete en portería"
    assert client.patch(f"/paquetes/{p['id']}/entregar", json={}, headers=auth(CEL)).status_code == 200
    assert _conteo(client, auth, ANA)["por_gestionar"] == 0


def test_cada_persona_ve_solo_lo_suyo(client, auth):
    _reserva(client, auth)
    assert _conteo(client, auth, ANA)["por_gestionar"] == 0 and _conteo(client, auth, CEL)["por_gestionar"] == 0       # no se filtra a otros roles
    assert _conteo(client, auth, ADM)["por_gestionar"] == 1


def test_el_administrador_no_se_avisa_a_si_mismo(client, auth, db):
    rid = _reserva(client, auth, quien=ADM)                                                         # él mismo pide una reserva
    assert rid and _conteo(client, auth, ADM) == {"no_leidas": 0, "por_gestionar": 0}


# ---------------------------------------------------------------- base de datos
def _cfg(url: str) -> Config:
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migracion_0027_solo_agrega_columnas_y_los_avisos_viejos_quedan_informativos():
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    cfg = _cfg(f"sqlite:///{ruta}")
    command.upgrade(cfg, "0026")
    con = sqlite3.connect(ruta)
    antes = [c[1] for c in con.execute("PRAGMA table_info(notificaciones)")]
    rol_id = con.execute("SELECT id FROM roles WHERE nombre = 'Residente'").fetchone()[0]          # las migraciones ya crean los roles
    con.execute("INSERT INTO usuarios (nombre_completo, email, password_encriptada, rol_id, esta_activo, esta_al_dia) VALUES ('Ana', 'ana@x.com', 'x', ?, 1, 1)", (rol_id,))
    con.execute("INSERT INTO notificaciones (usuario_id, titulo, leida, fecha) VALUES (1, 'Aviso viejo', 0, '2026-11-01 10:00:00')")
    con.commit(); con.close()

    command.upgrade(cfg, "0027")
    command.upgrade(cfg, "0027")                       # correrla de nuevo no rompe nada
    con = sqlite3.connect(ruta)
    despues = [c[1] for c in con.execute("PRAGMA table_info(notificaciones)")]
    assert despues[:len(antes)] == antes and set(despues) - set(antes) == {"requiere_gestion", "gestionada_en", "ref_tipo", "ref_id"}
    fila = con.execute("SELECT titulo, leida, requiere_gestion, gestionada_en FROM notificaciones").fetchone()
    assert fila == ("Aviso viejo", 0, 0, None)         # el aviso viejo se conserva y queda como informativo (nada aparece «pendiente» de golpe)
    assert "ix_notificaciones_ref" in {i[1] for i in con.execute("PRAGMA index_list(notificaciones)")}
    con.close()

    command.downgrade(cfg, "0026")                     # y se puede devolver sin perder los avisos
    con = sqlite3.connect(ruta)
    assert [c[1] for c in con.execute("PRAGMA table_info(notificaciones)")] == antes
    assert con.execute("SELECT titulo FROM notificaciones").fetchone() == ("Aviso viejo",)
    con.close()
