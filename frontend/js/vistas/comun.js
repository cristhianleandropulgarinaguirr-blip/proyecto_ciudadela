// Piezas compartidas entre vistas.
import { h } from "../ui.js";

export function cabecera(titulo, texto, { saludo } = {}) {
  return h("div", { class: "pagina-cab" },
    saludo ? h("div", { class: "saludo" }, saludo) : null,
    h("h1", {}, titulo), texto ? h("p", {}, texto) : null);
}
export const hoyLargo = () => new Date().toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });
export const mapaUsuarios = (lista) => new Map(lista.map((u) => [u.id, u]));
export const nombreDe = (mapa, id) => mapa.get(id)?.nombre_completo ?? `Residente #${id}`;

export function filtros(opciones, inicial, alCambiar) {
  const caja = h("div", { class: "chips", role: "group" });
  const pintar = (sel) => caja.replaceChildren(...opciones.map((o) =>
    h("button", { class: "chip", type: "button", "aria-pressed": String(o.id === sel), onclick: () => { pintar(o.id); alCambiar(o.id); } },
      o.texto, o.n != null ? h("span", { class: "n" }, o.n) : null)));
  pintar(inicial);
  return caja;
}

// Fecha en formato "bloque" (día grande + mes) usada en reservas.
export function bloqueFecha(d) {
  return h("div", { class: "fecha" }, h("b", {}, d.getDate()), h("span", {}, d.toLocaleDateString("es-CO", { month: "short" }).replace(".", "")));
}
