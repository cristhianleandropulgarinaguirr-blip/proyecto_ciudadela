// Instalar Ciudadela Digital como app (PWA): registra el service worker y maneja el botón «Instalar».
// - Android / Chrome / Edge (celular y computador): el navegador avisa con `beforeinstallprompt` y nosotros lo guardamos.
// - iPhone / iPad (Safari): no hay aviso automático; se explica «Compartir → Agregar a inicio».
// Importante: instalar como app y el service worker exigen HTTPS (o localhost). Con http://192.168.x.x solo queda un acceso directo.
let aviso = null;
const oyentes = new Set();

window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); aviso = e; oyentes.forEach((f) => f()); });
window.addEventListener("appinstalled", () => { aviso = null; oyentes.forEach((f) => f()); });

export function registrarServiceWorker() {
  if (!("serviceWorker" in navigator) || !window.isSecureContext) return;
  addEventListener("load", () => { navigator.serviceWorker.register("sw.js", { scope: "./" }).catch(() => {}); });
}

export const yaInstalada = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
export const esIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
export const puedeInstalar = () => !yaInstalada() && aviso !== null;
export const alCambiarInstalacion = (f) => { oyentes.add(f); return () => oyentes.delete(f); };

export async function instalar() {
  if (!aviso) return false;
  aviso.prompt();
  const { outcome } = await aviso.userChoice;
  aviso = null; oyentes.forEach((f) => f());
  return outcome === "accepted";
}

// Texto de ayuda según el dispositivo (para cuando no hay botón automático).
export function ayudaInstalar() {
  if (yaInstalada()) return "Ya la tienes instalada en este dispositivo.";
  if (esIOS()) return "En el iPhone: toca Compartir (el cuadro con la flecha) y luego «Agregar a inicio».";
  if (!window.isSecureContext) return "La instalación completa necesita la dirección segura (https) de tu conjunto. Por ahora puedes agregar un acceso directo desde el menú del navegador.";
  return "En el menú del navegador (⋮) elige «Instalar app» o «Agregar a la pantalla principal».";
}
