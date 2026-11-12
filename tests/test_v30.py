# tests/test_v30.py
# Versión 3.0: color por rol (frontend), cámara en fotos y rendimiento.
# Aquí se prueba lo que vive en el servidor: fotos livianas y sin GPS, miniaturas, service worker versionado,
# compresión GZip, caché de imágenes de la interfaz e índices nuevos.
import io
import os
import sqlite3
import tempfile

from alembic import command
from alembic.config import Config
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATOS = {"titulo": "Ascensor trabado", "descripcion": "Se detiene entre el piso 4 y 5"}


def foto_de_celular() -> bytes:
    """Como la que sale de un celular: grande (3000×2000), girada por EXIF y con metadatos de la cámara."""
    exif = Image.Exif()
    exif[0x010F] = "MarcaDelCelular"          # fabricante
    exif[0x0112] = 6                          # orientación: girar 90°
    b = io.BytesIO()
    Image.new("RGB", (3000, 2000), "orange").save(b, format="JPEG", exif=exif)
    return b.getvalue()


def test_foto_grande_se_reduce_se_endereza_y_pierde_los_metadatos(client, auth):
    ana = auth("ana@conjunto.com")
    r = client.post("/mantenimiento/reportar-danio", data=DATOS, headers=ana,
                    files={"archivo_foto": ("c.jpg", foto_de_celular(), "image/jpeg")})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    completa = client.get(f"/mantenimiento/danios/{rid}/foto", headers=ana)
    img = Image.open(io.BytesIO(completa.content))
    assert max(img.size) <= 1600 and img.size[1] > img.size[0]       # reducida y enderezada (quedó vertical)
    assert len(img.getexif()) == 0                                   # sin metadatos (ni ubicación GPS)

    mini = client.get(f"/mantenimiento/danios/{rid}/foto", params={"miniatura": True}, headers=ana)
    pequena = Image.open(io.BytesIO(mini.content))
    assert max(pequena.size) <= 640 and len(mini.content) < len(completa.content)


def test_miniatura_cae_a_la_original_si_no_existe(client, auth):
    """Fotos subidas antes de la 3.0 no tienen miniatura: el endpoint debe seguir funcionando."""
    from app.archivos import guardar_imagen_validada  # noqa: F401  (import para dejar claro de dónde sale)
    ana = auth("ana@conjunto.com")
    r = client.post("/mantenimiento/reportar-danio", data=DATOS, headers=ana,
                    files={"archivo_foto": ("c.jpg", foto_de_celular(), "image/jpeg")})
    rid, nombre = r.json()["id"], r.json()["foto_url"]
    from app.archivos import PREFIJO_MINIATURA
    from app.almacen import almacen
    almacen().borrar("", PREFIJO_MINIATURA + nombre)                 # simula una foto antigua
    assert client.get(f"/mantenimiento/danios/{rid}/foto", params={"miniatura": True}, headers=ana).status_code == 200


def test_miniatura_respeta_los_permisos(client, auth):
    ana, luis = auth("ana@conjunto.com"), auth("luis@conjunto.com")
    rid = client.post("/mantenimiento/reportar-danio", data=DATOS, headers=ana,
                      files={"archivo_foto": ("c.jpg", foto_de_celular(), "image/jpeg")}).json()["id"]
    assert client.get(f"/mantenimiento/danios/{rid}/foto", params={"miniatura": True}, headers=luis).status_code == 403
    assert client.get(f"/mantenimiento/danios/{rid}/foto", params={"miniatura": True}).status_code == 401


def test_service_worker_versionado_y_con_la_lista_de_archivos(client):
    r = client.get("/app/sw.js")
    assert r.status_code == 200 and "javascript" in r.headers["content-type"] and r.headers["cache-control"] == "no-cache"
    assert "__VERSION__" not in r.text and "__ARCHIVOS__" not in r.text         # la plantilla quedó resuelta
    assert 'const VERSION = "ciudadela-' in r.text
    assert '"estilos.css"' in r.text and '"js/app.js"' in r.text and '"js/foto.js"' in r.text and '"./"' in r.text
    assert "jsQR" not in r.text.split("const ARCHIVOS")[1].split("\n")[0]       # lo pesado y opcional no se descarga al instalar
    assert client.get("/app/sw.js").text == r.text                              # estable mientras no cambien los archivos


def test_texto_se_comprime_y_las_imagenes_de_la_interfaz_se_guardan_en_cache(client):
    css = client.get("/app/estilos.css", headers={"Accept-Encoding": "gzip"})
    assert css.headers.get("content-encoding") == "gzip" and css.headers["cache-control"] == "no-cache"
    logo = client.get("/app/img/logo-crema.png", headers={"Accept-Encoding": "gzip"})
    assert logo.status_code == 200 and "content-encoding" not in logo.headers   # ya viene comprimida: no se vuelve a comprimir
    assert "max-age=604800" in logo.headers["cache-control"]


def test_fuentes_sin_bloquear_y_carga_bajo_demanda_en_el_frontend(client):
    html = client.get("/app/").text
    assert 'rel="preload" as="style"' in html and "fonts.googleapis.com" in html
    app_js = client.get("/app/js/app.js").text
    assert 'import("./vistas/resumen.js")' in app_js and 'import * as resumen' not in app_js


def test_el_color_por_rol_esta_definido_para_los_tres_roles_en_claro_y_oscuro(client):
    css = client.get("/app/estilos.css").text
    for rol in ("Residente", "Guardia"):
        assert f':root[data-rol="{rol}"]' in css and f':root[data-rol="{rol}"][data-tema="oscuro"]' in css
    tema = client.get("/app/js/tema.js").text
    assert "Administrador" in tema and "Residente" in tema and "Guardia" in tema


def test_migracion_0011_crea_los_indices_nuevos():
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ruta}")
    command.upgrade(cfg, "head")
    con = sqlite3.connect(ruta)
    indices = {i[0] for i in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"ix_reservas_usuario_id", "ix_reservas_fecha_reserva", "ix_reportes_danios_usuario_id", "ix_reportes_danios_estado"} <= indices
    con.close()
    command.downgrade(cfg, "0010")                                              # y se puede devolver
    con = sqlite3.connect(ruta)
    assert "ix_reservas_usuario_id" not in {i[0] for i in con.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    con.close()


# ------------------------------------------------------------------ foto opcional en paquetes
ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"


def _paquete(client, auth, para=ANA):
    dest = next(u["id"] for u in client.get("/usuarios/", headers=auth(ADM)).json() if u["email"] == para)
    r = client.post("/paquetes/", json={"destinatario_id": dest, "remitente": "Servientrega"}, headers=auth(CEL))
    assert r.status_code == 201, r.text
    return r.json()


def test_paquete_con_foto_la_ve_el_destinatario_y_nadie_mas(client, auth):
    p = _paquete(client, auth)
    assert p["tiene_foto"] is False
    assert client.get(f"/paquetes/{p['id']}/foto", headers=auth(ANA)).status_code == 404        # aún sin foto

    r = client.post(f"/paquetes/{p['id']}/foto", headers=auth(CEL), files={"archivo": ("c.jpg", foto_de_celular(), "image/jpeg")})
    assert r.status_code == 200 and r.json()["tiene_foto"] is True

    assert client.get(f"/paquetes/{p['id']}/foto", headers=auth(ANA)).status_code == 200         # destinatario
    assert client.get(f"/paquetes/{p['id']}/foto", headers=auth(ADM)).status_code == 200         # administrador
    assert client.get(f"/paquetes/{p['id']}/foto", params={"miniatura": True}, headers=auth(CEL)).status_code == 200
    assert client.get(f"/paquetes/{p['id']}/foto", headers=auth(LUIS)).status_code == 403        # otro residente
    assert client.get(f"/paquetes/{p['id']}/foto").status_code == 401                            # sin sesión
    assert next(x for x in client.get("/paquetes/", headers=auth(ANA)).json() if x["id"] == p["id"])["tiene_foto"] is True


def test_solo_el_personal_adjunta_foto_y_solo_mientras_esta_en_porteria(client, auth):
    p = _paquete(client, auth)
    foto = {"archivo": ("c.jpg", foto_de_celular(), "image/jpeg")}
    assert client.post(f"/paquetes/{p['id']}/foto", headers=auth(ANA), files=foto).status_code == 403   # el residente no
    assert client.post(f"/paquetes/{p['id']}/foto", headers=auth(CEL), files={"archivo": ("x.jpg", b"no soy imagen", "image/jpeg")}).status_code == 400
    client.patch(f"/paquetes/{p['id']}/entregar", headers=auth(CEL))
    assert client.post(f"/paquetes/{p['id']}/foto", headers=auth(CEL), files=foto).status_code == 400   # ya entregado


def test_migracion_0012_agrega_foto_url_a_paquetes():
    ruta = os.path.join(tempfile.mkdtemp(), "nueva.db")
    cfg = Config(os.path.join(RAIZ, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(RAIZ, "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{ruta}")
    command.upgrade(cfg, "head")
    con = sqlite3.connect(ruta)
    assert "foto_url" in {c[1] for c in con.execute("PRAGMA table_info(paquetes)")}
    con.close()
