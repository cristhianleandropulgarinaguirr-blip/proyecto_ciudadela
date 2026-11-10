// Cliente HTTP de Ciudadela Digital: centraliza el token JWT y los errores de la API.
const CLAVE = "ciudadela.token";

export const sesion = {
  get token() { return sessionStorage.getItem(CLAVE); },
  guardar(t) { sessionStorage.setItem(CLAVE, t); },
  cerrar() { sessionStorage.removeItem(CLAVE); },
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

export const api = async (ruta, opc) => (await pedir(ruta, opc)).json();
export const apiBlob = async (ruta, opc) => (await pedir(ruta, opc)).blob();
