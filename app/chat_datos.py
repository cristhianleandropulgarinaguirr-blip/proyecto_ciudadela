# app/chat_datos.py — Versión 3.2: datos que alimentan al chat y respuestas «básicas» (sin IA).
# Principios:
#   · La IA nunca consulta la base de datos: este módulo calcula estadísticas AGREGADAS (cuántas reservas por zona y día)
#     y solo eso se le entrega como contexto. No salen nombres, apartamentos ni ningún dato de residentes.
#   · Los números del gráfico los calcula el servidor; la IA solo los explica con palabras.
import re
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import NamedTuple, Optional

from sqlalchemy.orm import Session

from app import ia
from app.constantes import EstadoReserva, RolNombre
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


# Secciones que SOLO existen para el administrador. Se usan en las respuestas básicas del administrador y nunca se le ofrecen a otro rol
# (ni siquiera si la IA las pidiera: la IA solo conoce las de ENLACES).
ENLACES_ADMIN = {
    "reservas": ("Aprobar reservas", "#/reservas"),
    "cartera": ("Ver la Cartera", "#/cartera"),
    "importar": ("Ir a Cargar datos", "#/importar"),
    "residentes": ("Ir a Usuarios", "#/residentes"),
    "inquilinos": ("Ver Arrendamientos", "#/inquilinos"),
    "trasteos": ("Ver Trasteos", "#/trasteos"),
    "indicadores": ("Ver Indicadores", "#/indicadores"),
    "auditoria": ("Ver la Auditoría", "#/auditoria"),
}


def accion_para(clave: Optional[str], perfil: Optional["Perfil"] = None) -> Optional[AccionChat]:
    if perfil is not None and perfil.rol == RolNombre.ADMINISTRADOR.value and clave in ENLACES_ADMIN:
        texto, enlace = ENLACES_ADMIN[clave]
        return AccionChat(texto=texto, enlace=enlace)
    if clave in ENLACES:
        texto, enlace = ENLACES[clave]
        # El inquilino solo ve Pagos y Votaciones si el propietario se las delegó: sin permiso no se le ofrece un botón que no podría abrir.
        if perfil is not None and perfil.rol == RolNombre.INQUILINO.value and ((clave == "cartera" and not perfil.puede_pagar) or (clave == "votaciones" and not perfil.puede_votar)):
            return None
        return AccionChat(texto=texto, enlace=enlace)
    return None


# ---------------------------------------------------------------- v4.2 · el asistente habla según el ROL de quien pregunta
# El rol lo decide el servidor con la sesión (nunca el texto del chat): un residente no puede «pedirle al bot» respuestas de administrador.
class Perfil(NamedTuple):
    rol: str = RolNombre.RESIDENTE.value
    puede_pagar: bool = True            # solo cambia para el inquilino: lo que su propietario le delegó
    puede_votar: bool = True


def perfil_de(db: Session, usuario) -> Perfil:
    from app import arrendamientos      # import tardío: este módulo se carga antes que las reglas de arrendamientos
    if usuario.rol == RolNombre.INQUILINO.value:
        d = arrendamientos.delegaciones(db, usuario)
        return Perfil(usuario.rol, "pagar" in d, "votar" in d)
    return Perfil(usuario.rol)


def sugerencias_iniciales(p: Perfil) -> list[str]:
    """Las 4 preguntas con las que arranca el chat: solo cosas que ESE rol puede hacer en la app."""
    if p.rol == RolNombre.ADMINISTRADOR.value:
        return ["¿Cómo apruebo una reserva?", "¿Qué zonas están más congestionadas?", "¿Cómo registro un pago de administración?", "¿Cómo publico un aviso en la Cartelera?"]
    if p.rol == RolNombre.INQUILINO.value:
        return ["¿Cómo reservo una zona?", "¿Cómo creo un pase QR para una visita?",
                "¿Cómo pago la administración?" if p.puede_pagar else "¿Qué puedo hacer como inquilino?",
                "¿Hay votaciones abiertas?" if p.puede_votar else "¿Qué eventos hay próximamente?"]
    return ["¿Cómo reservo una zona?", "¿Qué día está más libre la Zona BBQ?", "¿Cómo creo un pase QR para una visita?", "¿Hay votaciones abiertas?"]


# Preguntas de seguimiento «genéricas» que el modo básico (y a veces la IA) ofrecen: se reescriben o se quitan si no encajan con el rol.
_REEMPLAZOS_ADMIN = {
    "¿Cómo reservo una zona?": "¿Cómo apruebo una reserva?",
    "¿Hay votaciones abiertas?": "¿Cómo creo una votación?",
}


def adaptar_sugerencias(lista: list[str], p: Optional[Perfil], pregunta: Optional[str] = None) -> list[str]:
    """Deja solo seguimientos coherentes con el rol, sin repetidos, máximo 3. Si no queda ninguno, ofrece los iniciales.
    Nunca sugiere la misma pregunta que la persona acaba de hacer."""
    if p is None:
        return lista[:3]
    ya = _plano(pregunta) if pregunta else None
    salida: list[str] = []
    for s in lista:
        if ya and _plano(s) == ya:
            continue
        if p.rol == RolNombre.ADMINISTRADOR.value:
            s = _REEMPLAZOS_ADMIN.get(s, s)
        elif p.rol == RolNombre.INQUILINO.value:
            if (not p.puede_votar and "votacion" in _plano(s)) or (not p.puede_pagar and re.search(r"\b(pago|pagar|saldo)\b", _plano(s))):
                continue
        if s and s not in salida:
            salida.append(s)
    return (salida or [x for x in sugerencias_iniciales(p) if not ya or _plano(x) != ya][:2])[:3]


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

GUIA_INQUILINO_SIN = {
    "pagar": "- Pagos: el pago de la administración lo gestiona el propietario del apartamento (no te lo ha delegado): tú no ves la cartera ni pagas desde tu cuenta; si necesitas un comprobante, pídeselo a él o a la administración.",
    "votar": "- Votaciones: el voto del apartamento es del propietario (no te lo ha delegado): tú no votas desde tu cuenta.",
}
GUIA_ADMIN = """GUÍA DE LA APP PARA LA ADMINISTRACIÓN (cómo se hace cada cosa; no hay más pasos que estos):
- Reservas: en Reservas ves las solicitudes «Pendientes» y pulsas «Aprobar» o «Cancelar»; al residente le llega un aviso. Una zona ya aprobada para ese día no se puede aprobar dos veces.
- Cartera y pagos: en Cartera ves el saldo de cada apartamento. Cuando llega un pago por transferencia pulsas «Registrar pago» (valor y referencia) y queda el comprobante; «Registrar saldo» fija lo que debe un apartamento; «Paz y salvo» genera el certificado en PDF con QR si está al día.
- Cargar datos: en Cargar datos subes el censo de residentes o la cartera mensual desde Excel/CSV; primero ves una «Vista previa» con los errores fila por fila y luego aplicas.
- Cartelera: en Cartelera pulsas «Nuevo anuncio» y «Publicar» (avisos, reuniones y eventos). Si es «Urgente» y hay correo configurado, además sale por correo.
- Votaciones: «Nueva votación» (voto secreto, un voto por apartamento o por coeficiente de copropiedad con quórum). Los resultados se ven al cerrar.
- Quejas y sugerencias (PQRS) y Daños: los residentes radican y tú pulsas «Responder» y cambias el estado; el residente ve el avance.
- Arrendamientos: el propietario registra a su inquilino y tú pulsas «Aprobar» o «Rechazar»; el acceso vence con el contrato.
- Trasteos (mudanzas): el residente solicita, el sistema revisa el paz y salvo en las salidas, tú pulsas «Aprobar» y se alerta a la portería.
- Usuarios: creas cuentas, activas o desactivas y restableces claves temporales. Auditoría: bitácora de lo que se hizo en la app. Indicadores: cartera, zonas más reservadas y tiempos de respuesta.
- Portería: los guardas registran vehículos, visitantes y paquetes; funciona sin internet y se sincroniza al volver la conexión.
- Ajustes (toca tu avatar): cambiar la clave, activar los avisos en el celular, tema claro u oscuro. Campana: guarda tus avisos."""


def guia_para(p: Optional[Perfil]) -> str:
    """La guía que se le entrega a la IA: la del rol de quien pregunta (así no explica botones que esa persona no tiene)."""
    if p is None or p.rol == RolNombre.RESIDENTE.value:
        return GUIA_APP
    if p.rol == RolNombre.ADMINISTRADOR.value:
        return GUIA_ADMIN
    lineas = []
    for linea in GUIA_APP.splitlines():
        if linea.startswith("- Pagos:") and not p.puede_pagar:
            linea = GUIA_INQUILINO_SIN["pagar"]
        elif linea.startswith("- Votaciones:") and not p.puede_votar:
            linea = GUIA_INQUILINO_SIN["votar"]
        elif linea.startswith("- Comercio:"):
            continue                    # el comercio del conjunto es de los propietarios
        lineas.append(linea)
    lineas.append("- Documentos: como inquilino solo ves el Reglamento y las Circulares (no las actas ni los estados financieros).")
    return "\n".join(lineas).replace("GUÍA DE LA APP (", "GUÍA DE LA APP PARA UN INQUILINO (")


def describir_perfil(p: Optional[Perfil]) -> str:
    """Una línea para la IA: con quién habla. La calcula el servidor (es un DATO, no una orden de la persona)."""
    if p is None or p.rol == RolNombre.RESIDENTE.value:
        return "QUIÉN PREGUNTA: un residente (propietario). Orienta con las funciones de residente y propón preguntas de seguimiento de ese tipo."
    if p.rol == RolNombre.ADMINISTRADOR.value:
        return "QUIÉN PREGUNTA: la administración del conjunto. Orienta con las funciones de la administración (aprobar, registrar, publicar) y propón seguimientos de ese tipo, no de residente."
    delegado = ", ".join(x for x, ok in (("pagar la administración", p.puede_pagar), ("votar", p.puede_votar)) if ok) or "nada (no le ha delegado pagos ni votos)"
    return f"QUIÉN PREGUNTA: un inquilino. Su propietario le delegó: {delegado}. No le propongas ni le expliques lo que no puede hacer."


AYUDA_ADMIN = [
    (r"(aprobar|apruebo|aprobacion|pendiente).*(reserva)|(reserva).*(aprobar|apruebo|pendiente)", "En Reservas ves las solicitudes «Pendientes» y pulsas «Aprobar» o «Cancelar»; al residente le llega un aviso.", "reservas"),
    (r"(registr\w+|recib\w+|marcar).*(pago)|(pago).*(registr\w+|recib\w+|transferencia)", "En Cartera pulsas «Registrar pago» en el apartamento, escribes el valor y la referencia de la transferencia y queda el comprobante para el residente.", "cartera"),
    (r"(paz y salvo)", "En Cartera, en el apartamento que está al día, pulsas «Paz y salvo»: se genera el certificado en PDF con un QR que cualquiera puede verificar. Si el apartamento debe, no se emite.", "cartera"),
    (r"(publico|publicar|crear|nuevo|escribir).*(aviso|anuncio|cartelera|circular|evento)|(aviso|anuncio).*(publicar|cartelera)", "En Cartelera pulsas «Nuevo anuncio», eliges el tipo (aviso, reunión, evento o urgente) y «Publicar». Si es «Urgente» y hay correo configurado, también sale por correo.", "anuncios"),
    (r"(votacion|votar|consulta|encuesta)", "En Votaciones pulsas «Nueva votación»: defines las opciones y la fecha de cierre; el voto es secreto y puede ser uno por apartamento o por coeficiente con quórum. Los resultados se ven al cerrar.", "votaciones"),
    (r"(importar|cargar|subir|excel|csv|censo|cartera mensual)", "En Cargar datos subes el censo de residentes o la cartera mensual desde Excel o CSV. Primero ves una «Vista previa» con los errores fila por fila y solo después aplicas los cambios.", "importar"),
    (r"(inquilino|arrendamiento|arriendo|contrato)", "Los propietarios registran a su inquilino y tú lo apruebas o lo rechazas en Arrendamientos; la cuenta del inquilino se entrega al aprobar y su acceso vence con el contrato.", "inquilinos"),
    (r"(trasteo|mudanza)", "En Trasteos ves las solicitudes: en las salidas el sistema revisa el paz y salvo; tú pulsas «Aprobar» y se alerta a la portería, donde el guarda registra el inicio y el fin.", "trasteos"),
    (r"(crear|nuevo|desactivar|activar|restablecer|resetear).*(usuario|cuenta|clave|residente)|(usuario|cuenta|residente).*(crear|desactivar|restablecer)", "En Usuarios creas cuentas, las activas o desactivas y restableces una clave temporal cuando alguien la olvida.", "residentes"),
    (r"(auditoria|bitacora|quien (hizo|cambio)|historial de cambios)", "En Auditoría ves la bitácora de lo que se hizo en la app: quién, qué y cuándo.", "auditoria"),
    (r"(indicador|kpi|estadistica|informe|reporte)", "En Indicadores ves la cartera, las zonas más reservadas, los tiempos de respuesta de las PQRS y el flujo de visitantes por hora.", "indicadores"),
    (r"(pqrs|queja|reclamo|dano|danio|reparar)", "En Quejas y sugerencias y en Daños ves lo que radicaron los residentes: pulsas «Responder» y cambias el estado para que el residente vea el avance.", "pqrs"),
]
AYUDA_INQUILINO = [
    (r"(que puedo hacer|que funciones|que opciones|para que sirve)", "", None),      # se arma según lo delegado (ver _ayuda_por_perfil)
    (r"(votacion|votar|consulta|encuesta)", "NO_VOTAR", "votaciones"),
    (r"(pagar|pago|deuda|saldo|comprobante|administracion cuesta)", "NO_PAGAR", "cartera"),
]


def _ayuda_por_perfil(plano: str, p: Perfil) -> Optional[dict]:
    """Respuestas propias del rol (administración) o aclaraciones de lo que el inquilino NO tiene delegado. None = que siga el flujo normal."""
    if p.rol == RolNombre.ADMINISTRADOR.value:
        for patron, ayuda, accion in AYUDA_ADMIN:
            if re.search(patron, plano):
                return {"respuesta": ayuda, "zona": None, "accion": accion, "sugerencias": ["¿Cómo registro un pago de administración?", "¿Cómo publico un aviso en la Cartelera?"]}
        return None
    if p.rol == RolNombre.INQUILINO.value:
        for patron, clave, accion in AYUDA_INQUILINO:
            if not re.search(patron, plano):
                continue
            if clave == "":
                delegado = [t for t, ok in (("pagar la administración", p.puede_pagar), ("votar", p.puede_votar)) if ok]
                extra = (" Además tu propietario te permite " + " y ".join(delegado) + ".") if delegado else " El pago y el voto del apartamento los maneja tu propietario."
                return {"respuesta": "Como inquilino puedes reservar zonas comunes, ver tus paquetes, autorizar visitas y crear pases QR, reportar daños, radicar quejas y ver la Cartelera, los documentos y las emergencias." + extra, "zona": None, "accion": "reservas", "sugerencias": []}
            if clave == "NO_VOTAR" and not p.puede_votar:
                return {"respuesta": "El voto del apartamento es de tu propietario y no te lo ha delegado, por eso no votas desde tu cuenta. Si quieres hacerlo, pídele que te lo delegue.", "zona": None, "accion": None, "sugerencias": []}
            if clave == "NO_PAGAR" and not p.puede_pagar:
                return {"respuesta": "El pago de la administración lo gestiona tu propietario y no te lo ha delegado, por eso no ves la cartera. Si quieres encargarte tú, pídele que te lo delegue.", "zona": None, "accion": None, "sugerencias": []}
    return None


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


def contexto_para_ia(stats: dict, ahora: Optional[datetime] = None, info: Optional[dict] = None, perfil: Optional[Perfil] = None) -> str:
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
    if perfil is not None:
        lineas.append(describir_perfil(perfil))
    lineas.append(guia_para(perfil))
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


def responder_basico(texto: str, stats: dict, zona_previa: Optional[str] = None, info: Optional[dict] = None, perfil: Optional[Perfil] = None) -> dict:
    """Responde con los datos reales cuando no hay IA (o falló). Devuelve {respuesta, zona, accion, sugerencias}.
    Con `perfil` (v4.2) las respuestas y los seguimientos son los de ese rol; sin él se comporta como siempre (residente)."""
    r = _responder_basico(texto, stats, zona_previa, info, perfil)
    if perfil is not None:
        r["sugerencias"] = adaptar_sugerencias(r["sugerencias"], perfil, texto)
    return r


def _responder_basico(texto: str, stats: dict, zona_previa: Optional[str], info: Optional[dict], perfil: Optional[Perfil]) -> dict:
    plano = _plano(texto)
    if perfil is not None and not pregunta_demanda_zona(plano, detectar_zona(texto) or zona_previa):
        propia = _ayuda_por_perfil(plano, perfil)
        if propia is not None:
            return propia
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
                return {"respuesta": ayuda, "zona": None, "accion": accion, "sugerencias": ["¿Cómo reservo una zona?", "¿Hay votaciones abiertas?", "¿Qué eventos hay próximamente?"]}

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

    return {"respuesta": "¡Hola! Te ayudo con todo lo relacionado con la app y nuestro conjunto: reservas, pagos, paquetes, visitas, votaciones, eventos y más. "
                         "Por ahora estoy en modo básico, así que pregúntame algo concreto, por ejemplo «¿cómo reservo una zona?».",
            "zona": None, "accion": None, "sugerencias": ["¿Cómo reservo una zona?", "¿Hay votaciones abiertas?", "¿Qué días suele estar más congestionado el BBQ?"]}


def pregunta_demanda_zona(plano: str, zona: Optional[str]) -> bool:
    """¿La pregunta trata de la demanda de una zona (y no de ayuda general)? Evita que «cuándo» robe preguntas como «cómo pago»."""
    return bool(zona and re.search(r"(congestion|concurrid|lleno|llena|ocupad|suele|libre|tranquil|dias?|horario|franja)", plano))
