// Utilidades de interfaz: crear DOM de forma segura, iconos, formatos, toasts y modales.
// h() usa textContent / setAttribute: nunca innerHTML con datos del usuario (evita XSS).

export function h(tag, attrs, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of hijos.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return el;
}
export const vaciar = (el) => { el.replaceChildren(); return el; };

// ---------- Iconos (SVG estáticos, trazo 2) ----------
const ICONOS = {
  grid: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  calendario: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  llave: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94z"/>',
  tarjeta: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
  carro: '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/><circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
  usuarios: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  salir: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  mas: '<path d="M12 5v14M5 12h14"/>',
  ok: '<path d="M20 6 9 17l-5-5"/>',
  urna: '<rect x="3" y="12" width="18" height="9" rx="2"/><path d="M8 12V9M16 12V9M12 3v8M9 8l3 3 3-3"/>',
  sinred: '<path d="M2 2l20 20M8.5 16.4a5 5 0 0 1 7 0M2 8.8a15 15 0 0 1 4.2-2.6M10.7 5.1A15 15 0 0 1 22 8.8M5 12.9a10 10 0 0 1 5.2-2.7M16.8 11a10 10 0 0 1 2.2 1.9M12 20h.01"/>',
  movil: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  ojo: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  ojoNo: '<path d="M9.9 4.2A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-2.2 3.2M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a10 10 0 0 0 5.4-1.6M2 2l20 20"/>',
  imagen: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
  subir: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  alerta: '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3zM12 9v4M12 17h.01"/>',
  buscar: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  flecha: '<path d="M5 12h14M12 5l7 7-7 7"/>',
  megafono: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
  reloj: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  descarga: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  pin: '<path d="M12 17v5M9 10.8a2 2 0 0 1-1.1 1.8l-1.8.9A2 2 0 0 0 5 15.2V17h14v-1.8a2 2 0 0 0-1.1-1.8l-1.8-.9a2 2 0 0 1-1.1-1.8V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  luna: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>',
  pantalla: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>',
  lugar: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
  editar: '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  basura: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  ajustes: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h3M20 17v4"/>',
  tienda: '<path d="M3 9l1.5-5h15L21 9M3 9h18M3 9v11h18V9"/><path d="M9 20v-6h6v6"/>',
  camara: '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  chispa: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  chat: '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.6-.8L3 21l1.9-5.4A8.4 8.4 0 1 1 21 11.5z"/>',
  compartir: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 13.5l6.8 4M15.4 6.5l-6.8 4"/>',
  escudo: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
  caja: '<path d="M21 8 12 3 3 8v8l9 5 9-5V8z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  telefono: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/>',
  identificacion: '<rect x="2" y="4" width="20" height="16" rx="2"/><circle cx="9" cy="11" r="2.5"/><path d="M5 17c.6-1.7 2-2.5 4-2.5s3.4.8 4 2.5M15 9h4M15 13h4"/>',
  campana: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
  archivo: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/>',
  mensaje: '<path d="M4 4h16v12H8l-4 4z"/><path d="M8 9h8M8 12h5"/>',
  apps: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  vacio: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
};
export function icono(nombre, tam) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "2"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("aria-hidden", "true");
  if (tam) { s.setAttribute("width", tam); s.setAttribute("height", tam); }
  s.innerHTML = ICONOS[nombre] ?? "";   // SVG estático definido arriba, sin datos del usuario
  return s;
}

// ---------- Tema claro / oscuro (la lógica vive en tema.js) ----------
const TEMAS = [["claro", "sol", "Tema claro"], ["oscuro", "luna", "Tema oscuro"]];
export function botonTema(extra = "") {
  const btn = h("button", { class: `btn suave icono btn-tema ${extra}`, type: "button" });
  const pintar = () => {
    const [, ic, texto] = TEMAS.find(([k]) => k === window.CiudadelaTema.obtener());
    btn.replaceChildren(icono(ic));
    btn.title = `${texto} · clic para cambiar`; btn.setAttribute("aria-label", `${texto}. Cambiar tema`);
  };
  btn.addEventListener("click", () => {
    const i = TEMAS.findIndex(([k]) => k === window.CiudadelaTema.obtener());
    window.CiudadelaTema.establecer(TEMAS[(i + 1) % TEMAS.length][0]);
    pintar();
  });
  pintar();
  return btn;
}

// Logo compacto (icono + nombre). sobreOscuro=true se usa en el menú y el login, que siempre son azul oscuro.
export function logo(sobreOscuro = false) {
  const wrap = h("span", { class: "logo" });
  if (sobreOscuro) wrap.append(h("img", { class: "logo-img crema fija", src: "img/icono-crema.png", alt: "" }));
  else wrap.append(h("img", { class: "logo-img claro", src: "img/icono.png", alt: "" }), h("img", { class: "logo-img crema", src: "img/icono-crema.png", alt: "" }));
  wrap.append(h("span", { class: "logo-texto" }, "Ciudadela Digital"));
  return wrap;
}
// Logo completo (celular + conjunto + nombre), versión crema para fondos oscuros.
export const logoCompleto = () => h("img", { class: "logo-completo", src: "img/logo-crema.png", alt: "Ciudadela Digital · Control Residencial" });

// ---------- Formatos ----------
const cop = new Intl.NumberFormat("es-CO", { style: "currency", currency: "COP", maximumFractionDigits: 0 });
export const dinero = (n) => cop.format(n ?? 0);
// La API guarda created/ingreso en UTC sin "Z": se la agregamos para convertir a hora local.
export const deUtc = (s) => new Date(/Z|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z");
export const deLocal = (s) => new Date(s);
export const fmtHora = (d) => d.toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" });
export const fmtFechaLarga = (d) => d.toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });
export const fmtFechaCorta = (d) => d.toLocaleDateString("es-CO", { day: "numeric", month: "short", year: "numeric" });
export function hace(d) {
  const min = Math.max(0, Math.floor((Date.now() - d.getTime()) / 60000));
  if (min < 1) return "ahora mismo";
  if (min < 60) return `hace ${min} min`;
  const hrs = Math.floor(min / 60);
  if (hrs < 24) return `hace ${hrs} h ${min % 60} min`;
  return `hace ${Math.floor(hrs / 24)} d`;
}
export const iniciales = (n = "") => n.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "?";

// ---------- Piezas reutilizables ----------
const COLOR_ESTADO = {
  Aprobada: "bosque", Solucionado: "bosque", "Al día": "bosque", Dentro: "bosque", Activo: "bosque",
  Pendiente: "laton", "En Revision": "laton",
  Abierto: "arcilla", "En mora": "arcilla",
  "En Reparacion": "borde",
  Activa: "bosque", "Pendiente de pago": "laton", Rechazada: "arcilla", Vencida: "borde",
  Revocado: "arcilla", Vencido: "laton", Usado: "borde",
  "En porteria": "laton", Anulado: "borde",
  Radicada: "laton", "En tramite": "borde", Resuelta: "bosque", Cerrada: "borde",
  Pendiente: "laton", Abierta: "bosque", Anulada: "borde",
  Finalizado: "borde", Rechazado: "arcilla",
};
const ETIQUETA = { "En Revision": "En revisión", "En Reparacion": "En reparación", "En porteria": "En portería", "En tramite": "En trámite" };
export const badge = (estado, texto) => h("span", { class: `badge ${COLOR_ESTADO[estado] ?? ""}` }, texto ?? ETIQUETA[estado] ?? estado);

const TIPOS = { Reunion: ["Reunión", "bosque"], Evento: ["Evento", "laton"], Aviso: ["Aviso", ""], Urgente: ["Urgente", "arcilla"], Mantenimiento: ["Mantenimiento", "borde"] };
export const etiquetaTipo = (t) => TIPOS[t]?.[0] ?? t;
export const badgeTipo = (t) => h("span", { class: `badge ${TIPOS[t]?.[1] ?? ""}` }, etiquetaTipo(t));
export const fmtFechaHora = (d) => d.toLocaleString("es-CO", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
export function duracion(min) {
  if (min == null) return "—";
  if (min < 60) return `${min} min`;
  const d = Math.floor(min / 1440), hh = Math.floor((min % 1440) / 60), m = min % 60;
  return d ? `${d} d ${hh} h` : `${hh} h ${m} min`;
}

export function placa(valor = "") {
  const v = valor.toUpperCase();
  return h("div", { class: `placa ${v ? "" : "vacia"}`, "aria-label": `Placa ${v}` }, h("b", {}, v || "ABC123"), h("small", {}, "COLOMBIA"));
}
export function estadoVacio(titulo, texto) {
  return h("div", { class: "vacio" }, icono("vacio"), h("b", {}, titulo), h("span", {}, texto));
}
export const esqueleto = (alto = 90, n = 3) => h("div", { class: "lista" }, Array.from({ length: n }, () => h("div", { class: "esq", style: `height:${alto}px` })));

export function contar(el, hasta, formato = (n) => String(n)) {
  const dur = 700, ini = performance.now();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || hasta === 0) { el.textContent = formato(hasta); return; }
  const paso = (t) => {
    const p = Math.min(1, (t - ini) / dur);
    el.textContent = formato(Math.round(hasta * (1 - Math.pow(1 - p, 3))));
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}
export function kpi(etiqueta, valor, { alerta = false, destacado = false, formato } = {}) {
  const v = h("div", { class: "val" }, "0");
  contar(v, valor, formato);
  return h("div", { class: `kpi ${alerta && valor > 0 ? "alerta" : ""} ${destacado ? "destacado" : ""}` }, h("div", { class: "et" }, etiqueta), v);
}

// Botón con estado "cargando": evita dobles clics y da retroalimentación.
export async function conCarga(btn, fn) {
  btn.classList.add("loading"); btn.disabled = true;
  try { return await fn(); } finally { btn.classList.remove("loading"); btn.disabled = false; }
}

// ---------- Toasts ----------
// Un <dialog> abierto con showModal() queda en la «capa superior» del navegador y tapa todo lo que está fuera de él
// (incluidos los avisos). Por eso, mientras hay un modal abierto, el contenedor de avisos vive DENTRO del modal
// y se muestra arriba para no tapar los campos ni los botones; al cerrarse vuelve al <body>.
function ubicarToasts() {
  const cont = document.getElementById("toasts"), d = document.getElementById("modal");
  if (!cont || !d) return cont;
  const destino = d.open ? d : document.body;
  if (cont.parentElement !== destino) destino.append(cont);
  cont.classList.toggle("en-modal", d.open);
  return cont;
}
document.getElementById("modal")?.addEventListener("close", ubicarToasts);

export function toast(texto, tipo = "ok") {
  const t = h("div", { class: `toast ${tipo}`, role: "status" }, icono(tipo === "ok" ? "ok" : "alerta"), h("span", {}, texto));
  ubicarToasts().append(t);
  setTimeout(() => { t.classList.add("sale"); setTimeout(() => t.remove(), 300); }, 4200);
}

// ---------- Modal (<dialog> nativo: foco atrapado y Esc incluidos) ----------
export function modal(titulo, contenido, { pie } = {}) {
  const d = document.getElementById("modal");
  const cerrar = () => d.close();
  const cont = document.getElementById("toasts");
  if (cont && d.contains(cont)) document.body.append(cont);   // se rescatan los avisos antes de vaciar el modal
  d.replaceChildren(h("div", { class: "modal-int" },
    h("div", { class: "modal-cab" }, h("h2", {}, titulo), h("button", { class: "btn suave icono sm", "aria-label": "Cerrar", onclick: cerrar }, icono("x"))),
    contenido, pie ? h("div", { class: "modal-pie" }, pie) : null));
  d.onclick = (e) => { if (e.target === d) cerrar(); };
  d.showModal();
  ubicarToasts();
  return { cerrar };
}
export function confirmar(titulo, texto, textoBtn = "Confirmar", peligro = false) {
  return new Promise((resolve) => {
    let resuelto = false;
    const fin = (v) => { if (!resuelto) { resuelto = true; resolve(v); } };
    const m = modal(titulo, h("p", { class: "muted" }, texto), { pie: [
      h("button", { class: "btn suave", onclick: () => { fin(false); m.cerrar(); } }, "Volver"),
      h("button", { class: `btn ${peligro ? "arcilla" : ""}`, onclick: () => { fin(true); m.cerrar(); } }, textoBtn),
    ] });
    document.getElementById("modal").addEventListener("close", () => fin(false), { once: true });
  });
}
