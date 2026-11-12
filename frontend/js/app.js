// Arranque de Ciudadela Digital: sesión, "shell" (menú + barra superior) y enrutador por hash.
import { api, sesion, cuandoExpire } from "./api.js";
import { h, icono, logo, toast, iniciales, vaciar, esqueleto, estadoVacio, botonTema } from "./ui.js";
import { vistaLogin } from "./vistas/login.js";
import { crearCampana, detenerCampana } from "./campana.js";
import { registrarServiceWorker } from "./instalar.js";

const A = "Administrador", R = "Residente", G = "Guardia";
// Cada ruta declara qué roles la ven: el menú se arma solo con lo permitido (la API igual valida con 403).
// `texto` puede variar por rol: el residente ve palabras de todos los días y el administrador, los nombres de oficina.
const RUTAS = [
  { id: "resumen", texto: "Inicio", icono: "grid", roles: [A, R, G], cargar: () => import("./vistas/resumen.js") },
  { id: "reservas", texto: "Reservas", icono: "calendario", roles: [A, R, G], cargar: () => import("./vistas/reservas.js") },
  { id: "paquetes", texto: { [R]: "Mis paquetes", otro: "Paquetes" }, icono: "caja", roles: [A, R, G], cargar: () => import("./vistas/paquetes.js") },
  { id: "cartera", texto: { [R]: "Mis pagos", otro: "Cartera" }, icono: "tarjeta", roles: [A, R], cargar: () => import("./vistas/cartera.js") },
  { id: "visitas", texto: { [R]: "Mis visitas", otro: "Visitas" }, icono: "identificacion", roles: [A, R], cargar: () => import("./vistas/visitas.js") },
  { id: "porteria", texto: "Portería", icono: "carro", roles: [A, G], cargar: () => import("./vistas/porteria.js") },
  { id: "mantenimiento", texto: { [R]: "Reportar un daño", otro: "Daños" }, icono: "llave", roles: [A, R], cargar: () => import("./vistas/mantenimiento.js") },
  { id: "pqrs", texto: { [R]: "Quejas y sugerencias", otro: "PQRS" }, icono: "mensaje", roles: [A, R], cargar: () => import("./vistas/pqrs.js") },
  { id: "anuncios", texto: "Cartelera", icono: "megafono", roles: [A, R, G], cargar: () => import("./vistas/anuncios.js") },
  { id: "comercio", texto: "Comercio", icono: "tienda", roles: [A, R], cargar: () => import("./vistas/comercio.js") },
  { id: "documentos", texto: "Documentos", icono: "archivo", roles: [A, R, G], cargar: () => import("./vistas/documentos.js") },
  { id: "emergencias", texto: "Emergencias", icono: "telefono", roles: [A, R, G], cargar: () => import("./vistas/emergencias.js") },
  { id: "auditoria", texto: "Auditoría", icono: "escudo", roles: [A], cargar: () => import("./vistas/auditoria.js") },
  { id: "residentes", texto: "Usuarios", icono: "usuarios", roles: [A], cargar: () => import("./vistas/residentes.js") },
  { id: "configuracion", texto: "Ajustes", icono: "ajustes", roles: [A, R, G], cargar: () => import("./vistas/configuracion.js"), menu: false },   // se abre desde el avatar
  { id: "mas", texto: "Más", icono: "mas", roles: [A, R, G], cargar: () => import("./vistas/mas.js"), menu: false },                                  // pantalla de todas las opciones
];
const etiqueta = (r, rol) => (typeof r.texto === "string" ? r.texto : r.texto[rol] ?? r.texto.otro);

// Barra inferior del celular: máximo 5 botones (4 + «Más»). Lo demás vive en «Más», con botones grandes.
const BARRA = {
  [R]: ["resumen", "reservas", "paquetes", "cartera"],
  [G]: ["resumen", "porteria", "paquetes", "emergencias"],
  [A]: ["resumen", "reservas", "cartera", "pqrs"],
};
// Enlaces de versiones anteriores que siguen funcionando.
const ALIAS = { qr: "visitas", visitantes: "visitas" };

const raiz = document.getElementById("app");
let usuario = null;
let turno = 0;

function mostrarLogin() {
  usuario = null;
  window.CiudadelaTema?.establecerRol("");       // el login siempre usa la identidad base (azul)
  detenerCampana();
  raiz.replaceChildren(vistaLogin(iniciar));
}

async function iniciar() {
  raiz.replaceChildren(h("div", { class: "arranque" }, h("div", { class: "spinner" })));
  try {
    usuario = await api("/usuarios/me");
  } catch {
    sesion.cerrar();
    return mostrarLogin();
  }
  window.CiudadelaTema?.establecerRol(usuario.rol);   // color del rol (admin azul · residente verde · guardia cobre)
  construirShell();
  navegar();
  precargarVistas();
  // Orden: primero la clave (si el administrador la restableció) y después la política de datos (solo la primera vez).
  const pedirPolitica = async () => { if (!usuario.politica_aceptada) { const { modalPolitica } = await import("./vistas/politica.js"); modalPolitica({ alAceptar: () => { usuario.politica_aceptada = true; } }); } };
  if (usuario.debe_cambiar_password) {
    const { modalCambiarClave } = await import("./vistas/clave.js");
    modalCambiarClave({ obligatorio: true, alCambiar: async () => { usuario = await api("/usuarios/me"); pedirPolitica(); } });
  } else pedirPolitica();
}

// Cuando el navegador está libre, baja en segundo plano las pantallas de la barra inferior: al tocarlas abren al instante.
function precargarVistas() {
  const libre = window.requestIdleCallback ?? ((f) => setTimeout(f, 1200));
  libre(() => {
    const ids = new Set(BARRA[usuario?.rol] ?? []);
    RUTAS.filter((r) => ids.has(r.id) && r.roles.includes(usuario?.rol)).forEach((r) => r.cargar().catch(() => {}));
  });
}

function cerrarSesion() { sesion.cerrar(); location.hash = ""; mostrarLogin(); }

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
      h("header", { class: "topbar" }, logo(false),
        h("div", { class: "topbar-acciones" }, crearCampana((ruta) => { location.hash = `#/${ruta}`; }), botonTema(),
        h("div", { class: "usuario-chip" },
          h("div", { class: "datos" }, h("b", {}, usuario.nombre_completo), h("span", { class: "rol-insignia" }, usuario.rol)),
          h("a", { class: "avatar avatar-enlace", href: "#/configuracion", title: "Configuración", "aria-label": "Abrir configuración" }, iniciales(usuario.nombre_completo)), salir))),
      h("main", { id: "contenido", tabindex: "-1" }))));
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
    vaciar(cont).append(h("div", { class: "centro" }, h("div", {},
      estadoVacio("No pudimos cargar esta sección", e.message),
      h("button", { class: "btn", style: "margin-top:1rem", onclick: navegar }, "Reintentar"))));
  }
}

let avisoExpiro = false;
cuandoExpire(() => {
  if (avisoExpiro) return;
  avisoExpiro = true;
  sesion.cerrar(); mostrarLogin();
  toast("Tu sesión expiró. Ingresa de nuevo.", "error");
  setTimeout(() => { avisoExpiro = false; }, 1000);
});

registrarServiceWorker();
addEventListener("hashchange", navegar);
sesion.token ? iniciar() : mostrarLogin();
