// Documentos del conjunto (PDF). Endpoints: GET /documentos/?categoria= · POST /documentos/ (multipart, admin)
//   GET /documentos/{id}/descargar · DELETE /documentos/{id} (admin)
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaCorta } from "../ui.js";
import { cabecera, filtros } from "./comun.js";
import { descargar, tamanoLegible } from "../descargas.js";

const CATEGORIAS = ["Reglamento", "Acta", "Circular", "Financiero", "Otros"];
const MAX_MB = 10;

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  let datos = await api("/documentos/"), filtro = "todas", texto = "";
  const lista = h("div", { class: "lista" });
  let chips = h("div");
  async function recargar() { datos = await api("/documentos/"); pintar(); }

  function subir() {
    const titulo = h("input", { id: "do-titulo", placeholder: " ", maxlength: "100", autocomplete: "off" });
    const cat = h("select", { id: "do-cat" }, CATEGORIAS.map((c) => h("option", { value: c }, c)));
    const desc = h("input", { id: "do-desc", placeholder: " ", maxlength: "200", autocomplete: "off" });
    const archivo = h("input", { id: "do-archivo", type: "file", accept: "application/pdf,.pdf" });
    const guardar = h("button", { class: "btn", type: "submit", form: "f-doc" }, icono("subir", 16), "Subir");
    const m = modal("Subir documento", h("form", { id: "f-doc", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      const f = archivo.files[0];
      if (titulo.value.trim().length < 3) return toast("Escribe un título.", "error");
      if (!f) return toast("Elige un archivo PDF.", "error");
      if (!/\.pdf$/i.test(f.name)) return toast("Solo se aceptan archivos PDF.", "error");
      if (f.size > MAX_MB * 1024 * 1024) return toast(`El PDF no puede pesar más de ${MAX_MB} MB.`, "error");
      const fd = new FormData(); fd.append("titulo", titulo.value.trim()); fd.append("categoria", cat.value); if (desc.value.trim()) fd.append("descripcion", desc.value.trim()); fd.append("archivo", f);
      try { await conCarga(guardar, () => api("/documentos/", { metodo: "POST", cuerpo: fd })); m.cerrar(); toast("Documento publicado. Todos los usuarios fueron avisados."); await recargar(); }
      catch (err) { toast(err.message, "error"); }
    } },
      h("div", { class: "field" }, titulo, h("label", { for: "do-titulo" }, "Título")),
      h("div", { class: "field" }, cat, h("label", { for: "do-cat" }, "Categoría")),
      h("div", { class: "field" }, desc, h("label", { for: "do-desc" }, "Descripción (opcional)")),
      h("div", { class: "field archivo" }, h("label", { for: "do-archivo", class: "fija" }, `Archivo PDF (máx. ${MAX_MB} MB)`), archivo)),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
    titulo.focus();
  }

  function pintar() {
    const n = (c) => (c === "todas" ? datos.length : datos.filter((d) => d.categoria === c).length);
    chips.replaceWith((chips = filtros([{ id: "todas", texto: "Todos", n: n("todas") }, ...CATEGORIAS.filter((c) => n(c)).map((c) => ({ id: c, texto: c, n: n(c) }))], filtro, (f) => { filtro = f; pintar(); })));
    const q = texto.trim().toLowerCase();
    const v = datos.filter((d) => (filtro === "todas" || d.categoria === filtro) && (!q || `${d.titulo} ${d.descripcion ?? ""}`.toLowerCase().includes(q)));
    lista.replaceChildren(...(v.length ? v.map((d) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("archivo")),
      h("div", { class: "cuerpo" }, h("b", {}, d.titulo), d.descripcion ? h("span", { style: "display:block" }, d.descripcion) : null,
        h("span", { class: "small muted", style: "display:block" }, `${d.categoria} · ${tamanoLegible(d.tamano)} · ${fmtFechaCorta(deUtc(d.fecha_creacion))}`)),
      h("div", { class: "acciones" },
        h("button", { class: "btn sm", onclick: (e) => descargar(e.currentTarget, `/documentos/${d.id}/descargar`, d.nombre_original) }, icono("descarga", 16), "Descargar"),
        esAdmin ? h("button", { class: "btn peligro sm", onclick: async () => {
          if (!(await confirmar("¿Eliminar el documento?", `«${d.titulo}» dejará de estar disponible para todos.`, "Sí, eliminar", true))) return;
          try { await api(`/documentos/${d.id}`, { metodo: "DELETE" }); toast("Documento eliminado"); await recargar(); } catch (e) { toast(e.message, "error"); }
        } }, "Eliminar") : null)))
      : [estadoVacio(datos.length ? "Sin coincidencias" : "Aún no hay documentos", esAdmin ? "Sube el reglamento, las actas y las circulares para que todos los consulten." : "La administración publicará aquí el reglamento, las actas y las circulares.")]));
  }

  pintar();
  const buscador = h("input", { type: "search", placeholder: "Buscar documento", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  return h("div", {}, cabecera("Documentos", "Reglamento, actas y circulares del conjunto en PDF."),
    h("div", { class: "barra" }, h("div", { class: "buscador" }, icono("buscar"), buscador), esAdmin ? h("button", { class: "btn", onclick: subir }, icono("mas", 18), "Subir documento") : null),
    h("div", { class: "card escalona" }, h("div", { style: "margin-bottom:1rem" }, chips), lista));
}
