// Chat del asistente «Ciudabot» (v3.2). Botón flotante + panel de conversación.
// Responde con datos reales de reservas (congestión de zonas comunes) y orienta dentro de la app.
// NUNCA reserva ni modifica nada: solo informa y lleva a la sección correcta.
// La conversación vive solo en memoria (se borra al cerrar sesión). Todo el DOM se arma con h(): nada de innerHTML.
// Endpoints: GET /asistente/chat/estado · POST /asistente/chat
import { api } from "./api.js";
import { h, icono, badge, deUtc, hace } from "./ui.js";

const CORTO = { lunes: "lun", martes: "mar", miércoles: "mié", jueves: "jue", viernes: "vie", sábado: "sáb", domingo: "dom" };
const INICIALES = ["¿Qué días suele estar más congestionado el BBQ?", "¿Qué día está más libre la piscina?", "¿Cómo reservo una zona?"];
const MAX_TURNOS = 8;

let fab = null, panel = null, cuerpo = null, campo = null, enviarBtn = null, pie = null, subtitulo = null;
let historial = [];            // [{ rol: "usuario" | "asistente", texto }] — lo que se manda como contexto
let ocupado = false, abierto = false, estado = null, nombre = "";

// ---------------------------------------------------------------- texto seguro con **negrita**
function formatear(texto) {
  const parrafos = String(texto).split(/\n+/).filter(Boolean);
  return parrafos.map((linea) => h("p", {}, linea.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((t) =>
    (t.startsWith("**") && t.endsWith("**") && t.length > 4 ? h("strong", {}, t.slice(2, -2)) : t))));
}

// ---------------------------------------------------------------- piezas de la conversación
function burbuja(clase, contenido) {
  const fila = h("div", { class: `chat-msg ${clase}` }, h("div", { class: "chat-burbuja" }, contenido));
  if (clase === "bot") fila.prepend(h("span", { class: "chat-avatar", "aria-hidden": "true" }, icono("chispa", 16)));
  return fila;
}

function grafico(g) {
  const maximo = Math.max(1, ...g.dias.map((d) => d.total));
  const columnas = g.dias.map((d, i) => {
    const barra = h("span", { class: "barra" });
    barra.style.setProperty("--r", (d.total / maximo).toFixed(3));
    barra.style.setProperty("--i", String(i));
    return h("div", { class: `col${d.destacado ? " top" : ""}` }, h("span", { class: "val" }, d.total), barra, h("span", { class: "dia" }, CORTO[d.dia] ?? d.dia));
  });
  return h("figure", { class: "chat-grafico" },
    h("figcaption", {}, h("b", {}, "Reservas por día"), h("span", {}, g.zona)),
    h("div", { class: "barras", role: "img", "aria-label": `Reservas por día en ${g.zona}: ${g.dias.map((d) => `${d.dia} ${d.total}`).join(", ")}` }, columnas),
    h("small", {}, `Según ${g.total} reservas pedidas o aprobadas. Mide la demanda, no la asistencia real.`));
}

function solicitudes(lista) {
  return h("div", { class: "chat-solicitudes" }, lista.map((s) => h("a", { class: "asistente-fila", href: s.enlace, onclick: () => cerrar() },
    h("div", {}, h("b", {}, `${s.referencia} · ${s.titulo}`), h("span", { class: "small muted" }, `${s.clase} · ${hace(deUtc(s.fecha))}`)), badge(s.estado))));
}

function agregarBot(r) {
  quitarSugerencias();
  const partes = [...formatear(r.respuesta)];
  if (r.grafico) partes.push(grafico(r.grafico));
  if (r.solicitudes?.length) partes.push(solicitudes(r.solicitudes));
  if (r.accion) partes.push(h("a", { class: "btn suave chat-accion", href: r.accion.enlace, onclick: () => cerrar() }, r.accion.texto, icono("flecha", 16)));
  cuerpo.append(burbuja("bot", partes));
  if (r.sugerencias?.length) cuerpo.append(sugerencias(r.sugerencias));
  bajar();
}

function sugerencias(lista) {
  return h("div", { class: "chat-chips", role: "group", "aria-label": "Preguntas sugeridas" },
    lista.map((t) => h("button", { class: "chat-chip", type: "button", onclick: () => enviar(t) }, t)));
}
const quitarSugerencias = () => cuerpo?.querySelectorAll(".chat-chips").forEach((c) => c.remove());
const bajar = () => requestAnimationFrame(() => cuerpo?.scrollTo({ top: cuerpo.scrollHeight, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }));

function escribiendo() {
  return h("div", { class: "chat-msg bot chat-escribiendo", role: "status", "aria-label": "Ciudabot está escribiendo" },
    h("span", { class: "chat-avatar", "aria-hidden": "true" }, icono("chispa", 16)),
    h("div", { class: "chat-burbuja" }, h("i"), h("i"), h("i")));
}

function bienvenida() {
  cuerpo.replaceChildren();
  const primero = nombre.split(" ")[0] || "";
  agregarBot({ respuesta: `¡Hola${primero ? `, ${primero}` : ""}! Soy **Ciudabot**. Te cuento qué días y horas se congestionan las zonas comunes (BBQ, piscina, salón…) con los datos reales de reservas, y te oriento en la app.`, sugerencias: INICIALES });
}

function actualizarPie() {
  const aviso = "Ciudabot puede equivocarse. No escribas cédulas, teléfonos ni claves.";
  const quedan = estado && estado.ia && estado.restantes != null ? ` · ${estado.restantes} mensajes con IA hoy` : "";
  pie.textContent = aviso + quedan;
  subtitulo.textContent = estado ? (estado.ia ? "Con IA · responde con datos de reservas" : "Modo básico · datos de reservas") : "Datos reales de reservas";
}

// ---------------------------------------------------------------- envío
async function enviar(texto, repetir = false) {
  texto = (texto ?? campo.value).trim();
  if (!texto || ocupado) return;
  ocupado = true; enviarBtn.disabled = true;
  quitarSugerencias();
  cuerpo.querySelectorAll(".chat-fallo").forEach((n) => n.remove());
  if (!repetir) { cuerpo.append(burbuja("usuario", formatear(texto))); campo.value = ""; ajustarCampo(); }
  const espera = escribiendo(); cuerpo.append(espera); bajar();
  const previo = historial.slice(-MAX_TURNOS);
  try {
    const r = await api("/asistente/chat", { metodo: "POST", json: { mensaje: texto.slice(0, 400), historial: previo } });
    historial.push({ rol: "usuario", texto: texto.slice(0, 700) }, { rol: "asistente", texto: String(r.respuesta).slice(0, 700) });
    historial = historial.slice(-MAX_TURNOS * 2);
    if (estado && r.restantes != null) estado.restantes = r.restantes;
    espera.remove(); agregarBot(r); actualizarPie();
  } catch (err) {
    espera.remove();
    const aviso = burbuja("bot error chat-fallo", h("p", {}, navigator.onLine === false ? "Parece que no tienes internet. Cuando vuelva la conexión, inténtalo de nuevo." : (err?.message || "No pude responder ahora. Inténtalo de nuevo en un momento.")));
    cuerpo.append(aviso, h("div", { class: "chat-chips chat-fallo" }, h("button", { class: "chat-chip", type: "button", onclick: () => enviar(texto, true) }, "Intentar de nuevo")));
    bajar();
  } finally {
    ocupado = false; enviarBtn.disabled = !campo.value.trim();
    if (abierto) campo.focus({ preventScroll: true });
  }
}

function ajustarCampo() {
  campo.style.height = "auto";
  campo.style.height = `${Math.min(campo.scrollHeight, 112)}px`;
  enviarBtn.disabled = ocupado || !campo.value.trim();
}

function reiniciar() {
  historial = []; ocupado = false; bienvenida(); campo.focus();
}

// ---------------------------------------------------------------- abrir / cerrar
async function abrir() {
  if (abierto) return;
  abierto = true; panel.hidden = false; fab.setAttribute("aria-expanded", "true"); fab.classList.add("oculto");
  document.addEventListener("keydown", alTeclear);
  window.visualViewport?.addEventListener("resize", ajustarTeclado);
  requestAnimationFrame(() => campo.focus({ preventScroll: true }));
  bajar();
  if (!estado) {
    try { estado = await api("/asistente/chat/estado"); } catch { estado = { ia: false, limite_diario: 0, restantes: 0 }; }
    actualizarPie();
  }
}

function cerrar() {
  if (!abierto) return;
  abierto = false; panel.hidden = true; fab.setAttribute("aria-expanded", "false"); fab.classList.remove("oculto");
  document.removeEventListener("keydown", alTeclear);
  window.visualViewport?.removeEventListener("resize", ajustarTeclado);
  fab.focus({ preventScroll: true });
}
const alTeclear = (e) => { if (e.key === "Escape") cerrar(); };

// En celulares, cuando sale el teclado el panel se encoge para que el campo de texto no quede tapado.
function ajustarTeclado() {
  const vv = window.visualViewport;
  if (!panel || !vv) return;
  const teclado = innerWidth < 640 && vv.height < innerHeight * 0.8;
  panel.style.top = teclado ? `${vv.offsetTop + 8}px` : "";
  panel.style.bottom = teclado ? "auto" : "";
  panel.style.height = teclado ? `${vv.height - 16}px` : "";
  if (teclado) bajar();
}

// ---------------------------------------------------------------- API del módulo
export function montarChat(usuario) {
  if (panel) return;                                  // ya está montado
  nombre = usuario?.nombre_completo ?? "";
  subtitulo = h("span", { class: "chat-sub" }, "Datos reales de reservas");
  cuerpo = h("div", { class: "chat-cuerpo", role: "log", "aria-live": "polite", "aria-relevant": "additions" });
  campo = h("textarea", { class: "chat-campo", rows: "1", maxlength: "400", placeholder: "Escribe tu pregunta…", "aria-label": "Escribe tu pregunta para Ciudabot", enterkeyhint: "send",
    oninput: ajustarCampo, onkeydown: (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar(); } } });
  enviarBtn = h("button", { class: "chat-enviar", type: "submit", "aria-label": "Enviar mensaje", disabled: true }, icono("flecha", 20));
  pie = h("p", { class: "chat-pie" });

  panel = h("section", { class: "chat-panel", id: "chat-panel", role: "dialog", "aria-label": "Chat con Ciudabot", hidden: true },
    h("header", { class: "chat-cab" },
      h("span", { class: "chat-logo", "aria-hidden": "true" }, icono("chispa", 22)),
      h("div", { class: "chat-titulo" }, h("b", {}, "Ciudabot"), subtitulo),
      h("button", { class: "chat-ico", type: "button", title: "Nueva conversación", "aria-label": "Nueva conversación", onclick: reiniciar }, icono("editar", 18)),
      h("button", { class: "chat-ico", type: "button", title: "Cerrar chat", "aria-label": "Cerrar chat", onclick: cerrar }, icono("x", 18))),
    cuerpo,
    h("form", { class: "chat-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); enviar(); } }, campo, enviarBtn),
    pie);
  fab = h("button", { class: "chat-fab", type: "button", "aria-label": "Abrir chat con Ciudabot", "aria-expanded": "false", "aria-controls": "chat-panel", onclick: abrir },
    icono("chat", 26), h("span", { class: "chat-fab-texto" }, "Pregúntale a Ciudabot"));
  document.body.append(fab, panel);
  bienvenida(); actualizarPie();
}

export function quitarChat() {
  document.removeEventListener("keydown", alTeclear);
  window.visualViewport?.removeEventListener("resize", ajustarTeclado);
  fab?.remove(); panel?.remove();
  fab = panel = cuerpo = campo = enviarBtn = pie = subtitulo = null;
  historial = []; ocupado = false; abierto = false; estado = null; nombre = "";
}
