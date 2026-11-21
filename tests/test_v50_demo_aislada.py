# tests/test_v50_demo_aislada.py — v5.0: la demo vive APARTE de la app real (MODO_DEMO), el administrador de la demo local y el flujo directo a WhatsApp.
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app import seed_demo
from app.models import Rol, Usuario
from app.security import verificar_password

RAIZ = Path(__file__).resolve().parent.parent
CLAVE = "Demo-clave-123"


# ---------------------------------------------------------------- administrador de la demo local
def test_con_admin_crea_un_administrador_activo_con_la_clave_de_la_demo(db):
    # La base de pruebas trae usuarios reales de otras pruebas: se borran para simular una base EXCLUSIVA de la demo.
    db.query(Usuario).delete()
    db.commit()
    r = seed_demo.crear(db, CLAVE, con_admin=True)
    admin = db.query(Usuario).filter(Usuario.email == seed_demo.EMAIL_ADMIN_DEMO).one()
    assert admin.esta_activo and verificar_password(CLAVE, admin.password_encriptada)
    assert db.query(Rol).filter(Rol.id == admin.rol_id).one().nombre == "Administrador"
    assert r["cuentas"][0][1] == seed_demo.EMAIL_ADMIN_DEMO


def test_sin_con_admin_no_se_crea_ningun_administrador_con_clave_conocida(db):
    seed_demo.crear(db, CLAVE, forzar=True)
    assert db.query(Usuario).filter(Usuario.email == seed_demo.EMAIL_ADMIN_DEMO).first() is None


def test_con_admin_se_niega_si_la_base_tiene_usuarios_reales(db):
    """El administrador con clave conocida jamás debe convivir con datos reales (la base de pruebas ya trae usuarios 'reales')."""
    with pytest.raises(ValueError, match="reales"):
        seed_demo.crear(db, CLAVE, con_admin=True)
    assert db.query(Usuario).filter(Usuario.email.like(f"%@{seed_demo.DOMINIO}")).count() == 0      # no quedó nada a medias


def test_preparar_local_es_idempotente(db):
    db.query(Usuario).delete()
    db.commit()
    assert seed_demo.preparar_local(db, CLAVE) is not None
    n = db.query(Usuario).count()
    assert seed_demo.preparar_local(db, CLAVE) is None          # segunda vez: no toca nada
    assert db.query(Usuario).count() == n


# ---------------------------------------------------------------- MODO_DEMO: configuración aislada (en un proceso aparte: se lee al importar)
def _config(**extra):
    tmp = tempfile.mkdtemp(prefix="demo_")
    entorno = {**os.environ, "SECRET_KEY": "clave-de-pruebas-solo-para-tests-0123456789abcdef", "DATABASE_URL": f"sqlite:///{tmp}/real.db",
               "UPLOAD_DIR": f"{tmp}/up", "ALMACEN": "supabase", "BCRYPT_ROUNDS": "4"}
    entorno.pop("MODO_DEMO", None)
    entorno.pop("DEMO_DATABASE_URL", None)
    entorno.update(extra)
    codigo = ("from app import config, sesiones, security\n"
              "print(config.DATABASE_URL, '|', config.UPLOAD_DIR, '|', config.ALMACEN, '|', sesiones.COOKIE, '|', security.SECRET_KEY.endswith(':modo-demo'))")
    return subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120)


def test_sin_modo_demo_todo_sigue_igual_que_antes():
    r = _config()
    assert r.returncode == 0, r.stderr[-600:]
    bd, subidas, almacen, cookie, clave_demo = [x.strip() for x in r.stdout.strip().splitlines()[-1].split("|")]
    assert bd.endswith("/real.db") and subidas.endswith("/up") and almacen == "supabase" and cookie == "ciudadela_rt" and clave_demo == "False"


def test_modo_demo_ignora_la_base_real_y_aisla_archivos_cookie_y_firma():
    r = _config(MODO_DEMO="1")
    assert r.returncode == 0, r.stderr[-600:]
    bd, subidas, almacen, cookie, clave_demo = [x.strip() for x in r.stdout.strip().splitlines()[-1].split("|")]
    assert bd == "sqlite:///./demo.db" and "real.db" not in bd            # NO usa DATABASE_URL
    assert subidas == "uploads_demo"                                       # NO usa UPLOAD_DIR
    assert almacen == "local"                                              # NUNCA Supabase Storage, aunque el .env diga supabase
    assert cookie == "ciudadela_rt_demo" and clave_demo == "True"


def test_modo_demo_acepta_su_propia_base_en_demo_database_url():
    r = _config(MODO_DEMO="1", DEMO_DATABASE_URL="sqlite:///./otra_demo.db")
    assert r.returncode == 0 and "sqlite:///./otra_demo.db" in r.stdout


def test_modo_demo_se_niega_a_usar_la_base_de_la_app_real():
    r = _config(MODO_DEMO="1", DEMO_DATABASE_URL="sqlite:///./propiedad_horizontal.db")
    assert r.returncode != 0 and "propiedad_horizontal.db" in r.stderr


# ---------------------------------------------------------------- «Solicitar demo» directo a WhatsApp (la landing)
LANDING_JS = (RAIZ / "landing" / "recursos" / "landing.js").read_text(encoding="utf-8")
LANDING_HTML = (RAIZ / "landing" / "index.html").read_text(encoding="utf-8")


def test_la_landing_ya_no_tiene_el_segundo_boton_ni_la_pantalla_que_pregunta():
    assert "btn-whatsapp" not in LANDING_JS and "btn-whatsapp" not in LANDING_HTML
    assert "Enviar mis datos por WhatsApp" not in LANDING_JS


def test_solicitar_demo_abre_whatsapp_en_el_mismo_toque_sin_window_open_noopener():
    assert "abrirWhatsApp(url)" in LANDING_JS
    assert 'window.open(url, "_blank", "noopener")' not in LANDING_JS          # devolvía null y abría WhatsApp dos veces
    assert "a.click()" in LANDING_JS


def test_el_guardado_solo_se_hace_con_autorizacion_y_la_casilla_ya_no_bloquea_con_whatsapp():
    assert "if (d.acepto) enviar(" in LANDING_JS
    assert "exigirConsentimiento: !conWhatsApp" in LANDING_JS
    assert 'name="acepto_datos" type="checkbox" required' not in LANDING_HTML


def test_la_pagina_de_la_app_lleva_la_cinta_demo_solo_en_modo_demo(client, monkeypatch):
    from app import config
    assert "data-modo-demo" not in client.get("/app/").text
    monkeypatch.setattr(config, "MODO_DEMO", True)
    assert 'data-modo-demo="1"' in client.get("/app/").text


# ---------------------------------------------------------------- tablas y filas: nada de texto aplastado en anchos medios
CSS = (RAIZ / "frontend" / "estilos.css").read_text(encoding="utf-8")


def test_las_tablas_se_deciden_por_el_ancho_de_su_tarjeta_y_no_por_el_de_la_ventana():
    assert "container-type: inline-size" in CSS and "@container (min-width: 720px)" in CSS and "@container (min-width: 1080px)" in CSS
    assert "flex: 1 1 14rem" in CSS          # las filas .item/.vehiculo siempre dejan un ancho mínimo al texto
    assert ".main { width: 100%; }" in CSS


@pytest.mark.parametrize("vista", ["residentes", "cartera"])
def test_las_tablas_con_muchas_columnas_son_tabla_ancha(vista):
    assert "tabla-wrap tabla-ancha" in (RAIZ / "frontend" / "js" / "vistas" / f"{vista}.js").read_text(encoding="utf-8")
