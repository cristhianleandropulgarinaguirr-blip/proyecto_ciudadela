// Reporte y seguimiento de daños.
// Endpoints: POST /mantenimiento/reportar-danio (multipart) · GET /mantenimiento/listar-danios
//            GET /mantenimiento/danios/{id}/foto (protegida: se pide con el token y se muestra como blob)
//            PATCH /mantenimiento/cambiar-estado/{id} (admin: SOLO «Aprobado» o «Abierto» = devolver, y únicamente sobre un reporte «Solucionado»)
//   v5.6 · Rol Mantenimiento (técnico sin cuenta): el administrador crea un enlace temporal por reporte
//            POST /mantenimiento/danios/{id}/enlace-tecnico · GET /mantenimiento/danios/{id}/enlaces-tecnico · POST /mantenimiento/enlaces-tecnico/{id}/revocar
//            GET /mantenimiento/danios/{id}/evidencias/{evidencia_id}/foto (lo que dejó el técnico: nota + foto)
import { api, apiBlob } from "../api.js";
import { botonResidente, tomarBorrador } from "../asistente.js";
import { marca } from "../marca.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, hace, fmtFechaHora } from "../ui.js";
import { selectorFoto } from "../foto.js";
import { autoguardar } from "../autoguardado.js";
import { cabecera, filtros, mapaUsuarios, nombreDe } from "./comun.js";

// v5.7 · El avance lo mueven el técnico (En reparación → Solucionado) y, al final, el administrador (Aprobado). Los pasos son solo de lectura.
const PASOS = [["Abierto", "Reportado"], ["En Reparacion", "En reparación"], ["Solucionado", "Solucionado"], ["Aprobado", "Aprobado"]];
const ETAPA_VISIBLE = (estado) => (estado === "En Revision" ? 0 : PASOS.findIndex(([v]) => v === estado));        // «En Revision» es heredado: se ve como recién reportado

// La foto se pide solo cuando la tarjeta está por verse (IntersectionObserver) y primero en miniatura (~30 KB); la completa se baja al ampliar.
const observador = "IntersectionObserver" in window
  ? new IntersectionObserver((items) => items.forEach((it) => { if (it.isIntersecting) { observador.unobserve(it.target); it.target._cargar?.(); } }), { rootMargin: "200px" })
  : null;

function cargarFoto(reporte, destino) {
  if (!reporte.foto_url || reporte.foto_url === "sin_foto.jpg") return;
  const ruta = `/mantenimiento/danios/${reporte.id}/foto`;
  destino._cargar = async () => {
    try {
      const url = URL.createObjectURL(await apiBlob(ruta, { params: { miniatura: true } }));
      destino.replaceChildren(h("img", { src: url, alt: `Foto del reporte: ${reporte.titulo}` }));
      destino.onclick = async () => {
        const grande = h("img", { class: "visor", src: url, alt: reporte.titulo });      // se muestra ya la miniatura y se reemplaza por la completa al llegar
        modal(reporte.titulo, grande);
        try { grande.src = URL.createObjectURL(await apiBlob(ruta)); } catch { /* se queda la miniatura */ }
      };
      destino.disabled = false; destino.setAttribute("aria-label", "Ampliar foto");
    } catch { /* si falla, se queda el ícono */ }
  };
  observador ? observador.observe(destino) : destino._cargar();
}

// ================================================================ v5.6 · evidencia del técnico
const ETIQUETA_ESTADO = Object.fromEntries(PASOS);

function cargarFotoEvidencia(reporte, ev, destino) {
  const ruta = `/mantenimiento/danios/${reporte.id}/evidencias/${ev.id}/foto`;
  destino._cargar = async () => {
    try {
      const url = URL.createObjectURL(await apiBlob(ruta, { params: { miniatura: true } }));
      destino.replaceChildren(h("img", { src: url, alt: "Foto de evidencia del técnico" }));
      destino.onclick = async () => {
        const grande = h("img", { class: "visor", src: url, alt: "Foto de evidencia del técnico" });
        modal(`Evidencia · ${reporte.titulo}`, grande);
        try { grande.src = URL.createObjectURL(await apiBlob(ruta)); } catch { /* se queda la miniatura */ }
      };
      destino.disabled = false;
    } catch { /* si falla, se queda el ícono */ }
  };
  observador ? observador.observe(destino) : destino._cargar();
}

/** Lo que el técnico dejó desde su enlace (estado, nota y foto). Lo ven el administrador y quien hizo el reporte. */
function bloqueEvidencias(r) {
  if (!r.evidencias?.length) return null;
  return h("div", { class: "evidencias" }, r.evidencias.map((ev) => {
    const foto = ev.tiene_foto ? h("button", { class: "evidencia-foto", type: "button", disabled: true, "aria-label": "Ampliar foto de evidencia" }, icono("imagen")) : null;
    if (foto) cargarFotoEvidencia(r, ev, foto);
    return h("div", { class: "evidencia" }, foto,
      h("div", {}, h("span", { class: "badge-mant" }, "Técnico"), " ", h("b", {}, ETIQUETA_ESTADO[ev.estado] ?? ev.estado),
        h("span", { class: "small muted" }, ` · ${hace(deUtc(ev.fecha))}`), ev.nota ? h("p", {}, ev.nota) : null));
  }));
}

/** El administrador revisa lo que dejó el técnico (nota + foto) y decide: aprobar (cierra) o devolver (se atiende de nuevo). */
async function aprobar(r, alCambiar) {
  const si = await confirmar("¿Aprobar este reporte?", `Confirmas que revisaste la nota y la foto del técnico y que «${r.titulo}» quedó bien resuelto. El reporte se cierra y el residente recibe un aviso.`, "Aprobar y cerrar");
  if (!si) return;
  try { await api(`/mantenimiento/cambiar-estado/${r.id}`, { metodo: "PATCH", params: { nuevo_estado: "Aprobado" } }); r.estado = "Aprobado"; toast("Reporte aprobado y cerrado."); alCambiar(); }
  catch (e) { toast(e.message, "error"); }
}

function devolver(r, alCambiar) {
  const motivo = h("textarea", { id: "dev-motivo", maxlength: "300", placeholder: " " });
  const enviar = h("button", { class: "btn peligro block", type: "button", onclick: () => conCarga(enviar, async () => {
    try {
      await api(`/mantenimiento/cambiar-estado/${r.id}`, { metodo: "PATCH", params: { nuevo_estado: "Abierto", motivo: motivo.value.trim() || undefined } });
      r.estado = "Abierto"; document.getElementById("modal").close(); toast("Reporte devuelto. Crea un enlace nuevo para que se atienda de nuevo."); alCambiar();
    } catch (e) { toast(e.message, "error"); }
  }) }, "Devolver el reporte");
  modal("Devolver el reporte", h("div", {},
    h("p", { class: "muted small" }, "El reporte vuelve a «Abierto» y le avisamos al residente. Después puedes crear un enlace nuevo para que el técnico lo atienda otra vez."),
    h("div", { class: "field" }, motivo, h("label", { for: "dev-motivo" }, "¿Qué hay que corregir? (opcional, lo verá el residente)")), enviar));
}

const VIGENCIAS = [[24, "1 día"], [72, "3 días (recomendado)"], [168, "7 días (el máximo)"]];
const BADGE_ENLACE = { Vigente: "bosque", Vencido: "laton", Revocado: "arcilla", Cerrado: "borde" };
const urlDelEnlace = (e) => `${location.origin}${e.enlace}`;

async function copiarEnlace(e) {
  try { await navigator.clipboard.writeText(urlDelEnlace(e)); toast("Enlace copiado."); }
  catch { toast("No se pudo copiar: selecciona el enlace y cópialo a mano.", "error"); }
}

/** Botones Copiar y WhatsApp de un enlace vigente. */
function accionesDelEnlace(e, r) {
  const mensaje = `Enlace para atender el daño «${r.titulo}» en ${marca.nombre}. Sirve hasta ${fmtFechaHora(deUtc(e.valido_hasta))} y es solo para este reporte, no lo reenvíes: ${urlDelEnlace(e)}`;
  return h("div", { class: "tec-acciones" },
    h("button", { class: "btn mant sm", type: "button", onclick: () => copiarEnlace(e) }, icono("compartir", 16), "Copiar"),
    h("a", { class: "btn mant-suave sm", href: `https://wa.me/?text=${encodeURIComponent(mensaje)}`, target: "_blank", rel: "noopener noreferrer" }, "Enviar por WhatsApp"));
}

/** Ventana del administrador: crear el enlace de un técnico, copiarlo/enviarlo y anular los que ya no hagan falta. */
async function abrirEnlaceTecnico(r) {
  const vigencia = h("select", { id: "tec-horas" }, VIGENCIAS.map(([v, t]) => h("option", { value: v, selected: v === 72 }, t)));
  const etiqueta = h("input", { id: "tec-etiqueta", maxlength: "80", placeholder: " " });
  const resultado = h("div", { class: "tec-resultado" });
  const lista = h("div", { class: "tec-lista" });

  async function pintarLista() {
    try {
      const enlaces = await api(`/mantenimiento/danios/${r.id}/enlaces-tecnico`);
      lista.replaceChildren(...(enlaces.length ? enlaces.map((e) => h("div", { class: "tec-fila" },
        h("div", {}, h("span", {}, h("span", { class: `badge ${BADGE_ENLACE[e.estado] ?? ""}` }, e.estado), e.etiqueta ? ` ${e.etiqueta}` : ""),
          h("span", { class: "small muted" }, e.estado === "Vigente" ? `Sirve hasta ${fmtFechaHora(deUtc(e.valido_hasta))}` : `Creado ${hace(deUtc(e.fecha_creacion))}`)),
        e.estado === "Vigente" ? h("div", { class: "tec-acciones" },
          h("button", { class: "btn suave sm", type: "button", onclick: () => copiarEnlace(e) }, "Copiar"),
          h("button", { class: "btn peligro sm", type: "button", onclick: () => anular(e) }, "Anular")) : null))
        : [h("p", { class: "small muted" }, "Todavía no has creado enlaces para este reporte.")]));
    } catch { lista.replaceChildren(h("p", { class: "small muted" }, "No se pudo cargar la lista de enlaces.")); }
  }

  async function anular(e) {
    const si = await confirmar("¿Anular este enlace?", "El técnico ya no podrá abrirlo ni actualizar el reporte. Cuando quieras puedes crear otro.", "Anular enlace", true);
    if (si) {
      try { await api(`/mantenimiento/enlaces-tecnico/${e.id}/revocar`, { metodo: "POST" }); toast("Enlace anulado."); }
      catch (err) { toast(err.message, "error"); }
    }
    abrirEnlaceTecnico(r);          // el aviso de confirmación usa la misma ventana: se vuelve a abrir ya actualizada
  }

  const generar = h("button", { class: "btn mant block", type: "button", onclick: () => conCarga(generar, async () => {
    try {
      const e = await api(`/mantenimiento/danios/${r.id}/enlace-tecnico`, { metodo: "POST", json: { horas: Number(vigencia.value), etiqueta: etiqueta.value.trim() || null } });
      resultado.replaceChildren(
        h("b", {}, "Enlace listo. Cualquiera que lo tenga puede abrirlo hasta que venza o lo anules."),
        h("input", { class: "tec-url", readonly: true, value: urlDelEnlace(e), "aria-label": "Enlace para el técnico", onfocus: (ev) => ev.target.select() }),
        accionesDelEnlace(e, r));
      toast("Enlace creado. Si había otro vigente, quedó anulado.");
      await pintarLista();
    } catch (err) { toast(err.message, "error"); }
  }) }, icono("llave", 18), "Generar enlace");

  pintarLista();
  modal("Enlace para el técnico", h("div", { class: "tec-modal" },
    h("p", { class: "muted small" }, "El técnico lo abre sin contraseña. Podrá pasar el reporte a «En reparación» o «Solucionado» y subir su foto de evidencia con una nota. Cuando lo marque como solucionado, tú revisas la evidencia y lo apruebas. Cada cambio queda en la auditoría y le avisa al residente."),
    h("div", { class: "tec-aviso" },
      h("b", {}, "Esto es lo que verá el técnico (más la foto del daño):"),
      h("blockquote", {}, h("b", {}, r.titulo), h("br"), r.descripcion),
      h("span", { class: "small" }, "Nunca verá el nombre ni el teléfono de quien reportó, pero el texto se muestra tal cual: revisa que no incluya datos personales.")),
    h("div", { class: "field" }, vigencia, h("label", { for: "tec-horas" }, "¿Cuánto tiempo sirve el enlace?")),
    h("div", { class: "field" }, etiqueta, h("label", { for: "tec-etiqueta" }, "¿Para quién es? (opcional, solo lo ves tú)")),
    generar, resultado,
    h("h3", {}, "Enlaces de este reporte"), lista));
}

export async function render(ctx) {
  const { usuario } = ctx;
  const esAdmin = usuario.rol === "Administrador";
  const [reportes, usuarios] = await Promise.all([api("/mantenimiento/listar-danios"), esAdmin ? api("/usuarios/") : Promise.resolve([])]);
  const mapa = mapaUsuarios(usuarios);
  let datos = reportes, filtro = "todos";
  const rejilla = h("div", { class: "danios" });
  let chips = h("div");

  const GRUPOS = { todos: () => true, abiertos: (r) => r.estado === "Abierto", proceso: (r) => r.estado === "En Revision" || r.estado === "En Reparacion",
    porAprobar: (r) => r.estado === "Solucionado", aprobados: (r) => r.estado === "Aprobado" };
  const DEFS = [["todos", "Todos"], ["abiertos", "Abiertos"], ["proceso", "En proceso"], ["porAprobar", esAdmin ? "Por aprobar" : "Solucionados"], ["aprobados", "Aprobados"]];

  function tarjeta(r) {
    const idx = ETAPA_VISIBLE(r.estado);
    const foto = h("button", { class: "foto", type: "button", disabled: true, "aria-label": "Sin foto" }, icono("imagen"));
    cargarFoto(r, foto);
    const pasos = h("div", { class: "pasos", role: "list", "aria-label": "Avance del reporte" }, PASOS.map(([, texto], i) =>
      h("span", { role: "listitem", class: `paso ${i < idx ? "hecho" : ""} ${i === idx ? "actual" : ""} ${i === idx && r.estado === "Aprobado" ? "ok" : ""}`, "aria-current": i === idx ? "step" : null }, h("i"), texto)));
    const porAprobar = r.estado === "Solucionado";
    const decision = esAdmin && porAprobar ? h("div", { class: "por-aprobar", role: "group", "aria-label": "Revisión final" },
      h("b", {}, "El técnico terminó. Revisa su nota y su foto y decide:"),
      h("div", { class: "tec-acciones" },
        h("button", { class: "btn sm", type: "button", onclick: () => aprobar(r, pintar) }, icono("ok", 16), "Aprobar"),
        h("button", { class: "btn suave sm", type: "button", onclick: () => devolver(r, pintar) }, "Devolver"))) : null;
    const insignia = esAdmin && porAprobar ? h("span", { class: "badge laton" }, "Por aprobar") : badge(r.estado);
    const nota = !esAdmin && porAprobar ? h("span", { class: "small muted" }, "El técnico ya terminó. La administración hará la revisión final.") : null;
    const sinEnlace = r.estado === "Solucionado" || r.estado === "Aprobado";
    return h("article", { class: "card danio" }, foto,
      h("div", { class: "info" },
        h("div", { style: "display:flex;justify-content:space-between;gap:.5rem;align-items:center;flex-wrap:wrap" }, insignia,
          h("span", { class: "small muted" }, hace(deUtc(r.fecha_creacion)))),
        h("h3", {}, r.titulo), h("p", {}, r.descripcion),
        esAdmin ? h("span", { class: "small muted" }, `Reportó: ${nombreDe(mapa, r.usuario_id)}`) : null, bloqueEvidencias(r), pasos, nota, decision,
        esAdmin ? h("div", { class: "acciones-tec" }, h("button", { class: "btn mant-suave sm", type: "button", disabled: sinEnlace,
          title: sinEnlace ? (porAprobar ? "El técnico ya terminó: aprueba o devuelve el reporte" : "Este reporte ya está aprobado") : "Crear un enlace temporal para que un técnico lo atienda sin cuenta",
          onclick: () => abrirEnlaceTecnico(r) }, icono("llave", 16), "Enlace para técnico")) : null));
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
  let auto = null;      // autoguardado del formulario (se crea abajo, cuando ya existen todos los campos)
  const foto = selectorFoto({ titulo: "Agregar foto del daño (opcional)", ayuda: "Toma la foto con la cámara o elígela de tu galería", clave: `danio-${ctx.usuario.id}`,
    antesDeAbrir: () => auto?.foto(true), alCambiar: (f) => auto?.foto(!!f) });
  const usarBorrador = (b) => { titulo.value = b.titulo; desc.value = b.descripcion; desc.focus(); };
  auto = autoguardar({ usuarioId: ctx.usuario.id, nombre: "danio", campos: { titulo, desc } });
  const enviar = h("button", { class: "btn block", type: "submit" }, "Enviar reporte");
  const form = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (titulo.value.trim().length < 5) return toast("El título debe tener al menos 5 caracteres.", "error");
    if (desc.value.trim().length < 10) return toast("Describe el daño con al menos 10 caracteres.", "error");
    const fd = new FormData(); fd.append("titulo", titulo.value.trim()); fd.append("descripcion", desc.value.trim());
    if (foto.archivo()) fd.append("archivo_foto", foto.archivo());
    try {
      await conCarga(enviar, () => api("/mantenimiento/reportar-danio", { metodo: "POST", cuerpo: fd }));
      toast("Reporte enviado. ¡Gracias por avisar!");
      form.reset(); foto.limpiar(); auto.reiniciar();
      datos = await api("/mantenimiento/listar-danios"); pintar();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "card-titulo" }, h("h2", {}, "Reportar un daño")), botonResidente("danio", usarBorrador),
    h("div", { class: "field" }, titulo, h("label", { for: "titulo" }, "¿Qué pasó?")),
    h("div", { class: "field" }, desc, h("label", { for: "desc" }, "Cuéntanos los detalles")),
    foto.el, enviar);

  const llegado = tomarBorrador("danio");      // el asistente lo trajo desde otra pantalla
  if (llegado) { usarBorrador(llegado); toast("Borrador cargado. Revísalo, agrega una foto si quieres y envíalo."); }
  else auto.avisar();
  pintar();
  return h("div", {},
    cabecera(esAdmin ? "Mantenimiento" : "Reportar un daño", esAdmin ? "El técnico atiende cada reporte desde su enlace. Tú revisas su evidencia y apruebas al final." : "Cuéntanos qué se dañó en las zonas comunes y sigue cómo avanza la solución."),
    h("div", { class: "grid lados escalona" }, form,
      h("div", {}, h("div", { style: "margin-bottom:1rem" }, chips), rejilla)));
}
