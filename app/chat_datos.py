# app/chat_datos.py — Versión 3.2: datos que alimentan al chat y respuestas «básicas» (sin IA).
# Principios:
#   · La IA nunca consulta la base de datos: este módulo calcula estadísticas AGREGADAS (cuántas reservas por zona y día)
#     y solo eso se le entrega como contexto. No salen nombres, apartamentos ni ningún dato de residentes.
#   · Los números del gráfico los calcula el servidor; la IA solo los explica con palabras.
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app import ia
from app.constantes import EstadoReserva
from app.models import Anuncio, Reserva, Votacion
from app.schemas.asistente import AccionChat, DiaConteo, GraficoZona

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
ZONAS = ["Salón Comunal", "Zona BBQ", "Piscina", "Gimnasio", "Cancha múltiple", "Sala de juegos"]
VENTANA_ATRAS_DIAS = 120
VENTANA_ADELANTE_DIAS = 60
MIN_RESERVAS_CONFIABLE = 6          # con menos reservas la tendencia es poco fiable y se avisa

# Sinónimos para reconocer la zona en el texto de la persona.
_ALIAS = {
    "Zona BBQ": ("bbq", "barbacoa", "asador", "parrilla", "asados", "asado"),
    "Salón Comunal": ("salon comunal", "salon", "comunal"),
    "Piscina": ("piscina", "alberca", "pileta"),
    "Gimnasio": ("gimnasio", "gym", "pesas"),
    "Cancha múltiple": ("cancha", "futbol", "baloncesto", "microfutbol"),
    "Sala de juegos": ("sala de juegos", "juegos", "billar", "ping pong"),
}

ENLACES = {
    "reservas": ("Ir a Reservas", "#/reservas"),
    "pqrs": ("Abrir Quejas y sugerencias", "#/pqrs"),
    "mantenimiento": ("Reportar un daño", "#/mantenimiento"),
    "votaciones": ("Ver Votaciones", "#/votaciones"),
    "anuncios": ("Ver la Cartelera", "#/anuncios"),
    "cartera": ("Ver mis pagos", "#/cartera"),
    "paquetes": ("Ver paquetes", "#/paquetes"),
    "emergencias": ("Ver teléfonos de emergencia", "#/emergencias"),
}


def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar texto escrito de cualquier manera."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def detectar_zona(texto: str) -> Optional[str]:
    plano = _plano(texto)
    for zona, alias in _ALIAS.items():
        if any(re.search(rf"\b{re.escape(a)}\b", plano) for a in alias):
            return zona
    return None


def normalizar_zona(valor: Optional[str]) -> Optional[str]:
    """Acepta solo zonas conocidas (lo que diga la IA se valida: nunca se confía en texto libre)."""
    if not valor:
        return None
    plano = _plano(valor)
    for zona in ZONAS:
        if _plano(zona) == plano:
            return zona
    return detectar_zona(valor)


def accion_para(clave: Optional[str]) -> Optional[AccionChat]:
    if clave in ENLACES:
        texto, enlace = ENLACES[clave]
        return AccionChat(texto=texto, enlace=enlace)
    return None


# ---------------------------------------------------------------- guía de uso de la app (texto fijo, sin datos de nadie)
DETALLE_ZONAS = "Salón Comunal (hasta 60 personas), Zona BBQ (hasta 20), Piscina (por turnos), Gimnasio (clases y eventos), Cancha múltiple (fútbol y baloncesto), Sala de juegos (hasta 15)"
GUIA_APP = """GUÍA DE LA APP (cómo se hace cada cosa; no hay más pasos que estos):
- Reservar: sección Reservas → elige la zona, el día y la hora (de 6:00 a. m. a 10:00 p. m., por horas) y envía la solicitud. La administración la aprueba o la cancela y te llega un aviso. Una zona ya aprobada para ese día no se puede reservar de nuevo. Puedes cancelar tus reservas desde la misma sección.
- Paquetes: portería los registra cuando llegan y a ti te avisa la campana (y el celular si activaste los avisos). En Mis paquetes ves solo los tuyos y cuándo los recogiste.
- Pagos: Mis pagos muestra cuánto debes, permite pagar la administración y descargar comprobantes.
- Visitas: en Mis visitas autorizas a personas frecuentes (familia, empleada, contratista) con nombre y documento; para una visita puntual con vehículo creas un pase QR (Mi QR) que compartes por WhatsApp: el primer escaneo es la entrada y el segundo la salida. Portería deja pasar solo a quien esté autorizado.
- Quejas y sugerencias (PQRS): radicas un asunto y una descripción y recibes un número de radicado; ves solo las tuyas y la administración responde. Puedes tener máximo 5 abiertas a la vez.
- Reportar un daño: describes qué se dañó en una zona común (con foto si quieres) y sigues el avance del arreglo.
- Votaciones: eliges una opción mientras la votación esté abierta. El voto es secreto; por lo general es un voto por apartamento y algunas exigen estar al día con la administración. Los resultados se ven al cerrar (o en vivo si la administración así lo definió).
- Cartelera: reuniones, eventos y avisos del conjunto; en los eventos puedes marcar que asistirás.
- Documentos: reglamento, actas y circulares en PDF para descargar.
- Comercio: directorio de negocios de los vecinos; contactas por WhatsApp. Para anunciar tu negocio eliges un plan, pagas por transferencia, pulsas «Ya pagué» y la administración confirma.
- Emergencias: directorio con un toque para llamar; en una emergencia real marca primero la línea 123.
- Ajustes (toca tu avatar): cambiar la clave, activar los avisos en el celular, elegir tema claro u oscuro y el tamaño del texto. En iPhone los avisos requieren tener la app instalada en la pantalla de inicio.
- Campana: guarda tus avisos (paquetes, reservas, respuestas a PQRS, anuncios, votaciones)."""

# Respuestas de ayuda del modo básico (sin IA): (patrón sobre texto sin tildes, respuesta, sección a la que llevar)
AYUDA_BASICA = [
    (r"(clave|contrasena|password)", "Para cambiar tu clave toca tu avatar (arriba a la derecha) para abrir Ajustes y usa la opción de cambiar clave.", None),
    (r"(notificacion|aviso|push|celular me avise|campana)", "En Ajustes (toca tu avatar) puedes activar los avisos en el celular. Todos tus avisos también quedan guardados en la campana de la barra superior. En iPhone necesitas tener la app instalada en la pantalla de inicio.", None),
    (r"(modo oscuro|tema oscuro|oscuro|texto mas grande|tamano del texto)", "En Ajustes (toca tu avatar) eliges el tema claro, oscuro o automático y el tamaño del texto. También hay un botón de tema en la barra superior.", None),
    (r"(pagar|pago|deuda|saldo|comprobante|administracion cuesta)", "En Mis pagos ves cuánto debes, pagas la administración y descargas tus comprobantes.", "cartera"),
    (r"(paquete|correspondencia|domicilio|encomienda)", "Portería registra tus paquetes cuando llegan y te avisa la campana. En Mis paquetes ves solo los tuyos y cuándo los recogiste.", "paquetes"),
    (r"(visita|visitante|invitado|\bqr\b|pase)", "En Mis visitas autorizas a personas frecuentes; para una visita puntual con vehículo creas un pase QR que compartes por WhatsApp (primer escaneo entrada, segundo salida).", None),
    (r"(queja|reclamo|sugerencia|pqrs|peticion)", "En Quejas y sugerencias escribes un asunto y una descripción y recibes un número de radicado. La administración te responde y ves el estado ahí mismo.", "pqrs"),
    (r"(dano|danio|arreglar|reparar|fuga|ascensor|bombillo)", "En Reportar un daño cuentas qué se dañó en una zona común (con foto si quieres) y sigues el avance del arreglo.", "mantenimiento"),
    (r"(documento|reglamento|acta|circular|manual de convivencia)", "En Documentos encuentras el reglamento, actas y circulares en PDF para descargar.", None),
    (r"(comercio|negocio|anunciar|emprendimiento)", "En Comercio ves los negocios de tus vecinos y los contactas por WhatsApp. Para anunciar el tuyo eliges un plan, pagas por transferencia y pulsas «Ya pagué»; la administración lo confirma.", None),
    (r"(telefono|emergencia|policia|bombero|ambulancia|123)", "En Emergencias tienes el directorio con un toque para llamar. En una emergencia real marca primero el 123.", "emergencias"),
    (r"(cancelar (mi )?reserva|como reservo|como reservar|hacer una reserva)", "En Reservas eliges la zona, el día y la hora (de 6:00 a. m. a 10:00 p. m.) y envías la solicitud; la administración la aprueba y te llega un aviso. También puedes cancelar tus reservas ahí.", "reservas"),
]


def _fmt_fecha(f: datetime) -> str:
    return f"{DIAS[f.weekday()]} {f:%d/%m} a las {((f.hour + 11) % 12) + 1}:{f:%M} {'a. m.' if f.hour < 12 else 'p. m.'}"


def _txt(texto: Optional[str], maximo: int) -> str:
    """Texto escrito por la administración, listo para entregarse a la IA como DATO (sin etiquetas, enlaces ni números largos)."""
    limpio, _ = ia.limpiar_salida(ia.limpiar_entrada(" ".join((texto or "").split()), maximo * 2), maximo)
    return ia.ocultar_datos_personales(limpio)


def info_conjunto(db: Session, ahora: Optional[datetime] = None) -> dict:
    """Información que ya ven TODOS los residentes en la app (Cartelera y Votaciones abiertas). Sin autores, sin votos ni resultados."""
    ahora = (ahora or ia.ahora_bogota()).replace(tzinfo=None)
    eventos = (db.query(Anuncio).filter(Anuncio.fecha_evento != None, Anuncio.fecha_evento >= ahora)      # noqa: E711
               .order_by(Anuncio.fecha_evento).limit(6).all())
    avisos = (db.query(Anuncio).filter(Anuncio.fecha_creacion >= datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30))
              .order_by(Anuncio.fijado.desc(), Anuncio.fecha_creacion.desc()).limit(5).all())
    utc = datetime.now(timezone.utc).replace(tzinfo=None)
    votaciones = (db.query(Votacion).filter(Votacion.estado == "Abierta", Votacion.fecha_cierre > utc)
                  .order_by(Votacion.fecha_cierre).limit(5).all())
    return {
        "eventos": [{"titulo": _txt(a.titulo, 100), "tipo": a.tipo, "fecha": a.fecha_evento, "lugar": _txt(a.lugar, 80)} for a in eventos],
        "avisos": [{"titulo": _txt(a.titulo, 100), "tipo": a.tipo, "resumen": _txt(a.contenido, 180)} for a in avisos if a.fecha_evento is None or a.fecha_evento < ahora],
        "votaciones": [{"titulo": _txt(v.titulo, 100), "cierra": v.fecha_cierre - timedelta(hours=5), "exige_al_dia": bool(v.exige_al_dia),
                        "un_voto_por": v.un_voto_por} for v in votaciones],
    }


# ---------------------------------------------------------------- estadísticas
def estadisticas(db: Session, ahora: Optional[datetime] = None) -> dict:
    """Reservas por zona y día de la semana (las canceladas no cuentan) y fechas ya ocupadas en los próximos 21 días."""
    ahora = (ahora or ia.ahora_bogota()).replace(tzinfo=None)
    desde, hasta = ahora - timedelta(days=VENTANA_ATRAS_DIAS), ahora + timedelta(days=VENTANA_ADELANTE_DIAS)
    filas = (db.query(Reserva.zona_comun, Reserva.fecha_reserva, Reserva.estado)
             .filter(Reserva.fecha_reserva >= desde, Reserva.fecha_reserva < hasta, Reserva.estado != EstadoReserva.CANCELADA.value)
             .limit(20000).all())
    por_zona: dict[str, dict] = {z: {"dias": Counter(), "franjas": Counter(), "ocupados": set(), "total": 0} for z in ZONAS}
    limite_ocupado = ahora + timedelta(days=21)
    for zona, fecha, estado in filas:
        info = por_zona.get(zona)
        if info is None:                                  # zona con otro nombre escrito por alguien: se ignora
            continue
        info["total"] += 1
        info["dias"][fecha.weekday()] += 1
        info["franjas"]["mañana" if fecha.hour < 12 else "tarde" if fecha.hour < 18 else "noche"] += 1
        if estado == EstadoReserva.APROBADA.value and ahora.date() <= fecha.date() <= limite_ocupado.date():
            info["ocupados"].add(fecha.date())
    return por_zona


def grafico(stats: dict, zona: Optional[str]) -> Optional[GraficoZona]:
    if zona not in stats or stats[zona]["total"] == 0:
        return None
    conteo = stats[zona]["dias"]
    maximo = max(conteo.values())
    dias = [DiaConteo(dia=DIAS[i], total=conteo.get(i, 0), destacado=conteo.get(i, 0) == maximo and maximo > 0) for i in range(7)]
    return GraficoZona(zona=zona, total=stats[zona]["total"], dias=dias)


def contexto_para_ia(stats: dict, ahora: Optional[datetime] = None, info: Optional[dict] = None) -> str:
    """Texto compacto con los datos del conjunto. Son DATOS (no órdenes) y no contienen información de personas."""
    ahora = (ahora or ia.ahora_bogota()).replace(tzinfo=None)
    lineas = [f"Hoy es {DIAS[ahora.weekday()]} {ahora:%d/%m/%Y}. Las cifras cuentan reservas pedidas o aprobadas (no canceladas) de los últimos "
              f"{VENTANA_ATRAS_DIAS} días y los próximos {VENTANA_ADELANTE_DIAS}: miden demanda, no asistencia real."]
    for zona in ZONAS:
        z = stats[zona]
        if z["total"] == 0:
            lineas.append(f"- {zona}: sin reservas registradas.")
            continue
        dias = ", ".join(f"{DIAS[i]} {z['dias'].get(i, 0)}" for i in range(7))
        franjas = ", ".join(f"{k} {v}" for k, v in z["franjas"].most_common())
        ocupados = ", ".join(sorted(f"{d:%d/%m}" for d in z["ocupados"])) or "ninguno"
        poco = " (pocos datos: la tendencia aún no es fiable)" if z["total"] < MIN_RESERVAS_CONFIABLE else ""
        lineas.append(f"- {zona}: {z['total']} reservas{poco}. Por día: {dias}. Franjas: {franjas}. Fechas ya aprobadas en los próximos 21 días: {ocupados}.")
    lineas.append(f"Zonas comunes y aforos: {DETALLE_ZONAS}.")
    lineas.append(GUIA_APP)
    if info is not None:
        lineas.append("PRÓXIMOS EVENTOS Y REUNIONES (Cartelera): " + ("; ".join(
            f"{e['titulo']} ({e['tipo']}) el {_fmt_fecha(e['fecha'])}" + (f" en {e['lugar']}" if e["lugar"] else "") for e in info["eventos"]) or "ninguno programado."))
        lineas.append("AVISOS RECIENTES (Cartelera): " + ("; ".join(f"{a['titulo']} ({a['tipo']}): {a['resumen']}" for a in info["avisos"]) or "ninguno."))
        lineas.append("VOTACIONES ABIERTAS: " + ("; ".join(
            f"{v['titulo']} (cierra el {_fmt_fecha(v['cierra'])}; {'un voto por ' + v['un_voto_por']}{'; exige estar al día' if v['exige_al_dia'] else ''})"
            for v in info["votaciones"]) or "ninguna en este momento."))
    return "\n".join(lineas)


# ---------------------------------------------------------------- respuesta sin IA
def _lista(dias: list[str]) -> str:
    return dias[0] if len(dias) == 1 else ", ".join(dias[:-1]) + " y " + dias[-1]


def responder_basico(texto: str, stats: dict, zona_previa: Optional[str] = None, info: Optional[dict] = None) -> dict:
    """Responde con los datos reales cuando no hay IA (o falló). Devuelve {respuesta, zona, accion, sugerencias}."""
    plano = _plano(texto)
    zona = detectar_zona(texto) or zona_previa
    quiere_libre = bool(re.search(r"\b(libre|libres|tranquil\w*|vacio|vacia|menos (?:concurrid|congestion|lleno|ocupad)\w*|mejor dia)\b", plano))
    pregunta_demanda = bool(re.search(r"(congestion|concurrid|lleno|llena|ocupad|mas visitad|mas usad|dias?|suele|cuando|horario|franja|tarde|noche|manana)", plano))
    pide_reservar = bool(re.search(r"\b(reservar|apartar|agendar|separar)\b", plano))

    if info is not None and re.search(r"(votacion|votar|consulta|encuesta)", plano):
        v = info["votaciones"]
        cuerpo = ("Hay votaciones abiertas: " + "; ".join(f"«{x['titulo']}» (cierra el {_fmt_fecha(x['cierra'])})" for x in v) + ". Tu voto es secreto.") if v else "Ahora mismo no hay votaciones abiertas."
        return {"respuesta": cuerpo, "zona": None, "accion": "votaciones" if v else None, "sugerencias": ["¿Qué eventos hay próximamente?"]}
    if info is not None and re.search(r"(evento|reunion|asamblea|cartelera|proxim\w+ (?:evento|reunion)|que hay (?:este|esta|para)|aviso|anuncio)", plano) and not pide_reservar:
        e, a = info["eventos"], info["avisos"]
        partes = []
        if e:
            partes.append("Próximos eventos: " + "; ".join(f"{x['titulo']} el {_fmt_fecha(x['fecha'])}" + (f" en {x['lugar']}" if x["lugar"] else "") for x in e) + ".")
        if a:
            partes.append("Avisos recientes: " + "; ".join(x["titulo"] for x in a) + ".")
        return {"respuesta": " ".join(partes) or "No hay eventos programados ni avisos recientes en la Cartelera.", "zona": None,
                "accion": "anuncios", "sugerencias": ["¿Hay votaciones abiertas?"]}
    if not pregunta_demanda_zona(plano, zona):
        for patron, ayuda, accion in AYUDA_BASICA:
            if re.search(patron, plano):
                return {"respuesta": ayuda, "zona": None, "accion": accion, "sugerencias": ["¿Qué días suele estar más congestionado el BBQ?", "¿Hay votaciones abiertas?"]}

    if pide_reservar and not pregunta_demanda:
        return {"respuesta": "Para reservar una zona común entra a la sección Reservas, elige la zona, el día y la hora, y la administración confirma tu solicitud.",
                "zona": zona, "accion": "reservas", "sugerencias": ["¿Qué día está más libre la Zona BBQ?", "¿Cuándo se llena más la piscina?"]}

    if zona and pregunta_demanda or zona and quiere_libre:
        info = stats[zona]
        if info["total"] == 0:
            return {"respuesta": f"Todavía no hay reservas registradas en {zona}, así que aún no puedo decirte cuándo se congestiona. ¡Es buen momento para reservar!",
                    "zona": None, "accion": "reservas", "sugerencias": ["¿Cómo reservo una zona?"]}
        conteo = info["dias"]
        valores = [conteo.get(i, 0) for i in range(7)]
        tope, minimo = max(valores), min(valores)
        mas = [DIAS[i] for i, v in enumerate(valores) if v == tope]
        menos = [DIAS[i] for i, v in enumerate(valores) if v == minimo]
        franja = info["franjas"].most_common(1)[0][0]
        aviso = " Ojo: hay pocas reservas registradas, así que es una tendencia inicial." if info["total"] < MIN_RESERVAS_CONFIABLE else ""
        if quiere_libre:
            cuerpo = f"En {zona} lo más tranquilo suele ser {_lista(menos)} ({minimo} reservas). Lo más movido: {_lista(mas)} ({tope})."
        else:
            cuerpo = f"En {zona} los días más congestionados son {_lista(mas)} ({tope} de {info['total']} reservas). Lo más tranquilo: {_lista(menos)}. La franja más pedida es la {franja}."
        return {"respuesta": cuerpo + aviso, "zona": zona, "accion": "reservas",
                "sugerencias": ["¿Qué día está más libre?" if not quiere_libre else "¿Cuál es el día más congestionado?", "¿Y la piscina?" if zona != "Piscina" else "¿Y el salón comunal?"]}

    if pregunta_demanda:                                           # sin zona concreta: ranking general
        totales = sorted(((stats[z]["total"], z) for z in ZONAS if stats[z]["total"]), reverse=True)
        if not totales:
            return {"respuesta": "Aún no hay reservas registradas, por eso no puedo calcular qué zonas se congestionan.", "zona": None, "accion": "reservas", "sugerencias": []}
        top = ", ".join(f"{z} ({n})" for n, z in totales[:3])
        return {"respuesta": f"Las zonas con más demanda son: {top}. Dime de cuál quieres saber los días más congestionados.", "zona": None, "accion": None,
                "sugerencias": [f"¿Qué días se congestiona {totales[0][1]}?"]}

    return {"respuesta": "Puedo contarte qué días y franjas se congestionan las zonas comunes (BBQ, piscina, salón…) y guiarte por la app. "
                         "Por ahora estoy en modo básico, así que pregúntame algo como «¿qué días suele estar más lleno el BBQ?».",
            "zona": None, "accion": None, "sugerencias": ["¿Qué días suele estar más congestionado el BBQ?", "¿Qué día está más libre la piscina?"]}


def pregunta_demanda_zona(plano: str, zona: Optional[str]) -> bool:
    """¿La pregunta trata de la demanda de una zona (y no de ayuda general)? Evita que «cuándo» robe preguntas como «cómo pago»."""
    return bool(zona and re.search(r"(congestion|concurrid|lleno|llena|ocupad|suele|libre|tranquil|dias?|horario|franja)", plano))
