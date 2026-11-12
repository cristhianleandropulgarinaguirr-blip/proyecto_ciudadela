// Cliente HTTP de Ciudadela Digital: centraliza el token JWT y los errores de la API.
const CLAVE = "ciudadela.token";

// El token vive en localStorage (no en sessionStorage): al abrir la cámara nativa del celular el navegador/PWA pasa a segundo plano
// y el sistema puede cerrar la página para liberar memoria. Al volver, la página se recarga y sessionStorage ya estaría vacío
// (→ te mandaba al login). La seguridad no cambia: el JWT sigue expirando solo en el servidor (60 min; Guardia, más).
const leer = (k) => { try { return localStorage.getItem(k) ?? sessionStorage.getItem(k); } catch { return null; } };
const borrar = (k) => { try { localStorage.removeItem(k); } catch {} try { sessionStorage.removeItem(k); } catch {} };

export const sesion = {
  get token() { return leer(CLAVE); },
  guardar(t) { try { localStorage.setItem(CLAVE, t); } catch { sessionStorage.setItem(CLAVE, t); } },
  cerrar() { borrar(CLAVE); lecturas.clear(); },
};

let alExpirar = () => {};
export const cuandoExpire = (fn) => { alExpirar = fn; };

export class ApiError extends Error {
  constructor(mensaje, status) { super(mensaje); this.status = status; }
}

// FastAPI responde {detail: "texto"} o, en 422, {detail: [{loc, msg}]}.
function mensajeDe(datos, status) {
  const d = datos?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const campo = String(d[0].loc?.at(-1) ?? "");
    return `Revisa el campo «${campo}»: ${d[0].msg}`;
  }
  if (status === 413) return "El archivo es demasiado grande.";
  if (status >= 500) return "Algo falló en el servidor. Intenta de nuevo.";
  return "No se pudo completar la acción.";
}

async function pedir(ruta, { metodo = "GET", params, json, form, cuerpo } = {}) {
  let url = ruta;
  if (params) url += "?" + new URLSearchParams(params);
  const headers = {};
  if (sesion.token) headers.Authorization = `Bearer ${sesion.token}`;
  let body;
  if (json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  else if (form) body = new URLSearchParams(form);   // login = application/x-www-form-urlencoded
  else if (cuerpo) body = cuerpo;                    // FormData (multipart) — el navegador pone el boundary

  let res;
  try { res = await fetch(url, { method: metodo, headers, body }); }
  catch { throw new ApiError("Sin conexión con el servidor. Revisa tu internet.", 0); }

  if (res.status === 401 && ruta !== "/auth/login" && sesion.token) alExpirar();
  if (!res.ok) {
    const datos = await res.json().catch(() => null);
    throw new ApiError(mensajeDe(datos, res.status), res.status);
  }
  return res;
}

// Caché corta en memoria para lecturas (GET): evita pedir lo mismo dos veces seguidas al navegar entre pantallas
// (por ejemplo, la cartelera en Inicio y luego en Cartelera). Cualquier escritura (POST/PUT/PATCH/DELETE) la vacía,
// y lo que cambia sin parar (notificaciones, portería, sesión) nunca se guarda.
const TTL_MS = 12000;
const NO_CACHEAR = [/^\/notificaciones/, /^\/porteria/, /^\/usuarios\/me/, /^\/auth/, /^\/visitantes-autorizados\/dentro/];
const lecturas = new Map();            // clave → { t, promesa }
export const vaciarCache = () => lecturas.clear();

export async function api(ruta, opc = {}) {
  const metodo = (opc.metodo ?? "GET").toUpperCase();
  if (metodo !== "GET") {
    const r = await pedir(ruta, opc).then((x) => x.json());
    lecturas.clear();
    return r;
  }
  if (NO_CACHEAR.some((re) => re.test(ruta))) return (await pedir(ruta, opc)).json();
  const clave = `${sesion.token}|${ruta}?${opc.params ? new URLSearchParams(opc.params) : ""}`;
  const previa = lecturas.get(clave);
  if (previa && Date.now() - previa.t < TTL_MS) return structuredClone(await previa.promesa);
  const promesa = pedir(ruta, opc).then((x) => x.json());
  lecturas.set(clave, { t: Date.now(), promesa });
  promesa.catch(() => lecturas.delete(clave));     // un error no se guarda
  return structuredClone(await promesa);
}
export const apiBlob = async (ruta, opc) => (await pedir(ruta, opc)).blob();
