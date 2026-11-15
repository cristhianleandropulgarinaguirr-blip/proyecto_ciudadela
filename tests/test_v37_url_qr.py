# v3.7 · La dirección del QR del paz y salvo debe poder abrirse desde un celular.
from types import SimpleNamespace
from app import config
from app.routers import paz_y_salvo as pz


def _peticion(url):
    from starlette.datastructures import URL
    u = URL(url)
    return SimpleNamespace(url=u, base_url=URL(f"{u.scheme}://{u.netloc}/"))


def test_url_publica_manda_sobre_todo(monkeypatch):
    monkeypatch.setattr(config, "URL_PUBLICA", "https://mi-conjunto.onrender.com")
    assert pz._url_base(_peticion("http://127.0.0.1:8000/x")) == "https://mi-conjunto.onrender.com"


def test_desde_localhost_se_usa_la_ip_de_la_red(monkeypatch):
    monkeypatch.setattr(config, "URL_PUBLICA", "")
    monkeypatch.setattr(pz, "_ip_de_la_red_local", lambda: "192.168.1.20")
    assert pz._url_base(_peticion("http://127.0.0.1:8000/x")) == "http://192.168.1.20:8000"
    assert pz._url_base(_peticion("http://localhost:8000/x")) == "http://192.168.1.20:8000"


def test_sin_red_local_o_con_dominio_real_no_se_cambia(monkeypatch):
    monkeypatch.setattr(config, "URL_PUBLICA", "")
    monkeypatch.setattr(pz, "_ip_de_la_red_local", lambda: None)
    assert pz._url_base(_peticion("http://127.0.0.1:8000/x")) == "http://127.0.0.1:8000"
    monkeypatch.setattr(pz, "_ip_de_la_red_local", lambda: "192.168.1.20")
    assert pz._url_base(_peticion("https://app.ejemplo.com/x")) == "https://app.ejemplo.com"
