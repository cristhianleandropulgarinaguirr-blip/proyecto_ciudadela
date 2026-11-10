// La campana de notificaciones de la barra superior.
// Endpoints: GET /notificaciones/conteo (cada minuto) · GET /notificaciones/ · POST /notificaciones/{id}/leer · POST /notificaciones/leer-todas
import { api } from "./api.js";
import { h, icono, modal, toast, deUtc, hace, estadoVacio } from "./ui.js";

let reloj = null;

export function detenerCampana() { clearInterval(reloj); reloj = null; }

export function crearCampana(ir) {
  const burbuja = h("span", { class: "burbuja", hidden: true });
  const boton = h("button", { class: "btn suave icono campana", type: "button", "aria-label": "Notificaciones", title: "Notificaciones" }, icono("campana"), burbuja);

  const pintarConteo = (n) => {
    burbuja.hidden = n === 0; burbuja.textContent = n > 9 ? "9+" : String(n);
    boton.setAttribute("aria-label", n ? `Notificaciones: ${n} sin leer` : "Notificaciones");
  };
  const refrescar = async () => { try { pintarConteo((await api("/notificaciones/conteo")).no_leidas); } catch { /* sin red: se reintenta en el siguiente ciclo */ } };

  boton.onclick = async () => {
    const lista = h("div", { class: "lista notificaciones" });
    const m = modal("Notificaciones", lista);
    let datos = [];
    const pintar = () => lista.replaceChildren(...(datos.length ? datos.map((n) => h("button", { class: `notif ${n.leida ? "leida" : ""}`, type: "button", onclick: async () => {
      if (!n.leida) { try { await api(`/notificaciones/${n.id}/leer`, { metodo: "POST" }); n.leida = true; refrescar(); } catch { /* no bloquea la navegación */ } }
      m.cerrar(); if (n.enlace) ir(n.enlace.replace(/^#\/?/, ""));
    } }, h("span", { class: "punto", "aria-hidden": "true" }), h("span", { class: "txt" }, h("b", {}, n.titulo), n.mensaje ? h("span", {}, n.mensaje) : null, h("small", {}, hace(deUtc(n.fecha)))))) : [estadoVacio("Sin notificaciones", "Aquí verás avisos de paquetes, PQRS, reservas, anuncios y documentos.")]));
    try {
      datos = await api("/notificaciones/", { params: { limite: 30 } });
      pintar();
      if (datos.some((n) => !n.leida)) lista.before(h("button", { class: "btn suave sm", type: "button", style: "margin-bottom:.8rem", onclick: async (e) => {
        try { await api("/notificaciones/leer-todas", { metodo: "POST" }); datos.forEach((n) => (n.leida = true)); pintar(); pintarConteo(0); e.currentTarget.remove(); } catch (err) { toast(err.message, "error"); }
      } }, icono("ok", 16), "Marcar todas como leídas"));
    } catch (err) { m.cerrar(); toast(err.message, "error"); }
  };

  detenerCampana();
  refrescar();
  reloj = setInterval(() => { if (!document.hidden) refrescar(); }, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && reloj) refrescar(); });
  return boton;
}
