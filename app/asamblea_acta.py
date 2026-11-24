# app/asamblea_acta.py
# Reglas de negocio del ACTA de la asamblea (Art. 47 de la Ley 675 de 2001) — V5.4, Fase 4. Los endpoints (routers/asamblea_acta.py) solo traducen HTTP a estas funciones.
#
# Qué exige el Art. 47 y cómo lo cubre este módulo (lectura prudente; la valida un abogado de propiedad horizontal):
#  · El acta indica si la asamblea es ordinaria o extraordinaria, la forma de la convocatoria, el orden del día, el nombre y la calidad de los asistentes
#    (propietario o apoderado) con su coeficiente y los votos emitidos en cada caso  →  `construir_contenido` y `render_pdf`.
#  · La firman el presidente y el secretario de la reunión  →  el PDF trae los renglones de firma y la app guarda la copia firmada y escaneada.
#  · El administrador la pone a disposición de los propietarios dentro de los 20 días hábiles siguientes a la fecha de la reunión  →  `limite_publicacion`.
#
# Ciclo: Borrador (se edita) → Sellada (se CONGELA: contenido completo + huella SHA-256, que queda en la bitácora encadenada) → copia firmada → publicada.
#
# Qué NO hace: no reemplaza el libro de actas ni al presidente, al secretario o al abogado. El PDF es el soporte que genera la app; la validez del acta
# depende de las firmas y de que el proceso de la asamblea se haya cumplido conforme a la ley y al reglamento del conjunto.
import hashlib
import io
import json
import re
from datetime import date, datetime
from typing import Optional
from xml.sax.saxutils import escape

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app import asamblea_votos as reglas_votos, asambleas as reglas, calendario_co, config, marca, unidades as reglas_unidades
from app.archivos import leer_documento
from app.constantes import EstadoActa, EstadoVotacionAsamblea, ModalidadAsamblea
from app.models import (Asamblea, AsambleaActa, AsambleaAsistente, AsambleaEvento, AsambleaVotacion, AsambleaVotacionOpcion, AsambleaVoto, Unidad, ahora_utc)

VERSION_CONTENIDO = 1
DECIMALES = 6


# ---------------------------------------------------------------- acceso y plazo
def acta_de(db: Session, asamblea_id: int) -> Optional[AsambleaActa]:
    return db.query(AsambleaActa).filter(AsambleaActa.asamblea_id == asamblea_id).one_or_none()


def fecha_reunion(a: Asamblea) -> date:
    """Día (hora de Colombia) en que se instaló la asamblea; si aún no se instala, el de la reunión citada."""
    return reglas.local(a.instalada_en or a.fecha_sesion).date()


def limite_publicacion(a: Asamblea) -> date:
    """Último día para poner el acta a disposición de los propietarios: `ASAMBLEA_ACTA_DIAS_HABILES` (20) días hábiles contados desde la fecha de la reunión (ese día no cuenta)."""
    return calendario_co.dia_habil_numero(fecha_reunion(a), config.ASAMBLEA_ACTA_DIAS_HABILES, config.ASAMBLEA_SABADO_HABIL)


def plazo_vencido(a: Asamblea, ahora: Optional[datetime] = None) -> bool:
    return reglas.local(ahora or ahora_utc()).date() > limite_publicacion(a)


def esta_sellada(acta: Optional[AsambleaActa]) -> bool:
    return bool(acta and acta.estado == EstadoActa.SELLADA.value)


# ---------------------------------------------------------------- contenido (todo lo que lleva el acta)
def _r(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), DECIMALES)


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _bloque_asamblea(a: Asamblea) -> dict:
    return {"id": a.id, "titulo": a.titulo, "tipo": a.tipo, "modalidad": a.modalidad, "lugar": a.lugar, "url_videollamada": a.url_videollamada,
            "instrucciones_virtual": a.instrucciones_virtual, "orden_del_dia": a.orden_del_dia, "fecha_sesion": _iso(a.fecha_sesion), "fecha_segunda": _iso(a.fecha_segunda),
            "fecha_convocatoria": _iso(a.fecha_convocatoria), "convocatoria_hash": a.convocatoria_hash, "sin_quorum_en": _iso(a.sin_quorum_en),
            "convocatoria_numero": a.convocatoria_numero, "instalada_en": _iso(a.instalada_en), "cerrada_en": _iso(a.cerrada_en), "quorum_inicial": _r(a.quorum_inicial),
            "quorum_final": _r(a.quorum_final), "restringe_mora": bool(a.restringe_mora), "max_poderes": a.max_poderes}


def _bloque_convocatoria(db: Session, a: Asamblea) -> dict:
    """Cómo se convocó: documentos que acompañaron la convocatoria y por qué medio se avisó a cada unidad (app o entrega manual)."""
    ultimo: dict[int, str] = {}
    for ev in db.query(AsambleaEvento).filter(AsambleaEvento.asamblea_id == a.id, AsambleaEvento.tipo.in_(["Notificada", "SinCuenta", "EntregaManual"]),
                                              AsambleaEvento.unidad_id.isnot(None)).order_by(AsambleaEvento.secuencia).all():
        ultimo[ev.unidad_id] = ev.tipo
    dias = (reglas.local(a.fecha_sesion).date() - reglas.local(a.fecha_convocatoria).date()).days if a.fecha_convocatoria else None
    return {"dias_anticipacion": dias, "unidades_avisadas": len(ultimo),
            "por_app": sum(1 for t in ultimo.values() if t == "Notificada"), "entrega_manual": sum(1 for t in ultimo.values() if t == "EntregaManual"),
            "pendientes": sum(1 for t in ultimo.values() if t == "SinCuenta"),
            "documentos": [d.titulo for d in reglas.documentos_adjuntos(db, a.id)]}


def _asistentes(db: Session, a: Asamblea) -> list[dict]:
    """Una fila por unidad acreditada. NO lleva el número de documento: el acta se pone a disposición de todos los propietarios y la ley no lo exige."""
    aptos = {u.id: u.apartamento for u in db.query(Unidad).all()}
    filas = db.query(AsambleaAsistente).filter(AsambleaAsistente.asamblea_id == a.id).all()
    salida = [{"unidad_id": f.unidad_id, "unidad": aptos.get(f.unidad_id, "?"), "nombre": f.nombre, "calidad": "Apoderado" if f.es_apoderado else "Propietario",
               "modalidad": f.modalidad_ingreso, "coeficiente": _r(f.coeficiente_acreditado), "ingreso": _iso(f.hora_ingreso), "salida": _iso(f.hora_salida),
               "con_voto": bool(f.con_voto)} for f in filas]
    return sorted(salida, key=lambda x: (x["unidad"], x["unidad_id"]))


def _votaciones(db: Session, a: Asamblea) -> list[dict]:
    """Cada pregunta con su resultado congelado. Los votos de la app son SECRETOS (solo constan unidades y coeficiente por opción); los presenciales son nominales."""
    aptos = {u.id: u.apartamento for u in db.query(Unidad).all()}
    salida = []
    for v in db.query(AsambleaVotacion).filter(AsambleaVotacion.asamblea_id == a.id).order_by(AsambleaVotacion.numero).all():
        d = {"numero": v.numero, "titulo": v.titulo, "descripcion": v.descripcion, "tipo": v.tipo, "mayoria": v.mayoria, "estado": v.estado}
        if v.estado in (EstadoVotacionAsamblea.ABIERTA.value, EstadoVotacionAsamblea.CERRADA.value, EstadoVotacionAsamblea.ANULADA.value) and v.abierta_en:
            d.update(abierta_en=_iso(v.abierta_en), padron_unidades=len(reglas_votos.padron_de(v)), coeficiente_padron=_r(v.coef_padron), quorum_apertura=_r(v.quorum_apertura))
        if v.estado == EstadoVotacionAsamblea.CERRADA.value and v.resultado:
            res = json.loads(v.resultado)
            filas = (db.query(AsambleaVoto.unidad_id, AsambleaVoto.peso, AsambleaVotacionOpcion.texto)
                     .join(AsambleaVotacionOpcion, AsambleaVotacionOpcion.id == AsambleaVoto.opcion_id)
                     .filter(AsambleaVoto.votacion_id == v.id, AsambleaVoto.via == "Manual").all())
            nominales = sorted(({"unidad": aptos.get(u, "?"), "coeficiente": _r(p), "voto": t} for u, p, t in filas), key=lambda x: x["unidad"])
            d.update(cerrada_en=_iso(v.cerrada_en), quorum_cierre=_r(v.quorum_cierre), resultado=res, resultado_hash=v.resultado_hash,
                     titular=reglas_votos.titular_resultado(v, res), votos_nominales=nominales)
        if v.estado == EstadoVotacionAsamblea.ANULADA.value:
            d["motivo_anulacion"] = v.motivo_anulacion
        salida.append(d)
    return salida


def _bitacora_hasta(db: Session, a: Asamblea, hasta: Optional[int] = None) -> dict:
    q = db.query(AsambleaEvento.secuencia, AsambleaEvento.hash).filter(AsambleaEvento.asamblea_id == a.id)
    if hasta is not None:
        q = q.filter(AsambleaEvento.secuencia <= hasta)
    ultimo = q.order_by(AsambleaEvento.secuencia.desc()).first()
    return {"secuencia": ultimo[0] if ultimo else 0, "huella": ultimo[1] if ultimo else reglas.HASH_INICIAL}


def calcular_evidencia(db: Session, a: Asamblea, secuencia_bitacora: Optional[int] = None) -> dict:
    """Lo que prueba lo ocurrido: asistentes, votaciones y el punto de la bitácora encadenada. Es lo que `verificar` vuelve a calcular contra la base de datos."""
    return {"asistentes": _asistentes(db, a), "votaciones": _votaciones(db, a), "bitacora": _bitacora_hasta(db, a, secuencia_bitacora)}


def construir_contenido(db: Session, a: Asamblea, acta: Optional[AsambleaActa]) -> dict:
    """El acta completa como datos. Sin la hora en que se genera: así el mismo estado de la asamblea siempre da la misma huella."""
    resumen = reglas_unidades.resumen(db)
    ev = calcular_evidencia(db, a)
    presentes = [x for x in ev["asistentes"] if x["salida"] is None]
    return {
        "version": VERSION_CONTENIDO,
        "asamblea": _bloque_asamblea(a),
        "convocatoria": _bloque_convocatoria(db, a),
        "dignatarios": {"presidente": acta.presidente_nombre if acta else None, "secretario": acta.secretario_nombre if acta else None, "comision": acta.comision if acta else None},
        "desarrollo": acta.desarrollo if acta else None,
        "quorum": {"unidades_total": resumen.unidades, "coeficiente_total": _r(resumen.total), "unidades_presentes": len(presentes),
                   "coeficiente_presente": _r(sum(x["coeficiente"] for x in presentes))},
        "plazo": {"dias_habiles": config.ASAMBLEA_ACTA_DIAS_HABILES, "limite_publicacion": limite_publicacion(a).isoformat()},
        "evidencia": ev,
    }


def _canonico(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def huella(contenido: dict) -> str:
    return hashlib.sha256(_canonico(contenido).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- verificación
def verificar(db: Session, a: Asamblea, acta: AsambleaActa) -> dict:
    """Comprueba que el acta sellada no se alteró. Cuatro revisiones independientes; si cualquiera falla, `ok` es falso."""
    if not esta_sellada(acta) or not acta.contenido:
        raise HTTPException(status_code=409, detail="El acta todavía no está sellada: no hay nada congelado que verificar.")
    pruebas: list[dict] = []

    def anotar(nombre: str, ok: bool, detalle: str) -> None:
        pruebas.append({"nombre": nombre, "ok": bool(ok), "detalle": detalle})

    guardado = json.loads(acta.contenido)
    anotar("Texto del acta", huella(guardado) == acta.contenido_hash,
           "El contenido congelado coincide con su huella SHA-256." if huella(guardado) == acta.contenido_hash else "El contenido guardado del acta fue modificado: su huella ya no coincide.")

    hasta = guardado["evidencia"]["bitacora"]["secuencia"]
    ahora_ = {"asamblea": _bloque_asamblea(a), "evidencia": calcular_evidencia(db, a, hasta)}
    antes = {"asamblea": guardado["asamblea"], "evidencia": guardado["evidencia"]}
    distintas = [n for n, x, y in (("datos de la asamblea", ahora_["asamblea"], antes["asamblea"]), ("asistentes", ahora_["evidencia"]["asistentes"], antes["evidencia"]["asistentes"]),
                                   ("votaciones", ahora_["evidencia"]["votaciones"], antes["evidencia"]["votaciones"]), ("bitácora", ahora_["evidencia"]["bitacora"], antes["evidencia"]["bitacora"]))
                 if _canonico(x) != _canonico(y)]
    anotar("Asistentes y votos", not distintas,
           "Lo que hoy hay en la base de datos (asistentes, votaciones y resultados) es idéntico a lo que se congeló." if not distintas
           else "Hay diferencias con lo congelado en: " + ", ".join(distintas) + ". Alguien modificó la base de datos después de sellar el acta.")

    integra, danada, total = reglas.verificar_bitacora(db, a.id)
    anotar("Bitácora encadenada", integra, f"Los {total} eventos están encadenados y ninguno fue alterado." if integra else f"La cadena se rompe en el evento n.º {danada}.")

    if acta.firmada_archivo:
        datos = leer_documento(acta.firmada_archivo)
        ok = datos is not None and hashlib.sha256(datos).hexdigest() == acta.firmada_hash
        anotar("Copia firmada", ok, "El PDF firmado guardado es el mismo que se subió." if ok else "El PDF firmado ya no coincide con el que se subió (o no está disponible).")
    return {"ok": all(p["ok"] for p in pruebas), "huella": acta.contenido_hash, "sellada_en": acta.sellada_en, "comprobaciones": pruebas}


# ---------------------------------------------------------------- PDF
def _num(x: Optional[float], dec: int = 4) -> str:
    if x is None:
        return "—"
    return format(float(x), f".{dec}f").rstrip("0").rstrip(".").replace(".", ",") or "0"


def _fecha(iso: Optional[str]) -> str:
    return reglas.fmt_local(datetime.fromisoformat(iso)) if iso else "—"


def _corta(iso: Optional[str]) -> str:
    return reglas.local(datetime.fromisoformat(iso)).strftime("%d/%m %H:%M") if iso else "—"


def _canvas_con_pie(pie: str, marca_agua: Optional[str]):
    """Canvas que dibuja en cada página «Página x de y», el pie y, si es borrador, la marca de agua."""
    class _Numerado(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas: list[dict] = []

        def showPage(self):
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._decorar(total)
                super().showPage()
            super().save()

        def _decorar(self, total: int) -> None:
            ancho, alto = letter
            if marca_agua:
                self.saveState()
                self.setFont("Helvetica-Bold", 96)
                self.setFillColor(colors.Color(0.55, 0.55, 0.55))
                self.setFillAlpha(0.13)
                self.translate(ancho / 2, alto / 2)
                self.rotate(45)
                self.drawCentredString(0, 0, marca_agua)
                self.restoreState()
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#555555"))
            self.drawString(2.2 * cm, 1.1 * cm, pie[:150])
            self.drawRightString(ancho - 2.2 * cm, 1.1 * cm, f"Página {self._pageNumber} de {total}")
    return _Numerado


def render_pdf(c: dict, *, borrador: bool, huella_acta: Optional[str] = None, sellada_en: Optional[datetime] = None) -> bytes:
    """Dibuja el acta a partir de sus datos (`construir_contenido` o el JSON congelado). El borrador lleva marca de agua y NO tiene valor hasta sellarse y firmarse."""
    asm, conv, dig, qr, ev = c["asamblea"], c["convocatoria"], c["dignatarios"], c["quorum"], c["evidencia"]
    est = getSampleStyleSheet()
    normal = ParagraphStyle("n", parent=est["Normal"], fontSize=9.5, leading=13.5)
    celda = ParagraphStyle("c", parent=normal, fontSize=8, leading=10)
    celda_b = ParagraphStyle("cb", parent=celda, fontName="Helvetica-Bold")
    titulo = ParagraphStyle("t", parent=est["Title"], fontSize=14.5, leading=18, spaceAfter=2)
    sub = ParagraphStyle("s", parent=est["Heading3"], fontSize=11, spaceBefore=11, spaceAfter=3, textColor=colors.HexColor("#17324D"))
    pequeno = ParagraphStyle("p", parent=normal, fontSize=8, leading=10.5, textColor=colors.HexColor("#555555"))
    aviso = ParagraphStyle("a", parent=normal, fontSize=9, leading=12, textColor=colors.HexColor("#8A1C1C"), borderColor=colors.HexColor("#C9A0A0"), borderWidth=0.8, borderPadding=5, spaceAfter=8)
    P = lambda t, e=normal: Paragraph(re.sub(r"(?<!\.)\.\.(?!\.)", ".", t), e)        # noqa: E731  (las fechas terminan en «p. m.»: evita el doble punto al cerrar la frase)
    E = escape
    reunion_virtual = asm["modalidad"] in (ModalidadAsamblea.VIRTUAL.value, ModalidadAsamblea.MIXTA.value)

    def tabla(filas, anchos, cabecera=True, extra=()):
        t = Table(filas, colWidths=anchos, repeatRows=1 if cabecera else 0)
        estilo = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#B8C2C8")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
        if cabecera:
            estilo.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E9EEF1")))
        t.setStyle(TableStyle(estilo + list(extra)))
        return t

    partes: list = []
    if borrador:
        partes.append(P("<b>BORRADOR.</b> Documento de trabajo generado con la información registrada hasta este momento. No tiene valor como acta hasta que se selle en la aplicación y la firmen el presidente y el secretario.", aviso))
    partes += [P(E(marca.nombre()), pequeno), P(f"ACTA DE ASAMBLEA GENERAL {E(asm['tipo'].upper())} DE COPROPIETARIOS", titulo),
               P(E(asm["titulo"]), ParagraphStyle("st", parent=normal, alignment=1, fontSize=11.5)), Spacer(1, 6)]

    # 1. datos de la reunión
    partes.append(P("1. Datos de la reunión", sub))
    partes.append(P(f"<b>Clase de asamblea:</b> {E(asm['tipo'])} · <b>Modalidad:</b> {E(asm['modalidad'].lower())}."))
    if asm["lugar"]:
        partes.append(P(f"<b>Lugar:</b> {E(asm['lugar'])}."))
    if reunion_virtual:
        partes.append(P("<b>Medios tecnológicos:</b> " + E(" · ".join(x for x in (asm["url_videollamada"], asm["instrucciones_virtual"]) if x) or "los indicados en la convocatoria") + "."))
    if asm["sin_quorum_en"]:
        partes.append(P(f"La primera convocatoria ({_fecha(asm['fecha_sesion'])}) no logró quórum; se dejó constancia el {_fecha(asm['sin_quorum_en'])} y la reunión se citó en segunda convocatoria."))
    if asm["instalada_en"]:
        partes.append(P(f"<b>Instalación:</b> {_fecha(asm['instalada_en'])}, en {asm['convocatoria_numero']}.ª convocatoria. <b>Cierre:</b> {_fecha(asm['cerrada_en']) if asm['cerrada_en'] else 'la reunión sigue en curso'}."))
    else:
        partes.append(P(f"<b>Reunión citada para:</b> {_fecha(asm['fecha_sesion'])} (aún sin instalar)."))

    # 2. convocatoria
    partes.append(P("2. Convocatoria", sub))
    dias = f", con {conv['dias_anticipacion']} día(s) calendario de diferencia hasta la reunión" if conv["dias_anticipacion"] is not None else ""
    partes.append(P(f"La convocatoria se envió el {_fecha(asm['fecha_convocatoria'])}{dias}. Segunda convocatoria prevista: {_fecha(asm['fecha_segunda'])}."))
    partes.append(P(f"Se avisó a {conv['unidades_avisadas']} unidad(es): {conv['por_app']} por la aplicación, {conv['entrega_manual']} con entrega manual registrada"
                    + (f" y {conv['pendientes']} sin constancia de entrega" if conv["pendientes"] else "") + "."))
    if conv["documentos"]:
        partes.append(P("Documentos que acompañaron la convocatoria: " + E("; ".join(conv["documentos"])) + "."))
    if asm["convocatoria_hash"]:
        partes.append(P(f"Huella (SHA-256) del contenido de la convocatoria enviada: <font name='Courier'>{asm['convocatoria_hash']}</font>", pequeno))

    # 3. orden del día
    partes.append(P("3. Orden del día", sub))
    partes += [P(E(l.strip())) for l in asm["orden_del_dia"].splitlines() if l.strip()]

    # 4. quórum
    partes.append(P("4. Verificación del quórum", sub))
    regla = "más de la mitad de los coeficientes de copropiedad" if asm["convocatoria_numero"] != 2 else "un número plural de propietarios (segunda convocatoria, Art. 41)"
    partes.append(P(f"Quórum al instalar: <b>{_num(asm['quorum_inicial'])} %</b> del coeficiente (se exige {regla}). "
                    + (f"Quórum al cierre: <b>{_num(asm['quorum_final'])} %</b>." if asm["quorum_final"] is not None else "El quórum final se registra al cerrar la reunión.")))
    partes.append(P(f"{'Presentes al cierre' if asm['cerrada_en'] else 'Presentes ahora'}: {qr['unidades_presentes']} unidad(es) con {_num(qr['coeficiente_presente'])} % del coeficiente, de un total de {qr['unidades_total']} unidades ({_num(qr['coeficiente_total'])} %)."))

    # 5. dignatarios
    partes.append(P("5. Dignatarios de la reunión", sub))
    partes.append(P(f"<b>Presidente:</b> {E(dig['presidente'] or '— (por designar)')}<br/><b>Secretario:</b> {E(dig['secretario'] or '— (por designar)')}<br/>"
                    f"<b>Comisión verificadora de la redacción del acta:</b> {E(dig['comision'] or 'no se designó')}"))

    # 6. asistentes
    partes.append(P("6. Asistentes (nombre y calidad) y coeficiente", sub))
    if ev["asistentes"]:
        filas = [[P(x, celda_b) for x in ("Unidad", "Nombre", "Calidad", "Medio", "Coef. %", "Ingreso", "Salida")]]
        for x in ev["asistentes"]:
            filas.append([P(E(x["unidad"]), celda), P(E(x["nombre"]) + ("" if x["con_voto"] else " <i>(sin voto)</i>"), celda), P(x["calidad"], celda), P(x["modalidad"], celda),
                          P(_num(x["coeficiente"]), celda), P(_corta(x["ingreso"]), celda), P(_corta(x["salida"]) if x["salida"] else "presente", celda)])
        partes += [tabla(filas, [2.5 * cm, 4.2 * cm, 2.1 * cm, 1.9 * cm, 1.6 * cm, 2.45 * cm, 2.45 * cm]), Spacer(1, 3)]
        partes.append(P("Ingreso y salida: día/mes y hora de Colombia. «Sin voto»: la unidad cuenta para el quórum pero no vota (restricción por mora que establece el reglamento).", pequeno))
    else:
        partes.append(P("No hay asistentes acreditados."))

    # 7. votaciones
    partes.append(P("7. Votaciones y decisiones", sub))
    sin_votar = [v for v in ev["votaciones"] if v["estado"] == EstadoVotacionAsamblea.BORRADOR.value]
    for v in (x for x in ev["votaciones"] if x["estado"] != EstadoVotacionAsamblea.BORRADOR.value):
        bloque = [P(f"<b>{v['numero']}. {E(v['titulo'])}</b> — {E(v['tipo'])}" + (f" · mayoría {v['mayoria'].lower()}" if v["tipo"] == "Decisión" else ""))]
        if v.get("descripcion"):
            bloque.append(P(E(v["descripcion"]), pequeno))
        if v["estado"] == EstadoVotacionAsamblea.ANULADA.value:
            bloque.append(P(f"<b>Votación anulada.</b> Motivo: {E(v.get('motivo_anulacion') or '—')}"))
        elif v["estado"] == EstadoVotacionAsamblea.ABIERTA.value:
            bloque.append(P("Votación abierta al momento de generar este borrador: aún no tiene resultado."))
        else:
            r = v["resultado"]
            bloque.append(P(f"<b>Resultado: {E(v['titular'])}.</b> Votaron {r['unidades_votaron']} de {r['unidades_padron']} unidades del padrón ({r['votos_app']} por la aplicación y {r['votos_presenciales']} presenciales). "
                            f"Quórum al abrir {_num(v['quorum_apertura'])} % y al cerrar {_num(v['quorum_cierre'])} %."))
            if r["aprobada"] is not None:
                base = "del coeficiente de todo el conjunto" if r.get("base") == "conjunto" else "del coeficiente presente con derecho a voto"
                bloque.append(P(f"A favor: {_num(r.get('porcentaje_a_favor'))} % {base}; se necesitaba {'70 % o más' if r.get('umbral') == 70 else 'más del 50 %'}."))
            filas = [[P(x, celda_b) for x in ("Opción", "Unidades", "Coeficiente %", "% de presentes", "% del conjunto")]]
            for o in r["opciones"]:
                filas.append([P(E(o["texto"]), celda), P(str(o["votos"]), celda), P(_num(o["coeficiente"]), celda), P(_num(o["porcentaje_presentes"], 2), celda), P(_num(o["porcentaje_conjunto"], 2), celda)])
            bloque += [tabla(filas, [6 * cm, 2.2 * cm, 3 * cm, 3 * cm, 3 * cm]), Spacer(1, 3)]
            if r["motivos"]:
                bloque.append(P("Observaciones: " + E(" ".join(r["motivos"])), pequeno))
            if v["votos_nominales"]:
                bloque.append(P("Votos presenciales (nominales): " + E("; ".join(f"{n['unidad']}: {n['voto']} ({_num(n['coeficiente'])} %)" for n in v["votos_nominales"])) + ".", pequeno))
            if r["votos_app"]:
                bloque.append(P("Los votos emitidos desde la aplicación son secretos: constan el número de unidades y el coeficiente por opción, no quién votó qué.", pequeno))
            bloque.append(P(f"Huella (SHA-256) del resultado: <font name='Courier'>{v['resultado_hash']}</font>", pequeno))
        partes += [KeepTogether(bloque), Spacer(1, 5)]
    if not any(x["estado"] != EstadoVotacionAsamblea.BORRADOR.value for x in ev["votaciones"]):
        partes.append(P("No se realizaron votaciones dentro de la aplicación."))
    if sin_votar:
        partes.append(P(f"Propuestas preparadas que no se sometieron a votación: {len(sin_votar)} ({E('; '.join(v['titulo'] for v in sin_votar))}).", pequeno))

    # 8. desarrollo
    partes.append(P("8. Desarrollo del orden del día y decisiones adoptadas", sub))
    if c["desarrollo"] and c["desarrollo"].strip():
        partes += [P(E(l.strip())) for l in c["desarrollo"].splitlines() if l.strip()]
    else:
        partes.append(P("— El secretario aún no ha redactado el desarrollo de la reunión. —", pequeno))

    # 9. constancias
    partes.append(P("9. Constancias y evidencia", sub))
    if reunion_virtual:
        partes.append(P("Reunión con participación a distancia: la conexión y la desconexión de cada asistente, con fecha y hora, constan en la bitácora de evidencia de la aplicación. "
                        "Se recomienda conservar la grabación de la sesión como prueba principal."))
    partes.append(P(f"Bitácora de evidencia: {ev['bitacora']['secuencia']} eventos encadenados con huella SHA-256 hasta este punto. Huella del último evento: <font name='Courier'>{ev['bitacora']['huella']}</font>", pequeno))

    # 10. firmas y plazo
    limite = date.fromisoformat(c["plazo"]["limite_publicacion"]).strftime("%d/%m/%Y")
    cierre = [P("10. Firmas", sub), P("Para constancia se firma por quienes presidieron y secretariaron la reunión.")]
    linea = lambda nombre, cargo: P(f"<br/><br/>_______________________________<br/>{E(nombre)}<br/>{cargo}", normal)  # noqa: E731
    firmas = [[linea(dig["presidente"] or "Presidente", "Presidente de la asamblea"), linea(dig["secretario"] or "Secretario", "Secretario de la asamblea")]]
    cierre.append(Table(firmas, colWidths=[8.6 * cm, 8.6 * cm]))
    if dig["comision"]:
        cierre.append(P("<br/>Comisión verificadora de la redacción del acta: " + E(dig["comision"]) + " ______________________", normal))
    cierre.append(P(f"<br/>Plazo para poner el acta a disposición de los propietarios: hasta el {limite} ({c['plazo']['dias_habiles']} días hábiles desde la fecha de la reunión, Art. 47 de la Ley 675 de 2001).", pequeno))
    if not borrador and huella_acta:
        cierre.append(P(f"Acta sellada el {reglas.fmt_local(sellada_en) if sellada_en else '—'}. Huella (SHA-256) de su contenido: <font name='Courier'>{huella_acta}</font>. "
                        "Puedes comprobar que no se alteró con «Verificar integridad» en la aplicación.", pequeno))
    partes.append(KeepTogether(cierre))

    pie = "BORRADOR · sin valor hasta que se selle y se firme" if borrador else f"{marca.nombre()} · Acta sellada · huella {(huella_acta or '')[:16]}…"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm, invariant=1,
                            title=f"Acta · {asm['titulo']}", author=marca.nombre())
    doc.build(partes, canvasmaker=_canvas_con_pie(pie, "BORRADOR" if borrador else None))
    return buf.getvalue()
