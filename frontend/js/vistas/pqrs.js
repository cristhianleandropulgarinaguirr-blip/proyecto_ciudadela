// PQRS: peticiones, quejas, reclamos y sugerencias.
// Endpoints: GET/POST /pqrs/ · PATCH /pqrs/{id} (administrador) · GET /reportes/pqrs.xlsx (administrador)
import { api } from "../api.js";
import { botonResidente, tomarBorrador } from "../asistente.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, deUtc, hace, fmtFechaHora, kpi } from "../ui.js";
import { cabecera, filtros } from "./comun.js";
import { autoguardar } from "../autoguardado.js";
import { descargar, hoyArchivo } from "../descargas.js";

const TIPOS = [["Peticion", "Petición"], ["Queja", "Queja"], ["Reclamo", "Reclamo"], ["Sugerencia", "Sugerencia"]];
const etiquetaTipo = (t) => TIPOS.find(([k]) => k === t)?.[1] ?? t;
const AYUDA = { Peticion: "Solicitas algo a la administración.", Queja: "Algo no funcionó bien o te molesta.", Reclamo: "Hay un cobro o servicio que no estás de acuerdo.", Sugerencia: "Tienes una idea para mejorar." };

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  const cargar = () => api("/pqrs/", { params: { limite: 300 } });
  let datos = await cargar(), filtro = esAdmin ? "pendientes" : "todas", texto = "";
  const lista = h("div", { class: "lista" }), resumen = h("div", { class: "kpis" });
  let chips = h("div");
  const abierta = (p) => p.estado === "Radicada" || p.estado === "En tramite";
  async function recargar() { datos = await cargar(); pintar(); }

  function responder(p) {
    const estado = h("select", { id: "pq-estado" }, [["En tramite", "En trámite (aún trabajando en ello)"], ["Resuelta", "Resuelta (ya tiene respuesta)"], ["Cerrada", "Cerrada"]]
      .map(([v, t]) => h("option", { value: v, selected: v === (p.estado === "Radicada" ? "Resuelta" : p.estado) }, t)));
    const resp = h("textarea", { id: "pq-resp", placeholder: " ", maxlength: "2000" }); resp.value = p.respuesta ?? "";
    const guardar = h("button", { class: "btn", type: "submit", form: "f-pqrs" }, "Guardar");
    const m = modal(`${p.radicado} · ${p.asunto}`, h("form", { id: "f-pqrs", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (estado.value === "Resuelta" && resp.value.trim().length < 5) return toast("Escribe la respuesta para el residente.", "error");
      const cuerpo = { estado: estado.value }; if (resp.value.trim() && resp.value.trim() !== (p.respuesta ?? "")) cuerpo.respuesta = resp.value.trim();
      try { await conCarga(guardar, () => api(`/pqrs/${p.id}`, { metodo: "PATCH", json: cuerpo })); m.cerrar(); toast("Solicitud actualizada. El residente fue avisado."); await recargar(); }
      catch (err) { toast(err.message, "error"); }
    } },
      h("p", { class: "muted small", style: "margin-bottom:.4rem" }, `${etiquetaTipo(p.tipo)} de ${p.usuario_nombre}${p.apartamento ? ` · ${p.apartamento}` : ""}`),
      h("p", { class: "texto-largo", style: "margin-bottom:1rem" }, p.descripcion),
      h("div", { class: "field" }, estado, h("label", { for: "pq-estado" }, "Estado")),
      h("div", { class: "field" }, resp, h("label", { for: "pq-resp" }, "Respuesta para el residente"))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
  }

  function pintar() {
    const n = (f) => (f === "todas" ? datos.length : f === "pendientes" ? datos.filter(abierta).length : datos.filter((p) => p.estado === f).length);
    resumen.replaceChildren(kpi(esAdmin ? "Por atender" : "Abiertas", n("pendientes"), { destacado: true, alerta: esAdmin && n("pendientes") > 0 }), kpi("Resueltas", n("Resuelta")));
    chips.replaceWith((chips = filtros([{ id: "pendientes", texto: "Abiertas", n: n("pendientes") }, { id: "Resuelta", texto: "Resueltas", n: n("Resuelta") }, { id: "todas", texto: "Todas", n: n("todas") }], filtro, (f) => { filtro = f; pintar(); })));
    const q = texto.trim().toLowerCase();
    const v = datos.filter((p) => (filtro === "todas" || (filtro === "pendientes" ? abierta(p) : p.estado === filtro))
      && (!q || [p.asunto, p.radicado, p.usuario_nombre, p.apartamento].some((x) => (x ?? "").toLowerCase().includes(q))));
    lista.replaceChildren(...(v.length ? v.map((p) => h("article", { class: "pqrs" },
      h("div", { class: "pqrs-cab" }, h("div", {}, h("b", {}, p.asunto), h("span", { class: "small muted", style: "display:block" },
        [p.radicado, etiquetaTipo(p.tipo), esAdmin ? `${p.usuario_nombre}${p.apartamento ? ` · ${p.apartamento}` : ""}` : null, hace(deUtc(p.fecha_creacion))].filter(Boolean).join(" · "))), badge(p.estado)),
      h("p", { class: "texto-largo" }, p.descripcion),
      p.respuesta ? h("div", { class: "respuesta" }, h("b", {}, `Respuesta${p.respondido_por ? ` de ${p.respondido_por}` : ""}`), h("p", { class: "texto-largo" }, p.respuesta),
        p.fecha_respuesta ? h("small", { class: "muted" }, fmtFechaHora(deUtc(p.fecha_respuesta))) : null) : null,
      esAdmin && p.estado !== "Cerrada" ? h("div", { class: "acciones", style: "margin-top:.6rem" }, h("button", { class: "btn suave sm", onclick: () => responder(p) }, icono("editar", 16), p.respuesta ? "Editar respuesta" : "Responder")) : null))
      : [estadoVacio(esAdmin ? "Sin solicitudes en esta vista" : "Aún no has enviado solicitudes", esAdmin ? "Cuando un residente radique una PQRS aparecerá aquí." : "Usa el formulario para enviar una petición, queja, reclamo o sugerencia.")]));
  }

  // ----- Formulario del residente -----
  let formulario = null;
  if (!esAdmin) {
    let tipo = "Peticion", auto = null;      // `auto`: autoguardado del formulario (se crea abajo)
    const usarBorrador = (b) => { tipo = b.tipo; asunto.value = b.asunto; desc.value = b.descripcion; pintarTipos(); asunto.focus(); };
    const asunto = h("input", { id: "pq-asunto", placeholder: " ", maxlength: "100", autocomplete: "off" });
    const desc = h("textarea", { id: "pq-desc", placeholder: " ", maxlength: "2000" });
    const tipos = h("div", { class: "chips", role: "group", "aria-label": "Tipo de solicitud" });
    const ayuda = h("p", { class: "small muted", style: "margin:.5rem 0 1rem" });
    const pintarTipos = () => { tipos.replaceChildren(...TIPOS.map(([v, t]) => h("button", { class: "chip", type: "button", "aria-pressed": String(v === tipo), onclick: () => { tipo = v; pintarTipos(); auto?.programar(); } }, t))); ayuda.textContent = AYUDA[tipo]; };
    const enviar = h("button", { class: "btn block", type: "submit" }, icono("flecha", 18), "Enviar solicitud");
    formulario = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (asunto.value.trim().length < 5) return toast("Escribe un asunto de al menos 5 caracteres.", "error");
      if (desc.value.trim().length < 10) return toast("Cuéntanos un poco más (mínimo 10 caracteres).", "error");
      try {
        const r = await conCarga(enviar, () => api("/pqrs/", { metodo: "POST", json: { tipo, asunto: asunto.value.trim(), descripcion: desc.value.trim() } }));
        toast(`Solicitud radicada: ${r.radicado}`); asunto.value = ""; desc.value = ""; auto.reiniciar(); filtro = "pendientes"; await recargar();
      } catch (err) { toast(err.message, "error"); }
    } },
      h("div", { class: "card-titulo" }, h("h2", {}, "Nueva solicitud")), botonResidente("pqrs", usarBorrador), tipos, ayuda,
      h("div", { class: "field" }, asunto, h("label", { for: "pq-asunto" }, "Asunto")),
      h("div", { class: "field" }, desc, h("label", { for: "pq-desc" }, "Cuéntanos qué pasó o qué necesitas")), enviar);
    auto = autoguardar({ usuarioId: ctx.usuario.id, nombre: "pqrs", campos: { asunto, desc }, extra: () => ({ tipo }),
      alRestaurar: (e) => { if (TIPOS.some(([v]) => v === e.tipo)) tipo = e.tipo; } });
    pintarTipos();
    const llegado = tomarBorrador("pqrs");      // el asistente lo trajo desde otra pantalla
    if (llegado) { usarBorrador(llegado); toast("Borrador cargado. Revísalo y envíalo cuando estés de acuerdo."); }
    else auto.avisar();
  }

  pintar();
  const buscador = h("input", { type: "search", placeholder: "Buscar", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  const excel = esAdmin ? h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, "/reportes/pqrs.xlsx", `pqrs_${hoyArchivo()}.xlsx`, { aviso: "PQRS exportadas a Excel." }) }, icono("descarga", 16), "Exportar a Excel") : null;
  return h("div", {},
    cabecera(esAdmin ? "PQRS" : "Quejas y sugerencias", esAdmin ? "Peticiones, quejas, reclamos y sugerencias de los residentes." : "Cuéntale a la administración lo que necesitas, lo que no te gustó o tus ideas, y sigue su respuesta."),
    h("div", { class: formulario ? "grid lados escalona" : "escalona" }, formulario,
      h("div", {}, resumen, h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, esAdmin ? "Solicitudes" : "Mis solicitudes"), h("div", { class: "barra-mini" }, excel, h("div", { class: "buscador" }, icono("buscar"), buscador))),
        h("div", { style: "margin-bottom:1rem" }, chips), lista))));
}
