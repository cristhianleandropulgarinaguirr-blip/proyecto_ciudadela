// Mis visitas: todo lo de «va a llegar alguien» en un solo lugar.
//   Hoy · Frecuentes · Con vehículo · Mi carnet
// Endpoints: GET/POST /visitantes-autorizados/ · DELETE /visitantes-autorizados/{id} (+ los de qr.js y visitantes.js)
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga } from "../ui.js";
import { cabecera } from "./comun.js";
import { render as vistaFrecuentes } from "./visitantes.js";
import { pestanaCarnet, pestanaVehiculo } from "./qr.js";

const hoyISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };

// Visita de un solo día: se autoriza «hasta hoy» y se vence sola a la medianoche.
async function pestanaHoy() {
  const hoy = hoyISO();
  const lista = h("div", { class: "lista" });
  const nombre = h("input", { id: "vh-nombre", placeholder: " ", maxlength: "60", autocomplete: "off" });
  const doc = h("input", { id: "vh-doc", class: "mono", placeholder: " ", maxlength: "20", autocomplete: "off", spellcheck: "false", inputmode: "text" });
  const boton = h("button", { class: "btn block", type: "submit" }, icono("ok", 18), "Autorizar para hoy");

  async function cargar() {
    const todos = await api("/visitantes-autorizados/");
    const deHoy = todos.filter((v) => v.vigente_hasta === hoy && v.notas === "Visita de hoy");
    lista.replaceChildren(...(deHoy.length ? deHoy.map((v) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("identificacion")),
      h("div", { class: "cuerpo" }, h("b", {}, v.nombre), h("span", {}, `Cédula ${v.documento} · vale hasta las 11:59 p. m.`)),
      h("div", { class: "acciones" }, v.dentro ? badge("Dentro", "Ya está dentro") : null,
        h("button", { class: "btn peligro sm", onclick: async () => { try { await api(`/visitantes-autorizados/${v.id}`, { metodo: "DELETE" }); toast("Visita cancelada"); await cargar(); } catch (e) { toast(e.message, "error"); } } }, "Quitar"))))
      : [estadoVacio("Sin visitas para hoy", "Cuando autorices a alguien, aparecerá aquí.")]));
  }

  const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (nombre.value.trim().length < 3) return toast("Escribe el nombre de tu visita.", "error");
    if (!/^[A-Za-z0-9]{5,15}$/.test(doc.value.replace(/[\s.\-]/g, ""))) return toast("Escribe la cédula de tu visita (mínimo 5 números).", "error");
    try {
      await conCarga(boton, () => api("/visitantes-autorizados/", { metodo: "POST", json: { nombre: nombre.value.trim(), documento: doc.value, tipo: "Amigo", vigente_hasta: hoy, notas: "Visita de hoy" } }));
      toast("Listo. Portería ya puede dejarlo pasar hoy."); nombre.value = ""; doc.value = ""; await cargar();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "card-titulo" }, h("h2", {}, "¿Quién viene hoy?")),
    h("p", { class: "muted small", style: "margin-bottom:1rem" }, "Funciona solo por hoy y se vence sola a la medianoche. Pídele a tu visita que lleve su cédula."),
    h("div", { class: "field" }, nombre, h("label", { for: "vh-nombre" }, "Nombre de tu visita")),
    h("div", { class: "field" }, doc, h("label", { for: "vh-doc" }, "Cédula")), boton);
  await cargar();
  return h("div", { class: "grid dos escalona" }, form, h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Autorizadas para hoy")), lista));
}

const PESTANAS = [["hoy", "Hoy"], ["frecuentes", "Frecuentes"], ["vehiculo", "Vehículo"], ["carnet", "Mi carnet"]];

export async function render(ctx) {
  const panel = h("div"), tabs = h("div", { class: "tabs", role: "tablist" });
  let actual = "hoy";
  async function mostrar(cual) {
    actual = cual;
    tabs.replaceChildren(...PESTANAS.map(([id, t]) => h("button", { class: "tab", role: "tab", "aria-selected": String(id === actual), onclick: () => id !== actual && mostrar(id) }, t)));
    panel.replaceChildren(h("div", { class: "esq", style: "height:200px" }));
    try {
      const nodo = cual === "hoy" ? await pestanaHoy() : cual === "frecuentes" ? await vistaFrecuentes(ctx, { sinCabecera: true })
        : cual === "vehiculo" ? await pestanaVehiculo(ctx) : await pestanaCarnet(ctx);
      if (cual === actual) panel.replaceChildren(nodo);
    } catch (e) { toast(e.message, "error"); }
  }
  await mostrar("hoy");
  return h("div", {}, cabecera("Mis visitas", "¿Va a llegar alguien? Autorízalo aquí para que portería lo deje pasar."), tabs, panel);
}
