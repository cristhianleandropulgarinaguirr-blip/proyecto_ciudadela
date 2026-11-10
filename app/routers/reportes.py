# app/routers/reportes.py
# Bloque 3 · Reportes descargables. Excel (.xlsx) para el administrador y un PDF con el estado de cuenta.
# Las horas salen en hora de Colombia (UTC-5) y los textos que empiezan por = + - @ se neutralizan para que
# Excel nunca los interprete como fórmulas.
import io
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session, aliased

from app.auditoria import auditar
from app.constantes import RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import AccesoVisitante, Auditoria, Pago, Paquete, PQRS, Rol, Usuario, VisitanteAutorizado
from app.routers.pqrs import radicado

TAG = "Reportes"
router = APIRouter(prefix="/reportes", tags=[TAG])
ADMIN = RolNombre.ADMINISTRADOR
HORA_COLOMBIA = timezone(timedelta(hours=-5))
MAX_FILAS = 20000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _hora(d: Optional[datetime]) -> str:
    return d.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M") if d else ""


def _seguro(valor):
    if valor is None:
        return ""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return valor
    texto = str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _excel(hoja: str, titulo: str, encabezados: list[str], filas: list[list], archivo: str) -> Response:
    libro = Workbook()
    ws = libro.active
    ws.title = hoja[:31]
    ws.append([titulo])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Generado el {datetime.now(HORA_COLOMBIA):%Y-%m-%d %H:%M} (hora de Colombia) · {len(filas)} registro(s)"])
    ws["A2"].font = Font(italic=True, color="666666")
    ws.append([])
    ws.append(encabezados)
    for c in ws[4]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5D50")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for fila in filas:
        ws.append([_seguro(v) for v in fila])
    for i, enc in enumerate(encabezados, start=1):
        ancho = max([len(str(enc))] + [len(str(f[i - 1])) for f in filas[:300] if i - 1 < len(f)]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(max(ancho, 10), 55)
    ws.freeze_panes = "A5"
    memoria = io.BytesIO()
    libro.save(memoria)
    nombre = f"{archivo}_{datetime.now(HORA_COLOMBIA):%Y%m%d_%H%M}.xlsx"
    return Response(content=memoria.getvalue(), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/cartera.xlsx", summary="Exportar la cartera a Excel", response_class=Response,
            description="Solo **Administrador**. Un renglón por residente: cuota, saldo y si está al día.")
def cartera(db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    residentes = (db.query(Usuario).join(Rol, Rol.id == Usuario.rol_id).filter(Rol.nombre == RolNombre.RESIDENTE.value)
                  .order_by(Usuario.apartamento, Usuario.nombre_completo).limit(MAX_FILAS).all())
    filas = [[u.apartamento, u.nombre_completo, u.email, u.valor_administracion, u.saldo_pendiente, "Al día" if u.saldo_pendiente == 0 else "En mora",
              u.parqueadero_asignado, "Sí" if u.esta_activo else "No"] for u in residentes]
    filas.append(["TOTAL", "", "", sum(u.valor_administracion or 0 for u in residentes), sum(u.saldo_pendiente or 0 for u in residentes), "", "", ""])
    auditar(db, admin, "Exportó reporte", "Reporte", None, f"Cartera ({len(residentes)} residentes)")
    db.commit()
    return _excel("Cartera", "Cartera de administración", ["Apartamento", "Residente", "Correo", "Cuota mensual (COP)", "Saldo pendiente (COP)",
                                                           "Estado", "Parqueadero", "Activo"], filas, "cartera")


@router.get("/pqrs.xlsx", summary="Exportar las PQRS a Excel", response_class=Response, description="Solo **Administrador**.")
def pqrs(db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    resp = aliased(Usuario)
    filas = (db.query(PQRS, Usuario, resp.nombre_completo).join(Usuario, Usuario.id == PQRS.usuario_id)
             .outerjoin(resp, resp.id == PQRS.respondido_por).order_by(PQRS.id.desc()).limit(MAX_FILAS).all())
    datos = [[radicado(p), p.tipo, p.estado, u.nombre_completo, u.apartamento, p.asunto, p.descripcion, _hora(p.fecha_creacion), p.respuesta, r, _hora(p.fecha_respuesta)]
             for p, u, r in filas]
    auditar(db, admin, "Exportó reporte", "Reporte", None, f"PQRS ({len(datos)} filas)")
    db.commit()
    return _excel("PQRS", "Peticiones, quejas, reclamos y sugerencias", ["Radicado", "Tipo", "Estado", "Residente", "Apartamento", "Asunto", "Descripción",
                                                                         "Radicada (hora Colombia)", "Respuesta", "Respondió", "Respondida (hora Colombia)"], datos, "pqrs")


@router.get("/paquetes.xlsx", summary="Exportar los paquetes a Excel", response_class=Response, description="Solo **Administrador**.")
def paquetes(db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    rec, ent = aliased(Usuario), aliased(Usuario)
    filas = (db.query(Paquete, Usuario, rec.nombre_completo, ent.nombre_completo).join(Usuario, Usuario.id == Paquete.destinatario_id)
             .outerjoin(rec, rec.id == Paquete.recibido_por).outerjoin(ent, ent.id == Paquete.entregado_por)
             .order_by(Paquete.id.desc()).limit(MAX_FILAS).all())
    datos = [[p.id, p.tipo, p.estado, u.nombre_completo, u.apartamento, p.remitente, p.descripcion, _hora(p.fecha_recepcion), r, p.entregado_a, e, _hora(p.fecha_entrega)]
             for p, u, r, e in filas]
    auditar(db, admin, "Exportó reporte", "Reporte", None, f"Paquetes ({len(datos)} filas)")
    db.commit()
    return _excel("Paquetes", "Paquetes y correspondencia", ["N.º", "Tipo", "Estado", "Destinatario", "Apartamento", "Remitente", "Descripción", "Llegó (hora Colombia)",
                                                            "Lo recibió", "Entregado a", "Lo entregó", "Entregado (hora Colombia)"], datos, "paquetes")


@router.get("/visitantes.xlsx", summary="Exportar los ingresos de visitantes a pie a Excel", response_class=Response, description="Solo **Administrador**.")
def visitantes(db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    anf, gi, go = aliased(Usuario), aliased(Usuario), aliased(Usuario)
    filas = (db.query(AccesoVisitante, VisitanteAutorizado, anf, gi.nombre_completo, go.nombre_completo)
             .join(VisitanteAutorizado, VisitanteAutorizado.id == AccesoVisitante.visitante_id).join(anf, anf.id == VisitanteAutorizado.usuario_id)
             .outerjoin(gi, gi.id == AccesoVisitante.ingreso_registrado_por).outerjoin(go, go.id == AccesoVisitante.salida_registrada_por)
             .order_by(AccesoVisitante.id.desc()).limit(MAX_FILAS).all())
    datos = [[v.nombre, v.documento, v.tipo, h.nombre_completo, h.apartamento, _hora(a.fecha_ingreso), _hora(a.fecha_salida), "Dentro" if a.fecha_salida is None else "Salió", i, o]
             for a, v, h, i, o in filas]
    auditar(db, admin, "Exportó reporte", "Reporte", None, f"Visitantes a pie ({len(datos)} filas)")
    db.commit()
    return _excel("Visitantes", "Ingresos de visitantes a pie", ["Visitante", "Documento", "Relación", "Autorizado por", "Apartamento", "Ingreso (hora Colombia)",
                                                                "Salida (hora Colombia)", "Estado", "Registró ingreso", "Registró salida"], datos, "visitantes_a_pie")


@router.get("/auditoria.xlsx", summary="Exportar la auditoría a Excel", response_class=Response,
            description="Solo **Administrador**. Mismo filtro `entidad` que la pantalla de auditoría.")
def auditoria(entidad: Optional[str] = Query(None, max_length=30), db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    q = db.query(Auditoria, Usuario.nombre_completo).outerjoin(Usuario, Usuario.id == Auditoria.actor_id)
    if entidad:
        q = q.filter(Auditoria.entidad == entidad)
    filas = q.order_by(Auditoria.id.desc()).limit(MAX_FILAS).all()
    datos = [[_hora(a.fecha), n or "Sistema", a.accion, a.entidad, a.entidad_id, a.detalle] for a, n in filas]
    # La exportación se audita DESPUÉS de leer, para que no aparezca dentro de su propio archivo.
    auditar(db, admin, "Exportó reporte", "Reporte", None, f"Auditoría{f' · {entidad}' if entidad else ''} ({len(datos)} filas)")
    db.commit()
    return _excel("Auditoría", "Bitácora de auditoría", ["Fecha (hora Colombia)", "Quién", "Acción", "Entidad", "N.º", "Detalle"], datos, "auditoria")


@router.get("/estado-cuenta/{usuario_id}.pdf", summary="Descargar el estado de cuenta en PDF", response_class=Response,
            description="El residente descarga el suyo; el **Administrador** el de cualquier residente. Si no hay saldo pendiente, el documento lo indica como «a paz y salvo».",
            responses={403: {"description": "No es tu estado de cuenta"}, 404: {"description": "Usuario no encontrado"}})
def estado_cuenta_pdf(usuario_id: int, db: Session = Depends(get_db), actual: Usuario = Depends(get_current_user)):
    if usuario_id != actual.id and actual.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Solo puedes descargar tu propio estado de cuenta.")
    u = db.get(Usuario, usuario_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    cop = lambda n: "$ " + f"{int(n or 0):,}".replace(",", ".")   # noqa: E731
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=colors.HexColor("#2F5D50"), fontSize=22, spaceAfter=4)
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=11, leading=16)
    ahora = datetime.now(HORA_COLOMBIA)
    al_dia = (u.saldo_pendiente or 0) == 0
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    memoria = io.BytesIO()
    doc = SimpleDocTemplate(memoria, pagesize=letter, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Estado de cuenta - {u.apartamento or u.nombre_completo}", author="Ciudadela Digital")
    tabla = Table([["Residente", esc(u.nombre_completo)], ["Apartamento", esc(u.apartamento) or "—"], ["Cuota mensual de administración", cop(u.valor_administracion)],
                   ["Saldo pendiente", cop(u.saldo_pendiente)], ["Estado", "Al día" if al_dia else "En mora"]], colWidths=[7 * cm, 9 * cm])
    tabla.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 11), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("FONTNAME", (1, 3), (1, 3), "Helvetica-Bold"), ("TEXTCOLOR", (1, 4), (1, 4), colors.HexColor("#2E7D32" if al_dia else "#B3541E"))]))
    nota = ("Con corte a la fecha de este documento, el apartamento se encuentra <b>a paz y salvo</b> por concepto de cuotas de administración."
            if al_dia else f"Con corte a la fecha de este documento, el apartamento registra un saldo pendiente de <b>{cop(u.saldo_pendiente)}</b>.")
    doc.build([Paragraph("Ciudadela Digital", titulo), Paragraph("Estado de cuenta de administración", estilos["Heading3"]),
               Paragraph(f"Generado el {ahora:%d/%m/%Y} a las {ahora:%H:%M} (hora de Colombia)", normal), Spacer(1, 18), tabla, Spacer(1, 18), Paragraph(nota, normal), Spacer(1, 30),
               Paragraph("Documento informativo generado por la aplicación. La validez como certificado requiere la firma del administrador.",
                         ParagraphStyle("p", parent=normal, fontSize=9, textColor=colors.HexColor("#777777")))])
    nombre = f"estado_cuenta_{(u.apartamento or str(u.id)).replace(' ', '_')}_{ahora:%Y%m%d}.pdf"
    return Response(content=memoria.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/recibo/{pago_id}.pdf", summary="Descargar el comprobante de un pago en PDF", response_class=Response,
            description="Quien hizo el pago o el **Administrador**. Es un comprobante informativo de la aplicación (no reemplaza la factura ni el recibo de caja oficial).",
            responses={403: {"description": "No es tu pago"}, 404: {"description": "Pago no encontrado"}})
def recibo_pdf(pago_id: int, db: Session = Depends(get_db), actual: Usuario = Depends(get_current_user)):
    pago = db.get(Pago, pago_id)
    if pago is None:
        raise HTTPException(status_code=404, detail="Pago no encontrado.")
    if pago.usuario_id != actual.id and actual.rol != ADMIN.value:
        raise HTTPException(status_code=403, detail="Solo puedes descargar tus propios comprobantes.")
    u = db.get(Usuario, pago.usuario_id)
    cop = lambda n: "$ " + f"{int(n or 0):,}".replace(",", ".")   # noqa: E731
    esc = lambda t: (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")   # noqa: E731
    numero = f"REC-{pago.fecha.year}-{pago.id:06d}"
    cuando = pago.fecha.replace(tzinfo=timezone.utc).astimezone(HORA_COLOMBIA)
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle("t", parent=estilos["Title"], textColor=colors.HexColor("#2F5D50"), fontSize=22, spaceAfter=4)
    normal = ParagraphStyle("n", parent=estilos["Normal"], fontSize=11, leading=16)
    memoria = io.BytesIO()
    doc = SimpleDocTemplate(memoria, pagesize=letter, leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
                            title=f"Comprobante {numero}", author="Ciudadela Digital")
    tabla = Table([["Comprobante N.º", numero], ["Fecha y hora", f"{cuando:%d/%m/%Y %H:%M} (hora de Colombia)"], ["Residente", esc(u.nombre_completo)],
                   ["Apartamento", esc(u.apartamento) or "—"], ["Concepto", "Pago de cuota de administración"], ["Saldo antes del pago", cop(pago.saldo_anterior)],
                   ["Valor pagado", cop(pago.valor)], ["Saldo después del pago", cop(pago.saldo_posterior)]], colWidths=[7 * cm, 9 * cm])
    tabla.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 11), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#444444")),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("FONTNAME", (1, 6), (1, 6), "Helvetica-Bold"), ("TEXTCOLOR", (1, 6), (1, 6), colors.HexColor("#2E7D32"))]))
    doc.build([Paragraph("Ciudadela Digital", titulo), Paragraph("Comprobante de pago", estilos["Heading3"]), Spacer(1, 14), tabla, Spacer(1, 22),
               Paragraph("Documento informativo generado por la aplicación al registrar el pago. No reemplaza la factura ni el recibo de caja oficial de la administración.",
                         ParagraphStyle("p", parent=normal, fontSize=9, textColor=colors.HexColor("#777777")))])
    return Response(content=memoria.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="comprobante_{numero}.pdf"'})
