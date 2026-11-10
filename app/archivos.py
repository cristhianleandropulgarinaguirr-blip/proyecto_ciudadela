# app/archivos.py
# Validación y almacenamiento seguro de imágenes subidas con UploadFile.
import io
import os
import uuid

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError

from app.almacen import almacen
from app.config import MAX_PDF_MB, MAX_UPLOAD_MB, UPLOAD_DIR

# formato real detectado por Pillow -> extensión con la que se guarda
FORMATOS_PERMITIDOS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
TIPOS_MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}


async def guardar_imagen_validada(archivo: UploadFile) -> str:
    """Valida que el archivo sea una imagen real y la guarda con un nombre aleatorio.

    Se revisa: tipo MIME declarado, tamaño máximo y el contenido real del archivo
    (no basta con la extensión: alguien podría subir un .exe renombrado a .jpg).
    Devuelve el nombre del archivo guardado.
    """
    if archivo.content_type not in TIPOS_MIME_PERMITIDOS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten imágenes JPG, PNG o WEBP.",
        )

    limite = MAX_UPLOAD_MB * 1024 * 1024
    contenido = await archivo.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"La imagen supera el máximo de {MAX_UPLOAD_MB} MB.",
        )

    try:
        with Image.open(io.BytesIO(contenido)) as imagen:
            formato = imagen.format
            imagen.verify()  # comprueba que el archivo no esté corrupto
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es una imagen válida.")

    if formato not in FORMATOS_PERMITIDOS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato de imagen no permitido.")

    nombre = f"{uuid.uuid4().hex}{FORMATOS_PERMITIDOS[formato]}"  # nombre aleatorio: evita sobrescribir y path traversal
    almacen().guardar("", nombre, contenido)
    return nombre


TIPOS_POR_EXTENSION = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def leer_imagen(nombre: str):
    """(bytes, tipo MIME) de una imagen guardada, o None si no existe."""
    datos = almacen().leer("", nombre)
    if datos is None:
        return None
    return datos, TIPOS_POR_EXTENSION.get(os.path.splitext(nombre)[1].lower(), "application/octet-stream")


def borrar_imagen(nombre: str) -> None:
    almacen().borrar("", nombre)


def leer_documento(nombre: str) -> bytes | None:
    return almacen().leer("documentos", nombre)


def borrar_documento(nombre: str) -> None:
    almacen().borrar("documentos", nombre)


def ruta_imagen(nombre: str) -> str:
    return os.path.join(UPLOAD_DIR, os.path.basename(nombre))


CARPETA_DOCUMENTOS = os.path.join(UPLOAD_DIR, "documentos")


async def guardar_pdf_validado(archivo: UploadFile) -> tuple[str, int]:
    """Valida que sea un PDF real (tipo MIME, tamaño y firma «%PDF-») y lo guarda con nombre aleatorio.
    Devuelve (nombre_guardado, tamaño_en_bytes)."""
    if archivo.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo se permiten archivos PDF.")
    limite = MAX_PDF_MB * 1024 * 1024
    contenido = await archivo.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=f"El PDF supera el máximo de {MAX_PDF_MB} MB.")
    if not contenido.startswith(b"%PDF-"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo no es un PDF válido.")
    nombre = f"{uuid.uuid4().hex}.pdf"
    almacen().guardar("documentos", nombre, contenido)
    return nombre, len(contenido)


def ruta_documento(nombre: str) -> str:
    return os.path.join(CARPETA_DOCUMENTOS, os.path.basename(nombre))
