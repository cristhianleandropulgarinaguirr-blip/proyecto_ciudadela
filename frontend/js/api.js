// Cliente HTTP de Ciudadela Digital: sesión, renovación automática del token y errores de la API.
//
// SESIÓN (versión 3.1):
//  - El servidor entrega un token de acceso CORTO (15 min) y una cookie de renovación HttpOnly (JavaScript no puede leerla).
//  - El token de acceso vive en sessionStorage (solo esa pestaña) y se renueva solo antes de vencer o al recibir un 401.
//  - Si el celular cierra la página al abrir la cámara, al volver NO se pierde la sesión: la cookie renueva el token sin pedir la clave.
//  - Solo se muestra el login cuando el SERVIDOR dice que la sesión ya no existe (401 al renovar). Un fallo de red, un servidor
//    que está despertando (Render gratis) o un error 5xx NUNCA cierran la sesión.
import { red } from "./red.js";

const TOKEN = "ciudadela.acceso", PISTA = "ciudadela.sesion";
const CSRF = { "X-Requested-With": "ciudadela" };
const MARGEN_S = 30;           // se renueva si al token le quedan menos de estos segundos

const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* modo privado */ } };
const lsDel = (k) => { try { localStorage.removeItem(k); } catch { /* nada */ } };
const ssGet = (k) => { try { return sessionStorage.getItem(k); } catch { return null; } };
const ssSet = (k, v) => { try { sessionStorage.setItem(k, v); } catch { /* nada */ } };
const ssDel = (k) => { try { sessionStorage.removeItem(k); } catch { /* nada */ } };

// Limpieza de la versión anterior: el token ya NO se guarda en localStorage (cualquier script de la página podía leerlo).
lsDel("ciudadela.token"); ssDel("ciudadela.token");

let acceso = null;                 // { t: token, exp: ms epoch }
try { const g = JSON.parse(ssGet(TOKEN) ?? "null"); if (g?.t && g.exp) acceso = g; } catch { /* sin sesión guardada */ }

export const sesion = {
  /** ¿Hay una sesión que intentar recuperar? (La cookie es HttpOnly: esta «pista» solo evita una petición inútil en el login). */
  get posible() { return !!acceso || lsGet(PISTA) === "1"; },
  get token() { return acceso?.t ?? null; },
  guardar(datos) {
    acceso = { t: datos.access_token, exp: Date.now() + (datos.expira_en ?? 900) * 1000 };
    ssSet(TOKEN, JSON.stringify(acceso)); lsSet(PISTA, "1");
  },
  /** Borra la sesión de este navegador (no avisa al servidor: para eso está `cerrarEnServidor`). */
  cerrar() { acceso = null; ssDel(TOKEN); lsDel(PISTA); lecturas.clear(); },
};

let alExpirar = () => {};
export const cuandoExpire = (fn) => { alExpirar = fn; };

export class ApiError extends Error {
  constructor(mensaje, status) { super(mensaje); this.status = status; }
  get sinRed() { return this.status === 0; }
}
export const esErrorDeRed = (e) => e instanceof ApiError && e.status === 0;

// ---------------------------------------------------------------- renovación (una sola a la vez)
let renovando = null;
/** Devuelve "ok" | "negada" (el servidor dice que ya no hay sesión) | "sin-red" (no se pudo preguntar). */
export function renovar() {
  return (renovando ??= (async () => {
    try {
      const res = await fetch("/auth/refresh", { method: "POST", headers: CSRF, credentials: "same-origin" });
      if (res.ok) { sesion.guardar(await res.json()); return "ok"; }
      if (res.status === 401 || res.status === 403) return "negada";
      return "sin-red";                       // 5xx o el servidor despertando: no es lo mismo que «sesión cerrada»
    } catch { return "sin-red"; }
    finally { setTimeout(() => { renovando = null; }, 0); }
  })());
}

/** Restaura la sesión al abrir la app: "ok" | "sin-sesion" | "sin-red". Reintenta unos segundos si el servidor está despertando. */
export async function restaurarSesion() {
  if (acceso && acceso.exp - Date.now() > MARGEN_S * 1000) return "ok";
  if (!sesion.posible) return "sin-sesion";
  for (let i = 0; i < 4; i++) {
    const r = await renovar();
    if (r === "ok") return "ok";
    if (r === "negada") { sesion.cerrar(); return "sin-sesion"; }
    await new Promise((f) => setTimeout(f, 1500 * (i + 1)));
  }
  return "sin-red";
}

export async function cerrarEnServidor() {
  try { await fetch("/auth/logout", { method: "POST", headers: CSRF, credentials: "same-origin", keepalive: true }); } catch { /* sin red: la sesión vence sola */ }
}

// ---------------------------------------------------------------- errores
// FastAPI responde {detail: "texto"} o, en 422, {detail: [{loc, msg}]}.
function mensajeDe(datos, status) {
  const d = datos?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const campo = String(d[0].loc?.at(-1) ?? "");
    return `Revisa el campo «${campo}»: ${d[0].msg}`;
  }
  if (status === 413) return "El archivo es demasiado grande.";
  if (status === 429) return "Demasiados intentos. Espera un momento e inténtalo de nuevo.";
  if (status >= 500) return "Algo falló en el servidor. Intenta de nuevo.";
  return "No se pudo completar la acción.";
}

const espera = (ms) => new Promise((f) => setTimeout(f, ms));
const TRANSITORIOS = new Set([502, 503, 504]);    // el servidor gratis de Render devuelve esto mientras despierta

async function enviar(ruta, { metodo = "GET", params, json, form, cuerpo, timeout = 25000 }, token) {
  let url = ruta;
  if (params) url += "?" + new URLSearchParams(params);
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let body;
  if (json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
  else if (form) body = new URLSearchParams(form);   // login = application/x-www-form-urlencoded
  else if (cuerpo) body = cuerpo;                    // FormData (multipart) — el navegador pone el boundary
  const control = new AbortController();
  const t = setTimeout(() => control.abort(), timeout);
  try { return await fetch(url, { method: metodo, headers, body, signal: control.signal, credentials: "same-origin" }); }
  catch { throw new ApiError("Sin conexión con el servidor. Revisa tu internet.", 0); }
  finally { clearTimeout(t); }
}

async function pedir(ruta, opc = {}) {
  const esAuth = ruta === "/auth/login" || ruta === "/auth/refresh";
  const metodo = (opc.metodo ?? "GET").toUpperCase();
  // Si al token le queda poco, se renueva ANTES de pedir (así casi nunca se ve un 401).
  if (!esAuth && acceso && acceso.exp - Date.now() < MARGEN_S * 1000) await renovar();
  const reintentos = metodo === "GET" ? 2 : 0;       // lecturas: se reintenta si el servidor está despertando; escrituras: nunca (podrían duplicarse)

  let res, intento = 0;
  for (;;) {
    try { res = await enviar(ruta, opc, esAuth ? null : sesion.token); }
    catch (e) { if (e.sinRed) red.fallo(); if (intento++ < reintentos) { await espera(700 * intento); continue; } throw e; }
    if (TRANSITORIOS.has(res.status) && intento++ < reintentos) { await espera(900 * intento); continue; }
    break;
  }
  red.ok();

  // 401 con sesión: se intenta renovar UNA vez y se repite la petición. Solo si el servidor niega la renovación se cierra la sesión.
  if (res.status === 401 && !esAuth && sesion.posible) {
    const r = await renovar();
    if (r === "ok") { res = await enviar(ruta, opc, sesion.token); }
    else if (r === "negada") { alExpirar(); }
    else throw new ApiError("Sin conexión con el servidor. Revisa tu internet.", 0);
  }
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
const NO_CACHEAR = [/^\/notificaciones/, /^\/porteria/, /^\/usuarios\/me/, /^\/auth/, /^\/visitantes-autorizados\/(dentro|sincronizacion)/, /^\/push/, /^\/votaciones\/pendientes/];
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
  const clave = `${ruta}?${opc.params ? new URLSearchParams(opc.params) : ""}`;
  const previa = lecturas.get(clave);
  if (previa && Date.now() - previa.t < TTL_MS) return structuredClone(await previa.promesa);
  const promesa = pedir(ruta, opc).then((x) => x.json());
  lecturas.set(clave, { t: Date.now(), promesa });
  promesa.catch(() => lecturas.delete(clave));     // un error no se guarda
  return structuredClone(await promesa);
}
export const apiBlob = async (ruta, opc) => (await pedir(ruta, opc)).blob();
