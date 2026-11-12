# app/archivos.py
# Validación y almacenamiento seguro de imágenes subidas con UploadFile.
import io
import os
import uuid

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.almacen import almacen
from app.config import MAX_PDF_MB, MAX_UPLOAD_MB, UPLOAD_DIR

# formato real detectado por Pillow -> extensión con la que se guarda
FORMATOS_PERMITIDOS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
TIPOS_MIME_PERMITIDOS = {"image/jpeg", "image/png", "image/webp"}


LADO_MAX = 1600          # px: suficiente para ver un daño con detalle; las fotos de celular traen 3000-4000 px
LADO_MINIATURA = 640     # px: tarjetas de las listas
PREFIJO_MINIATURA = "m_"


def _reducir(contenido: bytes, formato: str, lado: int) -> bytes:
    """Re-codifica la imagen: corrige la rotación, la reduce a `lado` px y descarta los metadatos EXIF (incluida la ubicación GPS del celular).
    Si algo falla devuelve el original: optimizar nunca debe impedir que la foto se guarde."""
    try:
        with Image.open(io.BytesIO(contenido)) as im:
            im = ImageOps.exif_transpose(im)
            if max(im.size) > lado:
                im.thumbnail((lado, lado), Image.Resampling.LANCZOS)
            salida = io.BytesIO()
            if formato == "JPEG":
                im.convert("RGB").save(salida, "JPEG", quality=82, optimize=True, progressive=True)
            elif formato == "PNG":
                im.save(salida, "PNG", optimize=True)
            else:
                im.save(salida, "WEBP", quality=82, method=4)
            return salida.getvalue()
    except Exception:  # noqa: BLE001 - cualquier fallo de Pillow: se conserva el original ya validado
        return contenido


async def guardar_imagen_validada(archivo: UploadFile, con_miniatura: bool = False) -> str:
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
    almacen().guardar("", nombre, _reducir(contenido, formato, LADO_MAX))
    if con_miniatura:
        almacen().guardar("", PREFIJO_MINIATURA + nombre, _reducir(contenido, formato, LADO_MINIATURA))
    return nombre


TIPOS_POR_EXTENSION = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def leer_imagen(nombre: str, miniatura: bool = False):
    """(bytes, tipo MIME) de una imagen guardada, o None si no existe. Con `miniatura` usa la versión pequeña si existe (si no, la original)."""
    datos = almacen().leer("", PREFIJO_MINIATURA + nombre) if miniatura else None
    if datos is None:
        datos = almacen().leer("", nombre)
    if datos is None:
        return None
    return datos, TIPOS_POR_EXTENSION.get(os.path.splitext(nombre)[1].lower(), "application/octet-stream")


def borrar_imagen(nombre: str) -> None:
    almacen().borrar("", nombre)
    almacen().borrar("", PREFIJO_MINIATURA + nombre)


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
