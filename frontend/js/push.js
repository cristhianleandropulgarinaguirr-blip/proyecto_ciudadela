// Avisos push en el celular (Web Push). Se activan desde Ajustes: el navegador pide permiso solo cuando la persona toca el botón.
// En iPhone/iPad funcionan únicamente con la app INSTALADA en la pantalla de inicio (iOS 16.4 o superior).
import { api } from "./api.js";
import { esIOS, yaInstalada } from "./instalar.js";

const b64aBytes = (b64) => {
  const crudo = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(crudo, (c) => c.charCodeAt(0));
};

export const soportaPush = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && window.isSecureContext;

async function registro() { return navigator.serviceWorker.ready; }

/** Estado para pintar la tarjeta de Ajustes: { estado, texto }.
 *  estado: "no-soportado" | "ios-instalar" | "apagado-servidor" | "bloqueado" | "activo" | "inactivo" */
export async function estadoPush() {
  if (!soportaPush()) {
    if (esIOS() && !yaInstalada()) return { estado: "ios-instalar", texto: "En iPhone, primero instala la app: toca Compartir y luego «Agregar a inicio». Después podrás activar los avisos." };
    return { estado: "no-soportado", texto: "Este navegador no permite avisos en el celular." };
  }
  let cfg;
  try { cfg = await api("/push/config"); } catch { return { estado: "inactivo", texto: "No pudimos consultar el estado. Revisa tu conexión." }; }
  if (!cfg.activo) return { estado: "apagado-servidor", texto: "El administrador aún no configuró los avisos en el servidor." };
  if (Notification.permission === "denied") return { estado: "bloqueado", texto: "Bloqueaste los avisos en el navegador. Actívalos en los permisos del sitio (candado junto a la dirección)." };
  const sub = await (await registro()).pushManager.getSubscription();
  return sub && Notification.permission === "granted"
    ? { estado: "activo", texto: "Recibirás avisos de paquetes, votaciones, reservas y comunicados aunque la app esté cerrada." }
    : { estado: "inactivo", texto: "Actívalos para enterarte al instante de paquetes, votaciones y comunicados." };
}

export async function activarPush() {
  const cfg = await api("/push/config");
  if (!cfg.activo || !cfg.clave_publica) throw new Error("Los avisos no están configurados en el servidor.");
  const permiso = await Notification.requestPermission();
  if (permiso !== "granted") throw new Error("No diste permiso para recibir avisos.");
  const reg = await registro();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64aBytes(cfg.clave_publica) });
  await api("/push/suscribir", { metodo: "POST", json: sub.toJSON() });
}

export async function desactivarPush() {
  const sub = await (await registro()).pushManager.getSubscription();
  if (!sub) return;
  try { await api("/push/desuscribir", { metodo: "POST", json: { endpoint: sub.endpoint } }); } catch { /* sin red: igual se libera en este equipo */ }
  await sub.unsubscribe();
}

/** Al cerrar sesión: este celular deja de recibir los avisos de esa cuenta (los recibiría quien entre después). Mejor esfuerzo. */
export async function liberarPushAlSalir() {
  try { if (soportaPush()) { await desactivarPush(); } } catch { /* nada */ }
}

/** Al iniciar sesión: si ya había permiso en este equipo, se asocia la suscripción a la cuenta actual (cambio de persona en la portería). */
export async function reasociarPush() {
  try {
    if (!soportaPush() || Notification.permission !== "granted") return;
    const sub = await (await registro()).pushManager.getSubscription();
    if (sub) await api("/push/suscribir", { metodo: "POST", json: sub.toJSON() });
  } catch { /* nada */ }
}

export async function probarPush() { return api("/push/probar", { metodo: "POST" }); }
