// Votaciones y consultas del conjunto. VOTO SECRETO: el servidor guarda quién votó y cuántos votos tiene cada opción por separado.
// Endpoints: GET /votaciones/ · POST /votaciones/ · POST /{id}/votar · POST /{id}/cerrar · POST /{id}/anular · GET /{id}/participacion
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaHora, kpi } from "../ui.js";
import { cabecera } from "./comun.js";

const pc = (n) => Number(n ?? 0).toLocaleString("es-CO", { maximumFractionDigits: 4 });   // 0,8523 (coma decimal)

function faltan(d) {
  const ms = d - Date.now();
  if (ms <= 0) return "terminó";
  const min = Math.round(ms / 60000);
  if (min < 60) return `faltan ${min} min`;
  if (min < 1440) return `faltan ${Math.round(min / 60)} h`;
  return `faltan ${Math.round(min / 1440)} día(s)`;
}

function formularioNueva(alCrear) {
  const titulo = h("input", { id: "vt-titulo", placeholder: " ", maxlength: "120", required: true });
  const desc = h("textarea", { id: "vt-desc", placeholder: " ", maxlength: "1000" });
  const porDefecto = new Date(Date.now() + 3 * 86400e3); porDefecto.setMinutes(0, 0, 0);
  const aLocal = (d) => new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  const cierre = h("input", { id: "vt-cierre", type: "datetime-local", value: aLocal(porDefecto), required: true });
  const cajaOpc = h("div", { class: "opciones-voto" });
  let opciones = ["Sí", "No", "Me abstengo"], unoPor = "apartamento", vivo = false, alDia = false, pondera = false, resumenCoef = null;
  const infoCoef = h("p", { class: "small muted", hidden: true, style: "margin:.4rem 0 0 1.9rem" });

  const pintarOpc = () => cajaOpc.replaceChildren(...opciones.map((t, i) => h("div", { class: "fila-opcion" },
    h("input", { value: t, maxlength: "80", placeholder: `Opción ${i + 1}`, "aria-label": `Opción ${i + 1}`, oninput: (e) => { opciones[i] = e.target.value; } }),
    opciones.length > 2 ? h("button", { type: "button", class: "btn suave sm icono", "aria-label": "Quitar opción", onclick: () => { opciones.splice(i, 1); pintarOpc(); } }, icono("x", 16)) : null)),
  opciones.length < 8 ? h("button", { type: "button", class: "btn suave sm", onclick: () => { opciones.push(""); pintarOpc(); } }, icono("mas", 16), "Agregar opción") : null);

  const chips = h("div", { class: "chips", role: "group", "aria-label": "Quién vota" });
  const pintarChips = () => chips.replaceChildren(...[["apartamento", "Un voto por apartamento"], ["persona", "Un voto por persona"]].map(([id, t]) =>
    h("button", { class: "chip", type: "button", "aria-pressed": String(unoPor === id), disabled: pondera && id === "persona", onclick: () => { unoPor = id; pintarChips(); } }, t)));
  const pintarInfoCoef = () => {
    infoCoef.hidden = !pondera;
    if (!pondera) return;
    if (!resumenCoef) { infoCoef.textContent = "Revisando los coeficientes…"; return; }
    const r = resumenCoef;
    infoCoef.className = `small ${r.completo ? "muted" : "texto-error"}`;
    infoCoef.textContent = r.completo ? `Listo: los ${r.apartamentos} apartamentos tienen coeficiente y suman ${pc(r.total)} %.`
      : r.sin_coeficiente.length ? `Faltan ${r.sin_coeficiente.length} de ${r.apartamentos} apartamentos sin coeficiente (por ejemplo: ${r.sin_coeficiente.slice(0, 3).join(", ")}). Cárgalos en «Usuarios» o en «Cargar datos» antes de publicar.`
      : `Los coeficientes suman ${pc(r.total)} % y deberían sumar 100 %. Puedes publicar, pero revisa la suma.`;
  };
  const caja = (texto, ayuda, alCambiar) => h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => alCambiar(e.target.checked) }), h("span", {}, h("b", {}, texto), h("small", {}, ayuda)));

  const ok = h("button", { class: "btn", type: "submit", form: "f-votacion" }, icono("ok", 16), "Publicar votación");
  const m = modal("Nueva votación", h("form", { id: "f-votacion", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    const limpias = opciones.map((o) => o.trim()).filter(Boolean);
    if (titulo.value.trim().length < 3) return toast("Escribe la pregunta o el título.", "error");
    if (limpias.length < 2) return toast("Agrega al menos dos opciones.", "error");
    if (!cierre.value) return toast("Indica cuándo cierra la votación.", "error");
    try {
      await conCarga(ok, () => api("/votaciones/", { metodo: "POST", json: { titulo: titulo.value.trim(), descripcion: desc.value.trim() || null, opciones: limpias,
        fecha_cierre: new Date(cierre.value).toISOString(), un_voto_por: unoPor, resultados_en_vivo: vivo, exige_al_dia: alDia, ponderada: pondera } }));
      m.cerrar(); toast("Votación publicada. Los residentes ya recibieron el aviso."); alCrear();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "field" }, titulo, h("label", { for: "vt-titulo" }, "Pregunta o título")),
    h("div", { class: "field" }, desc, h("label", { for: "vt-desc" }, "Explicación (opcional)")),
    h("div", { class: "etiqueta-seccion" }, "Opciones"), cajaOpc,
    h("div", { class: "field", style: "margin-top:1rem" }, cierre, h("label", { for: "vt-cierre" }, "Cierra el")),
    h("div", { class: "etiqueta-seccion" }, "Quién vota"), chips,
    caja("Mostrar resultados mientras se vota", "Si no, se publican solo al cerrar (recomendado).", (v) => { vivo = v; }),
    caja("Solo residentes al día con la administración", "Para decisiones de asamblea.", (v) => { alDia = v; }),
    caja("Votar por coeficiente de copropiedad (Ley 675)", "Cada apartamento vota con su porcentaje y se calcula el quórum. Cuenta un voto por apartamento.", (v) => {
      pondera = v; if (v) unoPor = "apartamento"; pintarChips(); pintarInfoCoef();
      if (v && !resumenCoef) api("/usuarios/coeficientes/resumen").then((r) => { resumenCoef = r; pintarInfoCoef(); }).catch(() => { infoCoef.textContent = "No pude revisar los coeficientes ahora; el servidor lo validará al publicar."; });
    }), infoCoef,
    h("p", { class: "small muted", style: "margin-top:.8rem" }, "El voto es secreto: ni la administración puede ver qué votó cada persona.")),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  pintarOpc(); pintarChips(); titulo.focus();
}

async function verParticipacion(v) {
  const caja = h("div", {}, h("div", { class: "esq", style: "height:120px" }));
  modal(`Participación · ${v.titulo}`, caja);
  try {
    const p = await api(`/votaciones/${v.id}/participacion`);
    const lista = (t, xs) => h("div", { style: "margin-bottom:1rem" }, h("b", {}, `${t} (${xs.length})`), xs.length ? h("ul", { class: "lista-simple" }, xs.map((x) => h("li", {}, x))) : h("p", { class: "small muted" }, "Nadie."));
    const quorum = p.coeficiente_participaron != null
      ? h("p", { class: "small", style: "margin-bottom:1rem" }, h("b", {}, `Quórum: ${pc(p.coeficiente_participaron)} % del coeficiente`), ` ya votó · falta ${pc(p.coeficiente_pendientes)} %.`) : null;
    caja.replaceChildren(quorum, lista("Ya votaron", p.participaron), lista("Faltan por votar", p.pendientes), h("p", { class: "small muted" }, "Solo se muestra quién votó, nunca qué votó."));
  } catch (e) { caja.replaceChildren(h("p", { class: "muted" }, e.message)); }
}

function tarjeta(v, esAdmin, recargar) {
  const cierre = deUtc(v.fecha_cierre), abierta = v.estado === "Abierta";
  const pct = v.elegibles ? Math.min(100, Math.round((v.participacion * 100) / v.elegibles)) : 0;
  let elegida = null;
  const cuerpo = h("div", { class: "opciones-voto" });

  const resultados = () => {
    const max = Math.max(...v.opciones.map((o) => o.votos ?? 0));
    return [...v.opciones.map((o) => h("div", { class: `resultado-op ${max > 0 && o.votos === max ? "gana" : ""}` },
      h("div", { class: "fila" }, h("b", {}, o.texto), h("span", {}, v.ponderada ? `${pc(o.coeficiente)} % del coeficiente · ${o.votos} voto(s) · ${pc(o.porcentaje)}%` : `${o.votos} · ${o.porcentaje}%`)),
      h("div", { class: "barra-progreso" }, h("i", { style: `width:${o.porcentaje}%` })))),
    h("p", { class: "small muted" }, v.ponderada ? `${v.total_votos} apartamento(s) votaron. El porcentaje es sobre el coeficiente que votó.` : `${v.total_votos} voto(s) en total.`)];
  };

  const pintar = () => {
    if (v.puede_votar) {
      // Opciones para marcar (radio). Si la votación muestra resultados en vivo, se ven debajo sin quitar la posibilidad de votar.
      const marcar = (id) => { elegida = id; pintar(); };
      const opciones = v.opciones.map((o) => h("button", { type: "button", role: "radio", class: "opcion-voto", "aria-checked": String(elegida === o.id),
        onclick: () => marcar(o.id), onkeydown: (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); marcar(o.id); } } },
        h("span", { class: "marca", "aria-hidden": "true" }), h("span", { class: "texto" }, o.texto)));
      cuerpo.replaceChildren(h("div", { class: "grupo-radio", role: "radiogroup", "aria-label": "Elige tu opción" }, opciones),
        ...(v.resultados_visibles ? [h("div", { class: "etiqueta-seccion" }, "Resultados en vivo"), ...resultados()] : []));
    } else if (v.resultados_visibles) {
      cuerpo.replaceChildren(...resultados(), v.ya_vote ? h("p", { class: "small muted" }, "Tu voto quedó registrado.") : null);
    } else {
      cuerpo.replaceChildren(h("p", { class: "small muted" }, v.ya_vote ? "Tu voto quedó registrado. Los resultados se publican al cerrar." : v.motivo_no_puede ?? ""));
    }
  };
  pintar();

  const votar = h("button", { class: "btn", type: "button", onclick: async () => {
    if (!elegida) return toast("Elige una opción.", "error");
    const texto = v.opciones.find((o) => o.id === elegida).texto;
    if (!(await confirmar("¿Confirmas tu voto?", `Votarás «${texto}». Tu voto es secreto y no se puede cambiar.${v.ponderada ? ` Tu voto vale ${pc(v.tu_coeficiente)} % del coeficiente de copropiedad.` : v.un_voto_por === "apartamento" ? " Cuenta como el voto de tu apartamento." : ""}`, "Sí, votar"))) return;
    try { await conCarga(votar, () => api(`/votaciones/${v.id}/votar`, { metodo: "POST", json: { opcion_id: elegida } })); toast("Voto registrado. ¡Gracias por participar!"); recargar(); }
    catch (e) { toast(e.message, "error"); recargar(); }
  } }, icono("urna", 18), "Votar");

  const admin = esAdmin && abierta ? [
    h("button", { class: "btn suave sm", onclick: async () => { if (await confirmar("¿Cerrar la votación ahora?", "Se publican los resultados y se avisa a los residentes.", "Sí, cerrar")) { try { await api(`/votaciones/${v.id}/cerrar`, { metodo: "POST" }); toast("Votación cerrada"); recargar(); } catch (e) { toast(e.message, "error"); } } } }, "Cerrar ahora"),
    h("button", { class: "btn peligro sm", onclick: async () => { if (await confirmar("¿Anular la votación?", "No se publicarán resultados. Queda en la auditoría.", "Sí, anular", true)) { try { await api(`/votaciones/${v.id}/anular`, { metodo: "POST" }); toast("Votación anulada"); recargar(); } catch (e) { toast(e.message, "error"); } } } }, "Anular")] : [];

  return h("article", { class: `card votacion ${abierta ? "" : "terminada"}` },
    h("div", { class: "card-titulo" }, h("h2", {}, v.titulo), badge(v.estado)),
    v.descripcion ? h("p", { class: "muted" }, v.descripcion) : null,
    h("p", { class: "small muted" }, abierta ? `Cierra ${fmtFechaHora(cierre)} (${faltan(cierre)})` : v.estado === "Anulada" ? "Votación anulada" : `Cerró ${fmtFechaHora(cierre)}`,
      ` · ${v.ponderada ? "por coeficiente de copropiedad" : v.un_voto_por === "apartamento" ? "un voto por apartamento" : "un voto por persona"}${v.exige_al_dia ? " · solo residentes al día" : ""}`),
    v.ponderada && v.tu_coeficiente != null && !esAdmin ? h("p", { class: "small" }, `Tu voto vale `, h("b", {}, `${pc(v.tu_coeficiente)} %`), " del coeficiente.") : null,
    cuerpo,
    h("div", { class: "participacion" }, h("div", { class: "barra-progreso" }, h("i", { style: `width:${v.ponderada ? Math.min(100, v.quorum_coeficiente) : pct}%` })),
      h("span", { class: "small muted" }, v.ponderada ? `Quórum: ${pc(v.quorum_coeficiente)} % del coeficiente · han votado ${v.participacion} de ${v.elegibles} apartamentos` : `Han votado ${v.participacion} de ${v.elegibles}`)),
    h("div", { class: "acciones-fila" }, v.puede_votar ? votar : null, esAdmin ? h("button", { class: "btn suave sm", onclick: () => verParticipacion(v) }, icono("usuarios", 16), "Quién votó") : null, ...admin));
}

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  const cont = h("div", { class: "lista-votaciones" });
  const resumen = h("div", { class: "kpis" });
  async function cargar() {
    const datos = await api("/votaciones/");
    const abiertas = datos.filter((v) => v.estado === "Abierta");
    resumen.replaceChildren(kpi(esAdmin ? "Votaciones abiertas" : "Por votar", esAdmin ? abiertas.length : abiertas.filter((v) => v.puede_votar).length, { destacado: true }));
    cont.replaceChildren(...(datos.length ? datos.map((v) => tarjeta(v, esAdmin, cargar))
      : [estadoVacio("Aún no hay votaciones", esAdmin ? "Crea la primera con «Nueva votación»." : "Cuando la administración abra una consulta, la verás aquí.")]));
  }
  await cargar();
  return h("div", {}, cabecera("Votaciones", "Participa en las decisiones del conjunto. Tu voto es secreto."),
    esAdmin ? h("div", { style: "margin-bottom:1rem" }, h("button", { class: "btn", onclick: () => formularioNueva(cargar) }, icono("mas", 18), "Nueva votación")) : null,
    resumen, cont);
}
