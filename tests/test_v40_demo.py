# tests/test_v40_demo.py — «Solicitar demo» (ruta pública que ESCRIBE en la base: debe ser difícil de abusar).
# v4.8: el aviso va por Telegram al vendedor (no hay pantalla ni campana para el administrador) y la ruta solo existe si LANDING_ACTIVA=1.
import pytest
from sqlalchemy import func

from app import avisos_demo
from app.models import Notificacion, SolicitudDemo

_ENVIAR_REAL = avisos_demo.enviar      # la verdadera, guardada antes de que cada prueba la reemplace

BASE = {"nombre": "Marcela Rojas", "conjunto": "Conjunto Reserva del Sol", "celular": "310 000 0001", "acepto_datos": True}


def _enviar(client, **cambios):
    return client.post("/demo/solicitar", json={**BASE, **cambios})


def _filas(db):
    db.expire_all()
    return db.query(func.count(SolicitudDemo.id)).scalar()


# ------------------------------------------------------------------ enviar
@pytest.fixture(autouse=True)
def avisos(monkeypatch):
    """Ninguna prueba toca la red: el envío real se reemplaza por una lista donde queda lo que SE HABRÍA enviado."""
    enviados = []
    monkeypatch.setattr(avisos_demo, "enviar", lambda texto: enviados.append(texto) or True)
    return enviados


def test_una_solicitud_valida_se_guarda_y_avisa_por_telegram_al_vendedor(client, db, avisos):
    r = _enviar(client, correo="marcela@ejemplo.com", ciudad="Facatativá", apartamentos=120, mensaje="Quiero ver la portería")
    assert r.status_code == 201 and r.json()["ok"] is True and r.headers["cache-control"] == "no-store"
    s = db.query(SolicitudDemo).one()
    assert (s.nombre, s.conjunto, s.celular, s.correo, s.ciudad, s.apartamentos, s.estado, s.origen) == \
           ("Marcela Rojas", "Conjunto Reserva del Sol", "3100000001", "marcela@ejemplo.com", "Facatativá", 120, "Nueva", "formulario")
    assert s.acepto_datos is not None
    assert len(avisos) == 1
    for dato in ("Nueva solicitud de demo", "Marcela Rojas", "Conjunto Reserva del Sol", "3100000001", "marcela@ejemplo.com", "Facatativá", "120", "Quiero ver la portería",
                 "Escríbele por WhatsApp: https://wa.me/573100000001", "el formulario"):
        assert dato in avisos[0], dato


def test_nadie_dentro_de_la_app_recibe_campana_ni_ve_las_solicitudes(client, db, auth):
    """v4.7: los prospectos son del vendedor, no del administrador de un conjunto."""
    _enviar(client)
    assert db.query(Notificacion).count() == 0
    h = auth("admin@conjunto.com")
    assert client.get("/demo/solicitudes", headers=h).status_code in (404, 405)
    assert client.patch("/demo/solicitudes/1", json={"estado": "Contactada"}, headers=h).status_code in (404, 405)
    assert "/demo/solicitudes" not in client.get("/openapi.json").text


def test_si_telegram_esta_caido_la_persona_igual_recibe_el_ok_y_el_contacto_queda_guardado(client, db, monkeypatch):
    import httpx
    from app import config
    monkeypatch.setattr(avisos_demo, "enviar", _ENVIAR_REAL)           # el envío VERDADERO, pero con internet caído
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:token")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "987")

    def red_caida(url, json, timeout):
        raise httpx.ConnectTimeout("sin red")
    monkeypatch.setattr(avisos_demo.httpx, "post", red_caida)
    r = _enviar(client)
    assert r.status_code == 201 and _filas(db) == 1


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


def test_el_campo_trampa_de_robots_responde_ok_pero_no_guarda_ni_avisa(client, db, avisos):
    r = _enviar(client, sitio_web="http://spam.example")
    assert r.status_code == 201 and r.json()["ok"] is True          # el robot no debe enterarse de que lo descubrimos
    assert _filas(db) == 0 and avisos == []


def test_el_mismo_celular_no_se_duplica_en_24_horas_ni_avisa_dos_veces(client, db, avisos):
    assert _enviar(client).status_code == 201
    assert _enviar(client, nombre="Otra Persona", conjunto="Otro Conjunto").status_code == 201
    assert _filas(db) == 1 and len(avisos) == 1
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


def test_el_envio_whatsapp_se_guarda_marcado(client, db, avisos):
    assert _enviar(client, origen="whatsapp").status_code == 201
    s = db.query(SolicitudDemo).one()
    assert s.origen == "whatsapp"
    assert len(avisos) == 1 and "botón «Solicitar demo»" in avisos[0]


def test_no_se_guarda_la_ip_ni_datos_del_dispositivo():
    columnas = {c.name for c in SolicitudDemo.__table__.columns}
    assert not (columnas & {"ip", "ip_cliente", "user_agent", "agente", "dispositivo", "huella"})


# ------------------------------------------------------------------ la demo solo existe donde la landing está activa
def test_con_la_landing_apagada_la_solicitud_de_demo_no_existe(client, db, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "LANDING_ACTIVA", False)
    assert _enviar(client).status_code == 404 and _filas(db) == 0


# ------------------------------------------------------------------ el envío real (Telegram), sin salir a internet
class _Resp:
    def __init__(self, codigo=200):
        self.status_code = codigo


@pytest.fixture()
def telegram(monkeypatch):
    """Vuelve a poner el envío real y deja listo un httpx.post falso que guarda lo que habría pedido."""
    from app import config
    monkeypatch.undo()                       # quita el reemplazo de `avisos` para probar la función verdadera
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123456:token-secreto")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "987654321")
    return monkeypatch, []


def test_el_aviso_va_a_telegram_con_el_chat_y_el_texto(telegram):
    mp, llamadas = telegram
    mp.setattr(avisos_demo.httpx, "post", lambda url, json, timeout: llamadas.append((url, json, timeout)) or _Resp(200))
    assert avisos_demo.enviar("Hola ñandú\ncon tilde á") is True
    url, cuerpo, timeout = llamadas[0]
    assert url == "https://api.telegram.org/bot123456:token-secreto/sendMessage" and timeout <= 10
    assert cuerpo == {"chat_id": "987654321", "text": "Hola ñandú\ncon tilde á", "disable_web_page_preview": True}
    assert "parse_mode" not in cuerpo          # el texto lo escribió un desconocido: nunca se interpreta como formato


def test_un_aviso_muy_largo_se_recorta(telegram):
    mp, llamadas = telegram
    mp.setattr(avisos_demo.httpx, "post", lambda url, json, timeout: llamadas.append(json) or _Resp(200))
    avisos_demo.enviar("x" * 9000)
    assert len(llamadas[0]["text"]) == avisos_demo.MAX_TEXTO


def test_sin_token_o_sin_chat_no_se_intenta_nada(telegram):
    from app import config
    mp, llamadas = telegram
    mp.setattr(avisos_demo.httpx, "post", lambda *a, **k: llamadas.append(1) or _Resp(200))
    mp.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    assert avisos_demo.enviar("hola") is False
    mp.setattr(config, "TELEGRAM_BOT_TOKEN", "123:t")
    mp.setattr(config, "TELEGRAM_CHAT_ID", "")
    assert avisos_demo.enviar("hola") is False and llamadas == []


def test_si_telegram_falla_no_hay_excepcion_y_el_token_no_se_escribe_en_el_registro(telegram, caplog):
    import logging
    import httpx
    mp, _ = telegram

    def red_caida(url, json, timeout):
        raise httpx.ConnectError(f"no hay red en {url}")      # httpx suele incluir la dirección completa (con el token) en el mensaje
    mp.setattr(avisos_demo.httpx, "post", red_caida)
    with caplog.at_level(logging.INFO, logger="ciudadela.avisos"):
        assert avisos_demo.enviar("hola") is False
        mp.setattr(avisos_demo.httpx, "post", lambda url, json, timeout: _Resp(401))
        assert avisos_demo.enviar("hola") is False
    registro = caplog.text
    assert "ConnectError" in registro and "401" in registro
    assert "token-secreto" not in registro and "987654321" not in registro


def test_la_landing_abre_whatsapp_directo_con_los_datos_escritos(client):
    # v5.0: ya no hay un último paso que pregunte «¿quieres ir a WhatsApp?»: «Solicitar demo» abre WhatsApp en el mismo toque.
    js = client.get("/landing/landing.js").text
    assert "Enviar mis datos por WhatsApp" not in js
    assert "abrirWhatsApp(url)" in js and "mensajeConDatos" in js and "encodeURIComponent" in js
