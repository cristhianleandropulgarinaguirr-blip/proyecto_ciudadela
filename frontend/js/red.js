// Estado de la conexión. `navigator.onLine` miente (dice «en línea» con wifi sin internet), así que se combina con lo que
// pasa de verdad: si una petición falla por red → sin conexión; si una sale bien → con conexión. Mientras no haya conexión
// se «sondea» /salud cada pocos segundos para detectar el regreso sin esperar a que la persona toque algo.
let enLinea = navigator.onLine !== false;
let sonda = null;
const oyentes = new Set();

const avisar = () => oyentes.forEach((f) => { try { f(enLinea); } catch { /* un oyente no rompe a los demás */ } });
function poner(valor) {
  if (valor === enLinea) return;
  enLinea = valor; avisar();
  if (!enLinea) iniciarSonda(); else detenerSonda();
}
function iniciarSonda() {
  if (sonda) return;
  sonda = setInterval(async () => {
    try {
      const c = new AbortController(), t = setTimeout(() => c.abort(), 6000);
      const r = await fetch("/salud", { cache: "no-store", signal: c.signal }); clearTimeout(t);
      if (r.ok) poner(true);
    } catch { /* sigue sin conexión */ }
  }, 5000);
}
function detenerSonda() { clearInterval(sonda); sonda = null; }

addEventListener("online", () => { /* el navegador cree que volvió: se confirma con una petición real */ fetch("/salud", { cache: "no-store" }).then((r) => r.ok && poner(true)).catch(() => {}); });
addEventListener("offline", () => poner(false));
if (!enLinea) iniciarSonda();

export const red = {
  get enLinea() { return enLinea; },
  fallo() { poner(false); },
  ok() { poner(true); },
  alCambiar(fn) { oyentes.add(fn); return () => oyentes.delete(fn); },
};
