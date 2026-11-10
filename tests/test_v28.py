# tests/test_v28.py — Versión 2.8: almacén de archivos (local / Supabase Storage), pagos reales, PWA y cabeceras.
import httpx
import pytest

from app import almacen as modulo_almacen
from app import config
from app.almacen import AlmacenLocal, AlmacenSupabase

ANA, LUIS, CEL, ADM = "ana@conjunto.com", "luis@conjunto.com", "celador@conjunto.com", "admin@conjunto.com"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def id_de(client, auth, email):
    return next(u["id"] for u in client.get("/usuarios/", headers=auth(ADM)).json() if u["email"] == email)


def deuda(client, auth, email, valor):
    client.patch(f"/administracion/registrar-deuda/{id_de(client, auth, email)}?saldo_pendiente={valor}", headers=auth(ADM))


# ------------------------------------------------------------ almacén
def test_almacen_local_guarda_lee_borra_y_no_sale_de_su_carpeta():
    a = AlmacenLocal()
    a.guardar("documentos", "x.pdf", b"hola")
    assert a.leer("documentos", "x.pdf") == b"hola"
    assert a.leer("documentos", "../../x.pdf") == b"hola"          # basename: «../» no escapa de la carpeta
    a.borrar("documentos", "x.pdf")
    assert a.leer("documentos", "x.pdf") is None


class SupabaseFalso:
    """Imita Supabase Storage en memoria y registra las peticiones recibidas."""
    def __init__(self):
        self.objetos, self.peticiones = {}, []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.peticiones.append(req)
        clave = req.url.path
        if req.method == "POST":
            self.objetos[clave] = req.content
            return httpx.Response(200, json={"Key": clave})
        if req.method == "GET":
            return httpx.Response(200, content=self.objetos[clave]) if clave in self.objetos else httpx.Response(400, json={"statusCode": "404"})
        if req.method == "DELETE":
            self.objetos.pop(clave, None)
            return httpx.Response(200, json=[])
        return httpx.Response(405)


@pytest.fixture()
def supabase(monkeypatch):
    falso = SupabaseFalso()
    monkeypatch.setattr(config, "SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "sb_secret_prueba")
    monkeypatch.setattr(config, "SUPABASE_BUCKET", "ciudadela-archivos")
    monkeypatch.setattr(modulo_almacen, "_instancia", AlmacenSupabase(httpx.Client(transport=httpx.MockTransport(falso))))
    yield falso
    modulo_almacen.reiniciar_almacen()


def test_supabase_ciclo_completo_y_cabeceras_segun_tipo_de_clave(supabase, monkeypatch):
    a = modulo_almacen.almacen()
    a.guardar("documentos", "a b.pdf", b"datos")
    assert a.leer("documentos", "a b.pdf") == b"datos"
    assert a.leer("documentos", "no-existe.pdf") is None            # 400 con statusCode 404 → None
    a.borrar("documentos", "a b.pdf")
    assert a.leer("documentos", "a b.pdf") is None
    subida = supabase.peticiones[0]
    assert str(subida.url) == "https://abc.supabase.co/storage/v1/object/ciudadela-archivos/documentos/a%20b.pdf"
    assert subida.headers["apikey"] == "sb_secret_prueba" and "authorization" not in subida.headers   # clave nueva: sin Bearer
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "eyJ.clave.antigua")
    a.guardar("", "f.jpg", b"x")
    assert supabase.peticiones[-1].headers["authorization"] == "Bearer eyJ.clave.antigua"             # clave antigua: con Bearer


def test_supabase_caido_responde_503_y_no_rompe_la_lectura(monkeypatch):
    def caido(req):
        raise httpx.ConnectError("sin red")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SECRET_KEY", "sb_secret_prueba")
    a = AlmacenSupabase(httpx.Client(transport=httpx.MockTransport(caido)))
    assert a.leer("", "x.jpg") is None
    with pytest.raises(Exception) as e:
        a.guardar("", "x.jpg", b"1")
    assert getattr(e.value, "status_code", None) == 503


def test_supabase_exige_url_y_clave(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    with pytest.raises(RuntimeError):
        AlmacenSupabase()


def test_documento_viaja_por_supabase_de_punta_a_punta(client, auth, supabase):
    r = client.post("/documentos/", headers=auth(ADM), data={"titulo": "Reglamento interno", "categoria": "Reglamento"},
                    files={"archivo": ("reglamento.pdf", PDF, "application/pdf")})
    assert r.status_code == 201, r.text
    d = r.json()
    assert any("/documentos/" in k for k in supabase.objetos)        # el PDF está en «Supabase», no en disco
    bajado = client.get(f"/documentos/{d['id']}/descargar", headers=auth(ANA))
    assert bajado.status_code == 200 and bajado.content == PDF and "reglamento.pdf" in bajado.headers["content-disposition"]
    assert client.get(f"/documentos/{d['id']}/descargar").status_code == 401
    assert client.delete(f"/documentos/{d['id']}", headers=auth(ADM)).status_code == 200
    assert supabase.objetos == {}                                    # al eliminar también se borra el archivo
    assert client.get(f"/documentos/{d['id']}/descargar", headers=auth(ANA)).status_code == 404


# ------------------------------------------------------------ pagos reales
def test_config_de_pagos_la_ven_todos_los_roles(client, auth):
    for quien in (ANA, CEL, ADM):
        r = client.get("/administracion/config-pagos", headers=auth(quien)).json()
        assert set(r) == {"pagos_simulados", "instrucciones"}
    assert client.get("/administracion/config-pagos").status_code == 401


def test_con_pagos_simulados_apagados_el_residente_no_puede_pagarse_solo(client, auth, monkeypatch):
    deuda(client, auth, ANA, 300000)
    monkeypatch.setattr(config, "PAGOS_SIMULADOS", False)
    assert client.get("/administracion/config-pagos", headers=auth(ANA)).json()["pagos_simulados"] is False
    r = client.post("/administracion/simular-pago-pasarela?valor_pagado=100000", headers=auth(ANA))
    assert r.status_code == 403
    assert client.get(f"/administracion/estado-cuenta/{id_de(client, auth, ANA)}", headers=auth(ANA)).json()["saldo_pendiente"] == 300000


def test_el_administrador_registra_el_pago_recibido(client, auth):
    deuda(client, auth, ANA, 300000)
    uid = id_de(client, auth, ANA)
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=100000", headers=auth(ANA)).status_code == 403   # el residente no
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=100000", headers=auth(CEL)).status_code == 403
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=100000").status_code == 401
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=999999", headers=auth(ADM)).status_code == 400   # excede
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=0", headers=auth(ADM)).status_code == 422
    assert client.post("/administracion/registrar-pago/9999?valor_pagado=1000", headers=auth(ADM)).status_code == 404
    r = client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=100000&referencia=Transf.%20884213", headers=auth(ADM)).json()
    assert r["saldo_pendiente"] == 200000 and r["esta_al_dia"] is False and r["pago_id"]
    r = client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=200000", headers=auth(ADM)).json()
    assert r["saldo_pendiente"] == 0 and r["esta_al_dia"] is True
    assert client.post(f"/administracion/registrar-pago/{uid}?valor_pagado=1000", headers=auth(ADM)).status_code == 400     # ya no debe nada
    pagos = client.get("/administracion/mis-pagos", headers=auth(ANA)).json()
    assert [p["valor"] for p in pagos] == [200000, 100000] and pagos[0]["comprobante"].startswith("REC-")
    assert client.get(f"/reportes/recibo/{pagos[0]['id']}.pdf", headers=auth(ANA)).content.startswith(b"%PDF")
    avisos = [n["titulo"] for n in client.get("/notificaciones/", headers=auth(ANA)).json()]
    assert avisos.count("Registramos tu pago de administración") == 2
    det = [x["detalle"] for x in client.get("/auditoria/?entidad=Cartera", headers=auth(ADM)).json() if x["accion"] == "Registró pago recibido"]
    assert any("884213" in (d or "") for d in det)


# ------------------------------------------------------------ PWA y cabeceras
def test_la_app_se_puede_instalar_y_las_cabeceras_son_seguras(client):
    sw = client.get("/app/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"] and sw.headers["cache-control"] == "no-cache"
    man = client.get("/app/manifest.webmanifest")
    assert man.status_code == 200 and man.headers["cache-control"] == "no-cache" and man.json()["display"] == "standalone"
    assert client.get("/app/").headers["x-content-type-options"] == "nosniff"
    h = client.get("/salud", headers={"x-forwarded-proto": "https"}).headers
    assert h["x-frame-options"] == "DENY" and "camera=(self)" in h["permissions-policy"] and "max-age" in h["strict-transport-security"]
    assert "strict-transport-security" not in client.get("/salud").headers      # sin HTTPS no se envía HSTS
