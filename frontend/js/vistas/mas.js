// "Más": todas las secciones en botones grandes, agrupadas, para quien no encuentra algo en la barra inferior.
import { h, icono } from "../ui.js";
import { cabecera } from "./comun.js";

const GRUPOS = [
  ["Mi día a día", ["visitas", "reservas", "paquetes", "cartera"]],
  ["Trámites", ["mantenimiento", "pqrs", "documentos"]],
  ["Comunidad", ["votaciones", "anuncios", "comercio", "emergencias"]],
  ["Administración", ["porteria", "residentes", "auditoria"]],
  ["Mi cuenta", ["configuracion"]],
];

export async function render(ctx) {
  const rutas = new Map(ctx.rutas.map((r) => [r.id, r]));
  const grupos = GRUPOS.map(([titulo, ids]) => [titulo, ids.map((id) => rutas.get(id)).filter(Boolean)]).filter(([, r]) => r.length);
  return h("div", {}, cabecera("Más opciones", "Toca lo que necesites."),
    ...grupos.map(([titulo, lista]) => h("section", { class: "mas-grupo" }, h("h2", {}, titulo),
      h("div", { class: "mas-rejilla" }, lista.map((r) => h("a", { class: "mas-tile", href: `#/${r.id}` }, icono(r.icono), h("span", {}, r.texto)))))),
    h("button", { class: "btn suave block mas-salir", onclick: ctx.salir }, icono("salir", 18), "Cerrar sesión"));
}
