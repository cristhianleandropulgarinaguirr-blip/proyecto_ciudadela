// Política de tratamiento de datos (Ley 1581 de 2012). Se muestra una vez, al primer ingreso, y no se puede cerrar sin responder.
// Endpoint: POST /auth/aceptar-politica-datos
import { api } from "../api.js";
import { h, modal, toast, conCarga } from "../ui.js";

// IMPORTANTE: es un texto base. Antes de operar con residentes reales, el conjunto debe ajustarlo (nombre del responsable,
// canal de contacto) y validarlo con su asesor jurídico.
const PUNTOS = [
  ["¿Qué datos guardamos?", "Tu nombre, correo, apartamento, saldo de administración, reservas, reportes, paquetes y, si autorizas visitantes, su nombre y documento."],
  ["¿Para qué?", "Solo para administrar el conjunto: reservas, cartera, portería, paquetes y comunicación con los residentes."],
  ["¿Quién los ve?", "La administración y la portería, y solo lo necesario para su trabajo. Otros residentes no ven tu saldo ni tus datos personales."],
  ["Tus derechos", "Puedes conocer, actualizar y corregir tus datos, pedir que se eliminen y retirar tu autorización escribiendo a la administración."],
  ["Si autorizas a otra persona", "Asegúrate de que sabe que registraste su nombre y documento en la portería del conjunto."],
];

export function modalPolitica({ alAceptar } = {}) {
  const acepto = h("input", { id: "pol-acepto", type: "checkbox" });
  const boton = h("button", { class: "btn", type: "button", disabled: true }, "Aceptar y continuar");
  acepto.addEventListener("change", () => { boton.disabled = !acepto.checked; });
  const m = modal("Tus datos y tu privacidad", h("div", { class: "politica" },
    h("p", { class: "muted", style: "margin-bottom:1rem" }, "Antes de empezar, cuéntanos si estás de acuerdo con cómo cuidamos tu información."),
    ...PUNTOS.map(([t, x]) => h("div", { class: "pol-punto" }, h("b", {}, t), h("p", {}, x))),
    h("label", { class: "pol-check", for: "pol-acepto" }, acepto, h("span", {}, "He leído y acepto el tratamiento de mis datos personales."))),
  { pie: [boton] });
  boton.onclick = async () => {
    try { await conCarga(boton, () => api("/auth/aceptar-politica-datos", { metodo: "POST" })); m.cerrar(); alAceptar?.(); }
    catch (e) { toast(e.message, "error"); }
  };
  const d = document.getElementById("modal");
  d.classList.add("modal-fijo");
  d.addEventListener("cancel", (ev) => ev.preventDefault());
  d.onclick = null;
  d.addEventListener("close", () => d.classList.remove("modal-fijo"), { once: true });
  return m;
}
