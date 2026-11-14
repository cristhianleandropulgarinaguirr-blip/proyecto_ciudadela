// Arranque de Ciudadela Digital: sesión, "shell" (menú + barra superior) y enrutador por hash.
import { api, sesion, cuandoExpire, restaurarSesion, cerrarEnServidor, esErrorDeRed } from "./api.js";
import { borrarAutoTodos } from "./autoguardado.js";
import { h, icono, logo, toast, iniciales, vaciar, esqueleto, estadoVacio, botonTema, confirmar, modal } from "./ui.js";
import { vistaLogin } from "./vistas/login.js";
import { crearCampana, detenerCampana, actualizarCampana } from "./campana.js";
import { registrarServiceWorker } from "./instalar.js";
import { red } from "./red.js";
import { iniciarOffline, limpiarAlSalir, hayPendientes, alCambiarCola, sincronizar, conflictos, descartarConflictos } from "./offline.js";
import { reasociarPush, liberarPushAlSalir, soportaPush } from "./push.js";
import { avisoCamara } from "./foto.js";

const A = "Administrador", R = "Residente", G = "Guardia", I = "Inquilino";
// Cada ruta declara qué roles la ven: el menú se arma solo con lo permitido (la API igual valida con 403).
// `texto` puede variar por rol: el residente ve palabras de todos los días y el administrador, los nombres de oficina.
const RUTAS = [
  { id: "resumen", texto: "Inicio", icono: "grid", roles: [A, R, G, I], cargar: () => import("./vistas/resumen.js") },
  { id: "reservas", texto: "Reservas", icono: "calendario", roles: [A, R, G, I], cargar: () => import("./vistas/reservas.js") },
  { id: "paquetes", texto: { [R]: "Mis paquetes", [I]: "Mis paquetes", otro: "Paquetes" }, icono: "caja", roles: [A, R, G, I], cargar: () => import("./vistas/paquetes.js") },
  { id: "cartera", texto: { [R]: "Mis pagos", otro: "Cartera" }, icono: "tarjeta", roles: [A, R], cargar: () => import("./vistas/cartera.js") },
  { id: "votaciones", texto: "Votaciones", icono: "urna", roles: [A, R], cargar: () => import("./vistas/votaciones.js") },
  { id: "visitas", texto: { [R]: "Mis visitas", [I]: "Mis visitas", otro: "Visitas" }, icono: "identificacion", roles: [A, R, I], cargar: () => import("./vistas/visitas.js") },
  { id: "inquilinos", texto: { [A]: "Arrendamientos", otro: "Mis inquilinos" }, icono: "usuarios", roles: [A, R], cargar: () => import("./vistas/inquilinos.js") },
  { id: "porteria", texto: "Portería", icono: "carro", roles: [A, G], cargar: () => import("./vistas/porteria.js") },
  { id: "mantenimiento", texto: { [R]: "Reportar un daño", [I]: "Reportar un daño", otro: "Daños" }, icono: "llave", roles: [A, R, I], cargar: () => import("./vistas/mantenimiento.js") },
  { id: "pqrs", texto: { [R]: "Quejas y sugerencias", [I]: "Quejas y sugerencias", otro: "PQRS" }, icono: "mensaje", roles: [A, R, I], cargar: () => import("./vistas/pqrs.js") },
  { id: "anuncios", texto: "Cartelera", icono: "megafono", roles: [A, R, G, I], cargar: () => import("./vistas/anuncios.js") },
  { id: "comercio", texto: "Comercio", icono: "tienda", roles: [A, R, I], cargar: () => import("./vistas/comercio.js") },
  { id: "documentos", texto: "Documentos", icono: "archivo", roles: [A, R, G, I], cargar: () => import("./vistas/documentos.js") },
  { id: "emergencias", texto: "Emergencias", icono: "telefono", roles: [A, R, G, I], cargar: () => import("./vistas/emergencias.js") },
  { id: "auditoria", texto: "Auditoría", icono: "escudo", roles: [A], cargar: () => import("./vistas/auditoria.js") },
  { id: "residentes", texto: "Usuarios", icono: "usuarios", roles: [A], cargar: () => import("./vistas/residentes.js") },
  { id: "configuracion", texto: "Ajustes", icono: "ajustes", roles: [A, R, G, I], cargar: () => import("./vistas/configuracion.js"), menu: false },   // se abre desde el avatar
  { id: "mas", texto: "Más", icono: "apps", roles: [A, R, G, I], cargar: () => import("./vistas/mas.js"), menu: false },                                  // pantalla de todas las opciones
];
const etiqueta = (r, rol) => (typeof r.texto === "string" ? r.texto : r.texto[rol] ?? r.texto.otro);

// Barra inferior del celular: máximo 5 botones (4 + «Más»). Lo demás vive en «Más», con botones grandes.
const BARRA = {
  [R]: ["resumen", "reservas", "paquetes", "cartera"],
  [G]: ["resumen", "porteria", "paquetes", "emergencias"],
  [A]: ["resumen", "reservas", "cartera", "pqrs"],
  [I]: ["resumen", "reservas", "paquetes", "visitas"],
};
// Enlaces de versiones anteriores que siguen funcionando.
const ALIAS = { qr: "visitas", visitantes: "visitas" };

const raiz = document.getElementById("app");
const PERFIL = "ciudadela.perfil";       // copia mínima del perfil (id, nombre, rol) para poder abrir la portería sin internet
let usuario = null;
let turno = 0;
let sinConexion = false;                 // la app se abrió sin poder consultar al servidor (se usa el perfil guardado)

const guardarPerfil = (u) => { try { localStorage.setItem(PERFIL, JSON.stringify({ id: u.id, nombre_completo: u.nombre_completo, rol: u.rol, email: u.email, politica_aceptada: true, debe_cambiar_password: false })); } catch { /* nada */ } };
const leerPerfil = () => { try { return JSON.parse(localStorage.getItem(PERFIL) ?? "null"); } catch { return null; } };
const borrarPerfil = () => { try { localStorage.removeItem(PERFIL); } catch { /* nada */ } };

// Chat «Ciudabot» (v3.2): se descarga con la app ya abierta (en un momento libre) para no retrasar el arranque.
let chatMod = null;
function iniciarChat() {
  if (!usuario || usuario.rol === "Guardia") return;          // el guardia no tiene asistente; la API tampoco se lo permite
  const montar = () => import("./chat.js").then((m) => { chatMod = m; if (usuario) m.montarChat(usuario); }).catch(() => {});
  (window.requestIdleCallback ?? ((f) => setTimeout(f, 600)))(montar);
}

function mostrarLogin() {
  chatMod?.quitarChat();
  usuario = null;
  window.CiudadelaTema?.establecerRol("");       // el login siempre usa la identidad base (azul)
  detenerCampana();
  raiz.replaceChildren(vistaLogin(iniciar));
}

// El servidor no responde (internet caído o servidor gratuito despertando). La sesión NO se cierra: se reintenta solo.
function mostrarSinConexion() {
  const reintentar = () => { quitar(); arrancar(); };
  const quitar = red.alCambiar((en) => { if (en) reintentar(); });
  const t = setInterval(() => { if (!document.body.contains(pantalla)) clearInterval(t); else { clearInterval(t); reintentar(); } }, 8000);
  const pantalla = h("div", { class: "centro" }, h("div", { class: "sin-conexion" }, icono("sinred", 40),
    h("h2", {}, "Esperando conexión con el servidor"),
    h("p", { class: "muted" }, "Tu sesión sigue abierta. Si el servidor estaba dormido puede tardar hasta un minuto en despertar; lo intentamos de nuevo solo."),
    h("button", { class: "btn", onclick: () => { clearInterval(t); reintentar(); } }, "Reintentar ahora")));
  raiz.replaceChildren(pantalla);
}

// Abre la app: recupera la sesión (con la cookie de renovación) y distingue «no hay sesión» de «no hay internet».
async function arrancar() {
  raiz.replaceChildren(h("div", { class: "arranque" }, h("div", { class: "spinner" })));
  const r = await restaurarSesion();
  if (r === "sin-sesion") return mostrarLogin();
  if (r === "sin-red") {
    const perfil = leerPerfil();
    if (perfil) { usuario = perfil; sinConexion = true; return abrirApp(); }     // portería sin internet: se abre con el perfil guardado
    return mostrarSinConexion();
  }
  iniciar();
}

async function iniciar() {
  raiz.replaceChildren(h("div", { class: "arranque" }, h("div", { class: "spinner" })));
  try {
    usuario = await api("/usuarios/me");
    guardarPerfil(usuario); sinConexion = false;
  } catch (e) {
    if (esErrorDeRed(e) || e.status >= 500) {
      const perfil = leerPerfil();
      if (perfil) { usuario = perfil; sinConexion = true; return abrirApp(); }
      return mostrarSinConexion();
    }
    sesion.cerrar();                                  // solo un 401/403 real del servidor llega hasta aquí
    return mostrarLogin();
  }
  abrirApp();
}

async function abrirApp() {
  window.CiudadelaTema?.establecerRol(usuario.rol);   // color del rol (admin azul · residente teal · guardia ámbar · inquilino violeta)
  construirShell();
  iniciarChat();
  navegar();
  precargarVistas();
  iniciarOffline(usuario);
  avisoCamara();                                      // si el celular cerró la app mientras estaba la cámara, se explica qué pasó
  if (sinConexion) {
    red.fallo();
    const quitar = red.alCambiar(async (en) => {       // al volver internet se confirma el perfil en silencio, sin recargar la pantalla
      if (!en) return;
      quitar();
      try { usuario = await api("/usuarios/me"); guardarPerfil(usuario); sinConexion = false; reasociarPush(); } catch { /* se reintentará al abrir */ }
    });
    return;
  }
  reasociarPush();                                    // si este equipo ya tenía avisos activados, quedan a nombre de quien entró ahora
  sugerirAvisos();
  // Orden: primero la clave (si el administrador la restableció) y después la política de datos (solo la primera vez).
  const pedirPolitica = async () => { if (!usuario.politica_aceptada) { const { modalPolitica } = await import("./vistas/politica.js"); modalPolitica({ alAceptar: () => { usuario.politica_aceptada = true; } }); } };
  if (usuario.debe_cambiar_password) {
    const { modalCambiarClave } = await import("./vistas/clave.js");
    modalCambiarClave({ obligatorio: true, alCambiar: async () => { usuario = await api("/usuarios/me"); pedirPolitica(); } });
  } else pedirPolitica();
}

// Una sola vez por equipo: recuerda que existen los avisos en el celular (el permiso se pide en Ajustes, nunca de golpe).
function sugerirAvisos() {
  try {
    if (!soportaPush() || Notification.permission !== "default" || localStorage.getItem("ciudadela.pushSugerido")) return;
    localStorage.setItem("ciudadela.pushSugerido", "1");
    setTimeout(() => toast("Activa los avisos en Ajustes para enterarte de paquetes y votaciones aunque la app esté cerrada."), 5000);
  } catch { /* nada */ }
}

// Cuando el navegador está libre, baja en segundo plano las pantallas de la barra inferior: al tocarlas abren al instante.
function precargarVistas() {
  const libre = window.requestIdleCallback ?? ((f) => setTimeout(f, 1200));
  libre(() => {
    const ids = new Set(BARRA[usuario?.rol] ?? []);
    RUTAS.filter((r) => ids.has(r.id) && r.roles.includes(usuario?.rol)).forEach((r) => r.cargar().catch(() => {}));
  });
}

// Al salir: avisa si queda trabajo sin enviar, libera los avisos push de este equipo, revoca la sesión en el servidor y borra lo guardado.
async function cerrarSesion() {
  if (await hayPendientes()) {
    await sincronizar().catch(() => {});
    const quedan = await hayPendientes();
    if (quedan && !(await confirmar("Hay registros sin enviar", `Tienes ${quedan} registro(s) guardados en este equipo que aún no llegaron al servidor. Si cierras sesión se quedan guardados y se enviarán cuando vuelvas a ingresar con tu cuenta en este equipo. ¿Cerrar sesión?`, "Cerrar sesión", true))) return;
  }
  await liberarPushAlSalir();
  await cerrarEnServidor();
  chatMod?.quitarChat();                              // la conversación solo vive en memoria: se borra al salir
  borrarAutoTodos(); borrarPerfil(); await limpiarAlSalir(); sesion.cerrar();
  location.hash = ""; mostrarLogin();
}

function construirShell() {
  const permitidas = RUTAS.filter((r) => r.roles.includes(usuario.rol));
  const enlace = (r) => h("a", { href: `#/${r.id}`, "data-id": r.id }, icono(r.icono), h("span", {}, etiqueta(r, usuario.rol)));
  const porId = new Map(permitidas.map((r) => [r.id, r]));
  // Escritorio: menú lateral con todo. Celular: barra inferior con 4 botones + «Más».
  const lateral = h("nav", { class: "nav nav-lateral", "aria-label": "Principal" }, permitidas.filter((r) => r.menu !== false).map(enlace));
  const inferior = h("nav", { class: "nav nav-inferior", "aria-label": "Principal" },
    (BARRA[usuario.rol] ?? []).map((id) => porId.get(id)).filter(Boolean).map(enlace), enlace(porId.get("mas")));

  const salir = h("button", { class: "btn suave icono", "aria-label": "Cerrar sesión", title: "Cerrar sesión", onclick: cerrarSesion }, icono("salir"));
  raiz.replaceChildren(h("div", { class: "shell" },
    h("aside", { class: "sidebar" }, logo(true), lateral, inferior),
    h("div", { class: "main" },
      crearBanner(),
      h("header", { class: "topbar" }, logo(false),
        h("div", { class: "topbar-acciones" }, crearCampana((ruta) => { location.hash = `#/${ruta}`; }), botonTema(),
        h("div", { class: "usuario-chip" },
          h("div", { class: "datos" }, h("b", {}, usuario.nombre_completo), h("span", { class: "rol-insignia" }, usuario.rol)),
          h("a", { class: "avatar avatar-enlace", href: "#/configuracion", title: "Configuración", "aria-label": "Abrir configuración" }, iniciales(usuario.nombre_completo)), salir))),
      h("main", { id: "contenido", tabindex: "-1" }))));
}

// Franja de estado de la conexión: sin internet, registros por enviar y registros que el servidor rechazó.
function crearBanner() {
  const banner = h("div", { class: "banner-red", role: "status", "aria-live": "polite", hidden: true });
  let n = 0, f = 0;
  async function pintar() {
    const malos = (await conflictos()).length;
    const partes = [];
    if (!red.enLinea) partes.push(h("span", { class: "txt" }, icono("sinred", 16), `Sin conexión${n ? ` · ${n} registro(s) por enviar` : ""}. Lo que registres se guarda en este equipo y se envía solo.`));
    else if (n || f) partes.push(h("span", { class: "txt" }, `Enviando ${n + f} pendiente(s)…`), h("button", { class: "btn suave sm", onclick: () => sincronizar() }, "Enviar ahora"));
    if (malos) partes.push(h("button", { class: "btn suave sm", onclick: verRechazados }, `${malos} registro(s) no se aceptaron`));
    banner.replaceChildren(...partes); banner.hidden = !partes.length;
    banner.classList.toggle("sin-red", !red.enLinea);
  }
  async function verRechazados() {
    const lista = await conflictos();
    const m = modal("Registros que el servidor no aceptó", h("div", {}, h("p", { class: "muted", style: "margin-bottom:.8rem" }, "Se hicieron sin internet, pero al enviarlos el servidor los rechazó (por ejemplo, porque otra persona ya lo había registrado). No se repiten solos."),
      ...lista.map((c) => h("div", { class: "item" }, h("div", { class: "cuerpo" }, h("b", {}, c.resumen || c.tipo), h("span", {}, c.mensaje))))),
    { pie: [h("button", { class: "btn", onclick: async () => { await descartarConflictos(); m.cerrar(); pintar(); } }, "Entendido")] });
  }
  alCambiarCola((nn, ff) => { n = nn; f = ff; pintar(); });
  red.alCambiar(() => pintar());
  addEventListener("ciudadela:sincronizado", pintar);
  pintar();
  return banner;
}

async function navegar() {
  if (!usuario) return;
  const permitidas = RUTAS.filter((r) => r.roles.includes(usuario.rol));
  const pedido = location.hash.replace("#/", "");
  const id = ALIAS[pedido] ?? pedido;
  const ruta = permitidas.find((r) => r.id === id) ?? permitidas.find((r) => r.menu !== false);
  if (pedido !== ruta.id) { location.replace(`#/${ruta.id}`); return; }   // normaliza enlaces viejos (#/qr → #/visitas)

  // En la barra inferior, «Más» se marca cuando la pantalla actual no tiene botón propio.
  const enBarra = (BARRA[usuario.rol] ?? []).includes(ruta.id);
  document.querySelectorAll(".nav-lateral a").forEach((a) => (a.dataset.id === ruta.id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  document.querySelectorAll(".nav-inferior a").forEach((a) => ((a.dataset.id === ruta.id || (a.dataset.id === "mas" && !enBarra)) ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));

  const cont = document.getElementById("contenido");
  const mio = ++turno;
  vaciar(cont).append(esqueleto(110, 4));
  try {
    const ctx = { usuario, ir: (r) => { location.hash = `#/${r}`; }, recargar: navegar, salir: cerrarSesion,
      rutas: permitidas.filter((r) => r.id !== "resumen" && r.id !== "mas").map((r) => ({ id: r.id, icono: r.icono, texto: etiqueta(r, usuario.rol) })),
      actualizarUsuario: async () => { usuario = await api("/usuarios/me"); return usuario; } };
    const modulo = await ruta.cargar();
    if (mio !== turno) return;
    const nodo = await modulo.render(ctx);
    if (mio !== turno) return;           // el usuario ya navegó a otra pantalla
    nodo.classList.add("vista");
    vaciar(cont).append(nodo);
    window.scrollTo({ top: 0 });
  } catch (e) {
    if (mio !== turno) return;
    if (esErrorDeRed(e) && ruta.id === "resumen" && usuario.rol === G) { location.replace("#/porteria"); return; }   // sin internet, la portería abre directo en lo que sí funciona
    vaciar(cont).append(h("div", { class: "centro" }, h("div", {},
      estadoVacio("No pudimos cargar esta sección", e.message),
      h("button", { class: "btn", style: "margin-top:1rem", onclick: navegar }, "Reintentar"))));
  }
}

let avisoExpiro = false;
cuandoExpire(() => {
  if (avisoExpiro) return;
  avisoExpiro = true;
  borrarPerfil(); sesion.cerrar(); limpiarAlSalir(); mostrarLogin();
  toast("Tu sesión expiró. Ingresa de nuevo.", "error");
  setTimeout(() => { avisoExpiro = false; }, 1000);
});

// Mensajes del service worker: tocar un aviso push lleva a su pantalla; un aviso con la app abierta refresca la campana.
navigator.serviceWorker?.addEventListener("message", (e) => {
  const m = e.data ?? {};
  if (m.tipo === "ir" && typeof m.enlace === "string" && usuario) location.hash = m.enlace.startsWith("#") ? m.enlace : `#/${m.enlace}`;
  else if (m.tipo === "push") actualizarCampana();
  else if (m.tipo === "resuscribir") reasociarPush();
});

registrarServiceWorker();
addEventListener("hashchange", navegar);
sesion.posible ? arrancar() : mostrarLogin();
