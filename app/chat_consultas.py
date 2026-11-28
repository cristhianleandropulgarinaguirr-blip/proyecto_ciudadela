# app/chat_consultas.py — v5.7 · Consultas de DATOS REALES para el chat (el chatbot «no básico»).
#
# Cómo funciona (y por qué es seguro):
#   1. La IA SOLO elige una consulta de este catálogo cerrado (un `id` + parámetros simples). Nunca escribe SQL ni toca la base de datos.
#   2. El SERVIDOR valida que el rol de la SESIÓN pueda hacer esa consulta y la ejecuta con consultas fijas de solo lectura.
#   3. Lo que ve el administrador en el chat es una TABLA armada por el servidor (con nombres).
#   4. A la IA, para que redacte su análisis, solo le viaja `resumen_ia`: cifras y apartamentos, NUNCA nombres de personas.
# Todo lo que diga la persona o la IA se trata como dato no confiable: los parámetros se validan contra listas cerradas y rangos.
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.chat_datos import _plano
from app.constantes import RolNombre
from app.models import (Arrendamiento, Notificacion, Paquete, PQRS, ReporteDanio, Reserva, Rol, Trasteo, Usuario)

MAX_FILAS = 15                       # filas que se muestran en el chat; el resto se ve completo en la sección correspondiente
MAX_FILAS_IA = 15                    # apartamentos/valores que se le entregan a la IA para su análisis
ADMIN = RolNombre.ADMINISTRADOR.value
UTC_A_BOGOTA = timedelta(hours=-5)


def pesos(n: int) -> str:
    return "$" + f"{int(n or 0):,}".replace(",", ".")


def _fecha_utc(d: Optional[datetime]) -> str:
    return (d + UTC_A_BOGOTA).strftime("%d/%m/%Y %H:%M") if d else "—"


def _fecha_local(d: Optional[datetime]) -> str:
    return d.strftime("%d/%m/%Y %H:%M") if d else "—"


@dataclass
class Resultado:
    titulo: str
    columnas: list[str]
    filas: list[list[str]]                      # lo que ve la persona (puede llevar nombres)
    total: int                                  # cuántos hay en total (puede ser mayor que las filas mostradas)
    resumen_ia: str                             # lo ÚNICO que viaja a la IA: cifras y apartamentos, sin nombres
    resumen_basico: str                         # texto armado por el servidor (modo sin IA o si la IA falla)
    enlace: str = ""
    enlace_texto: str = ""
    vacio: str = "No hay nada por mostrar."


@dataclass
class Consulta:
    id: str
    descripcion: str                            # se le explica a la IA para que elija bien (sin datos)
    ejecutar: Callable[..., Resultado]
    parametros: dict = field(default_factory=dict)      # nombre -> valores permitidos (lista) o «int» con rango
    roles: tuple = (ADMIN,)
    patron: str = ""                            # el modo básico (sin IA) la reconoce con esta expresión sobre el texto sin tildes


def _recortar(filas: list, total: int) -> list:
    return filas[:MAX_FILAS]


# ------------------------------------------------------------------ las consultas
def residentes_en_mora(db: Session, orden: str = "saldo", minimo: int = 0, **_) -> Resultado:
    """Los mismos residentes que ve «Cartera»: activos, con saldo pendiente o sin estar al día."""
    q = (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id)
         .filter(Rol.nombre == RolNombre.RESIDENTE.value, Usuario.esta_activo.is_(True),
                 or_(Usuario.esta_al_dia.is_(False), Usuario.saldo_pendiente > 0)))
    if minimo > 0:
        q = q.filter(Usuario.saldo_pendiente >= minimo)
    q = q.order_by(Usuario.saldo_pendiente.desc(), Usuario.apartamento) if orden == "saldo" else q.order_by(Usuario.apartamento, Usuario.nombre_completo)
    todos = q.all()
    total, suma = len(todos), sum(u.saldo_pendiente or 0 for u in todos)
    filas = [[u.apartamento or "—", u.nombre_completo, pesos(u.saldo_pendiente), pesos(u.valor_administracion)] for u in _recortar(todos, total)]
    if not todos:
        return Resultado("Residentes en mora", ["Apto", "Residente", "Saldo", "Cuota"], [], 0, "No hay residentes en mora.", "Ahora mismo no hay residentes en mora.",
                         "#/cartera", "Abrir Cartera", "No hay residentes en mora.")
    mayor = max(todos, key=lambda u: u.saldo_pendiente or 0)
    sin_saldo = sum(1 for u in todos if not (u.saldo_pendiente or 0))
    lista_ia = "; ".join(f"Apto {u.apartamento or 's/n'}: {pesos(u.saldo_pendiente)}" for u in todos[:MAX_FILAS_IA])
    resumen_ia = (f"Residentes en mora: {total}. Saldo total pendiente: {pesos(suma)}. Promedio por residente: {pesos(suma // total)}. "
                  f"Mayor saldo: apto {mayor.apartamento or 's/n'} con {pesos(mayor.saldo_pendiente)}. "
                  + (f"{sin_saldo} figuran en mora sin saldo registrado. " if sin_saldo else "")
                  + f"Detalle (los {min(total, MAX_FILAS_IA)} de mayor saldo): {lista_ia}.")
    basico = (f"Hay {total} residente{'s' if total != 1 else ''} en mora, con un saldo total de {pesos(suma)}. "
              f"El mayor saldo es el del apto {mayor.apartamento or 's/n'} ({pesos(mayor.saldo_pendiente)}).")
    return Resultado("Residentes en mora", ["Apto", "Residente", "Saldo", "Cuota"], filas, total, resumen_ia, basico, "#/cartera", "Abrir Cartera")


def reservas_pendientes(db: Session, **_) -> Resultado:
    rs = db.query(Reserva).filter(Reserva.estado == "Pendiente").order_by(Reserva.fecha_reserva).all()
    nombres = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({r.usuario_id for r in rs})).all()} if rs else {}
    filas = [[r.zona_comun, _fecha_local(r.fecha_reserva), (nombres.get(r.usuario_id).nombre_completo if nombres.get(r.usuario_id) else "—"),
              (nombres.get(r.usuario_id).apartamento or "—") if nombres.get(r.usuario_id) else "—"] for r in rs[:MAX_FILAS]]
    por_zona: dict = {}
    for r in rs:
        por_zona[r.zona_comun] = por_zona.get(r.zona_comun, 0) + 1
    ia = f"Reservas pendientes de aprobar: {len(rs)}. Por zona: " + (", ".join(f"{z} {n}" for z, n in sorted(por_zona.items(), key=lambda x: -x[1])) or "ninguna") + "."
    return Resultado("Reservas pendientes", ["Zona", "Fecha", "Quién", "Apto"], filas, len(rs), ia,
                     f"Hay {len(rs)} reserva{'s' if len(rs) != 1 else ''} pendiente{'s' if len(rs) != 1 else ''} de aprobar." if rs else "No hay reservas pendientes.",
                     "#/reservas", "Aprobar reservas", "No hay reservas pendientes de aprobar.")


def pqrs_abiertas(db: Session, **_) -> Resultado:
    ps = db.query(PQRS).filter(PQRS.estado.in_(["Radicada", "En tramite"])).order_by(PQRS.fecha_creacion).all()
    nombres = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({p.usuario_id for p in ps})).all()} if ps else {}
    filas = [[p.tipo, p.asunto[:60], (nombres[p.usuario_id].apartamento or "—") if p.usuario_id in nombres else "—", p.estado, _fecha_utc(p.fecha_creacion)] for p in ps[:MAX_FILAS]]
    por_tipo: dict = {}
    for p in ps:
        por_tipo[p.tipo] = por_tipo.get(p.tipo, 0) + 1
    antigua = min((p.fecha_creacion for p in ps if p.fecha_creacion), default=None)
    dias = (datetime.utcnow() - antigua).days if antigua else 0
    ia = (f"PQRS abiertas (radicadas o en trámite): {len(ps)}. Por tipo: " + (", ".join(f"{t} {n}" for t, n in por_tipo.items()) or "ninguna")
          + (f". La más antigua lleva {dias} días sin resolverse." if ps else "."))
    return Resultado("Quejas y sugerencias abiertas", ["Tipo", "Asunto", "Apto", "Estado", "Radicada"], filas, len(ps), ia,
                     f"Hay {len(ps)} PQRS abiertas; la más antigua lleva {dias} días." if ps else "No hay PQRS abiertas.", "#/pqrs", "Abrir Quejas y sugerencias", "No hay PQRS abiertas.")


def danios(db: Session, filtro: str = "pendientes", **_) -> Resultado:
    q = db.query(ReporteDanio)
    q = q.filter(ReporteDanio.estado == "Solucionado") if filtro == "por_aprobar" else q.filter(ReporteDanio.estado != "Aprobado")
    ds = q.order_by(ReporteDanio.fecha_creacion).all()
    nombres = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({d.usuario_id for d in ds})).all()} if ds else {}
    etiqueta = {"Solucionado": "Por aprobar", "En Revision": "En revisión", "En Reparacion": "En reparación"}
    filas = [[d.titulo[:55], (nombres[d.usuario_id].apartamento or "—") if d.usuario_id in nombres else "—", etiqueta.get(d.estado, d.estado), _fecha_utc(d.fecha_creacion)] for d in ds[:MAX_FILAS]]
    por_estado: dict = {}
    for d in ds:
        por_estado[etiqueta.get(d.estado, d.estado)] = por_estado.get(etiqueta.get(d.estado, d.estado), 0) + 1
    titulo = "Daños por aprobar" if filtro == "por_aprobar" else "Daños sin cerrar"
    ia = f"{titulo}: {len(ds)}. Por estado: " + (", ".join(f"{e} {n}" for e, n in por_estado.items()) or "ninguno") + "."
    return Resultado(titulo, ["Daño", "Apto", "Estado", "Reportado"], filas, len(ds), ia,
                     f"{titulo}: {len(ds)}." if ds else "No hay daños en ese estado.", "#/mantenimiento", "Abrir Mantenimiento", "No hay daños en ese estado.")


def trasteos_por_aprobar(db: Session, **_) -> Resultado:
    ts = db.query(Trasteo).filter(Trasteo.estado == "Pendiente").order_by(Trasteo.fecha_inicio).all()
    filas = [[t.apartamento or "—", t.tipo, _fecha_utc(t.fecha_inicio), t.empresa or "—"] for t in ts[:MAX_FILAS]]
    ia = f"Trasteos pendientes de aprobar: {len(ts)}." + (f" El más próximo es el {_fecha_utc(ts[0].fecha_inicio)}." if ts else "")
    return Resultado("Trasteos por aprobar", ["Apto", "Tipo", "Desde", "Empresa"], filas, len(ts), ia,
                     f"Hay {len(ts)} trasteo{'s' if len(ts) != 1 else ''} por aprobar." if ts else "No hay trasteos por aprobar.", "#/trasteos", "Ver Trasteos", "No hay trasteos por aprobar.")


def arrendamientos_por_aprobar(db: Session, **_) -> Resultado:
    cs = db.query(Arrendamiento).filter(Arrendamiento.estado == "Pendiente").order_by(Arrendamiento.fecha_creacion).all()
    ids = {c.inquilino_id for c in cs}
    nombres = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if cs else {}
    filas = [[c.apartamento or "—", nombres.get(c.inquilino_id, "—"), _fecha_local(c.fecha_inicio)[:10], _fecha_local(c.fecha_fin)[:10]] for c in cs[:MAX_FILAS]]
    ia = f"Contratos de arrendamiento por aprobar: {len(cs)}."
    return Resultado("Arrendamientos por aprobar", ["Apto", "Inquilino", "Desde", "Hasta"], filas, len(cs), ia,
                     f"Hay {len(cs)} contrato{'s' if len(cs) != 1 else ''} de arrendamiento por aprobar." if cs else "No hay arrendamientos por aprobar.",
                     "#/inquilinos", "Ver Arrendamientos", "No hay arrendamientos por aprobar.")


def paquetes_sin_recoger(db: Session, **_) -> Resultado:
    ps = db.query(Paquete).filter(Paquete.estado == "En porteria").order_by(Paquete.fecha_recepcion).all()
    nombres = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({p.destinatario_id for p in ps})).all()} if ps else {}
    filas = [[(nombres[p.destinatario_id].apartamento or "—") if p.destinatario_id in nombres else "—", p.remitente or "—", _fecha_utc(p.fecha_recepcion)] for p in ps[:MAX_FILAS]]
    antiguo = min((p.fecha_recepcion for p in ps if p.fecha_recepcion), default=None)
    dias = (datetime.utcnow() - antiguo).days if antiguo else 0
    ia = f"Paquetes en portería sin recoger: {len(ps)}." + (f" El más antiguo lleva {dias} días." if ps else "")
    return Resultado("Paquetes sin recoger", ["Apto", "Remitente", "Llegó"], filas, len(ps), ia,
                     f"Hay {len(ps)} paquete{'s' if len(ps) != 1 else ''} sin recoger en portería." if ps else "No hay paquetes sin recoger.", "#/paquetes", "Ver paquetes", "No hay paquetes sin recoger.")


def avisos_por_gestionar(db: Session, usuario: Optional[Usuario] = None, **_) -> Resultado:
    ns = (db.query(Notificacion).filter(Notificacion.usuario_id == (usuario.id if usuario else -1), Notificacion.requiere_gestion.is_(True), Notificacion.gestionada_en.is_(None))
          .order_by(Notificacion.id.desc()).all())
    filas = [[n.titulo, (n.mensaje or "")[:80], _fecha_utc(n.fecha)] for n in ns[:MAX_FILAS]]
    ia = f"Avisos del administrador por gestionar: {len(ns)}. Títulos: " + ("; ".join(sorted({n.titulo for n in ns})) or "ninguno") + "."
    return Resultado("Avisos por gestionar", ["Aviso", "Detalle", "Fecha"], filas, len(ns), ia,
                     f"Tienes {len(ns)} aviso{'s' if len(ns) != 1 else ''} por gestionar." if ns else "No tienes avisos por gestionar.", "", "", "Estás al día: no tienes avisos por gestionar.")


CATALOGO: dict[str, Consulta] = {c.id: c for c in [
    Consulta("residentes_en_mora", "Lista de residentes que están en mora de administración (apartamento, nombre, saldo). Para «quién debe», «morosos», «cartera vencida».",
             residentes_en_mora, {"orden": ["saldo", "apartamento"], "minimo": (0, 100_000_000)},
             patron=r"\b(mora|moroso|morosos|morosas|adeud\w*|deben|debe plata|cartera vencida|atrasad\w+ (?:en|con) (?:el )?pago|sin pagar)\b"),
    Consulta("reservas_pendientes", "Reservas de zonas comunes que esperan aprobación del administrador.", reservas_pendientes,
             patron=r"\breservas?\b.*\b(pendiente|por aprobar|sin aprobar|esperando)|\b(pendiente|por aprobar)\w*\b.*\breservas?\b"),
    Consulta("pqrs_abiertas", "Quejas, peticiones, reclamos y sugerencias (PQRS) abiertas que aún no se resuelven.", pqrs_abiertas,
             patron=r"\b(pqrs|quejas?|reclamos?|peticion(?:es)?|sugerencias?)\b.*\b(abierta|abiertas|pendiente|pendientes|sin responder|sin resolver|por responder)|\b(pendiente|pendientes|abiertas?)\b.*\b(pqrs|quejas?|reclamos?)"),
    Consulta("danios", "Reportes de daños (mantenimiento). filtro=pendientes (todo lo no cerrado) o por_aprobar (el técnico ya terminó y falta la aprobación del administrador).",
             danios, {"filtro": ["pendientes", "por_aprobar"]},
             patron=r"\b(danos?|danios?|reparaciones|arreglos?)\b.*\b(pendiente|pendientes|abierto|abiertos|por aprobar|sin cerrar|sin resolver)|\b(pendiente|pendientes|por aprobar)\b.*\b(danos?|danios?)"),
    Consulta("trasteos_por_aprobar", "Solicitudes de trasteo (mudanzas) pendientes de aprobar.", trasteos_por_aprobar, patron=r"\b(trasteos?|mudanzas?)\b"),
    Consulta("arrendamientos_por_aprobar", "Contratos de arrendamiento (inquilinos) pendientes de aprobar.", arrendamientos_por_aprobar,
             patron=r"\b(arriendos?|arrendamientos?|inquilinos?)\b.*\b(pendiente|pendientes|por aprobar|sin aprobar)|\b(pendiente|pendientes|por aprobar)\b.*\b(arriendos?|arrendamientos?|inquilinos?)"),
    Consulta("paquetes_sin_recoger", "Paquetes que están en portería esperando que el residente los recoja.", paquetes_sin_recoger,
             patron=r"\bpaquetes?\b.*\b(porteria|sin recoger|sin entregar|pendiente|pendientes|esperando)|\b(sin recoger|sin entregar)\b.*\bpaquetes?"),
    Consulta("avisos_por_gestionar", "Avisos (notificaciones) del propio administrador que siguen por gestionar: lo que tiene pendiente por hacer.", avisos_por_gestionar,
             patron=r"\b(por gestionar|sin gestionar|que tengo pendiente|mis pendientes|pendientes? por hacer|que me falta|que debo gestionar|que debo hacer hoy)\b"),
]}


# ------------------------------------------------------------------ puertas de entrada (validan TODO lo que viene de la IA o del texto)
def disponibles(rol: str) -> list[Consulta]:
    return [c for c in CATALOGO.values() if rol in c.roles]


def catalogo_para_ia(rol: str) -> str:
    """El catálogo que se le muestra a la IA: ids, para qué sirve cada uno y qué parámetros acepta. No contiene datos de nadie."""
    lineas = []
    for c in disponibles(rol):
        parametros = "; ".join(f"{n}={'|'.join(v) if isinstance(v, list) else f'número entre {v[0]} y {v[1]}'}" for n, v in c.parametros.items())
        lineas.append(f"- {c.id}: {c.descripcion}" + (f" Parámetros opcionales: {parametros}." if parametros else ""))
    return "\n".join(lineas)


def ids_validos() -> list[str]:
    return list(CATALOGO)


def _limpiar_parametros(c: Consulta, crudos) -> dict:
    """Solo pasan los parámetros declarados y con valores permitidos; cualquier otra cosa se descarta en silencio."""
    limpios: dict = {}
    if not isinstance(crudos, dict):
        return limpios
    for nombre, permitido in c.parametros.items():
        v = crudos.get(nombre)
        if isinstance(permitido, list):
            if isinstance(v, str) and v in permitido:
                limpios[nombre] = v
        else:
            try:
                n = int(re.sub(r"[^\d]", "", str(v))) if v is not None else None
            except ValueError:
                n = None
            if n is not None and permitido[0] <= n <= permitido[1]:
                limpios[nombre] = n
    return limpios


def ejecutar(db: Session, usuario: Usuario, consulta_id: Optional[str], parametros=None) -> Optional[Resultado]:
    """Ejecuta una consulta SOLO si existe y el rol de la sesión puede hacerla. Devuelve None si no corresponde (la IA o el texto pueden pedir lo que sea)."""
    c = CATALOGO.get(consulta_id or "")
    if c is None or usuario.rol not in c.roles:
        return None
    return c.ejecutar(db, usuario=usuario, **_limpiar_parametros(c, parametros))


_MINIMO = re.compile(r"(?:mas de|mayor(?:es)? (?:a|de)|superior(?:es)? a|desde)\s+\$?\s*([\d.,]+)\s*(millon(?:es)?|mil)?")


def detectar(texto: str, rol: str) -> Optional[tuple[str, dict]]:
    """Modo sin IA: reconoce las preguntas más comunes del administrador con expresiones regulares sobre el texto sin tildes."""
    plano = _plano(texto).lstrip("¿¡ \t\"'«")                 # sin los signos de apertura: «¿Cómo…» empieza con «¿», no con «cómo»
    # Una pregunta de «cómo se hace» no pide datos: «¿Cómo registro a un residente en mora?» se la responde la guía, no la tabla.
    if re.match(r"^(como|donde|que pasos|cual es el proceso|que significa|para que sirve)\b", plano) and not re.search(r"\b(quien|quienes|cuantos|cuantas|lista|listame|muestrame|dame|dime)\b", plano):
        return None
    for c in disponibles(rol):
        if c.patron and re.search(c.patron, plano):
            parametros: dict = {}
            if c.id == "residentes_en_mora":
                if "por apartamento" in plano or "orden alfabetico" in plano:
                    parametros["orden"] = "apartamento"
                m = _MINIMO.search(plano)
                if m:
                    try:
                        valor = float(m.group(1).replace(".", "").replace(",", "."))
                        parametros["minimo"] = int(valor * (1_000_000 if (m.group(2) or "").startswith("millon") else 1000 if m.group(2) == "mil" else 1))
                    except ValueError:
                        pass
            if c.id == "danios" and re.search(r"por aprobar|sin aprobar|solucionad", plano):
                parametros["filtro"] = "por_aprobar"
            return c.id, parametros
    return None
