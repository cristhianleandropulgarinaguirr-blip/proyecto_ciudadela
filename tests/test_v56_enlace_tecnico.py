# tests/test_v56_enlace_tecnico.py — Rol Mantenimiento: el técnico (sin cuenta) atiende UN reporte desde un enlace temporal.
# Se prueba lo prometido en el diseño: enlace atado a un reporte, con vencimiento y revocable; la página muestra solo lo mínimo
# (nunca datos del residente); el técnico solo pasa a En Reparación / Solucionado con nota y foto; todo queda en la auditoría y avisa.
import io
import os
import sqlite3
import tempfile
from datetime import timedelta

from alembic import command
from alembic.config import Config
from PIL import Image

from app import limitador
from app.models import Auditoria, EnlaceTecnico, EvidenciaDanio, Notificacion, ReporteDanio, Usuario, ahora_utc
from tests.test_arrendamientos import inquilino_activo

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _png(color=(200, 40, 30)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(b, "PNG")
    return b.getvalue()


def _reporte(client, auth, email=ANA, con_foto=True, titulo="Fuga de agua en el baño", descripcion="Gotea el sifón del lavamanos del baño principal."):
    archivos = {"archivo_foto": ("dano.png", _png(), "image/png")} if con_foto else None
    r = client.post("/mantenimiento/reportar-danio", data={"titulo": titulo, "descripcion": descripcion}, files=archivos, headers=auth(email))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _enlace(client, auth, reporte_id, **cuerpo):
    r = client.post(f"/mantenimiento/danios/{reporte_id}/enlace-tecnico", json=cuerpo, headers=auth(ADM))
    assert r.status_code == 201, r.text
    j = r.json()
    j["token"] = j["enlace"].rsplit("/", 1)[1]
    return j


def _estado(client, token, estado, nota="", foto=True):
    datos = {"nuevo_estado": estado, "nota": nota}
    archivos = {"archivo_foto": ("evidencia.png", _png((20, 140, 60)), "image/png")} if foto else None
    return client.post(f"/tecnico-publico/{token}/estado", data=datos, files=archivos)


# ---------------------------------------------------------------- crear, listar y anular (administrador)
def test_solo_el_administrador_crea_enlaces(client, auth):
    rid = _reporte(client, auth)
    for quien in (ANA, LUIS, CEL):
        assert client.post(f"/mantenimiento/danios/{rid}/enlace-tecnico", json={}, headers=auth(quien)).status_code == 403
    assert client.post(f"/mantenimiento/danios/{rid}/enlace-tecnico", json={}).status_code == 401
    e = _enlace(client, auth, rid, horas=24, etiqueta="  Plomero · Don Jaime ")
    assert e["estado"] == "Vigente" and e["etiqueta"] == "Plomero · Don Jaime" and e["enlace"].startswith("/tecnico/")
    assert len(e["token"]) >= 32                       # 192 bits: imposible de adivinar


def test_vigencia_por_defecto_y_topes(client, auth, db):
    rid = _reporte(client, auth)
    por_defecto = _enlace(client, auth, rid)
    db.expire_all()
    fila = db.get(EnlaceTecnico, por_defecto["id"])
    assert timedelta(hours=71) < fila.valido_hasta - ahora_utc() <= timedelta(hours=72)        # 72 h por defecto
    for horas in (0, 169):
        assert client.post(f"/mantenimiento/danios/{rid}/enlace-tecnico", json={"horas": horas}, headers=auth(ADM)).status_code == 422


def test_no_se_crea_enlace_para_reporte_inexistente_ni_solucionado(client, auth):
    assert client.post("/mantenimiento/danios/9999/enlace-tecnico", json={}, headers=auth(ADM)).status_code == 404
    rid = _reporte(client, auth)
    assert client.patch(f"/mantenimiento/cambiar-estado/{rid}", params={"nuevo_estado": "Solucionado"}, headers=auth(ADM)).status_code == 200
    r = client.post(f"/mantenimiento/danios/{rid}/enlace-tecnico", json={}, headers=auth(ADM))
    assert r.status_code == 400 and "solucionado" in r.json()["detail"].lower()


def test_un_enlace_nuevo_anula_el_anterior(client, auth):
    rid = _reporte(client, auth)
    viejo, nuevo = _enlace(client, auth, rid), _enlace(client, auth, rid)
    assert client.get(f"/tecnico-publico/{viejo['token']}").json()["enlace"]["estado"] == "Revocado"      # si reenviaron el viejo, ya no sirve
    assert client.get(f"/tecnico-publico/{nuevo['token']}").json()["enlace"]["estado"] == "Vigente"
    lista = client.get(f"/mantenimiento/danios/{rid}/enlaces-tecnico", headers=auth(ADM)).json()
    assert [x["estado"] for x in lista] == ["Vigente", "Revocado"]
    assert lista[0]["enlace"] and lista[1]["enlace"] is None          # de un enlace anulado no se vuelve a entregar la ruta
    assert client.get(f"/mantenimiento/danios/{rid}/enlaces-tecnico", headers=auth(ANA)).status_code == 403


def test_el_administrador_anula_un_enlace(client, auth):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    assert client.post(f"/mantenimiento/enlaces-tecnico/{e['id']}/revocar", headers=auth(ANA)).status_code == 403
    r = client.post(f"/mantenimiento/enlaces-tecnico/{e['id']}/revocar", headers=auth(ADM))
    assert r.status_code == 200 and r.json()["estado"] == "Revocado" and r.json()["enlace"] is None
    # desde ese instante, ni la página, ni la foto, ni el cambio de estado
    pub = client.get(f"/tecnico-publico/{e['token']}").json()
    assert pub["enlace"] == {"estado": "Revocado", "sirve": False, "valido_hasta": pub["enlace"]["valido_hasta"]} and pub["reporte"] is None
    assert client.get(f"/tecnico-publico/{e['token']}/foto").status_code == 404
    assert _estado(client, e["token"], "En Reparacion", "voy").status_code == 400
    assert client.post(f"/mantenimiento/enlaces-tecnico/{e['id']}/revocar", headers=auth(ADM)).status_code == 400      # ya no estaba vigente
    assert client.post("/mantenimiento/enlaces-tecnico/9999/revocar", headers=auth(ADM)).status_code == 404


# ---------------------------------------------------------------- lo que ve el técnico: lo mínimo
def test_la_pagina_publica_se_sirve_sin_cache_y_con_csp_estricta(client):
    r = client.get("/tecnico/cualquier-cosa")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"] and "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"] and r.headers["referrer-policy"] == "no-referrer"
    assert "/app/tecnico/tecnico.js" in r.text and "<style" not in r.text and "__MARCA_NOMBRE__" not in r.text      # nada inline; la marca ya se aplicó


def test_el_tecnico_ve_solo_lo_minimo_y_nunca_datos_del_residente(client, auth):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    r = client.get(f"/tecnico-publico/{e['token']}")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    rep = j["reporte"]
    assert set(rep) == {"titulo", "descripcion", "apartamento", "estado", "reportado", "tiene_foto", "estados_permitidos", "evidencias"}
    assert rep["apartamento"] == "Torre 1 Apt 101" and rep["tiene_foto"] is True and rep["estado"] == "Abierto"
    assert rep["estados_permitidos"] == ["En Reparacion", "Solucionado"]
    # el nombre, el correo y el id del residente ni siquiera viajan en la respuesta
    for prohibido in ("Ana Residente", "ana@conjunto.com", "usuario_id", "foto_url", "email", "telefono"):
        assert prohibido not in r.text


def test_un_token_falso_responde_404_igual_en_todas_las_rutas(client):
    assert client.get("/tecnico-publico/no-existe").status_code == 404
    assert client.get("/tecnico-publico/no-existe/foto").status_code == 404
    assert _estado(client, "no-existe", "En Reparacion", "x").status_code == 404


def test_la_foto_del_dano_solo_se_entrega_con_el_enlace_vigente(client, auth):
    con, sin = _reporte(client, auth), _reporte(client, auth, con_foto=False, titulo="Bombillo dañado", descripcion="El bombillo del pasillo no enciende.")
    e_con, e_sin = _enlace(client, auth, con), _enlace(client, auth, sin)
    r = client.get(f"/tecnico-publico/{e_con['token']}/foto")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/") and r.headers["cache-control"] == "no-store"
    assert client.get(f"/tecnico-publico/{e_con['token']}/foto", params={"miniatura": "true"}).status_code == 200
    assert client.get(f"/tecnico-publico/{e_sin['token']}/foto").status_code == 404
    assert client.get(f"/tecnico-publico/{e_sin['token']}").json()["reporte"]["tiene_foto"] is False


def test_un_enlace_vencido_no_entrega_ningun_dato(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    db.get(EnlaceTecnico, e["id"]).valido_hasta = ahora_utc() - timedelta(minutes=1)
    db.commit()
    j = client.get(f"/tecnico-publico/{e['token']}").json()
    assert j["enlace"]["estado"] == "Vencido" and j["enlace"]["sirve"] is False and j["reporte"] is None
    assert client.get(f"/tecnico-publico/{e['token']}/foto").status_code == 404
    assert _estado(client, e["token"], "En Reparacion", "voy").status_code == 400
    assert client.get(f"/mantenimiento/danios/{rid}/enlaces-tecnico", headers=auth(ADM)).json()[0]["estado"] == "Vencido"


# ---------------------------------------------------------------- lo que puede hacer el técnico
def test_el_tecnico_pasa_a_en_reparacion_queda_en_auditoria_y_avisa(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid, etiqueta="Plomero")
    r = _estado(client, e["token"], "En Reparacion", "Ya llegué, voy a cambiar el sifón.", foto=False)
    assert r.status_code == 200 and r.json()["estado"] == "En Reparacion" and r.json()["cerrado"] is False
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "En Reparacion"
    ev = db.query(EvidenciaDanio).filter(EvidenciaDanio.reporte_id == rid).one()
    assert ev.estado == "En Reparacion" and ev.nota.startswith("Ya llegué") and ev.foto is None
    # auditoría: sin actor (no tiene cuenta), pero con el enlace y la etiqueta
    a = db.query(Auditoria).filter(Auditoria.accion.like("Técnico cambió%")).one()
    assert a.actor_id is None and a.entidad == "Daño" and a.entidad_id == rid and "Abierto → En Reparacion" in a.detalle and f"enlace #{e['id']}" in a.detalle and "Plomero" in a.detalle
    visto = client.get("/auditoria/", params={"entidad": "Daño"}, headers=auth(ADM)).json()
    assert any("Técnico cambió estado" in f["accion"] for f in visto)
    # avisos: al residente y al administrador que creó el enlace
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    adm = db.query(Usuario).filter(Usuario.email == ADM).one()
    assert db.query(Notificacion).filter(Notificacion.usuario_id == ana.id, Notificacion.titulo == "Tu reporte está en reparación").count() == 1
    assert db.query(Notificacion).filter(Notificacion.usuario_id == adm.id, Notificacion.titulo == "El técnico actualizó un daño").count() == 1
    # el residente ve lo que dejó el técnico en su lista
    mio = client.get("/mantenimiento/listar-danios", headers=auth(ANA)).json()[0]
    assert mio["estado"] == "En Reparacion" and mio["evidencias"][0]["nota"].startswith("Ya llegué") and mio["evidencias"][0]["tiene_foto"] is False
    # y el técnico ve su propio historial, ahora solo con «Solucionado» disponible
    otra = client.get(f"/tecnico-publico/{e['token']}").json()["reporte"]
    assert otra["estados_permitidos"] == ["Solucionado"] and otra["evidencias"][0]["estado"] == "En Reparacion"


def test_solucionado_exige_nota_y_foto_y_cierra_el_enlace(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    sin_foto = _estado(client, e["token"], "Solucionado", "Cambié el sifón y quedó seco.", foto=False)
    sin_nota = _estado(client, e["token"], "Solucionado", "ok", foto=True)
    assert sin_foto.status_code == 400 and "foto" in sin_foto.json()["detail"].lower()
    assert sin_nota.status_code == 400 and "nota" in sin_nota.json()["detail"].lower()
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Abierto"            # los intentos fallidos no cambiaron nada

    ok = _estado(client, e["token"], "Solucionado", "Cambié el sifón y quedó seco.")
    assert ok.status_code == 200 and ok.json()["cerrado"] is True
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Solucionado" and db.get(EnlaceTecnico, e["id"]).cerrado_en is not None
    # el enlace se cerró solo: ni datos, ni foto, ni más cambios
    cerrado = client.get(f"/tecnico-publico/{e['token']}").json()
    assert cerrado["enlace"]["estado"] == "Cerrado" and cerrado["reporte"] is None
    assert client.get(f"/tecnico-publico/{e['token']}/foto").status_code == 404
    assert _estado(client, e["token"], "En Reparacion", "otra vez").status_code == 400
    assert client.get(f"/mantenimiento/danios/{rid}/enlaces-tecnico", headers=auth(ADM)).json()[0]["estado"] == "Cerrado"
    assert db.query(Notificacion).filter(Notificacion.titulo == "Tu reporte quedó solucionado").count() == 1


def test_el_tecnico_no_puede_poner_otros_estados_ni_volver_atras(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    for malo in ("Abierto", "En Revision", "Cerrado", "", "<script>"):
        assert _estado(client, e["token"], malo, "intento", foto=False).status_code == 422
    assert _estado(client, e["token"], "En Reparacion", "voy", foto=False).status_code == 200
    again = _estado(client, e["token"], "En Reparacion", "otra vez", foto=False)
    assert again.status_code == 400 and "Solucionado" in again.json()["detail"]            # solo puede avanzar
    db.expire_all()
    assert db.query(EvidenciaDanio).filter(EvidenciaDanio.reporte_id == rid).count() == 1


def test_una_foto_falsa_se_rechaza_y_no_cambia_nada(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    falso = client.post(f"/tecnico-publico/{e['token']}/estado", data={"nuevo_estado": "Solucionado", "nota": "Quedó listo del todo."},
                        files={"archivo_foto": ("virus.jpg", b"MZ esto no es una imagen", "image/jpeg")})
    assert falso.status_code == 400
    texto = client.post(f"/tecnico-publico/{e['token']}/estado", data={"nuevo_estado": "Solucionado", "nota": "Quedó listo del todo."},
                        files={"archivo_foto": ("a.txt", b"hola", "text/plain")})
    assert texto.status_code == 400
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Abierto" and db.query(EvidenciaDanio).count() == 0
    assert db.get(EnlaceTecnico, e["id"]).cerrado_en is None            # el enlace sigue vigente para reintentar con una foto buena


def test_la_nota_se_limpia_y_se_limita(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    assert _estado(client, e["token"], "En Reparacion", "linea1\x00\x07\nlinea2 " + "x" * 600, foto=False).status_code == 200
    db.expire_all()
    nota = db.query(EvidenciaDanio).one().nota
    assert "\x00" not in nota and "\x07" not in nota and "linea1" in nota and "\n" in nota and len(nota) == 500


def test_un_enlace_solo_sirve_para_su_reporte(client, auth, db):
    a, b = _reporte(client, auth), _reporte(client, auth, email=LUIS, titulo="Portón trabado", descripcion="El portón del parqueadero no abre bien.")
    ea, eb = _enlace(client, auth, a), _enlace(client, auth, b)
    assert _estado(client, ea["token"], "En Reparacion", "voy con el de Ana", foto=False).status_code == 200
    db.expire_all()
    assert db.get(ReporteDanio, a).estado == "En Reparacion" and db.get(ReporteDanio, b).estado == "Abierto"
    assert client.get(f"/tecnico-publico/{eb['token']}").json()["reporte"]["apartamento"] == "Torre 2 Apt 202"


def test_si_quien_reporto_es_inquilino_tambien_se_avisa_al_propietario(client, auth, db):
    _, h_inq = inquilino_activo(client, auth, db)
    r = client.post("/mantenimiento/reportar-danio", data={"titulo": "Cerradura dañada", "descripcion": "La cerradura de la puerta no gira."}, headers=h_inq)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    e = _enlace(client, auth, rid)
    assert _estado(client, e["token"], "En Reparacion", "voy a revisarla", foto=False).status_code == 200
    db.expire_all()
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    marta = db.query(Usuario).filter(Usuario.email == "marta@correo.com").one()
    for quien in (marta, ana):
        assert db.query(Notificacion).filter(Notificacion.usuario_id == quien.id, Notificacion.titulo == "Tu reporte está en reparación").count() == 1


# ---------------------------------------------------------------- fotos de evidencia: quién las ve
def test_la_evidencia_la_ven_el_dueno_del_reporte_y_el_administrador(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    assert _estado(client, e["token"], "Solucionado", "Todo listo, probé varias veces.").status_code == 200
    ev = client.get("/mantenimiento/listar-danios", headers=auth(ANA)).json()[0]["evidencias"][0]
    assert ev["tiene_foto"] is True
    ruta = f"/mantenimiento/danios/{rid}/evidencias/{ev['id']}/foto"
    for quien, esperado in ((ANA, 200), (ADM, 200), (LUIS, 403), (CEL, 403)):
        assert client.get(ruta, headers=auth(quien)).status_code == esperado, quien
    assert client.get(ruta).status_code == 401
    assert client.get(ruta, headers=auth(ADM), params={"miniatura": "true"}).status_code == 200
    assert client.get(f"/mantenimiento/danios/{rid}/evidencias/9999/foto", headers=auth(ADM)).status_code == 404
    otro = _reporte(client, auth, email=LUIS, titulo="Otro daño", descripcion="Algo se dañó en otra parte del conjunto.")
    assert client.get(f"/mantenimiento/danios/{otro}/evidencias/{ev['id']}/foto", headers=auth(ADM)).status_code == 404      # la evidencia no se «presta» a otro reporte


def test_listar_danios_sigue_igual_sin_tecnico(client, auth):
    rid = _reporte(client, auth)
    mio = client.get("/mantenimiento/listar-danios", headers=auth(ANA)).json()
    assert mio[0]["id"] == rid and mio[0]["evidencias"] == [] and mio[0]["estado"] == "Abierto"


# ---------------------------------------------------------------- límites contra abuso
def test_limite_de_intentos_por_ip(client, auth):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    codigos = [_estado(client, e["token"], "Inventado", "x", foto=False).status_code for _ in range(11)]
    assert codigos[:10] == [422] * 10 and codigos[10] == 429


def test_limite_por_enlace_aunque_cambie_la_ip(client, auth):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    for _ in range(12):
        limitador.CAMBIOS_TECNICO_IP.reiniciar()                    # como si cada intento viniera de una IP distinta
        assert _estado(client, e["token"], "Inventado", "x", foto=False).status_code == 422
    limitador.CAMBIOS_TECNICO_IP.reiniciar()
    assert _estado(client, e["token"], "Inventado", "x", foto=False).status_code == 429


def test_un_envio_enorme_se_corta_antes_de_leer_la_foto(client, auth, db):
    rid = _reporte(client, auth)
    e = _enlace(client, auth, rid)
    r = client.post(f"/tecnico-publico/{e['token']}/estado", data={"nuevo_estado": "En Reparacion"},
                    files={"archivo_foto": ("grande.jpg", b"0" * (7 * 1024 * 1024), "image/jpeg")})
    assert r.status_code == 413
    db.expire_all()
    assert db.get(ReporteDanio, rid).estado == "Abierto"


# ---------------------------------------------------------------- base de datos y service worker
def _cfg(url: str) -> Config:
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def test_migracion_0026_crea_solo_tablas_nuevas_y_se_puede_devolver():
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    cfg = _cfg(f"sqlite:///{ruta}")
    command.upgrade(cfg, "0025")
    con = sqlite3.connect(ruta)
    antes = [c[1] for c in con.execute("PRAGMA table_info(reportes_danios)")]
    tablas = {t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "enlaces_tecnico" not in tablas and "evidencias_danio" not in tablas
    con.close()

    command.upgrade(cfg, "0026")
    command.upgrade(cfg, "0026")             # correrla de nuevo no rompe nada
    con = sqlite3.connect(ruta)
    tablas = {t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"enlaces_tecnico", "evidencias_danio"} <= tablas
    assert [c[1] for c in con.execute("PRAGMA table_info(reportes_danios)")] == antes         # la tabla de daños NO cambió
    assert {"token", "reporte_id", "valido_hasta", "revocado_en", "cerrado_en"} <= {c[1] for c in con.execute("PRAGMA table_info(enlaces_tecnico)")}
    indices = {i[1]: i[2] for i in con.execute("PRAGMA index_list(enlaces_tecnico)")}
    assert indices.get("ix_enlaces_tecnico_token") == 1                                          # el token es único
    con.close()

    command.downgrade(cfg, "0025")
    con = sqlite3.connect(ruta)
    tablas = {t[0] for t in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "enlaces_tecnico" not in tablas and "evidencias_danio" not in tablas and "reportes_danios" in tablas
    con.close()


def test_el_service_worker_no_descarga_la_pagina_del_tecnico_en_los_celulares_de_los_residentes(client):
    sw = client.get("/app/sw.js").text
    assert "estilos.css" in sw and "tecnico/" not in sw and "pase/" not in sw
