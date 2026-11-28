// Idioma de la interfaz: español (por defecto) o inglés. v5.8
//
// Cómo funciona, para que sea fácil de mantener:
//  · El español es la fuente: en el código los textos siguen escritos en español y NO hay que tocar cada pantalla.
//  · Con el idioma en inglés, este módulo carga el diccionario (`i18n-en.js`) y traduce lo que aparece en pantalla: textos, placeholder,
//    title, aria-label y alt. Un MutationObserver traduce también lo que se pinta después (pantallas nuevas, avisos, ventanas, el chat).
//    Corre antes de pintar, así nunca se ve un destello en español.
//  · Si a un texto le falta traducción, se ve en español: nada se rompe. En inglés, `window.i18nFaltantes()` en la consola lista lo que falta.
//  · Lo que escribe la gente (nombres, anuncios, descripciones) y lo que arma la IA NO se traduce: solo coinciden textos EXACTOS del diccionario.
//  · Fechas, horas y dinero usan el formato del idioma (`locale()`); «hace 5 min» y duraciones se escriben ya en el idioma elegido.
//  · Cambiar de idioma recarga la pantalla: es lo más seguro (no hay que «des-traducir» nada) y la sesión se conserva.
const CLAVE = "ciudadela.idioma";
const IDIOMAS = ["es", "en"];

function leer() {
  try { const g = localStorage.getItem(CLAVE); if (IDIOMAS.includes(g)) return g; } catch { /* sin almacenamiento: se queda en español */ }
  return "es";
}
let actual = leer();
let EXACTOS = new Map();
let PATRONES = [];
const faltantes = new Set();

export const idioma = () => actual;
export const esIngles = () => actual === "en";
/** Código de idioma para Intl y para toLocale…String(). */
export const locale = () => (actual === "en" ? "en-US" : "es-CO");
/** Código que entiende el reconocimiento de voz del navegador. */
export const vozLocale = () => (actual === "en" ? "en-US" : "es-CO");
/** Elige entre dos textos según el idioma (para lo que se arma en código, como «hace 5 min»). */
export const segun = (es, en) => (actual === "en" ? en : es);

const ATRIBUTOS = ["placeholder", "title", "aria-label", "alt"];
const SALTAR = new Set(["SCRIPT", "STYLE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "CODE", "PRE", "NOSCRIPT"]);
const HAY_LETRAS = /[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}/;

/** Traduce un texto (con sus espacios alrededor intactos). Primero coincidencia exacta; luego los patrones con partes variables. */
export function traducir(texto) {
  if (actual !== "en" || !texto) return texto;
  const base = texto.trim();
  if (!base) return texto;
  const exacto = EXACTOS.get(base);
  if (exacto !== undefined) return texto.replace(base, exacto);
  let salida = base;
  for (const [patron, reemplazo] of PATRONES) salida = salida.replace(patron, reemplazo);
  if (salida === base && HAY_LETRAS.test(base) && faltantes.size < 500) faltantes.add(base);          // solo para el desarrollador (en memoria, tope de 500)
  return salida === base ? texto : texto.replace(base, salida);
}
/** Para textos armados en código que se muestran fuera del DOM normal (por ejemplo notificaciones del sistema). */
export const t = (es) => traducir(es);

const omitido = (el) => !el || (el.closest?.("[data-no-traducir], [contenteditable='true']") != null);

function textoDe(nodo) {
  const padre = nodo.parentElement;
  if (!padre || SALTAR.has(padre.tagName) || omitido(padre)) return;
  const nuevo = traducir(nodo.nodeValue);
  if (nuevo !== nodo.nodeValue) nodo.nodeValue = nuevo;
}

function atributosDe(el) {
  if (omitido(el)) return;
  for (const a of ATRIBUTOS) {
    const v = el.getAttribute?.(a);
    if (v) { const n = traducir(v); if (n !== v) el.setAttribute(a, n); }
  }
  // Botones de formulario: el texto está en `value`.
  if (el.tagName === "INPUT" && (el.type === "button" || el.type === "submit")) { const n = traducir(el.value); if (n !== el.value) el.value = n; }
}

export function traducirArbol(raiz) {
  if (actual !== "en" || !raiz) return;
  if (raiz.nodeType === 3) return textoDe(raiz);
  if (raiz.nodeType !== 1 && raiz.nodeType !== 11) return;
  if (raiz.nodeType === 1) { if (omitido(raiz)) return; atributosDe(raiz); }
  const caminante = document.createTreeWalker(raiz, 4 /* texto */ | 1 /* elemento */);
  for (let n = caminante.nextNode(); n; n = caminante.nextNode()) {
    if (n.nodeType === 3) textoDe(n);
    else if (SALTAR.has(n.tagName) && n.tagName !== "INPUT") continue;
    else atributosDe(n);
  }
}

let observador = null;
function observar() {
  if (observador || typeof MutationObserver === "undefined") return;
  observador = new MutationObserver((cambios) => {
    for (const c of cambios) {
      if (c.type === "childList") c.addedNodes.forEach((n) => traducirArbol(n));
      else if (c.type === "characterData") textoDe(c.target);
      else if (c.type === "attributes") atributosDe(c.target);
    }
  });
  observador.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATRIBUTOS });
}

/** Se llama una sola vez al arrancar (antes de pintar nada). En inglés carga el diccionario y empieza a traducir. */
export async function iniciarIdioma() {
  document.documentElement.lang = actual;
  if (actual !== "en") return;
  try {
    const m = await import("./i18n-en.js");
    EXACTOS = new Map(Object.entries(m.EXACTOS).map(([k, v]) => [k.trim(), String(v).trim()]));      // las claves se buscan ya recortadas
    PATRONES = m.PATRONES;
  } catch { /* sin diccionario: la interfaz se queda en español, que es lo seguro */ }
  globalThis.i18nFaltantes = () => [...faltantes].sort();
  traducirArbol(document.body);
  document.title = traducir(document.title);
  observar();
}

/** Cambia el idioma y recarga la pantalla para que todo se pinte limpio en el idioma nuevo. */
export function cambiarIdioma(nuevo) {
  if (!IDIOMAS.includes(nuevo) || nuevo === actual) return;
  try { localStorage.setItem(CLAVE, nuevo); } catch { /* sin almacenamiento: no se puede recordar */ }
  location.reload();
}

/** Botón de la barra superior y del login: muestra el idioma al que se cambia («English» estando en español, «Español» estando en inglés). */
export function botonIdioma(h, extra = "") {
  const destino = actual === "en" ? "es" : "en";
  const nombre = destino === "en" ? "English" : "Español";
  return h("button", { class: `btn suave btn-idioma ${extra}`, type: "button", "data-no-traducir": "", lang: destino, title: nombre,
    "aria-label": destino === "en" ? "Cambiar idioma a inglés (Switch to English)" : "Switch language to Spanish (Cambiar a español)", onclick: () => cambiarIdioma(destino) },
  h("span", { "aria-hidden": "true" }, destino.toUpperCase()), h("span", { class: "btn-idioma-nombre" }, nombre));
}
