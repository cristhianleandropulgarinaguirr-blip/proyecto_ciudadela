# tests/test_v41_fase5.py — Versión 4.1, Fase 5: rendimiento transversal (guardas para que no se pierda lo ya optimizado).
import json
from datetime import timedelta
from pathlib import Path

from app.models import PQRS, Usuario, ahora_utc
from tests.test_arrendamientos import ADM, ANA

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
NUCLEO = {".html", ".js", ".css", ".webmanifest"}          # lo mismo que app/main.py guarda al instalar
EXCLUIDOS = {"vendor", "pase", "verificar", "tecnico"}                # carpetas con su propia política (jsQR pesado y páginas públicas)


def test_todo_archivo_estatico_nuevo_entra_solo_a_la_cache_del_service_worker(client):
    """Si alguien agrega vistas/algo.js o un .css nuevo, NO hay que tocar ninguna lista: el servidor lo incluye en la caché del celular."""
    sw = client.get("/app/sw.js").text
    lista = json.loads(sw.split("const ARCHIVOS = ")[1].split(";\n")[0])
    esperados = set()
    for p in FRONTEND.rglob("*"):
        if p.is_file() and p.name != "sw.js" and not (EXCLUIDOS & set(p.parts)) and p.suffix in NUCLEO:
            rel = p.relative_to(FRONTEND).as_posix()
            esperados.add("./" if rel == "index.html" else rel)
    faltan = esperados - set(lista)
    assert not faltan, f"Estos archivos no quedarían en la caché del service worker: {sorted(faltan)}"
    assert any(a.startswith("js/vistas/") for a in lista)         # las vistas (carga perezosa) también están, para abrir sin internet


def test_la_app_no_carga_librerias_de_graficos(client):
    """Los gráficos son SVG propio (js/graficos.js). Si alguien mete Chart.js, esta prueba avisa: pesa ~200 KB y se descargaría en el celular."""
    marcas = ("new chart(", "chart.umd", "chart.min.js", "cdn.jsdelivr.net/npm/chart")
    for p in FRONTEND.rglob("*"):
        if p.is_file() and p.suffix in {".js", ".html"} and p.name != "sw.js" and "vendor" not in p.parts:
            texto = p.read_text(encoding="utf-8").lower()
            assert not any(m in texto for m in marcas), f"{p.relative_to(FRONTEND)} carga una librería de gráficos"
    assert "chart" not in client.get("/app/").text.lower().replace("chart-", "")


def test_kpis_pqrs_ignora_respuestas_anteriores_a_la_creacion_como_antes(client, auth, db):
    """El promedio ahora lo calcula la base de datos: un dato corrupto (respuesta ANTES de radicar) sigue sin contarse."""
    ana = db.query(Usuario).filter(Usuario.email == ANA).one()
    ahora = ahora_utc()
    db.add_all([
        PQRS(usuario_id=ana.id, tipo="Queja", asunto="ok", descripcion="x" * 20, estado="Resuelta", fecha_creacion=ahora - timedelta(days=3), fecha_respuesta=ahora - timedelta(days=3) + timedelta(hours=8)),
        PQRS(usuario_id=ana.id, tipo="Queja", asunto="mal", descripcion="x" * 20, estado="Resuelta", fecha_creacion=ahora - timedelta(days=2), fecha_respuesta=ahora - timedelta(days=2, hours=5)),   # respondida «antes» de existir
    ])
    db.commit()
    j = client.get("/dashboard/kpis", params={"refrescar": "true"}, headers=auth(ADM)).json()
    assert j["pqrs"]["respondidas"] == 1 and j["pqrs"]["horas_promedio_respuesta"] == 8.0
