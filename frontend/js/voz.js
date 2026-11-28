// Voz a texto (v5.8): un botón de micrófono en cada campo donde se redacta (formularios y chat). Usa el reconocimiento de voz del navegador:
// no hay servidor ni costo, pero solo existe en Chrome, Edge, Safari y los navegadores de Android; en Firefox no hay botón (no se muestra nada roto).
//
// Cuidados de privacidad y seguridad:
//  · La PRIMERA vez se explica que el navegador manda el audio a su servicio de voz (en Chrome, al de Google) y se pide aceptar.
//  · Nunca aparece en campos sensibles: contraseñas, códigos, documentos, teléfonos, correos, tarjetas, placas, números… (ver `SENSIBLE`).
//    Cualquier campo se puede excluir a mano con el atributo `data-sin-voz`.
//  · Solo escucha mientras el botón está activo: se detiene al pulsarlo otra vez, al enviar, al salir de la pantalla o al esconder la app.
import { h, icono, toast, confirmar } from "./ui.js";
import { vozLocale, segun } from "./i18n.js";

const SR = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
const AVISO = "ciudadela.voz.aviso";
// Lo que NUNCA se dicta. Se revisa name, id, placeholder, autocomplete, inputmode y aria-label del campo.
const SENSIBLE = /contrase|clave|passw|\bpin\b|token|c[oó]digo|\bcode\b|\botp\b|c[eé]dula|documento|\bnit\b|tarjeta|\bcard\b|\bcvv\b|\biban\b|cuenta bancaria|placa|plate|tel[eé]fono|phone|celular|correo|e-?mail|usuario|username|referencia|folio|one-time-code|cc-|current-password|new-password/i;
const ES_IOS_INSTALADA = /iP(hone|ad|od)/.test(globalThis.navigator?.userAgent ?? "") && globalThis.navigator?.standalone === true;   // allí el dictado del navegador no es fiable: queda el del teclado

export const vozDisponible = () => Boolean(SR) && !ES_IOS_INSTALADA;

let activo = null;               // { campo, boton, rec }

export function campoDictable(el) {
  if (!el || el.disabled || el.readOnly || el.hidden || el.hasAttribute?.("data-sin-voz")) return false;
  if (el.tagName === "INPUT") { if (!["text", "search"].includes((el.type || "text").toLowerCase())) return false; }
  else if (el.tagName !== "TEXTAREA") return false;
  if (["numeric", "tel", "decimal", "email", "url"].includes(el.getAttribute("inputmode") || "")) return false;
  const huella = [el.name, el.id, el.placeholder, el.getAttribute("autocomplete"), el.getAttribute("aria-label")].filter(Boolean).join(" ");
  return !SENSIBLE.test(huella);
}

/** Arma el contenido del campo: lo que había antes del cursor + lo dictado + lo que había después. Respeta `maxlength` y devuelve dónde queda el cursor. */
export function componerDictado({ antes, despues, finales, interino = "", maximo = Infinity, locale = "es-CO" }) {
  const separador = antes && !/\s$/.test(antes) ? " " : "";
  let dictado = `${finales}${interino ? `${finales ? " " : ""}${interino.trimStart()}` : ""}`;
  if (!antes.trim() || /[.!?¿¡]\s*$/.test(antes)) dictado = dictado.charAt(0).toLocaleUpperCase(locale) + dictado.slice(1);
  const pegado = dictado && despues && !/^\s/.test(despues) ? " " : "";
  const hastaCursor = antes + separador + dictado + pegado;
  const texto = (hastaCursor + despues).slice(0, maximo);
  return { texto, cursor: Math.min(hastaCursor.length, maximo), truncado: (hastaCursor + despues).length > maximo };
}


function pintar(boton, escuchando) {
  boton.classList.toggle("escuchando", escuchando);
  boton.setAttribute("aria-pressed", String(escuchando));
  const texto = escuchando ? segun("Escuchando… toca para detener", "Listening… tap to stop") : segun("Dictar con el micrófono", "Dictate with the microphone");
  boton.setAttribute("aria-label", texto); boton.title = texto;
}

export function detenerVoz() {
  if (!activo) return;
  const { rec, boton } = activo;
  activo = null;
  try { rec.onend = null; rec.onerror = null; rec.stop(); } catch { /* ya estaba detenido */ }
  pintar(boton, false);
}

async function aceptoElAviso() {
  try { if (localStorage.getItem(AVISO) === "1") return true; } catch { /* sin almacenamiento: se pregunta cada vez */ }
  const si = await confirmar(segun("Dictar con el micrófono", "Dictate with the microphone"),
    segun("Para convertir tu voz en texto, tu navegador envía el audio a su servicio de reconocimiento de voz (en Chrome, al de Google). Nosotros no guardamos el audio. No dictes contraseñas, cédulas ni datos bancarios.",
      "To turn your voice into text, your browser sends the audio to its speech recognition service (in Chrome, Google's). We do not store the audio. Do not dictate passwords, ID numbers or bank details."),
    segun("Entendido, empezar", "Got it, start"));
  if (si) { try { localStorage.setItem(AVISO, "1"); } catch { /* no se pudo recordar */ } }
  return si;
}

const ERRORES = {
  "not-allowed": ["Permiso del micrófono denegado. Actívalo en el candado junto a la dirección del navegador y vuelve a intentarlo.", "Microphone permission denied. Turn it on from the lock icon next to the address bar and try again."],
  "service-not-allowed": ["Este navegador no permite el dictado aquí. Puedes usar el micrófono de tu teclado.", "This browser does not allow dictation here. You can use your keyboard's microphone."],
  "audio-capture": ["No encontramos un micrófono disponible.", "We could not find an available microphone."],
  "network": ["El dictado necesita conexión a internet.", "Dictation needs an internet connection."],
  "language-not-supported": ["Tu navegador no entiende este idioma en el dictado.", "Your browser does not support dictation in this language."],
};

async function iniciar(campo, boton) {
  if (!await aceptoElAviso()) return;
  const rec = new SR();
  rec.lang = vozLocale(); rec.continuous = true; rec.interimResults = true; rec.maxAlternatives = 1;
  const ini = campo.selectionStart ?? campo.value.length, fin = campo.selectionEnd ?? ini;
  const antes = campo.value.slice(0, ini), despues = campo.value.slice(fin);
  const maximo = campo.maxLength > 0 ? campo.maxLength : Infinity;
  let finales = "", avisoLimite = false;

  rec.onresult = (e) => {
    let interino = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const trozo = e.results[i][0].transcript;
      if (e.results[i].isFinal) finales += (finales && !/\s$/.test(finales) ? " " : "") + trozo.trim(); else interino += trozo;
    }
    const { texto, cursor, truncado } = componerDictado({ antes, despues, finales, interino, maximo, locale: vozLocale() });
    if (truncado && !avisoLimite) { avisoLimite = true; toast(segun("Llegaste al límite de caracteres de este campo.", "You reached this field's character limit.")); }
    campo.value = texto;
    try { campo.setSelectionRange(cursor, cursor); } catch { /* el tipo de campo no admite cursor */ }
    campo.dispatchEvent(new Event("input", { bubbles: true }));          // para que el autoguardado, los contadores y el chat se enteren
  };
  rec.onerror = (e) => {
    const m = ERRORES[e.error];
    if (m) toast(segun(m[0], m[1]), "error");
    detenerVoz();
  };
  rec.onend = () => detenerVoz();                                         // el navegador corta solo tras un rato de silencio
  try { rec.start(); } catch { return; }
  activo = { campo, boton, rec };
  pintar(boton, true);
  campo.focus({ preventScroll: true });
}

function alternar(campo, boton) {
  const mismo = activo?.campo === campo;
  detenerVoz();
  if (!mismo) iniciar(campo, boton);
}

function botonPara(campo) {
  const boton = h("button", { class: "voz-btn", type: "button", "data-no-traducir": "", "aria-pressed": "false", onclick: () => alternar(campo, boton) }, icono("microfono", 18));
  pintar(boton, false);
  return boton;
}

/** Pone el botón en los campos de redacción que haya dentro de `raiz`: los `.field` de los formularios y el campo del chat. */
export function adjuntarVoz(raiz) {
  if (!vozDisponible() || !raiz?.querySelectorAll) return;
  const contenedores = [...(raiz.matches?.(".field, .chat-form") ? [raiz] : []), ...raiz.querySelectorAll(".field, .chat-form")];
  for (const c of contenedores) {
    if (c.querySelector(":scope > .voz-btn")) continue;
    const campo = c.querySelector(":scope > textarea, :scope > input");
    if (!campo || !campoDictable(campo)) continue;
    const boton = botonPara(campo);
    if (c.classList.contains("chat-form")) { const enviar = c.querySelector(".chat-enviar"); enviar ? enviar.before(boton) : c.append(boton); boton.classList.add("en-chat"); }
    else { c.classList.add("con-voz"); c.classList.toggle("una-linea", campo.tagName === "INPUT"); c.append(boton); }
  }
}

export function iniciarVoz() {
  if (!vozDisponible() || typeof MutationObserver === "undefined") return;
  adjuntarVoz(document.body);
  new MutationObserver((cambios) => {
    for (const c of cambios) for (const n of c.addedNodes) if (n.nodeType === 1) adjuntarVoz(n);
    if (activo && !activo.campo.isConnected) detenerVoz();                 // la pantalla o la ventana se cerró con el micrófono encendido
  }).observe(document.body, { childList: true, subtree: true });
  addEventListener("hashchange", detenerVoz);
  document.addEventListener("visibilitychange", () => { if (document.hidden) detenerVoz(); });
  document.addEventListener("submit", detenerVoz, true);
  document.addEventListener("keydown", (e) => { if (activo && e.key === "Enter" && !e.shiftKey && e.target === activo.campo) setTimeout(detenerVoz, 0); }, true);   // Enter envía el chat
}
