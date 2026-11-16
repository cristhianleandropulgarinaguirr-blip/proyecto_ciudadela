# tests/test_v40_marca.py — Fase 4: WHITE-LABEL (nombre, color y logos del cliente) y landing en «/».
import json
import re
from html import unescape

import pytest

from app import config, marca


def _meta_marca(html: str) -> dict:
    m = re.search(r'<meta name="marca" content="([^"]*)"', html)
    assert m, "falta <meta name=marca>"
    return json.loads(unescape(m.group(1)))


@pytest.fixture()
def con_marca(monkeypatch):
    """Cambia la marca en memoria (sin tocar el entorno) y la deja como estaba al terminar la prueba.
    El service worker se calcula una vez por arranque del servidor (en producción la marca cambia con un reinicio); aquí se vacía esa memoria."""
    from app import main
    main._sw_cache.clear()

    def poner(**valores):
        for k, v in valores.items():
            monkeypatch.setattr(config, k, v)
        main._sw_cache.clear()
    yield poner
    monkeypatch.undo()
    main._sw_cache.clear()


# ------------------------------------------------------------------ valores por defecto: nada cambia
def test_sin_configurar_la_app_es_ciudadela_digital(client):
    html = client.get("/app/").text
    assert "<title>Ciudadela Digital ·" in html
    assert "__MARCA_" not in html                                   # ningún marcador sin reemplazar
    assert 'content="#07304A"' in html
    assert 'id="marca-estilo"' not in html                          # sin MARCA_COLOR no se inyecta ningún estilo
    datos = _meta_marca(html)
    assert datos["nombre"] == "Ciudadela Digital" and datos["asistente"] == "Ciudabot" and datos["color"] == ""


def test_manifest_por_defecto(client):
    r = client.get("/app/manifest.webmanifest")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "Ciudadela Digital" and m["short_name"] == "Ciudadela" and m["start_url"]


# ------------------------------------------------------------------ white-label
def test_nombre_y_color_del_cliente_llegan_a_la_pagina_el_manifest_y_el_service_worker(client, con_marca):
    con_marca(MARCA_NOMBRE="Torres del Alba", MARCA_NOMBRE_CORTO="Alba", MARCA_COLOR="#8A1C2B", MARCA_ESLOGAN="Vive tranquilo, vive en Alba.")
    html = client.get("/app/").text
    assert "<title>Torres del Alba ·" in html and 'content="Alba"' in html
    assert 'id="marca-estilo"' in html and "#8a1c2b" in html.lower()
    d = _meta_marca(html)
    assert d["nombre"] == "Torres del Alba" and d["color"] == "#8a1c2b" and d["eslogan"] == "Vive tranquilo, vive en Alba."
    m = client.get("/app/manifest.webmanifest").json()
    assert m["name"] == "Torres del Alba" and m["short_name"] == "Alba" and m["theme_color"] == d["tema_claro"]
    sw = client.get("/app/sw.js").text
    assert '"Torres del Alba"' in sw and "__NOMBRE__" not in sw


def test_un_nombre_con_comillas_y_etiquetas_no_rompe_la_pagina(client, con_marca):
    con_marca(MARCA_NOMBRE='Alba "<script>alert(1)</script>" & Cía')
    html = client.get("/app/").text
    assert "<script>alert(1)</script>" not in html
    assert _meta_marca(html)["nombre"] == 'Alba "<script>alert(1)</script>" & Cía'      # el dato llega intacto, pero escapado dentro del HTML
    sw = client.get("/app/sw.js").text
    assert "<script>" not in sw


def test_un_color_roto_se_ignora_en_vez_de_romper_la_app(client, con_marca):
    for malo in ("rojo", "#12345", "#GGGGGG", "8a1c2b", "red;}body{display:none"):
        con_marca(MARCA_COLOR=malo)
        html = client.get("/app/").text
        assert 'id="marca-estilo"' not in html, malo
        assert "display:none" not in html


def test_el_service_worker_cambia_de_version_cuando_cambia_la_marca(client, con_marca):
    def version():
        m = re.search(r'const VERSION = "ciudadela-([0-9a-f]+)"', client.get("/app/sw.js").text)
        assert m
        return m.group(1)
    v1 = version()
    assert version() == v1                       # sin cambios, la versión es estable
    con_marca(MARCA_COLOR="#0b6e4f")
    assert version() != v1


@pytest.mark.parametrize("color", ["#8a1c2b", "#f5d90a", "#0b6e4f", "#1a1a1a", "#ffffff", "#000000", "#fefefe"])
def test_cualquier_color_deja_el_texto_de_los_botones_legible(color):
    p = marca.paleta(color)
    assert marca.contraste(p["primario"], marca.TEXTO_SOBRE_PRIMARIO) >= 4.5
    for modo in ("claro", "oscuro"):
        assert all(re.fullmatch(r"#[0-9a-f]{6}|\d+, \d+, \d+", v) for v in p[modo].values())


def test_los_colores_de_rol_no_se_tocan(con_marca):
    con_marca(MARCA_COLOR="#8a1c2b")
    css = marca.css_de_marca()
    assert ':not([data-rol="Residente"])' in css and ':not([data-rol="Guardia"])' in css and ':not([data-rol="Inquilino"])' in css


# ------------------------------------------------------------------ logos del cliente
def test_el_logo_del_cliente_reemplaza_al_de_siempre_y_solo_los_nombres_permitidos(client, con_marca, tmp_path):
    (tmp_path / "icono.png").write_bytes(b"\x89PNG-del-cliente")
    (tmp_path / "secreto.txt").write_text("no se sirve")
    con_marca(MARCA_DIR=tmp_path)
    r = client.get("/app/img/icono.png")
    assert r.status_code == 200 and r.content == b"\x89PNG-del-cliente"
    assert client.get("/app/img/icono-crema.png").content != b"\x89PNG-del-cliente"        # los que el cliente no puso siguen siendo los de siempre
    assert client.get("/app/img/secreto.txt").status_code == 404
    assert client.get("/app/img/..%2Fsecreto.txt").status_code in (400, 404)


def test_el_logo_del_cliente_tambien_se_sirve_con_rutas_de_windows(con_marca, tmp_path):
    """En Windows Starlette entrega la ruta con barra invertida («img\\icono.png»). Se simula aquí para no depender del sistema operativo."""
    import asyncio
    from app.main import AppEstatica, FRONTEND_DIR
    (tmp_path / "icono.png").write_bytes(b"\x89PNG-del-cliente")
    con_marca(MARCA_DIR=tmp_path)
    estatica = AppEstatica(directory=FRONTEND_DIR, html=True)
    for ruta in ("img\\icono.png", "img/icono.png"):
        r = asyncio.run(estatica.get_response(ruta, {"method": "GET", "headers": []}))
        assert r.status_code == 200 and open(r.path, "rb").read() == b"\x89PNG-del-cliente", ruta


def test_cambiar_un_logo_cambia_la_huella(con_marca, tmp_path):
    con_marca(MARCA_DIR=tmp_path)
    antes = marca.huella()
    (tmp_path / "icono.png").write_bytes(b"nuevo")
    assert marca.huella() != antes


# ------------------------------------------------------------------ landing en «/»
def test_la_raiz_muestra_la_landing_con_su_politica_de_seguridad(client):
    r = client.get("/")
    assert r.status_code == 200 and 'id="demo"' in r.text and "Solicitar demo" in r.text
    assert "__MARCA_" not in r.text
    csp = r.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "<script>" not in r.text.replace('<script src="/landing/landing.js" defer></script>', "")       # nada de JavaScript dentro de la página
    assert r.headers["cache-control"] == "no-cache"


def test_la_landing_toma_la_marca_y_el_whatsapp(client, con_marca):
    con_marca(MARCA_NOMBRE="Torres del Alba", DEMO_WHATSAPP="573109998877", DEMO_CORREO="ventas@alba.co")
    r = client.get("/")
    assert "Torres del Alba" in r.text
    d = _meta_marca(r.text)
    assert d["whatsapp"] == "573109998877" and d["correo_ventas"] == "ventas@alba.co"


def test_sin_whatsapp_configurado_no_hay_numero_en_la_pagina(client):
    assert _meta_marca(client.get("/").text)["whatsapp"] == ""


@pytest.mark.parametrize("crudo,esperado", [("3101234567", "573101234567"), ("+57 310 123 4567", "573101234567"), ("12345", ""), ("abc", ""), ("", "")])
def test_el_whatsapp_se_normaliza_y_uno_invalido_no_deja_un_enlace_roto(crudo, esperado, monkeypatch):
    import importlib
    monkeypatch.setenv("DEMO_WHATSAPP", crudo)
    try:
        assert importlib.reload(config).DEMO_WHATSAPP == esperado
    finally:
        monkeypatch.delenv("DEMO_WHATSAPP", raising=False)
        importlib.reload(config)


def test_con_la_landing_apagada_la_raiz_lleva_a_la_app(client, con_marca):
    con_marca(LANDING_ACTIVA=False)
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"] == "/app/"


def test_los_archivos_de_la_landing_se_sirven_pero_la_plantilla_cruda_no(client):
    assert client.get("/landing/landing.css").status_code == 200
    js = client.get("/landing/landing.js")
    assert js.status_code == 200 and "/demo/solicitar" in js.text
    assert client.get("/landing/index.html").status_code == 404
    assert client.get("/landing/../index.html").status_code in (400, 404)


def test_la_app_sigue_en_app_y_la_documentacion_en_docs(client):
    assert client.get("/app/").status_code == 200
    assert client.get("/docs").status_code == 200


def test_el_asistente_se_presenta_con_el_nombre_de_la_marca(monkeypatch):
    import importlib
    from app.routers import asistente
    monkeypatch.setenv("MARCA_ASISTENTE", "Alba")
    monkeypatch.setenv("MARCA_NOMBRE", "Torres del Alba")
    try:
        importlib.reload(config)
        asistente = importlib.reload(asistente)
        assert "«Alba»" in asistente.SISTEMA_CHAT and "Torres del Alba" in asistente.SISTEMA_CHAT and "Ciudabot" not in asistente.SISTEMA_CHAT
    finally:
        monkeypatch.delenv("MARCA_ASISTENTE", raising=False)
        monkeypatch.delenv("MARCA_NOMBRE", raising=False)
        importlib.reload(config)
        importlib.reload(asistente)
