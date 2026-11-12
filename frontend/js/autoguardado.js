// Autoguardado de formularios: guarda en el celular lo que la persona va escribiendo y lo devuelve si la página se recarga
// (por ejemplo, cuando el sistema cierra la app mientras se abre la cámara).
//  - Solo se guardan textos y opciones. La foto NO se guarda (tras recargar no se puede recuperar): hay que volver a agregarla.
//  - Es por usuario y vence a las 12 horas. Se borra al enviar, al cancelar y al cerrar sesión con el botón «Cerrar sesión».
//  - Nunca se guardan contraseñas: solo se conectan los campos que cada formulario declara.
import { toast } from "./ui.js";

const PREFIJO = "ciudadela.auto.";
const VIGENCIA_MS = 12 * 60 * 60 * 1000;
const llave = (usuarioId, nombre) => `${PREFIJO}${usuarioId}.${nombre}`;
const almacen = () => { try { return localStorage; } catch { return null; } };

export function leerAuto(usuarioId, nombre) {
  const a = almacen(); if (!a) return null;
  try {
    const crudo = a.getItem(llave(usuarioId, nombre)); if (!crudo) return null;
    const d = JSON.parse(crudo);
    if (!d || typeof d.t !== "number" || Date.now() - d.t > VIGENCIA_MS) { a.removeItem(llave(usuarioId, nombre)); return null; }
    return d;
  } catch { return null; }
}
export function borrarAuto(usuarioId, nombre) { try { almacen()?.removeItem(llave(usuarioId, nombre)); } catch {} }
export function borrarAutoTodos() {
  const a = almacen(); if (!a) return;
  try { Object.keys(a).filter((k) => k.startsWith(PREFIJO)).forEach((k) => a.removeItem(k)); } catch {}
}

/**
 * autoguardar({ usuarioId, nombre, campos: { clave: elemento }, extra?: () => objeto, alRestaurar?: (extra) => void })
 *  - Al crearse restaura lo guardado (si hay) en los campos y llama a alRestaurar(extra) para lo que no es un campo (chips, plan, etc.).
 *  - Guarda solo (con una pequeña espera) cuando se escribe, y de inmediato cuando la página se oculta.
 * Devuelve { restaurado, conFoto, programar(), foto(valor), abierto(valor), avisar(), reiniciar(), soltar() }.
 */
export function autoguardar({ usuarioId, nombre, campos, extra = () => ({}), alRestaurar }) {
  const lista = Object.entries(campos);
  const primero = lista[0]?.[1];
  const inicial = Object.fromEntries(lista.map(([k, el]) => [k, String(el.value ?? "")]));
  const extraInicial = JSON.stringify(extra());
  const previo = leerAuto(usuarioId, nombre);
  const meta = { conFoto: false, abierto: false, ...(previo?.meta ?? {}) };
  const conFotoAlRestaurar = !!previo?.meta?.conFoto;

  if (previo) {
    for (const [k, el] of lista) if (typeof previo.campos?.[k] === "string") el.value = previo.campos[k];
    if (previo.extra) { try { alRestaurar?.(previo.extra); } catch {} }
  }

  let activo = true, visto = false, espera = null;
  const hayContenido = () => meta.conFoto
    || lista.some(([k, el]) => String(el.value ?? "").trim() !== inicial[k].trim())
    || JSON.stringify(extra()) !== extraInicial;

  function guardarYa() {
    if (!activo) return;
    if (primero?.isConnected) visto = true;
    else { if (visto) soltar(); return; }          // el formulario ya no está en pantalla: este autoguardado se retira solo
    clearTimeout(espera);
    if (!hayContenido()) { borrarAuto(usuarioId, nombre); return; }
    try {
      almacen()?.setItem(llave(usuarioId, nombre), JSON.stringify({
        t: Date.now(), campos: Object.fromEntries(lista.map(([k, el]) => [k, String(el.value ?? "")])), extra: extra(), meta }));
    } catch {}
  }
  const programar = () => { if (!activo) return; clearTimeout(espera); espera = setTimeout(guardarYa, 350); };
  const alOcultar = () => { if (document.visibilityState === "hidden") guardarYa(); };

  lista.forEach(([, el]) => { el.addEventListener("input", programar); el.addEventListener("change", programar); });
  document.addEventListener("visibilitychange", alOcultar);
  addEventListener("pagehide", guardarYa);

  function soltar() {
    activo = false; clearTimeout(espera);
    document.removeEventListener("visibilitychange", alOcultar);
    removeEventListener("pagehide", guardarYa);
  }

  return {
    restaurado: !!previo, conFoto: conFotoAlRestaurar, programar, soltar,
    /** Se llama justo antes de abrir la cámara o la galería (y cuando llega o se quita la foto): así queda guardado de inmediato. */
    foto(valor) { if (!activo) return; meta.conFoto = !!valor; guardarYa(); },
    /** Para formularios dentro de un ventana (modal): recuerda si estaba abierta para reabrirla al recargar. */
    abierto(valor) { if (!activo) return; meta.abierto = !!valor; guardarYa(); },
    avisar() { if (previo) toast(conFotoAlRestaurar ? "Recuperamos lo que habías escrito. Vuelve a agregar la foto." : "Recuperamos lo que habías escrito."); },
    /** Después de enviar o cancelar: borra el borrador pero sigue atento por si se escribe de nuevo. */
    reiniciar() { clearTimeout(espera); meta.conFoto = false; meta.abierto = false; borrarAuto(usuarioId, nombre); },
  };
}
