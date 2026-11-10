// Descarga de archivos protegidos: se piden con el token (un <a href> normal no lleva la sesión) y se guardan como blob.
import { apiBlob } from "./api.js";
import { h, toast, conCarga } from "./ui.js";

export function guardarBlob(blob, nombre) {
  const a = h("a", { href: URL.createObjectURL(blob), download: nombre });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** Descarga `ruta` con el botón en estado «cargando». `nombre` es el nombre con el que se guarda. */
export async function descargar(boton, ruta, nombre, { params, aviso } = {}) {
  try {
    const blob = await conCarga(boton, () => apiBlob(ruta, { params }));
    guardarBlob(blob, nombre);
    if (aviso) toast(aviso);
  } catch (err) { toast(err.message, "error"); }
}

export const hoyArchivo = () => new Date().toISOString().slice(0, 10);
export const tamanoLegible = (b) => (b < 1024 * 1024 ? `${Math.max(1, Math.round(b / 1024))} KB` : `${(b / 1024 / 1024).toFixed(1)} MB`);
