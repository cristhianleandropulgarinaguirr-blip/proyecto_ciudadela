// Solicitudes de demo (solo administrador, v4.0): los contactos que llegan desde «Solicitar demo» de la landing.
// Endpoints: GET /demo/solicitudes · PATCH /demo/solicitudes/{id}
// Esta pantalla solo aparece si la landing está activa (LANDING_ACTIVA=1): en la app de un cliente ya contratado no hace falta.
import { api } from "../api.js";
import { h, icono, estadoVacio, toast, conCarga, modal, deUtc, hace, kpi } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const ESTADOS = ["Nueva", "Contactada", "Agendada", "Descartada"];
const CLASE = { Nueva: "arcilla", Contactada: "laton", Agendada: "bosque", Descartada: "borde" };
const insignia = (estado) => h("span", { class: `badge ${CLASE[estado] ?? ""}` }, estado);
const enlaceWhatsApp = (celular, nombre) => `https://wa.me/57${celular}?text=${encodeURIComponent(`Hola ${nombre}, te escribimos por la demostración que pediste.`)}`;
const telefono = (c) => `${c.slice(0, 3)} ${c.slice(3, 6)} ${c.slice(6)}`;

export async function render() {
  let datos = await api("/demo/solicitudes"), filtro = "Nueva";
  const lista = h("div", { class: "lista" }), resumen = h("div", { class: "kpis" });
  let chips = h("div");
  const n = (e) => (e === "todas" ? datos.length : datos.filter((s) => s.estado === e).length);
  async function recargar() { datos = await api("/demo/solicitudes"); pintar(); }

  function gestionar(s) {
    const estado = h("select", { id: "dm-estado" }, ESTADOS.map((e) => h("option", { value: e, selected: e === s.estado }, e)));
    const nota = h("textarea", { id: "dm-nota", placeholder: " ", maxlength: "300" }); nota.value = s.nota ?? "";
    const guardar = h("button", { class: "btn", type: "submit", form: "f-demo" }, "Guardar");
    const m = modal(`${s.conjunto}`, h("form", { id: "f-demo", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      try {
        await conCarga(guardar, () => api(`/demo/solicitudes/${s.id}`, { metodo: "PATCH", json: { estado: estado.value, nota: nota.value.trim() || null } }));
        m.cerrar(); toast("Seguimiento guardado."); await recargar();
      } catch (err) { toast(err.message, "error"); }
    } },
      h("p", { class: "muted small", style: "margin-bottom:1rem" }, `${s.nombre} · ${telefono(s.celular)}`),
      h("div", { class: "field" }, estado, h("label", { for: "dm-estado" }, "Estado")),
      h("div", { class: "field" }, nota, h("label", { for: "dm-nota" }, "Nota de seguimiento (solo la ve la administración)"))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
  }

  function fila(s) {
    const detalle = [s.ciudad, s.apartamentos ? `${s.apartamentos} apartamentos` : null, s.origen === "whatsapp" ? "Desde WhatsApp" : null].filter(Boolean).join(" · ");
    return h("article", { class: "item" },
      h("div", { class: "cuerpo" },
        h("b", {}, s.conjunto),
        h("span", {}, `${s.nombre} · ${telefono(s.celular)}${s.correo ? ` · ${s.correo}` : ""}`),
        detalle ? h("span", { class: "small muted" }, detalle) : null,
        s.mensaje ? h("span", { class: "texto-largo" }, s.mensaje) : null,
        s.nota ? h("span", { class: "small" }, `Nota: ${s.nota}`) : null,
        h("span", { class: "small muted" }, hace(deUtc(s.fecha_creacion)))),
      h("div", { class: "acciones" },
        insignia(s.estado),
        h("a", { class: "btn suave sm", href: enlaceWhatsApp(s.celular, s.nombre), target: "_blank", rel: "noopener noreferrer", "aria-label": `Escribir por WhatsApp a ${s.nombre}` }, icono("mensaje", 16), "WhatsApp"),
        h("a", { class: "btn suave sm", href: `tel:+57${s.celular}`, "aria-label": `Llamar a ${s.nombre}` }, icono("telefono", 16), "Llamar"),
        h("button", { class: "btn suave sm", onclick: () => gestionar(s) }, icono("editar", 16), "Gestionar")));
  }

  function pintar() {
    resumen.replaceChildren(kpi("Nuevas", n("Nueva"), { destacado: true, alerta: true }), kpi("Contactadas", n("Contactada")), kpi("Agendadas", n("Agendada")));
    chips.replaceWith((chips = filtros([{ id: "Nueva", texto: "Nuevas", n: n("Nueva") }, { id: "Contactada", texto: "Contactadas", n: n("Contactada") }, { id: "Agendada", texto: "Agendadas", n: n("Agendada") },
      { id: "Descartada", texto: "Descartadas", n: n("Descartada") }, { id: "todas", texto: "Todas", n: n("todas") }], filtro, (f) => { filtro = f; pintar(); })));
    const v = datos.filter((s) => filtro === "todas" || s.estado === filtro);
    lista.replaceChildren(...(v.length ? v.map(fila) : [estadoVacio("Sin solicitudes en esta vista", "Cuando alguien pida una demostración desde la landing, aparecerá aquí y te llegará un aviso.")]));
  }

  pintar();
  return h("div", {}, cabecera("Solicitudes de demo", "Las personas que pidieron una demostración desde la página principal."),
    h("div", { class: "escalona" }, resumen, h("div", { class: "card" }, h("div", { style: "margin-bottom:1rem" }, chips), lista)));
}
