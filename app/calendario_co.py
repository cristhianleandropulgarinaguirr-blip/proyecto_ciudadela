# app/calendario_co.py
# Calendario laboral de Colombia: festivos (Ley 51 de 1983, «ley Emiliani») y conteo de días hábiles.
# Se usa para sugerir la fecha de la segunda convocatoria de una asamblea: el Art. 41 de la Ley 675 de 2001 dice que se hace
# «el tercer día hábil siguiente» a la primera convocatoria, a las 8 p. m.
from datetime import date, datetime, time, timedelta, timezone

HORA_COLOMBIA = timezone(timedelta(hours=-5))     # Colombia no tiene horario de verano
HORA_SEGUNDA_CONVOCATORIA = time(20, 0)           # «a las ocho pasado meridiano» (Art. 41)


def _pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo gregoriano anónimo de Meeus/Jones/Butcher)."""
    a, b, c = anio % 19, anio // 100, anio % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _al_lunes(d: date) -> date:
    """Los festivos «trasladables» pasan al lunes siguiente (si ya cae lunes, se quedan)."""
    return d if d.weekday() == 0 else d + timedelta(days=7 - d.weekday())


def festivos(anio: int) -> set[date]:
    pascua = _pascua(anio)
    fijos = {date(anio, 1, 1), date(anio, 5, 1), date(anio, 7, 20), date(anio, 8, 7), date(anio, 12, 8), date(anio, 12, 25)}
    trasladables = {date(anio, 1, 6), date(anio, 3, 19), date(anio, 6, 29), date(anio, 8, 15), date(anio, 10, 12), date(anio, 11, 1), date(anio, 11, 11)}
    semana_santa = {pascua - timedelta(days=3), pascua - timedelta(days=2)}                       # jueves y viernes santo (no se trasladan)
    movibles = {pascua + timedelta(days=39), pascua + timedelta(days=60), pascua + timedelta(days=68)}   # Ascensión, Corpus Christi, Sagrado Corazón
    return fijos | semana_santa | {_al_lunes(d) for d in trasladables | movibles}


def es_dia_habil(d: date, sabado_habil: bool = False) -> bool:
    if d.weekday() == 6 or d in festivos(d.year):
        return False
    return d.weekday() != 5 or sabado_habil


def dia_habil_numero(desde: date, n: int, sabado_habil: bool = False) -> date:
    """El día hábil número `n` DESPUÉS de `desde` (el propio día `desde` no cuenta). Salta domingos, festivos y, si no es hábil, los sábados."""
    d, contados = desde, 0
    while contados < n:
        d += timedelta(days=1)
        if es_dia_habil(d, sabado_habil):
            contados += 1
    return d


def tercer_dia_habil(desde: date, sabado_habil: bool = False) -> date:
    """Tercer día hábil DESPUÉS de `desde` (el día de la primera convocatoria no cuenta)."""
    return dia_habil_numero(desde, 3, sabado_habil)


def segunda_convocatoria(fecha_sesion_utc: datetime, sabado_habil: bool = False) -> datetime:
    """Fecha sugerida (UTC, sin zona) de la segunda convocatoria: tercer día hábil siguiente a la primera, a las 8 p. m. hora de Colombia."""
    local = fecha_sesion_utc.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA)
    dia = tercer_dia_habil(local.date(), sabado_habil)
    return datetime.combine(dia, HORA_SEGUNDA_CONVOCATORIA, tzinfo=HORA_COLOMBIA).astimezone(timezone.utc).replace(tzinfo=None)
