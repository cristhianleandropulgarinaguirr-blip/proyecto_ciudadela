// Reporte y seguimiento de daños.
// Endpoints: POST /mantenimiento/reportar-danio (multipart) · GET /mantenimiento/listar-danios
//            GET /mantenimiento/danios/{id}/foto (protegida: se pide con el token y se muestra como blob)
//            PATCH /mantenimiento/cambiar-estado/{id} (admin)
import { api, apiBlob } from "../api.js";
import { botonResidente, tomarBorrador } from "../asistente.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, deUtc, hace } from "../ui.js";
import { cabecera, filtros, mapaUsuarios, nombreDe } from "./comun.js";

const PASOS = [["Abierto", "Reportado"], ["En Revision", "En revisión"], ["En Reparacion", "En reparación"], ["Solucionado", "Solucionado"]];
const TIPOS = ["image/jpeg", "image/png", "image/webp"];
const MAX = 5 * 1024 * 1024;

async function cargarFoto(reporte, destino) {
  if (!reporte.foto_url || reporte.foto_url === "sin_foto.jpg") return;
  try {
    const url = URL.createObjectURL(await apiBlob(`/mantenimiento/danios/${reporte.id}/foto`));
    destino.replaceChildren(h("img", { src: url, alt: `Foto del reporte: ${reporte.titulo}`, loading: "lazy" }));
    destino.onclick = () => modal(reporte.titulo, h("img", { class: "visor", src: url, alt: reporte.titulo }));
    destino.disabled = false; destino.setAttribute("aria-label", "Ampliar foto");
  } catch { /* si falla, se queda el ícono */ }
}

export async function render(ctx) {
  const { usuario } = ctx;
  const esAdmin = usuario.rol === "Administrador";
  const [reportes, usuarios] = await Promise.all([api("/mantenimiento/listar-danios"), esAdmin ? api("/usuarios/") : Promise.resolve([])]);
  const mapa = mapaUsuarios(usuarios);
  let datos = reportes, filtro = "todos", archivo = null;
  const rejilla = h("div", { class: "danios" });
  let chips = h("div");

  const GRUPOS = { todos: () => true, abiertos: (r) => r.estado === "Abierto", proceso: (r) => r.estado === "En Revision" || r.estado === "En Reparacion", resueltos: (r) => r.estado === "Solucionado" };
  const DEFS = [["todos", "Todos"], ["abiertos", "Abiertos"], ["proceso", "En proceso"], ["resueltos", "Solucionados"]];

  function tarjeta(r) {
    const idx = PASOS.findIndex(([v]) => v === r.estado);
    const foto = h("button", { class: "foto", type: "button", disabled: true, "aria-label": "Sin foto" }, icono("imagen"));
    cargarFoto(r, foto);
    const pasos = h("div", { class: "pasos", role: "list" }, PASOS.map(([valor, texto], i) =>
      h("button", { type: "button", role: "listitem", class: `paso ${i < idx ? "hecho" : ""} ${i === idx ? "actual" : ""}`, disabled: !esAdmin || i === idx,
        title: esAdmin ? `Marcar como ${texto}` : texto,
        onclick: async () => {
          try { await api(`/mantenimiento/cambiar-estado/${r.id}`, { metodo: "PATCH", params: { nuevo_estado: valor } }); r.estado = valor; toast(`Estado: ${texto}`); pintar(); }
          catch (e) { toast(e.message, "error"); }
        } }, h("i"), texto)));
    return h("article", { class: "card danio" }, foto,
      h("div", { class: "info" },
        h("div", { style: "display:flex;justify-content:space-between;gap:.5rem;align-items:center;flex-wrap:wrap" }, badge(r.estado),
          h("span", { class: "small muted" }, hace(deUtc(r.fecha_creacion)))),
        h("h3", {}, r.titulo), h("p", {}, r.descripcion),
        esAdmin ? h("span", { class: "small muted" }, `Reportó: ${nombreDe(mapa, r.usuario_id)}`) : null, pasos));
  }
  function pintar() {
    const conteo = DEFS.map(([id, texto]) => ({ id, texto, n: datos.filter(GRUPOS[id]).length }));
    chips.replaceWith((chips = filtros(conteo, filtro, (f) => { filtro = f; pintar(); })));
    const v = datos.filter(GRUPOS[filtro]);
    rejilla.replaceChildren(...(v.length ? v.map(tarjeta) : [h("div", { class: "card", style: "grid-column:1/-1" }, estadoVacio("Sin reportes", "No hay reportes en esta categoría."))]));
  }

  // ----- Formulario -----
  const titulo = h("input", { id: "titulo", placeholder: " ", maxlength: "100", required: true });
  const desc = h("textarea", { id: "desc", placeholder: " ", maxlength: "1000", required: true });
  const entrada = h("input", { type: "file", accept: TIPOS.join(","), class: "sr-only", id: "foto-input" });
  const drop = h("label", { class: "drop", for: "foto-input" }, icono("subir"), h("b", {}, "Agregar foto"), h("span", { class: "small" }, "JPG, PNG o WEBP · máx. 5 MB"));
  function elegir(f) {
    if (!f) return;
    if (!TIPOS.includes(f.type)) return toast("La foto debe ser JPG, PNG o WEBP.", "error");
    if (f.size > MAX) return toast("La foto supera los 5 MB.", "error");
    archivo = f;
    drop.replaceChildren(h("img", { src: URL.createObjectURL(f), alt: "Vista previa" }), h("span", { class: "small" }, `${f.name} · toca para cambiar`));
  }
  entrada.addEventListener("change", () => elegir(entrada.files[0]));
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("sobre"); }));
  drop.addEventListener("drop", (e) => elegir(e.dataTransfer.files[0]));
  const usarBorrador = (b) => { titulo.value = b.titulo; desc.value = b.descripcion; desc.focus(); };
  const enviar = h("button", { class: "btn block", type: "submit" }, "Enviar reporte");
  const form = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (titulo.value.trim().length < 5) return toast("El título debe tener al menos 5 caracteres.", "error");
    if (desc.value.trim().length < 10) return toast("Describe el daño con al menos 10 caracteres.", "error");
    const fd = new FormData(); fd.append("titulo", titulo.value.trim()); fd.append("descripcion", desc.value.trim());
    if (archivo) fd.append("archivo_foto", archivo);
    try {
      await conCarga(enviar, () => api("/mantenimiento/reportar-danio", { metodo: "POST", cuerpo: fd }));
      toast("Reporte enviado. ¡Gracias por avisar!");
      form.reset(); archivo = null; drop.replaceChildren(icono("subir"), h("b", {}, "Agregar foto"), h("span", { class: "small" }, "JPG, PNG o WEBP · máx. 5 MB"));
      datos = await api("/mantenimiento/listar-danios"); pintar();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "card-titulo" }, h("h2", {}, "Reportar un daño")), botonResidente("danio", usarBorrador),
    h("div", { class: "field" }, titulo, h("label", { for: "titulo" }, "¿Qué pasó?")),
    h("div", { class: "field" }, desc, h("label", { for: "desc" }, "Cuéntanos los detalles")),
    drop, entrada, enviar);

  const llegado = tomarBorrador("danio");      // el asistente lo trajo desde otra pantalla
  if (llegado) { usarBorrador(llegado); toast("Borrador cargado. Revísalo, agrega una foto si quieres y envíalo."); }
  pintar();
  return h("div", {},
    cabecera(esAdmin ? "Mantenimiento" : "Reportar un daño", esAdmin ? "Toca un paso del avance para actualizar el estado de cada reporte." : "Cuéntanos qué se dañó en las zonas comunes y sigue cómo avanza la solución."),
    h("div", { class: "grid lados escalona" }, form,
      h("div", {}, h("div", { style: "margin-bottom:1rem" }, chips), rejilla)));
}
