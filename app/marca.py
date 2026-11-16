# app/marca.py — Versión 4.0: WHITE-LABEL.
# Convierte las variables MARCA_* (app/config.py) en lo que ve cada pantalla: el HTML de la app, el manifest de la PWA, el service worker,
# la landing y los PDF. Es el ÚNICO sitio donde vive «cómo se personaliza»: el resto del código solo pide `marca.nombre()`.
#
# Color: el cliente da UN color (MARCA_COLOR=#RRGGBB) y aquí se calculan las variantes que usa la interfaz (fondo del menú, tarjetas,
# versión para modo oscuro…). Si el color es demasiado claro para llevar texto blanco encima, se oscurece solo hasta que se lea bien.
# Los colores por ROL (residente teal, guardia ámbar, inquilino violeta) NO cambian: sirven para distinguir quién está usando la app.
import colorsys
import hashlib
import html
import json
import re
from pathlib import Path

from app import config

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
TEXTO_SOBRE_PRIMARIO = "#F2F7FA"
IMAGENES_PERSONALIZABLES = (
    "icono.png", "icono-crema.png", "logo.png", "logo-crema.png", "favicon.png",
    "apple-touch-180.png", "pwa-192.png", "pwa-512.png", "pwa-maskable-512.png",
)


def nombre() -> str:
    return config.MARCA_NOMBRE


def corto() -> str:
    return config.MARCA_NOMBRE_CORTO


def es_la_marca_por_defecto() -> bool:
    return config.MARCA_NOMBRE == config.MARCA_NOMBRE_POR_DEFECTO and not color_valido()


# ---------------------------------------------------------------- color
def color_valido() -> str:
    """El color configurado en minúsculas, o «» si no hay o no es un «#RRGGBB» válido (un valor roto jamás debe romper la app)."""
    c = config.MARCA_COLOR
    return c.lower() if _HEX.match(c) else ""


def _rgb(hexa: str) -> tuple[float, float, float]:
    return tuple(int(hexa[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(v * 255))) for v in (r, g, b)))


def _luminancia(hexa: str) -> float:
    def canal(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(hexa))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(hexa: str) -> tuple[float, float, float]:
    r, g, b = _rgb(hexa)
    return colorsys.rgb_to_hls(r, g, b)


def _con(h: float, l: float, s: float) -> str:
    return _hex(*colorsys.hls_to_rgb(h, max(0.0, min(1.0, l)), max(0.0, min(1.0, s))))


def paleta(base: str) -> dict:
    """Variantes de un color para modo claro y modo oscuro. `base` es un «#rrggbb» válido."""
    h, l, s = _hls(base)
    s = min(s, 0.75)                                  # un color chillón se suaviza: la interfaz es de uso diario
    primario = _con(h, l, s)
    while contraste(primario, TEXTO_SOBRE_PRIMARIO) < 4.5 and l > 0.05:   # el texto de los botones debe leerse (WCAG AA)
        l -= 0.02
        primario = _con(h, l, s)
    claro = {
        "--bosque": primario, "--bosque-2": _con(h, l + 0.12, s), "--bosque-100": _con(h, 0.92, min(s, 0.45)),
        "--menu": _con(h, min(l, 0.20), min(s + 0.05, 0.80)), "--primario": primario,
        "--rol-rgb": ", ".join(str(round(v * 255)) for v in _rgb(primario)),
        "--tarjeta": _con(h, 0.91, min(s, 0.40)), "--tarjeta-borde": _con(h, 0.62, min(s, 0.30)),
    }
    oscuro = {
        "--bosque": _con(h, 0.70, min(s, 0.60)), "--bosque-2": _con(h, 0.62, min(s, 0.55)), "--bosque-100": _con(h, 0.22, min(s, 0.50)),
        "--menu": _con(h, 0.10, min(s, 0.55)), "--primario": _con(h, 0.70, min(s, 0.60)), "--sobre-primario": _con(h, 0.08, min(s, 0.55)),
        "--papel": _con(h, 0.085, min(s, 0.50)), "--superficie": _con(h, 0.125, min(s, 0.50)), "--linea": _con(h, 0.24, min(s, 0.40)),
        "--tarjeta": _con(h, 0.19, min(s, 0.45)), "--tarjeta-borde": _con(h, 0.40, min(s, 0.35)), "--campo": _con(h, 0.105, min(s, 0.50)),
        "--esq-a": _con(h, 0.16, min(s, 0.50)), "--esq-b": _con(h, 0.22, min(s, 0.50)),
        "--rol-rgb": ", ".join(str(round(v * 255)) for v in _rgb(_con(h, 0.70, min(s, 0.60)))),
    }
    return {"claro": claro, "oscuro": oscuro, "primario": primario, "menu": claro["--menu"], "menu_oscuro": oscuro["--menu"]}


# Todo lo que NO sea residente, guardia o inquilino usa la identidad base (login, administrador, landing). Esos tres tienen su propio color.
_BASE = ':root:not([data-rol="Residente"]):not([data-rol="Guardia"]):not([data-rol="Inquilino"])'


def css_de_marca() -> str:
    """Bloque <style> que redefine las variables de color de la identidad base. Vacío si no hay color configurado."""
    c = color_valido()
    if not c:
        return ""
    p = paleta(c)
    bloque = lambda sel, d: f"{sel}{{" + ";".join(f"{k}:{v}" for k, v in d.items()) + "}"   # noqa: E731
    return bloque(_BASE, p["claro"]) + bloque(f'{_BASE}[data-tema="oscuro"]', p["oscuro"])


def colores_meta() -> tuple[str, str]:
    """(theme-color claro, theme-color oscuro) de la barra del navegador del celular."""
    c = color_valido()
    if not c:
        return "#07304A", "#06122B"
    p = paleta(c)
    return p["menu"], p["menu_oscuro"]


# ---------------------------------------------------------------- datos que lee el navegador
def datos_publicos() -> dict:
    """Lo que el navegador necesita saber de la marca. Nada sensible: es lo mismo que ya ve cualquiera al abrir la página."""
    claro, oscuro = colores_meta()
    return {"nombre": nombre(), "corto": corto(), "eslogan": config.MARCA_ESLOGAN, "descripcion": config.MARCA_DESCRIPCION,
            "conjunto": config.CONJUNTO_NOMBRE, "asistente": config.MARCA_ASISTENTE, "color": color_valido(), "tema_claro": claro, "tema_oscuro": oscuro,
            "landing": config.LANDING_ACTIVA}


def _json_en_atributo(datos: dict) -> str:
    return html.escape(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), quote=True)


def _e(texto: str) -> str:
    return html.escape(texto, quote=True)


def aplicar_a_html(plantilla: str, extra: dict | None = None) -> str:
    """Rellena los marcadores __MARCA_*__ de una página HTML. Todo se escapa: un nombre con comillas o «<» no puede romper la página."""
    claro, _ = colores_meta()
    estilo = css_de_marca()
    reemplazos = {
        "__MARCA_NOMBRE__": _e(nombre()), "__MARCA_CORTO__": _e(corto()), "__MARCA_ESLOGAN__": _e(config.MARCA_ESLOGAN),
        "__MARCA_DESCRIPCION__": _e(config.MARCA_DESCRIPCION), "__MARCA_CONJUNTO__": _e(config.CONJUNTO_NOMBRE),
        "__MARCA_COLOR_TEMA__": _e(claro), "__MARCA_JSON__": _json_en_atributo({**datos_publicos(), **(extra or {})}),
        "__MARCA_ESTILO__": f"<style id=\"marca-estilo\">{estilo}</style>" if estilo else "",
    }
    for k, v in reemplazos.items():
        plantilla = plantilla.replace(k, v)
    return plantilla


def manifest(plantilla_json: str) -> str:
    """manifest.webmanifest con el nombre y el color del cliente: así al instalar la app en el celular sale con SU nombre."""
    datos = json.loads(plantilla_json)
    claro, _ = colores_meta()
    datos.update({"name": nombre(), "short_name": corto(), "description": config.MARCA_DESCRIPCION,
                  "theme_color": claro, "background_color": claro})
    return json.dumps(datos, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- logos del cliente
def ruta_imagen_personalizada(nombre_archivo: str) -> Path | None:
    """Ruta de un logo del cliente en la carpeta marca/ (solo los nombres de IMAGENES_PERSONALIZABLES: nunca se sirve otro archivo)."""
    if nombre_archivo not in IMAGENES_PERSONALIZABLES:
        return None
    ruta = config.MARCA_DIR / nombre_archivo
    return ruta if ruta.is_file() else None


def huella() -> str:
    """Cambia cuando cambia cualquier cosa de la marca (textos, color o logos). Entra en la versión del service worker:
    así, al cambiar la marca, todos los celulares descargan la versión nueva en vez de seguir viendo la vieja guardada."""
    h = hashlib.sha256(json.dumps(datos_publicos(), sort_keys=True).encode())
    h.update(config.DEMO_WHATSAPP.encode())
    for n in IMAGENES_PERSONALIZABLES:
        r = ruta_imagen_personalizada(n)
        if r is not None:
            h.update(n.encode())
            h.update(r.read_bytes())
    return h.hexdigest()
