# app/routers/documentos.py
# Bloque 3 · Documentos del conjunto: el administrador sube PDFs (reglamento, actas, circulares, estados financieros)
# y todos los usuarios con sesión iniciada pueden descargarlos. No hay enlaces públicos.
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.archivos import borrar_documento, guardar_pdf_validado, leer_documento
from app.auditoria import auditar
from app.constantes import CategoriaDocumento, RolNombre
from app.database import get_db
from app.dependencies import get_current_user, requiere_roles
from app.models import Documento, Usuario
from app.notificaciones import notificar, usuarios_activos
from app.schemas.comunicacion import DocumentoResponse
from app.schemas.negocio import MensajeResponse

TAG = "Documentos del Conjunto"
router = APIRouter(prefix="/documentos", tags=[TAG])
ADMIN = RolNombre.ADMINISTRADOR
MAX_DOCUMENTOS = 200


def _nombre_descarga(original: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(original or "documento.pdf")).strip(" .") or "documento"
    return base if base.lower().endswith(".pdf") else base + ".pdf"


def _vistas(db: Session, docs: list[Documento]) -> list[DocumentoResponse]:
    ids = {d.subido_por for d in docs if d.subido_por}
    personas = {u.id: u.nombre_completo for u in db.query(Usuario).filter(Usuario.id.in_(ids)).all()} if ids else {}
    return [DocumentoResponse(id=d.id, titulo=d.titulo, categoria=d.categoria, descripcion=d.descripcion, nombre_original=d.nombre_original,
                              tamano=d.tamano, subido_por=personas.get(d.subido_por), fecha_creacion=d.fecha_creacion) for d in docs]


@router.get("/", response_model=list[DocumentoResponse], summary="Ver los documentos del conjunto",
            description="Roles: **todos**. Más recientes primero; filtra por `categoria`.")
def listar(categoria: Optional[CategoriaDocumento] = None, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    q = db.query(Documento)
    if categoria:
        q = q.filter(Documento.categoria == categoria.value)
    return _vistas(db, q.order_by(Documento.id.desc()).all())


@router.post("/", response_model=DocumentoResponse, status_code=status.HTTP_201_CREATED, summary="Subir un documento (PDF)",
             description="Solo **Administrador**. PDF real de máximo 10 MB (se revisa el contenido, no solo la extensión). Todos los usuarios reciben un aviso.",
             responses={400: {"description": "No es un PDF válido o ya hay demasiados documentos"}, 413: {"description": "Supera 10 MB"}})
async def subir(titulo: str = Form(..., min_length=3, max_length=100), categoria: CategoriaDocumento = Form(CategoriaDocumento.OTROS),
                descripcion: Optional[str] = Form(None, max_length=200), archivo: UploadFile = File(..., description="PDF"),
                db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    if db.query(func.count(Documento.id)).scalar() >= MAX_DOCUMENTOS:
        raise HTTPException(status_code=400, detail=f"Ya hay {MAX_DOCUMENTOS} documentos. Elimina alguno antiguo para subir otro.")
    guardado, tamano = await guardar_pdf_validado(archivo)
    d = Documento(titulo=" ".join(titulo.split()), categoria=categoria.value, descripcion=" ".join((descripcion or "").split()) or None,
                  archivo=guardado, nombre_original=_nombre_descarga(archivo.filename), tamano=tamano, subido_por=admin.id)
    db.add(d)
    db.flush()
    auditar(db, admin, "Subió documento", "Documento", d.id, f"{d.categoria}: {d.titulo}")
    notificar(db, usuarios_activos(db, excluir_id=admin.id), f"Nuevo documento: {d.titulo}", d.categoria, "#/documentos")
    db.commit()
    db.refresh(d)
    return _vistas(db, [d])[0]


@router.get("/{documento_id}/descargar", summary="Descargar un documento",
            description="Roles: **todos** (con sesión iniciada). Devuelve el PDF.", response_class=Response,
            responses={404: {"description": "Documento no encontrado"}})
def descargar(documento_id: int, db: Session = Depends(get_db), _: Usuario = Depends(get_current_user)):
    d = db.get(Documento, documento_id)
    datos = leer_documento(d.archivo) if d else None
    if datos is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return Response(content=datos, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_nombre_descarga(d.nombre_original)}"',
                             "X-Content-Type-Options": "nosniff"})


@router.delete("/{documento_id}", response_model=MensajeResponse, summary="Eliminar un documento",
               description="Solo **Administrador**. Borra también el archivo.", responses={404: {"description": "Documento no encontrado"}})
def eliminar(documento_id: int, db: Session = Depends(get_db), admin: Usuario = Depends(requiere_roles(ADMIN))):
    d = db.get(Documento, documento_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    archivo = d.archivo
    auditar(db, admin, "Eliminó documento", "Documento", d.id, f"{d.categoria}: {d.titulo}")
    db.delete(d)
    db.commit()
    borrar_documento(archivo)
    return {"mensaje": "Documento eliminado."}
