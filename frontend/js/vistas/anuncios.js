// Cartelera del conjunto.
// Endpoints: GET /anuncios/ · POST /anuncios/ (admin) · PATCH/DELETE /anuncios/{id} (admin)
//            PUT /anuncios/{id}/asistencia?asistire= · GET /anuncios/{id}/asistentes (admin)
import { api } from "../api.js";
import { h, icono, badgeTipo, etiquetaTipo, estadoVacio, toast, conCarga, modal, confirmar, deLocal, deUtc, hace, fmtFechaLarga, fmtHora, iniciales } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const TIPOS = ["Aviso", "Reunion", "Evento", "Urgente", "Mantenimiento"];
const finalizado = (a) => a.fecha_evento && deLocal(a.fecha_evento) < new Date(Date.now() - 3 * 3600 * 1000);   // 3 h de margen

// Orden: fijados → eventos próximos (por fecha) → resto (más nuevos) → eventos finalizados.
export function ordenar(lista) {
  const peso = (a) => (finalizado(a) ? 3 : a.fijado ? 0 : a.fecha_evento ? 1 : 2);
  return [...lista].sort((a, b) => peso(a) - peso(b)
    || (peso(a) === 1 ? deLocal(a.fecha_evento) - deLocal(b.fecha_evento) : deUtc(b.fecha_creacion) - deUtc(a.fecha_creacion)));
}

// Tarjeta compacta que usa el Inicio de cada rol.
export function cartelaResumen(anuncios) {
  const top = ordenar(anuncios.filter((a) => !finalizado(a))).slice(0, 3);
  return h("section", { class: "card" },
    h("div", { class: "card-titulo" }, h("h2", {}, "Cartelera"), h("a", { class: "btn suave sm", href: "#/anuncios" }, "Ver todo")),
    h("div", { class: "lista" }, top.length ? top.map((a) => h("a", { class: `anuncio-mini t-${a.tipo}`, href: "#/anuncios" },
      h("div", {}, a.fijado ? h("span", { class: "pin", title: "Fijado" }, icono("pin")) : badgeTipo(a.tipo)),
      h("div", {}, h("b", {}, a.titulo), h("span", {}, a.fecha_evento ? `${fmtFechaLarga(deLocal(a.fecha_evento))} · ${fmtHora(deLocal(a.fecha_evento))}` : hace(deUtc(a.fecha_creacion))))))
      : [estadoVacio("Sin anuncios", "Aquí verás reuniones, eventos y avisos del conjunto.")]));
}

function formulario(existente, alGuardar) {
  const campo = (id, et, el) => h("div", { class: "field" }, el, h("label", { for: id }, et));
  const titulo = h("input", { id: "a-titulo", placeholder: " ", maxlength: "120", value: existente?.titulo ?? "" });
  const contenido = h("textarea", { id: "a-contenido", placeholder: " ", maxlength: "2000" }, existente?.contenido ?? "");
  const tipo = h("select", { id: "a-tipo" }, TIPOS.map((t) => h("option", { value: t, selected: (existente?.tipo ?? "Aviso") === t }, etiquetaTipo(t))));
  const fecha = h("input", { id: "a-fecha", type: "datetime-local", placeholder: " ", value: existente?.fecha_evento?.slice(0, 16) ?? "" });
  const lugar = h("input", { id: "a-lugar", placeholder: " ", maxlength: "100", value: existente?.lugar ?? "" });
  const fijado = h("input", { type: "checkbox", id: "a-fijado", checked: existente?.fijado ?? false });
  const guardar = h("button", { class: "btn", type: "submit", form: "f-anuncio" }, existente ? "Guardar cambios" : "Publicar");
  const m = modal(existente ? "Editar anuncio" : "Nuevo anuncio", h("form", { id: "f-anuncio", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (titulo.value.trim().length < 3) return toast("El título debe tener al menos 3 caracteres.", "error");
    if (contenido.value.trim().length < 5) return toast("Escribe el mensaje del anuncio.", "error");
    const datos = { titulo: titulo.value.trim(), contenido: contenido.value.trim(), tipo: tipo.value,
      fecha_evento: fecha.value ? `${fecha.value}:00` : null, lugar: lugar.value.trim() || null, fijado: fijado.checked };
    try {
      await conCarga(guardar, () => existente ? api(`/anuncios/${existente.id}`, { metodo: "PATCH", json: datos }) : api("/anuncios/", { metodo: "POST", json: datos }));
      m.cerrar(); toast(existente ? "Anuncio actualizado" : "Anuncio publicado para todos los usuarios"); alGuardar();
    } catch (err) { toast(err.message, "error"); }
  } },
    campo("a-titulo", "Título", titulo), campo("a-contenido", "Mensaje", contenido),
    h("div", { class: "fila-campos" }, campo("a-tipo", "Tipo", tipo), campo("a-fecha", "Fecha y hora (si es un evento)", fecha)),
    campo("a-lugar", "Lugar (opcional)", lugar),
    h("label", { class: "switch-fila" }, h("span", { class: "switch" }, fijado, h("i")), "Fijar arriba de la cartelera")),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
}

async function verAsistentes(a) {
  try {
    const lista = await api(`/anuncios/${a.id}/asistentes`);
    modal(`Asistentes · ${a.titulo}`, lista.length
      ? h("ul", { class: "lista-asistentes" }, lista.map((u) => h("li", {}, h("div", { class: "avatar" }, iniciales(u.nombre_completo)),
          h("div", { class: "persona" }, h("div", {}, h("b", {}, u.nombre_completo), h("span", {}, u.apartamento ?? "Sin apartamento"))))))
      : estadoVacio("Aún nadie confirmó", "Cuando los residentes confirmen aparecerán aquí."));
  } catch (e) { toast(e.message, "error"); }
}

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  let datos = await api("/anuncios/"), filtro = "todos";
  const rejilla = h("div", { class: "cartelera" });
  let chips = h("div");
  const GRUPOS = { todos: () => true, eventos: (a) => a.tipo === "Reunion" || a.tipo === "Evento", avisos: (a) => a.tipo !== "Reunion" && a.tipo !== "Evento" };
  const recargar = async () => { datos = await api("/anuncios/"); pintar(); };

  function tarjeta(a) {
    const f = a.fecha_evento ? deLocal(a.fecha_evento) : null, pasado = finalizado(a);
    const botones = [];
    if (f && !pasado) {
      const btn = h("button", { class: "btn sm asistire suave", "aria-pressed": String(a.asistire), onclick: async () => {
        try { Object.assign(a, await conCarga(btn, () => api(`/anuncios/${a.id}/asistencia`, { metodo: "PUT", params: { asistire: !a.asistire } }))); pintar(); }
        catch (e) { toast(e.message, "error"); }
      } }, a.asistire ? icono("ok", 16) : null, a.asistire ? "Asistiré" : "Confirmar asistencia");
      botones.push(btn);
    }
    if (f) botones.push(h("span", { class: "small muted" }, `${a.asistentes} ${a.asistentes === 1 ? "confirmado" : "confirmados"}`));
    const admin = esAdmin ? [
      f ? h("button", { class: "btn suave sm", onclick: () => verAsistentes(a) }, "Asistentes") : null,
      h("button", { class: "btn suave icono sm", title: a.fijado ? "Quitar de fijados" : "Fijar arriba", "aria-label": a.fijado ? "Quitar de fijados" : "Fijar arriba",
        onclick: async () => { try { await api(`/anuncios/${a.id}`, { metodo: "PATCH", json: { fijado: !a.fijado } }); recargar(); } catch (e) { toast(e.message, "error"); } } }, icono("pin", 16)),
      h("button", { class: "btn suave icono sm", title: "Editar", "aria-label": "Editar", onclick: () => formulario(a, recargar) }, icono("editar", 16)),
      h("button", { class: "btn peligro icono sm", title: "Eliminar", "aria-label": "Eliminar", onclick: async () => {
        if (await confirmar("¿Eliminar este anuncio?", `«${a.titulo}» dejará de verse para todos.`, "Sí, eliminar", true)) {
          try { await api(`/anuncios/${a.id}`, { metodo: "DELETE" }); toast("Anuncio eliminado"); recargar(); } catch (e) { toast(e.message, "error"); }
        } } }, icono("basura", 16)),
    ] : [];
    return h("article", { class: `card anuncio t-${a.tipo} ${pasado ? "finalizado" : ""}` },
      h("div", { class: "cab" }, h("div", { style: "display:flex;gap:.5rem;align-items:center" }, badgeTipo(a.tipo), a.fijado ? h("span", { class: "pin", title: "Fijado" }, icono("pin")) : null, pasado ? h("span", { class: "badge" }, "Finalizado") : null),
        h("span", { class: "small muted" }, hace(deUtc(a.fecha_creacion)))),
      h("h3", {}, a.titulo), h("p", { class: "texto" }, a.contenido),
      f || a.lugar ? h("div", { class: "meta" },
        f ? h("span", {}, icono("calendario"), `${fmtFechaLarga(f)} · ${fmtHora(f)}`) : null,
        a.lugar ? h("span", {}, icono("lugar"), a.lugar) : null) : null,
      h("div", { class: "pie" }, h("span", { class: "autor" }, `Publicó ${a.autor_nombre}`), ...botones, ...admin));
  }

  function pintar() {
    const conteo = [["todos", "Todos"], ["eventos", "Reuniones y eventos"], ["avisos", "Avisos"]].map(([id, texto]) => ({ id, texto, n: datos.filter(GRUPOS[id]).length }));
    chips.replaceWith((chips = filtros(conteo, filtro, (f) => { filtro = f; pintar(); })));
    const v = ordenar(datos.filter(GRUPOS[filtro]));
    rejilla.replaceChildren(...(v.length ? v.map(tarjeta)
      : [h("div", { class: "card", style: "grid-column:1/-1" }, estadoVacio("No hay anuncios", esAdmin ? "Publica el primero con el botón «Nuevo anuncio»." : "Cuando la administración publique algo, lo verás aquí.")) ]));
  }

  pintar();
  return h("div", {},
    cabecera("Cartelera", "Reuniones, eventos y avisos de tu conjunto, siempre al día."),
    h("div", { class: "barra" }, chips, esAdmin ? h("button", { class: "btn", onclick: () => formulario(null, recargar) }, icono("mas", 18), "Nuevo anuncio") : null),
    rejilla);
}
