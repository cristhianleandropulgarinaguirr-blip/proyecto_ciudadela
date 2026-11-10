# app/almacen.py
# Dónde viven las fotos y los PDF. Dos opciones intercambiables (variable ALMACEN del .env):
#   - local:    carpeta UPLOAD_DIR del servidor (simple; se pierde en hostings con disco temporal).
#   - supabase: Supabase Storage por su API REST, en un bucket PRIVADO. El navegador nunca habla con Supabase:
#               la API descarga el archivo y lo entrega solo a quien tiene permiso (la clave secreta no sale del servidor).
import logging
import os
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from app import config

logger = logging.getLogger(__name__)


class AlmacenLocal:
    def _ruta(self, carpeta: str, nombre: str) -> str:
        base = os.path.join(config.UPLOAD_DIR, carpeta) if carpeta else config.UPLOAD_DIR
        return os.path.join(base, os.path.basename(nombre))      # basename: evita «../» (path traversal)

    def guardar(self, carpeta: str, nombre: str, datos: bytes) -> None:
        ruta = self._ruta(carpeta, nombre)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as f:
            f.write(datos)

    def leer(self, carpeta: str, nombre: str) -> bytes | None:
        try:
            with open(self._ruta(carpeta, nombre), "rb") as f:
                return f.read()
        except OSError:
            return None

    def borrar(self, carpeta: str, nombre: str) -> None:
        try:
            os.remove(self._ruta(carpeta, nombre))
        except OSError:
            pass


class AlmacenSupabase:
    """Cliente mínimo de Supabase Storage (subir, descargar, borrar). Acepta la clave nueva (sb_secret_…) y la antigua (service_role)."""

    def __init__(self, cliente: httpx.Client | None = None):
        if not (config.SUPABASE_URL and config.SUPABASE_SECRET_KEY):
            raise RuntimeError("ALMACEN=supabase necesita SUPABASE_URL y SUPABASE_SECRET_KEY en el .env")
        self._http = cliente or httpx.Client(timeout=20.0, follow_redirects=False)

    def _cabeceras(self) -> dict:
        clave = config.SUPABASE_SECRET_KEY
        h = {"apikey": clave}
        if not clave.startswith("sb_"):          # clave antigua (JWT): además va como Bearer. Las sb_secret_… NO se envían como Bearer.
            h["Authorization"] = f"Bearer {clave}"
        return h

    def _url(self, carpeta: str, nombre: str) -> str:
        objeto = f"{carpeta}/{os.path.basename(nombre)}" if carpeta else os.path.basename(nombre)
        return f"{config.SUPABASE_URL}/storage/v1/object/{quote(config.SUPABASE_BUCKET)}/{quote(objeto)}"

    def guardar(self, carpeta: str, nombre: str, datos: bytes) -> None:
        try:
            r = self._http.post(self._url(carpeta, nombre), content=datos,
                                headers={**self._cabeceras(), "Content-Type": "application/octet-stream", "x-upsert": "true"})
        except httpx.HTTPError as e:
            logger.error("Supabase Storage no respondió al subir: %s", e)
            raise HTTPException(status_code=503, detail="No pudimos guardar el archivo ahora mismo. Intenta de nuevo.")
        if r.status_code >= 300:
            logger.error("Supabase Storage rechazó la subida (%s): %s", r.status_code, r.text[:300])
            raise HTTPException(status_code=503, detail="No pudimos guardar el archivo ahora mismo. Intenta de nuevo.")

    def leer(self, carpeta: str, nombre: str) -> bytes | None:
        try:
            r = self._http.get(self._url(carpeta, nombre), headers=self._cabeceras())
        except httpx.HTTPError as e:
            logger.error("Supabase Storage no respondió al descargar: %s", e)
            return None
        if r.status_code == 200:
            return r.content
        if r.status_code not in (400, 404):      # Supabase devuelve 400 con statusCode 404 en el cuerpo cuando no existe
            logger.error("Supabase Storage devolvió %s al descargar: %s", r.status_code, r.text[:300])
        return None

    def borrar(self, carpeta: str, nombre: str) -> None:
        try:
            self._http.delete(self._url(carpeta, nombre), headers=self._cabeceras())
        except httpx.HTTPError as e:
            logger.warning("No se pudo borrar el archivo en Supabase Storage: %s", e)


_instancia = None


def almacen():
    """Devuelve el almacén configurado (se crea una sola vez)."""
    global _instancia
    if _instancia is None:
        _instancia = AlmacenSupabase() if config.ALMACEN == "supabase" else AlmacenLocal()
    return _instancia


def reiniciar_almacen() -> None:
    """Solo para pruebas: fuerza a releer la configuración."""
    global _instancia
    _instancia = None
