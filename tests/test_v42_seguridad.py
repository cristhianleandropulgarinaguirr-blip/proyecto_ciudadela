# tests/test_v42_seguridad.py — v4.2: interruptor de la documentación interactiva (/docs).
# La app se crea al importarse, así que cada caso corre en un proceso aparte con su propia variable de entorno.
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CODIGO = (
    "from fastapi.testclient import TestClient\n"
    "from app.main import app\n"
    "c = TestClient(app)\n"
    "print(c.get('/docs').status_code, c.get('/redoc').status_code, c.get('/openapi.json').status_code, c.get('/salud').status_code)\n"
)


def _estado_de_docs(valor):
    tmp = tempfile.mkdtemp(prefix="docs_")
    entorno = {**os.environ, "SECRET_KEY": "clave-de-pruebas-solo-para-tests-0123456789abcdef",
               "DATABASE_URL": f"sqlite:///{tmp}/t.db", "UPLOAD_DIR": f"{tmp}/up", "ALMACEN": "local"}
    if valor is None:
        entorno.pop("DOCS_ACTIVAS", None)
    else:
        entorno["DOCS_ACTIVAS"] = valor
    r = subprocess.run([sys.executable, "-c", CODIGO], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip().splitlines()[-1].split()


def test_por_defecto_la_documentacion_esta_visible():
    assert _estado_de_docs(None)[:3] == ["200", "200", "200"]


def test_con_docs_activas_en_cero_desaparecen_las_tres_rutas_pero_la_app_sigue_viva():
    docs, redoc, openapi, salud = _estado_de_docs("0")
    assert (docs, redoc, openapi) == ("404", "404", "404")
    assert salud == "200"


# ------------------------------------------------------------------ tope global de «Solicitar demo» (no depende de la IP)
def test_cambiar_la_cabecera_x_forwarded_for_no_evita_el_tope_global_de_demo(client, db, monkeypatch):
    from app import limitador
    from app.models import SolicitudDemo
    monkeypatch.setattr(limitador.SOLICITUDES_DEMO_TOTAL, "maximo", 3)
    base = {"nombre": "Robot Uno", "conjunto": "Conjunto Falso", "acepto_datos": True}
    codigos = []
    for i in range(6):
        # cada envío «viene» de una IP distinta (cabecera inventada) y de un celular distinto: el tope por IP y el anti-duplicado no lo frenan
        r = client.post("/demo/solicitar", json={**base, "celular": f"31000000{i:02d}"}, headers={"X-Forwarded-For": f"203.0.113.{i + 1}"})
        codigos.append(r.status_code)
    assert codigos == [201, 201, 201, 429, 429, 429]
    db.expire_all()
    assert db.query(SolicitudDemo).count() == 3


# ------------------------------------------------------------------ landing: quién atiende el WhatsApp
def _meta_marca(html):
    import json
    import re
    from html import unescape
    m = re.search(r'<meta name="marca" content="([^"]*)"', html)
    assert m, "falta <meta name=marca>"
    return json.loads(unescape(m.group(1)))


def test_la_landing_recibe_el_nombre_de_quien_atiende_el_whatsapp(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEMO_WHATSAPP", "573224101828")
    monkeypatch.setattr(config, "DEMO_CONTACTO", "Cristhian")
    d = _meta_marca(client.get("/").text)
    assert d["contacto"] == "Cristhian" and d["whatsapp"] == "573224101828"


def test_sin_contacto_configurado_el_valor_va_vacio_y_un_nombre_con_comillas_no_rompe_la_pagina(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "DEMO_CONTACTO", "")
    assert _meta_marca(client.get("/").text)["contacto"] == ""
    monkeypatch.setattr(config, "DEMO_CONTACTO", 'Cris"><script>alert(1)</script>')
    html = client.get("/").text
    assert "<script>alert(1)</script>" not in html
    assert _meta_marca(html)["contacto"].startswith("Cris")


# ------------------------------------------------------------------ landing: guía de instalación de la PWA
def test_la_landing_trae_la_guia_de_instalacion_para_android_iphone_y_computador(client):
    import re
    html = client.get("/").text
    for panel in ("ins-android", "ins-ios", "ins-escritorio"):
        assert f'id="{panel}"' in html, panel
        assert f'data-panel="{panel}"' in html, panel
    assert 'id="instalar"' in html and 'href="#instalar"' in html
    assert "Instalar app" in html and "Agregar a inicio" in html          # lo que de verdad dicen Chrome (Android) y Safari (iPhone)
    # Cada dibujo reutiliza el celular definido una sola vez, y ningún enlace interno apunta a un destino que no existe.
    assert 'id="fig-tel"' in html and html.count('<use href="#fig-tel"/>') >= 6
    ids = set(re.findall(r'id="([^"]+)"', html))
    rotos = [a for a in re.findall(r'href="#([^"]+)"', html) if a not in ids]
    assert rotos == []


def test_la_landing_sigue_sin_cargar_nada_de_otros_sitios_salvo_las_fuentes(client):
    import re
    r = client.get("/")
    externos = set(re.findall(r'(?:src|href)="(https?://[^"]+)"', r.text))
    assert all(u.startswith("https://fonts.") for u in externos), externos
    assert "script-src 'self'" in r.headers["content-security-policy"]
