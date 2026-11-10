// Comercio: directorio de negocios de los vecinos, con anuncios de pago.
// Endpoints: GET /comercio/ · /comercio/planes · /comercio/mios · /comercio/gestion · /comercio/resumen
//            POST /comercio/ (multipart) · /{id}/informar-pago · /{id}/aprobar · /{id}/rechazar · /{id}/renovar · /{id}/contacto
//            DELETE /comercio/{id} · GET /comercio/{id}/imagen (protegida: se muestra como blob)
import { api, apiBlob } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, dinero, kpi, deUtc, hace, fmtFechaCorta } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const CATEGORIAS = [["Comida", "Comida"], ["Belleza", "Belleza"], ["Hogar", "Hogar"], ["Servicios", "Servicios"], ["Mascotas", "Mascotas"], ["Educacion", "Educación"], ["Otros", "Otros"]];
const etiquetaCat = (c) => CATEGORIAS.find(([k]) => k === c)?.[1] ?? c;
const TIPOS_IMG = ["image/jpeg", "image/png", "image/webp"], MAX_MB = 5;

function imagenAnuncio(a) {
  const caja = h("div", { class: "com-img" }, icono("tienda"));
  if (a.tiene_imagen) apiBlob(`/comercio/${a.id}/imagen`).then((b) => caja.replaceChildren(h("img", { src: URL.createObjectURL(b), alt: a.nombre_negocio, loading: "lazy" }))).catch(() => {});
  return caja;
}

// ---------------------------------------------------------------- directorio
async function pestanaDirectorio() {
  const [datos] = await Promise.all([api("/comercio/")]);
  let cat = "todas", texto = "", chips = h("div");
  const rejilla = h("div", { class: "com-grid" });

  function tarjeta(a) {
    const escribir = h("button", { class: "btn sm", onclick: async () => {
      try { const r = await conCarga(escribir, () => api(`/comercio/${a.id}/contacto`, { metodo: "POST" })); window.open(r.whatsapp_url, "_blank", "noopener"); }
      catch (e) { toast(e.message, "error"); }
    } }, icono("chat", 16), "Escribir por WhatsApp");
    return h("article", { class: "card com-card" }, imagenAnuncio(a),
      h("div", { class: "com-cuerpo" },
        h("div", { class: "com-cab" }, h("span", { class: "badge borde" }, etiquetaCat(a.categoria)), a.precio_texto ? h("b", { class: "com-precio" }, a.precio_texto) : null),
        h("h3", {}, a.titulo), h("div", { class: "small muted" }, `${a.nombre_negocio} · ${a.propietario_nombre}${a.apartamento ? ` (${a.apartamento})` : ""}`),
        h("p", { class: "texto" }, a.descripcion), escribir));
  }
  function pintar() {
    const q = texto.trim().toLowerCase();
    const v = datos.filter((a) => (cat === "todas" || a.categoria === cat) && (!q || `${a.nombre_negocio} ${a.titulo} ${a.descripcion}`.toLowerCase().includes(q)));
    const usadas = CATEGORIAS.filter(([k]) => datos.some((a) => a.categoria === k));
    chips.replaceWith((chips = filtros([{ id: "todas", texto: "Todos", n: datos.length }, ...usadas.map(([k, t]) => ({ id: k, texto: t, n: datos.filter((a) => a.categoria === k).length }))], cat, (f) => { cat = f; pintar(); })));
    rejilla.replaceChildren(...(v.length ? v.map(tarjeta)
      : [h("div", { class: "card", style: "grid-column:1/-1" }, estadoVacio(datos.length ? "Sin coincidencias" : "Aún no hay negocios", datos.length ? "Prueba con otra categoría o palabra." : "Cuando un vecino publique su negocio, lo verás aquí."))]));
  }
  const buscar = h("input", { type: "search", placeholder: "Buscar negocio o producto", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  pintar();
  return h("div", {}, h("div", { class: "barra" }, h("div", { class: "buscador" }, icono("buscar"), buscar)), chips, rejilla);
}

// ---------------------------------------------------------------- publicar
async function formularioNuevo(alGuardar) {
  const { planes, instrucciones_pago } = await api("/comercio/planes");
  const c = (id, et, el, ayuda) => h("div", { class: "field" }, el, h("label", { for: id }, et), ayuda ? h("div", { class: "ayuda" }, ayuda) : null);
  const negocio = h("input", { id: "c-neg", placeholder: " ", maxlength: "60" });
  const cat = h("select", { id: "c-cat" }, CATEGORIAS.map(([k, t]) => h("option", { value: k }, t)));
  const titulo = h("input", { id: "c-tit", placeholder: " ", maxlength: "80" });
  const desc = h("textarea", { id: "c-desc", placeholder: " ", maxlength: "600" });
  const precio = h("input", { id: "c-precio", placeholder: " ", maxlength: "40" });
  const wa = h("input", { id: "c-wa", placeholder: " ", inputmode: "numeric", maxlength: "10", autocomplete: "off" });
  wa.addEventListener("input", () => { wa.value = wa.value.replace(/\D/g, ""); });

  let archivo = null;
  const entrada = h("input", { type: "file", accept: TIPOS_IMG.join(","), class: "sr-only", id: "c-img" });
  const vacioDrop = () => [icono("subir"), h("b", {}, "Agregar foto (opcional)"), h("span", { class: "small" }, "JPG, PNG o WEBP · máx. 5 MB")];
  const drop = h("label", { class: "drop", for: "c-img" }, ...vacioDrop());
  entrada.addEventListener("change", () => {
    const f = entrada.files[0]; if (!f) return;
    if (!TIPOS_IMG.includes(f.type)) return toast("La foto debe ser JPG, PNG o WEBP.", "error");
    if (f.size > MAX_MB * 1024 * 1024) return toast(`La foto supera los ${MAX_MB} MB.`, "error");
    archivo = f; drop.replaceChildren(h("img", { src: URL.createObjectURL(f), alt: "Vista previa" }), h("span", { class: "small" }, `${f.name} · toca para cambiar`));
  });

  let plan = "Mensual";
  const opciones = h("div", { class: "planes", role: "radiogroup", "aria-label": "Plan" }, planes.map((p) =>
    h("label", { class: "plan" }, h("input", { type: "radio", name: "plan", value: p.plan, checked: p.plan === plan, onchange: () => { plan = p.plan; } }),
      h("span", {}, h("b", {}, p.plan), h("small", {}, `${p.dias} días`), h("em", {}, dinero(p.valor))))));

  const ok = h("button", { class: "btn", type: "submit", form: "f-com" }, "Crear anuncio");
  const m = modal("Publica tu negocio", h("form", { id: "f-com", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (negocio.value.trim().length < 2) return toast("Escribe el nombre de tu negocio.", "error");
    if (titulo.value.trim().length < 5) return toast("El título debe tener al menos 5 caracteres.", "error");
    if (desc.value.trim().length < 10) return toast("Cuéntale a tus vecinos qué ofreces (mín. 10 caracteres).", "error");
    if (!/^3\d{9}$/.test(wa.value)) return toast("El WhatsApp debe ser un celular de 10 dígitos que empiece por 3.", "error");
    const fd = new FormData();
    fd.append("nombre_negocio", negocio.value.trim()); fd.append("categoria", cat.value); fd.append("titulo", titulo.value.trim());
    fd.append("descripcion", desc.value.trim()); fd.append("whatsapp", wa.value); fd.append("plan", plan);
    if (precio.value.trim()) fd.append("precio_texto", precio.value.trim());
    if (archivo) fd.append("imagen", archivo);
    try { await conCarga(ok, () => api("/comercio/", { metodo: "POST", cuerpo: fd })); m.cerrar(); toast("Anuncio creado. Falta el pago para activarlo."); alGuardar(); }
    catch (err) { toast(err.message, "error"); }
  } },
    c("c-neg", "Nombre del negocio", negocio),
    h("div", { class: "fila-campos" }, c("c-cat", "Categoría", cat), c("c-precio", "Precio (opcional)", precio, "Ej. Desde $6.000")),
    c("c-tit", "Título del anuncio", titulo), c("c-desc", "Descripción", desc),
    c("c-wa", "WhatsApp de contacto", wa, "Celular de 10 dígitos, sin +57"),
    drop, entrada, h("div", { class: "etiqueta-seccion" }, "Elige tu plan"), opciones,
    h("p", { class: "small muted", style: "margin-top:.8rem" }, instrucciones_pago)),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
}

// ---------------------------------------------------------------- mis anuncios
function pedirReferencia(a, alGuardar) {
  const ref = h("input", { id: "ref", placeholder: " ", maxlength: "60", autocomplete: "off" });
  const ok = h("button", { class: "btn", type: "submit", form: "f-ref" }, "Informar pago");
  const m = modal("Informar mi pago", h("form", { id: "f-ref", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (ref.value.trim().length < 3) return toast("Escribe el número o detalle del comprobante.", "error");
    try { await conCarga(ok, () => api(`/comercio/${a.id}/informar-pago`, { metodo: "POST", json: { referencia: ref.value.trim() } })); m.cerrar(); toast("Pago informado. El administrador lo revisará."); alGuardar(); }
    catch (err) { toast(err.message, "error"); }
  } }, h("p", { class: "muted", style: "margin-bottom:1rem" }, `Valor a pagar: ${dinero(a.valor)} (plan ${a.plan}).`),
    h("div", { class: "field" }, ref, h("label", { for: "ref" }, "Comprobante o referencia"))),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  ref.focus();
}

function renovarModal(a, alGuardar) {
  let plan = a.plan;
  api("/comercio/planes").then(({ planes }) => {
    const m = modal("Renovar anuncio", h("div", {}, h("p", { class: "muted", style: "margin-bottom:1rem" }, "Elige el plan; luego deberás pagarlo de nuevo."),
      h("div", { class: "planes" }, planes.map((p) => h("label", { class: "plan" }, h("input", { type: "radio", name: "plan-r", checked: p.plan === plan, onchange: () => { plan = p.plan; } }),
        h("span", {}, h("b", {}, p.plan), h("small", {}, `${p.dias} días`), h("em", {}, dinero(p.valor))))))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"),
      h("button", { class: "btn", onclick: async (e) => { try { await conCarga(e.currentTarget, () => api(`/comercio/${a.id}/renovar`, { metodo: "POST", json: { plan } })); m.cerrar(); toast("Listo: ahora falta el pago."); alGuardar(); } catch (err) { toast(err.message, "error"); } } }, "Renovar")] });
  }).catch((e) => toast(e.message, "error"));
}

async function pestanaMios(recargar) {
  const mios = await api("/comercio/mios");
  const filas = mios.map((a) => {
    const info = [];
    if (a.estado === "Activa") info.push(`Publicado hasta el ${fmtFechaCorta(deUtc(a.fecha_fin))}`, `${a.contactos} ${a.contactos === 1 ? "contacto" : "contactos"}`);
    if (a.estado === "Pendiente de pago") info.push(`Falta pagar ${dinero(a.valor)} (plan ${a.plan})`);
    if (a.estado === "En revision") info.push("El administrador está confirmando tu pago");
    if (a.estado === "Rechazada") info.push(`Motivo: ${a.motivo_rechazo}`);
    if (a.estado === "Vencida") info.push(`Venció el ${fmtFechaCorta(deUtc(a.fecha_fin))}`);
    const acc = [];
    if (a.estado === "Pendiente de pago") acc.push(h("button", { class: "btn sm", onclick: () => pedirReferencia(a, recargar) }, "Ya pagué"));
    if (a.estado === "Vencida" || a.estado === "Rechazada") acc.push(h("button", { class: "btn sm", onclick: () => renovarModal(a, recargar) }, "Renovar"));
    if (a.estado !== "Activa") acc.push(h("button", { class: "btn peligro icono sm", "aria-label": "Eliminar", title: "Eliminar", onclick: async () => {
      if (!(await confirmar("¿Eliminar este anuncio?", `«${a.titulo}» se borrará definitivamente.`, "Sí, eliminar", true))) return;
      try { await api(`/comercio/${a.id}`, { metodo: "DELETE" }); toast("Anuncio eliminado"); recargar(); } catch (e) { toast(e.message, "error"); }
    } }, icono("basura", 16)));
    return h("article", { class: "card com-mio" }, imagenAnuncio(a),
      h("div", { class: "cuerpo" }, h("div", { class: "com-cab" }, badge(a.estado), h("span", { class: "small muted" }, hace(deUtc(a.fecha_creacion)))),
        h("b", {}, a.titulo), h("div", { class: "small muted" }, `${a.nombre_negocio} · ${etiquetaCat(a.categoria)}`),
        ...info.map((t) => h("div", { class: "small" }, t)), acc.length ? h("div", { class: "acciones-fila" }, acc) : null));
  });
  return h("div", {}, h("div", { class: "barra" }, h("p", { class: "muted" }, "Tus vecinos verán tu negocio en el directorio mientras tu plan esté vigente."),
    h("button", { class: "btn", onclick: () => formularioNuevo(recargar).catch((e) => toast(e.message, "error")) }, icono("mas", 18), "Publicar mi negocio")),
    filas.length ? h("div", { class: "lista" }, filas) : h("div", { class: "card" }, estadoVacio("Aún no has publicado", "Anuncia tu comida, servicio o producto a todo el conjunto.")));
}

// ---------------------------------------------------------------- gestión (administrador)
async function pestanaGestion(recargar) {
  const [res, todos] = await Promise.all([api("/comercio/resumen"), api("/comercio/gestion")]);
  let filtro = "todos", chips = h("div");
  const lista = h("div", { class: "lista" });
  const ESTADOS = [["todos", "Todos"], ["En revision", "Por revisar"], ["Pendiente de pago", "Sin pagar"], ["Activa", "Activos"], ["Vencida", "Vencidos"], ["Rechazada", "Rechazados"]];

  function rechazar(a) {
    const motivo = h("textarea", { id: "mot", placeholder: " ", maxlength: "200" });
    const ok = h("button", { class: "btn arcilla", type: "submit", form: "f-rech" }, "Rechazar");
    const m = modal("Rechazar anuncio", h("form", { id: "f-rech", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (motivo.value.trim().length < 5) return toast("Explica el motivo (mín. 5 caracteres).", "error");
      try { await conCarga(ok, () => api(`/comercio/${a.id}/rechazar`, { metodo: "POST", json: { motivo: motivo.value.trim() } })); m.cerrar(); toast("Anuncio rechazado"); recargar(); }
      catch (err) { toast(err.message, "error"); }
    } }, h("div", { class: "field" }, motivo, h("label", { for: "mot" }, "Motivo (lo verá el dueño)"))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  }

  function pintar() {
    chips.replaceWith((chips = filtros(ESTADOS.map(([id, t]) => ({ id, texto: t, n: id === "todos" ? todos.length : todos.filter((a) => a.estado === id).length })), filtro, (f) => { filtro = f; pintar(); })));
    const v = todos.filter((a) => filtro === "todos" || a.estado === filtro);
    lista.replaceChildren(...(v.length ? v.map((a) => {
      const acc = [];
      if (a.estado === "En revision" || a.estado === "Pendiente de pago") {
        acc.push(h("button", { class: "btn sm", onclick: async (e) => { try { await conCarga(e.currentTarget, () => api(`/comercio/${a.id}/aprobar`, { metodo: "POST" })); toast("Pago confirmado: anuncio activo"); recargar(); } catch (err) { toast(err.message, "error"); } } }, icono("ok", 16), a.estado === "En revision" ? "Confirmar pago" : "Activar (pago en efectivo)"));
        acc.push(h("button", { class: "btn peligro sm", onclick: () => rechazar(a) }, "Rechazar"));
      }
      acc.push(h("button", { class: "btn peligro icono sm", "aria-label": "Eliminar", title: "Eliminar", onclick: async () => {
        if (!(await confirmar("¿Eliminar este anuncio?", "Se retira del directorio y no se puede deshacer.", "Sí, eliminar", true))) return;
        try { await api(`/comercio/${a.id}`, { metodo: "DELETE" }); toast("Anuncio eliminado"); recargar(); } catch (e) { toast(e.message, "error"); }
      } }, icono("basura", 16)));
      return h("article", { class: "card com-mio" }, imagenAnuncio(a), h("div", { class: "cuerpo" },
        h("div", { class: "com-cab" }, badge(a.estado), h("b", { class: "com-precio" }, `${dinero(a.valor)} · ${a.plan}`)),
        h("b", {}, a.titulo), h("div", { class: "small muted" }, `${a.nombre_negocio} · ${a.propietario_nombre}${a.apartamento ? ` (${a.apartamento})` : ""}`),
        a.referencia_pago ? h("div", { class: "small" }, `Comprobante: ${a.referencia_pago}`) : null,
        a.estado === "Activa" ? h("div", { class: "small" }, `Hasta el ${fmtFechaCorta(deUtc(a.fecha_fin))} · ${a.contactos} contactos`) : null,
        h("div", { class: "acciones-fila" }, acc)));
    }) : [h("div", { class: "card" }, estadoVacio("Nada por aquí", "No hay anuncios en este estado."))]));
  }
  pintar();
  return h("div", {}, h("div", { class: "kpis escalona" },
    kpi("Ingresos confirmados", res.ingresos_confirmados, { destacado: true, formato: dinero }), kpi("Por revisar", res.por_revisar, { alerta: true }),
    kpi("Sin pagar", res.pendientes_pago), kpi("Anuncios activos", res.activas), kpi("Contactos generados", res.contactos_totales)), chips, lista);
}

export async function render(ctx) {
  const rol = ctx.usuario.rol, panel = h("div"), tabs = h("div", { class: "tabs", role: "tablist" });
  const PESTANAS = [["directorio", "Directorio", ["Administrador", "Residente", "Guardia"]], ["mios", "Mis anuncios", ["Administrador", "Residente"]], ["gestion", "Gestión", ["Administrador"]]]
    .filter(([, , roles]) => roles.includes(rol));
  let actual = "directorio";
  async function mostrar(cual) {
    actual = cual;
    tabs.replaceChildren(...PESTANAS.map(([id, t]) => h("button", { class: "tab", role: "tab", "aria-selected": String(id === actual), onclick: () => id !== actual && mostrar(id) }, t)));
    panel.replaceChildren(h("div", { class: "esq", style: "height:180px" }));
    const recargar = () => mostrar(cual);
    try {
      const nodo = await ({ directorio: pestanaDirectorio, mios: () => pestanaMios(recargar), gestion: () => pestanaGestion(recargar) })[cual]();
      if (cual === actual) panel.replaceChildren(nodo);
    } catch (e) { toast(e.message, "error"); }
  }
  await mostrar("directorio");
  return h("div", {}, cabecera("Comercio", "Los negocios de tus vecinos: comida, servicios y más, a un toque de WhatsApp."), PESTANAS.length > 1 ? tabs : null, panel);
}
