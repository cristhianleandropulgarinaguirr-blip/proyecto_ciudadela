# app/routers/paz_y_salvo.py
# Paz y salvo con QR: el residente (o el administrador por él) genera un certificado en PDF solo si el apartamento está AL DÍA.
# El QR del PDF lleva a /verificar/<codigo> (página pública en app/routers/publico.py), donde cualquiera comprueba en el servidor
# que el documento es auténtico, no fue adulterado y sigue vigente (no vencido, no revocado y el apartamento sigue al día).
import io
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import segno
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import arrendamientos as reglas_arr, config
from app.auditoria import auditar
from app.constantes import Delegacion, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import PazSalvo, Usuario, ahora_utc
from app.notificaciones import notificar
from app.schemas.paz_y_salvo import PazSalvoCreate, PazSalvoResponse

TAG = "Paz y salvo"
router = APIRouter(prefix="/paz-y-salvo", tags=[TAG])
ADMIN, RESIDENTE, INQUILINO = RolNombre.ADMINISTRADOR, RolNombre.RESIDENTE, RolNombre.INQUILINO
HORA_COLOMBIA = timezone(timedelta(hours=-5))
MAX_POR_DIA = 10
MSG_CARTERA = "El paz y salvo del apartamento lo pide el propietario. Si quieres obtenerlo, pídele que active «Pagar la administración» en «Mis inquilinos»."


def folio(p: PazSalvo) -> str:
    return f"PS-{p.id:06d}"


def estado_de(p: PazSalvo, titular: Optional[Usuario]) -> str:
    """Vigente | Vencido | Revocado | No vigente (el apartamento ya no está al día o el titular se desactivó)."""
    if p.revocado:
        return "Revocado"
    if p.valido_hasta < ahora_utc():
        return "Vencido"
    if titular is None or not titular.esta_activo or not titular.esta_al_dia or (titular.saldo_pendiente or 0) > 0:
        return "No vigente"
    return "Vigente"


def vista(p: PazSalvo, titular: Usuario) -> PazSalvoResponse:
    return PazSalvoResponse(id=p.id, folio=folio(p), estado=estado_de(p, titular), titular=titular.nombre_completo, apartamento=titular.apartamento,
                            destino=p.destino, fecha_emision=p.fecha_emision, valido_hasta=p.valido_hasta, enlace=f"/verificar/{p.codigo}")


def _titular_de(db: Session, actual: Usuario, usuario_id: Optional[int]) -> Usuario:
    if actual.rol == ADMIN.value:
        titular = db.get(Usuario, usuario_id) if usuario_id else actual
        if titular is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    else:
        titular = reglas_arr.titular_con_delegacion(db, actual, Delegacion.PAGAR, MSG_CARTERA)     # al inquilino sin permiso lo frena aquí (403)
        if usuario_id is not None and usuario_id != titular.id:
            raise HTTPException(status_code=403, detail="Solo puedes pedir el paz y salvo de tu apartamento.")
    if titular.rol != RESIDENTE.value:
        raise HTTPException(status_code=400, detail="El paz y salvo se emite para el propietario (rol Residente) de un apartamento.")
    return titular


def _obtener(db: Session, paz_id: int, actual: Usuario) -> tuple[PazSalvo, Usuario]:
    p = db.get(PazSalvo, paz_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Paz y salvo no encontrado.")
    titular = db.get(Usuario, p.usuario_id)
    if actual.rol != ADMIN.value:
        propio = reglas_arr.titular_con_delegacion(db, actual, Delegacion.PAGAR, MSG_CARTERA)
        if p.usuario_id != propio.id:
            raise HTTPException(status_code=403, detail="Este paz y salvo no es de tu apartamento.")
    return p, titular


@router.post("", response_model=PazSalvoResponse, status_code=status.HTTP_201_CREATED, summary="Generar un paz y salvo",
             description="Roles: **Residente**, **Inquilino** (solo si su propietario le delegó pagar) y **Administrador** (para cualquier residente con `usuario_id`). "
                         "Solo se emite si el apartamento está **al día**. Sirve 30 días (`PAZ_Y_SALVO_DIAS`) y se verifica con el QR del PDF. Máximo 10 por día por apartamento.",
             responses={400: {"description": "El apartamento tiene saldo pendiente"}, 403: {"description": "Sin permiso"}, 429: {"description": "Demasiados en un día"}})
def emitir(datos: PazSalvoCreate, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    titular = _titular_de(db, actual, datos.usuario_id)
    if not titular.esta_al_dia or (titular.saldo_pendiente or 0) > 0:
        quien = "Tu apartamento" if titular.id == actual.id else f"El apartamento de {titular.nombre_completo}"
        raise HTTPException(status_code=400, detail=f"{quien} registra saldo pendiente: solo se emite el paz y salvo cuando la administración está al día.")
    hoy = ahora_utc() - timedelta(days=1)
    if db.query(func.count(PazSalvo.id)).filter(PazSalvo.usuario_id == titular.id, PazSalvo.fecha_emision >= hoy).scalar() >= MAX_POR_DIA:
        raise HTTPException(status_code=429, detail=f"Ya generaste {MAX_POR_DIA} paz y salvos hoy. Usa uno de los que ya tienes.")
    p = PazSalvo(usuario_id=titular.id, codigo=secrets.token_urlsafe(16), destino=datos.destino, emitido_por=actual.id,
                 fecha_emision=ahora_utc(), valido_hasta=ahora_utc() + timedelta(days=config.PAZ_Y_SALVO_DIAS))
    db.add(p)
    db.flush()
    auditar(db, actual, "Emitió paz y salvo", "PazSalvo", p.id, f"{folio(p)} · {titular.nombre_completo} ({titular.apartamento or 'sin apto'})" + (f" · {p.destino}" if p.destino else ""))
    if actual.id != titular.id:
        notificar(db, [titular], "Se generó un paz y salvo de tu apartamento", f"{folio(p)} · lo pidió {actual.nombre_completo}.", "#/cartera")
    db.commit()
    db.refresh(p)
    return vista(p, titular)


@router.get("", response_model=list[PazSalvoResponse], summary="Ver los paz y salvo",
            description="El residente (o su inquilino con permiso) ve los de su apartamento; el **Administrador** ve los más recientes de todos (máx. 100), o los de un residente con `usuario_id`.")
def listar(usuario_id: Optional[int] = Query(None), db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    q = db.query(PazSalvo)
    if actual.rol == ADMIN.value:
        if usuario_id:
            q = q.filter(PazSalvo.usuario_id == usuario_id)
    else:
        q = q.filter(PazSalvo.usuario_id == reglas_arr.titular_con_delegacion(db, actual, Delegacion.PAGAR, MSG_CARTERA).id)
    filas = q.order_by(PazSalvo.id.desc()).limit(100).all()
    duenos = {u.id: u for u in db.query(Usuario).filter(Usuario.id.in_({p.usuario_id for p in filas} or {0})).all()}
    return [vista(p, duenos[p.usuario_id]) for p in filas]


@router.post("/{paz_id}/revocar", response_model=PazSalvoResponse, summary="Revocar un paz y salvo",
             description="Solo **Administrador**. El certificado deja de verificarse como vigente de inmediato (si se emitió por error o el residente lo usó mal).",
             responses={404: {"description": "No existe"}})
def revocar(paz_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    p, titular = _obtener(db, paz_id, admin)
    if not p.revocado:
        p.revocado = True
        auditar(db, admin, "Revocó paz y salvo", "PazSalvo", p.id, f"{folio(p)} · {titular.nombre_completo}")
        notificar(db, [titular], "Se revocó un paz y salvo de tu apartamento", f"{folio(p)} ya no es válido.", "#/cartera")
        db.commit()
    return vista(p, titular)


# ---------------------------------------------------------------- PDF
def _url_base(request: Request) -> str:
    return config.URL_PUBLICA or str(request.base_url).rstrip("/")


@router.get("/{paz_id}/pdf", summary="Descargar el paz y salvo en PDF", response_class=Response,
            description="Dueño del apartamento (o su inquilino con permiso) o **Administrador**. El PDF lleva un **código QR** que abre la página pública de verificación.",
            responses={200: {"content": {"application/pdf": {}}}, 403: {"description": "No es de tu apartamento"}, 404: {"description": "No existe"}})
def pdf(paz_id: int, request: Request, db: Session = Depends(get_db), actual: Usuario = Depends(requiere_roles(RESIDENTE, INQUILINO, ADMIN))):
    p, titular = _obtener(db, paz_id, actual)
    url = f"{_url_base(request)}/verificar/{p.codigo}"
    qr = io.BytesIO()
    segno.make(url, error="m").save(qr, kind="png", scale=8, border=2)
    qr.seek(0)

    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    local = lambda d: d.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA)                    # noqa: E731
    estilos = getSampleStyleSheet()
    azul = colors.HexColor("#053550")
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=azul, fontSize=24, spaceAfter=2)
    sub = ParagraphStyle("s", parent=estilos["Heading3"], textColor=colors.HexColor("#4F5F6B"), alignment=1, spaceAfter=14)
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=12, leading=18, alignment=4)
    chico = ParagraphStyle("c", parent=estilos["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#666666"))
    memoria = io.BytesIO()
    doc = SimpleDocTemplate(memoria, pagesize=letter, leftMargin=2.4 * cm, rightMargin=2.4 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Paz y salvo {folio(p)}", author=config.CONJUNTO_NOMBRE)
    emitido, hasta = local(p.fecha_emision), local(p.valido_hasta)
    datos = [["Folio", folio(p)], ["Titular", esc(titular.nombre_completo)], ["Apartamento", esc(titular.apartamento) or "—"],
             ["Fecha de emisión", f"{emitido:%d/%m/%Y %H:%M} (hora de Colombia)"], ["Válido hasta", f"{hasta:%d/%m/%Y}"]]
    if p.destino:
        datos.append(["Para", esc(p.destino)])
    tabla = Table(datos, colWidths=[5 * cm, 11 * cm])
    tabla.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 11), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    texto = (f"La administración de <b>{esc(config.CONJUNTO_NOMBRE)}</b> certifica que el apartamento <b>{esc(titular.apartamento) or '—'}</b>, a nombre de "
             f"<b>{esc(titular.nombre_completo)}</b>, se encuentra <b>a paz y salvo</b> por concepto de cuotas de administración a la fecha de emisión de este documento.")
    pie = Table([[Image(qr, 3.6 * cm, 3.6 * cm), Paragraph(f"<b>Verifica este documento</b><br/>Escanea el código QR con la cámara de tu celular, o abre:<br/>{esc(url)}<br/><br/>"
                                                           "La página confirma si el certificado es auténtico y sigue vigente. Si el documento fue modificado o el código no coincide, no es válido.", chico)]],
                colWidths=[4.2 * cm, 11.8 * cm])
    pie.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#BBBBBB")), ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    doc.build([Paragraph(esc(config.CONJUNTO_NOMBRE), titulo), Paragraph("Certificado de paz y salvo de administración", sub), tabla, Spacer(1, 22), Paragraph(texto, normal),
               Spacer(1, 26), pie, Spacer(1, 16),
               Paragraph("Documento generado electrónicamente por Ciudadela Digital. Su autenticidad se comprueba con el código QR; no requiere firma manuscrita.", chico)])
    nombre = f"paz_y_salvo_{folio(p)}.pdf"
    return Response(memoria.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "private, no-store"})
