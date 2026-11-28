// La campana de notificaciones de la barra superior.
// Endpoints: GET /notificaciones/conteo (cada minuto) · GET /notificaciones/ · POST /notificaciones/{id}/leer · POST /notificaciones/leer-todas
//   v5.7 · «leída» NO es «gestionada»: POST /notificaciones/{id}/gestionar · POST /notificaciones/{id}/pendiente
//   Un aviso que pide una acción (aprobar, responder, recoger…) sigue «por gestionar» aunque se abra, hasta que se gestione a mano
//   o hasta que se resuelva lo que pedía. La campana lo recuerda con una burbuja ámbar aparte de la roja (sin leer).
import { api } from "./api.js";
import { h, icono, modal, toast, deUtc, hace, estadoVacio } from "./ui.js";

let reloj = null;
let alVolver = null;                    // único oyente de «volví a la app»: se quita al detener, así no se acumulan al cerrar e iniciar sesión
let alPedirAbrir = null;                // oyente de «abrir las notificaciones» (lo usa la tarjeta de Inicio)
let refrescarExterno = null;
let abrirLista = null;
/** La app lo llama cuando llega un aviso push mientras está abierta. */
export const actualizarCampana = () => refrescarExterno?.();
/** Abre la lista de notificaciones desde cualquier pantalla. `filtro`: "todas" | "por" (por gestionar) | "hechas" (gestionadas). */
export const abrirNotificaciones = (filtro = "todas") => abrirLista?.(filtro);

export function detenerCampana() {
  clearInterval(reloj); reloj = null;
  if (alVolver) { document.removeEventListener("visibilitychange", alVolver); alVolver = null; }
  if (alPedirAbrir) { document.removeEventListener("abrir-notificaciones", alPedirAbrir); alPedirAbrir = null; }
  abrirLista = null;
  try { navigator.clearAppBadge?.(); } catch { /* nada */ }
}

const FILTROS = [["todas", "Todas"], ["por", "Por gestionar"], ["hechas", "Gestionadas"]];
const estadoDe = (n) => n.estado_gestion ?? "informativa";
const CUMPLE = { todas: () => true, por: (n) => estadoDe(n) === "por_gestionar", hechas: (n) => estadoDe(n) === "gestionada" };

/** Etiqueta del estado de un aviso. Lleva ícono y TEXTO, no solo color: se entiende igual sin distinguir colores. */
export function etiquetaGestion(n) {
  const e = estadoDe(n);
  if (e === "por_gestionar") return h("span", { class: "gestion-chip por" }, icono("alerta", 14), "Por gestionar");
  if (e === "gestionada") return h("span", { class: "gestion-chip hecha" }, icono("ok", 14), "Gestionada");
  return null;
}

export function crearCampana(ir) {
  const burbuja = h("span", { class: "burbuja", hidden: true });
  const pendiente = h("span", { class: "burbuja pendiente", hidden: true, "aria-hidden": "true" });
  const boton = h("button", { class: "btn suave icono campana", type: "button", "aria-label": "Notificaciones", title: "Notificaciones" }, icono("campana"), burbuja, pendiente);

  const pintarConteo = ({ no_leidas: n = 0, por_gestionar: g = 0 } = {}) => {
    burbuja.hidden = n === 0; burbuja.textContent = n > 9 ? "9+" : String(n);
    pendiente.hidden = g === 0; pendiente.textContent = g > 9 ? "9+" : String(g);
    boton.classList.toggle("tiene-pendientes", g > 0);
    const partes = [n ? `${n} sin leer` : "", g ? `${g} por gestionar` : ""].filter(Boolean);
    const texto = partes.length ? `Notificaciones: ${partes.join(", ")}` : "Notificaciones";
    boton.setAttribute("aria-label", texto); boton.title = texto;
    // La insignia del ícono de la app muestra lo que todavía necesita atención (lo mayor entre sin leer y por gestionar).
    try { Math.max(n, g) ? navigator.setAppBadge?.(Math.max(n, g)) : navigator.clearAppBadge?.(); } catch { /* el navegador no soporta insignias */ }
  };
  const refrescar = async () => { try { pintarConteo(await api("/notificaciones/conteo")); } catch { /* sin red: se reintenta en el siguiente ciclo */ } };

  abrirLista = async (filtroInicial = "todas") => {
    const lista = h("div", { class: "lista notificaciones" });
    const chips = h("div", { class: "chips", role: "group", "aria-label": "Filtrar avisos" });
    const acciones = h("div", { class: "notif-barra" });
    const m = modal("Notificaciones", h("div", {}, chips, acciones, lista));
    let datos = [], filtro = FILTROS.some(([id]) => id === filtroInicial) ? filtroInicial : "todas";

    const marcar = async (n, ruta) => {
      try { Object.assign(n, await api(`/notificaciones/${n.id}/${ruta}`, { metodo: "POST" })); pintar(); refrescar(); }
      catch (err) { toast(err.message, "error"); }
    };

    function fila(n) {
      const estado = estadoDe(n);
      const principal = h("button", { class: `notif ${n.leida ? "leida" : ""}`, type: "button", onclick: async () => {
        // Abrir el aviso lo marca como leído, pero NO como gestionado: si pedía una acción, sigue «por gestionar».
        if (!n.leida) { try { await api(`/notificaciones/${n.id}/leer`, { metodo: "POST" }); n.leida = true; refrescar(); } catch { /* no bloquea la navegación */ } }
        m.cerrar(); if (n.enlace) ir(n.enlace.replace(/^#\/?/, ""));
      } }, h("span", { class: "punto", "aria-hidden": "true" }),
        h("span", { class: "txt" }, h("b", {}, n.titulo), n.mensaje ? h("span", {}, n.mensaje) : null, h("small", {}, hace(deUtc(n.fecha)))));
      if (estado === "informativa") return principal;
      return h("div", { class: `notif-fila ${estado === "por_gestionar" ? "por-gestionar" : "gestionada"}` }, principal,
        h("div", { class: "notif-gestion" }, etiquetaGestion(n),
          estado === "por_gestionar"
            ? h("button", { class: "btn suave sm", type: "button", onclick: () => marcar(n, "gestionar") }, icono("ok", 16), "Marcar como gestionada")
            : h("button", { class: "btn-enlace sm", type: "button", onclick: () => marcar(n, "pendiente") }, "Volver a pendiente")));
    }

    function pintar() {
      const porGestionar = datos.filter(CUMPLE.por).length;
      chips.replaceChildren(...FILTROS.map(([id, texto]) => h("button", { class: "chip", type: "button", "aria-pressed": String(id === filtro),
        onclick: () => { filtro = id; pintar(); } }, texto, id === "por" && porGestionar ? h("span", { class: "n" }, porGestionar) : null)));
      const visibles = datos.filter(CUMPLE[filtro]);
      lista.replaceChildren(...(visibles.length ? visibles.map(fila) : [
        filtro === "por" ? estadoVacio("Nada por gestionar", "Estás al día. Aquí aparecerán los avisos que esperan una acción tuya.")
          : filtro === "hechas" ? estadoVacio("Aún no hay avisos gestionados", "Cuando gestiones un aviso (o se resuelva solo), lo verás aquí.")
            : estadoVacio("Sin notificaciones", "Aquí verás avisos de paquetes, PQRS, reservas, anuncios y documentos.")]));
      acciones.replaceChildren(...(datos.some((n) => !n.leida) ? [h("button", { class: "btn suave sm", type: "button", onclick: async () => {
        try {
          await api("/notificaciones/leer-todas", { metodo: "POST" }); datos.forEach((n) => (n.leida = true)); pintar(); refrescar();
          if (porGestionar) toast(`Todas quedaron leídas. Te ${porGestionar === 1 ? "queda 1 aviso" : `quedan ${porGestionar} avisos`} por gestionar.`);
        } catch (err) { toast(err.message, "error"); }
      } }, icono("ok", 16), "Marcar todas como leídas")] : []));
    }

    try {
      datos = await api("/notificaciones/", { params: { limite: 50 } });
      pintar();
    } catch (err) { m.cerrar(); toast(err.message, "error"); }
  };
  boton.onclick = () => abrirLista("todas");

  detenerCampana();
  refrescarExterno = refrescar;
  alPedirAbrir = (e) => abrirNotificaciones(e.detail?.filtro);
  document.addEventListener("abrir-notificaciones", alPedirAbrir);
  refrescar();
  reloj = setInterval(() => { if (!document.hidden) refrescar(); }, 60000);
  alVolver = () => { if (!document.hidden && reloj) refrescar(); };
  document.addEventListener("visibilitychange", alVolver);
  return boton;
}

/** Tarjeta de Inicio: lo que sigue por gestionar, para que no se pierda aunque ya se hayan abierto los avisos. `null` si no hay nada pendiente. */
export async function tarjetaPorGestionar() {
  let pendientes = [];
  try { pendientes = await api("/notificaciones/", { params: { gestion: "por_gestionar", limite: 5 } }); } catch { return null; }
  if (!pendientes.length) return null;
  return h("section", { class: "card por-gestionar-tarjeta", "aria-label": "Avisos por gestionar" },
    h("div", { class: "card-titulo" }, h("h2", {}, icono("alerta", 20), pendientes.length === 1 ? "Tienes 1 aviso por gestionar" : "Tienes avisos por gestionar"),
      h("button", { class: "btn suave sm", type: "button", onclick: () => abrirNotificaciones("por") }, "Ver todos")),
    h("div", { class: "lista" }, pendientes.map((n) => h("a", { class: "item", href: n.enlace || "#/", "aria-label": `${n.titulo}. Por gestionar` },
      h("div", { class: "cuerpo" }, h("b", {}, n.titulo), n.mensaje ? h("span", { class: "small muted" }, n.mensaje) : null),
      etiquetaGestion(n)))));
}
