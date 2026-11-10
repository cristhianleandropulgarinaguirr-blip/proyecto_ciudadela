// Contactos de emergencia: todos los consultan (llamada con un toque); el administrador los gestiona.
// Endpoints: GET /emergencias/ · POST /emergencias/ · PATCH/DELETE /emergencias/{id}
import { api } from "../api.js";
import { h, icono, estadoVacio, toast, conCarga, modal, confirmar } from "../ui.js";
import { cabecera } from "./comun.js";

const CATEGORIAS = [["Emergencias", "Emergencias"], ["Salud", "Salud"], ["Seguridad", "Seguridad"], ["Servicios publicos", "Servicios públicos"], ["Administracion", "Administración"], ["Otros", "Otros"]];
const etiquetaCat = (c) => CATEGORIAS.find(([k]) => k === c)?.[1] ?? c;
const marcable = (tel) => tel.replace(/[^\d+]/g, "");   // "601 234 5678" -> "6012345678" para tel:

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  let datos = await api("/emergencias/");
  const cont = h("div");

  async function recargar() { datos = await api("/emergencias/"); pintar(); }

  function formulario(c) {
    const campo = (id, et, el, ayuda) => h("div", { class: "field" }, el, h("label", { for: id }, et), ayuda ? h("div", { class: "ayuda" }, ayuda) : null);
    const nombre = h("input", { id: "em-nombre", placeholder: " ", maxlength: "60", value: c?.nombre ?? "" });
    const tel = h("input", { id: "em-tel", type: "tel", placeholder: " ", maxlength: "20", inputmode: "tel", value: c?.telefono ?? "" });
    const cat = h("select", { id: "em-cat" }, CATEGORIAS.map(([v, t]) => h("option", { value: v, selected: (c?.categoria ?? "Otros") === v }, t)));
    const desc = h("input", { id: "em-desc", placeholder: " ", maxlength: "120", value: c?.descripcion ?? "" });
    const orden = h("input", { id: "em-orden", type: "number", min: "0", max: "1000", placeholder: " ", value: c?.orden ?? 100 });
    const guardar = h("button", { class: "btn", type: "submit", form: "f-emerg" }, c ? "Guardar cambios" : "Agregar");
    const m = modal(c ? "Editar contacto" : "Nuevo contacto de emergencia", h("form", { id: "f-emerg", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (nombre.value.trim().length < 3) return toast("Escribe el nombre del contacto.", "error");
      if (marcable(tel.value).replace("+", "").length < 3) return toast("Escribe un teléfono válido.", "error");
      const cuerpo = { nombre: nombre.value.trim(), telefono: tel.value.trim(), categoria: cat.value, descripcion: desc.value.trim() || null, orden: Number(orden.value) || 0 };
      try {
        await conCarga(guardar, () => c ? api(`/emergencias/${c.id}`, { metodo: "PATCH", json: cuerpo }) : api("/emergencias/", { metodo: "POST", json: cuerpo }));
        m.cerrar(); toast(c ? "Contacto actualizado" : "Contacto agregado"); await recargar();
      } catch (err) { toast(err.message, "error"); }
    } },
      campo("em-nombre", "Nombre", nombre), campo("em-tel", "Teléfono", tel, "Ej. 123, 601 234 5678 o +57 300 123 4567"),
      h("div", { class: "fila-campos" }, campo("em-cat", "Categoría", cat), campo("em-orden", "Orden", orden, "Menor número = aparece primero")),
      campo("em-desc", "Descripción (opcional)", desc)),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
    nombre.focus();
  }

  function tarjeta(c) {
    return h("div", { class: `contacto ${c.telefono === "123" ? "principal" : ""}` },
      h("div", { class: "cuerpo" }, h("b", {}, c.nombre), h("span", {}, [etiquetaCat(c.categoria), c.descripcion].filter(Boolean).join(" · "))),
      h("a", { class: "btn llamar", href: `tel:${marcable(c.telefono)}`, "aria-label": `Llamar a ${c.nombre}, ${c.telefono}` }, icono("telefono", 20), c.telefono),
      esAdmin ? h("div", { class: "admin-acc" },
        h("button", { class: "btn suave sm", onclick: () => formulario(c) }, icono("editar", 16), "Editar"),
        h("button", { class: "btn peligro sm", onclick: async () => {
          if (!(await confirmar("¿Eliminar este contacto?", `${c.nombre} dejará de verse para todos.`, "Sí, eliminar", true))) return;
          try { await api(`/emergencias/${c.id}`, { metodo: "DELETE" }); toast("Contacto eliminado"); await recargar(); } catch (e) { toast(e.message, "error"); }
        } }, "Eliminar")) : null);
  }

  function pintar() {
    cont.replaceChildren(datos.length ? h("div", { class: "emergencias escalona" }, datos.map(tarjeta))
      : h("div", { class: "card" }, estadoVacio("Sin contactos", esAdmin ? "Agrega la clínica más cercana, el CAI del cuadrante o el servicio de gas." : "La administración aún no ha cargado contactos.")));
  }

  pintar();
  return h("div", {},
    cabecera("Emergencias", "Toca un número para llamar. En una emergencia real, marca primero la línea única 123."),
    esAdmin ? h("div", { class: "barra" }, h("p", { class: "muted" }, "Agrega los números locales de tu conjunto: clínica, CAI del cuadrante, gas, ascensores."), h("button", { class: "btn", onclick: () => formulario(null) }, icono("mas", 18), "Nuevo contacto")) : null,
    cont);
}
