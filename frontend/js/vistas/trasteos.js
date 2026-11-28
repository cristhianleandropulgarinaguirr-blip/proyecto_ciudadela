// Trasteos (mudanzas): solicitud → validación de paz y salvo → aprobación del administrador → alerta a la portería → inicio y fin que registra el guardia.
// Endpoints: GET /trasteos · POST /trasteos · POST /trasteos/{id}/aprobar · /rechazar · /cancelar · /iniciar · /finalizar
// Un solo archivo para todos los roles; cada rol ve y hace solo lo suyo (la API valida igual con 403).
import { locale } from "../i18n.js";
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, kpi } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const DIA = (d) => d.toLocaleDateString(locale(), { weekday: "short", day: "numeric", month: "short" });
const HORA = (d) => d.toLocaleTimeString(locale(), { hour: "numeric", minute: "2-digit" });
const aLocal = (d) => new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
const esHoy = (d) => d.toDateString() === new Date().toDateString();

function ventana(t) {
  const a = deUtc(t.fecha_inicio), b = deUtc(t.fecha_fin);
  return a.toDateString() === b.toDateString() ? `${DIA(a)} · ${HORA(a)} a ${HORA(b)}` : `${DIA(a)} ${HORA(a)} → ${DIA(b)} ${HORA(b)}`;
}

// ---------------------------------------------------------------- formulario de solicitud (residente / inquilino)
function formularioSolicitud(alCrear) {
  let tipo = "Salida";
  const inicio = new Date(Date.now() + 24 * 3600e3); inicio.setMinutes(0, 0, 0);
  const fin = new Date(inicio.getTime() + 4 * 3600e3);
  const desde = h("input", { id: "tr-desde", type: "datetime-local", value: aLocal(inicio), required: true });
  const hasta = h("input", { id: "tr-hasta", type: "datetime-local", value: aLocal(fin), required: true });
  const empresa = h("input", { id: "tr-empresa", placeholder: " ", maxlength: "80" });
  const placa = h("input", { id: "tr-placa", placeholder: " ", maxlength: "15", autocapitalize: "characters" });
  const obs = h("textarea", { id: "tr-obs", placeholder: " ", maxlength: "300" });
  const ayuda = h("p", { class: "small muted", style: "margin:.4rem 0 1rem" });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Tipo de trasteo" });
  const pintar = () => {
    chips.replaceChildren(...[["Salida", "Voy a sacar muebles"], ["Entrada", "Voy a meter muebles"]].map(([id, t]) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(tipo === id), onclick: () => { tipo = id; pintar(); } }, t)));
    ayuda.textContent = tipo === "Salida"
      ? "Para sacar muebles el apartamento debe estar al día con la administración. El sistema genera tu paz y salvo automáticamente; si hay saldo pendiente, no se podrá solicitar."
      : "Para meter muebles solo necesitas la aprobación de la administración.";
  };

  const ok = h("button", { class: "btn", type: "submit", form: "f-trasteo" }, icono("ok", 16), "Enviar solicitud");
  const m = modal("Solicitar un trasteo", h("form", { id: "f-trasteo", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (!desde.value || !hasta.value) return toast("Indica desde y hasta qué hora.", "error");
    const a = new Date(desde.value), b = new Date(hasta.value);
    if (b <= a) return toast("La hora final debe ser posterior a la de inicio.", "error");
    try {
      await conCarga(ok, () => api("/trasteos", { metodo: "POST", json: { tipo, fecha_inicio: a.toISOString(), fecha_fin: b.toISOString(),
        empresa: empresa.value.trim() || null, placa: placa.value.trim() || null, observaciones: obs.value.trim() || null } }));
      m.cerrar(); toast("Solicitud enviada. Te avisamos cuando la administración la revise."); alCrear();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "etiqueta-seccion", style: "margin-top:0" }, "¿Qué vas a hacer?"), chips, ayuda,
    h("div", { class: "fila-campos" }, h("div", { class: "field" }, desde, h("label", { for: "tr-desde" }, "Desde")), h("div", { class: "field" }, hasta, h("label", { for: "tr-hasta" }, "Hasta"))),
    h("div", { class: "fila-campos" }, h("div", { class: "field" }, empresa, h("label", { for: "tr-empresa" }, "Empresa de trasteos (opcional)")), h("div", { class: "field" }, placa, h("label", { for: "tr-placa" }, "Placa del vehículo (opcional)"))),
    h("div", { class: "field" }, obs, h("label", { for: "tr-obs" }, "Observaciones (opcional)")),
    h("p", { class: "small muted" }, "Máximo 12 horas por solicitud. La portería solo deja pasar el trasteo dentro de este horario.")),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  pintar();
  desde.focus();
}

// ---------------------------------------------------------------- tarjeta de un trasteo
function tarjeta(t, rol, recargar) {
  const admin = rol === "Administrador", guardia = rol === "Guardia";
  const accion = async (ruta, cuerpo, ok) => { try { await api(`/trasteos/${t.id}/${ruta}`, { metodo: "POST", json: cuerpo }); toast(ok); recargar(); } catch (e) { toast(e.message, "error"); recargar(); } };
  const btns = [];

  if (admin && t.estado === "Pendiente") {
    btns.push(h("button", { class: "btn", onclick: async () => {
      const texto = t.tipo === "Salida" ? "Se avisa a la portería. El paz y salvo se vuelve a comprobar ahora." : "Se avisa a la portería.";
      if (!(await confirmar(t.simultaneo_con ? "Ya hay otro trasteo en ese horario" : "¿Aprobar el trasteo?",
        t.simultaneo_con ? `El apartamento ${t.simultaneo_con} ya tiene un trasteo aprobado en esa franja. ¿Aprobar este también?` : texto, "Sí, aprobar"))) return;
      accion("aprobar", { permitir_simultaneo: Boolean(t.simultaneo_con) }, "Trasteo aprobado. Portería ya fue avisada.");
    } }, icono("ok", 16), "Aprobar"));
    btns.push(h("button", { class: "btn peligro sm", onclick: () => pedirMotivo("Rechazar la solicitud", "Explícale al residente por qué no se aprueba.", "Rechazar", true, (motivo) => accion("rechazar", { motivo }, "Solicitud rechazada")) }, "Rechazar"));
  }
  if (!guardia && ["Pendiente", "Aprobado"].includes(t.estado)) {
    btns.push(h("button", { class: "btn suave sm", onclick: async () => { if (await confirmar("¿Cancelar el trasteo?", t.estado === "Aprobado" ? "Ya estaba aprobado: se le avisa a la portería." : "Se retira la solicitud.", "Sí, cancelar", true)) accion("cancelar", null, "Trasteo cancelado"); } }, "Cancelar"));
  }
  if ((guardia || admin) && t.estado === "Aprobado") {
    btns.push(h("button", { class: "btn", disabled: !t.puede_iniciar, onclick: async () => {
      if (await confirmar(`¿Dejar ${t.tipo === "Salida" ? "salir" : "entrar"} el trasteo?`, `${t.apartamento ?? ""}${t.empresa ? ` · ${t.empresa}` : ""}${t.placa ? ` · placa ${t.placa}` : ""}`, "Sí, iniciar")) accion("iniciar", null, "Inicio registrado");
    } }, icono("carro", 16), t.tipo === "Salida" ? "Autorizar salida" : "Autorizar entrada"));
  }
  if ((guardia || admin) && t.estado === "En curso") {
    btns.push(h("button", { class: "btn", onclick: async () => { if (await confirmar("¿Terminó el trasteo?", "Se registra como completado.", "Sí, terminó")) accion("finalizar", null, "Trasteo completado"); } }, icono("ok", 16), "Registrar fin"));
  }

  const hoy = esHoy(deUtc(t.fecha_inicio)) && ["Aprobado", "En curso"].includes(t.estado);
  return h("article", { class: `card trasteo ${["Pendiente", "Aprobado", "En curso"].includes(t.estado) ? "" : "terminada"}` },
    h("div", { class: "card-titulo" }, h("h2", {}, `${t.tipo === "Salida" ? "Salida" : "Entrada"} de trasteo · ${t.apartamento ?? "—"}`), h("div", { class: "etiquetas" }, hoy ? h("span", { class: "badge laton" }, "Hoy") : null, badge(t.estado))),
    h("p", { class: "muted" }, icono("reloj", 14), " ", ventana(t)),
    h("p", { class: "small muted" }, [t.empresa, t.placa ? `placa ${t.placa}` : null, admin || guardia ? `pide ${t.solicitante}` : null].filter(Boolean).join(" · ") || "Sin empresa ni placa registradas"),
    t.observaciones ? h("p", { class: "small" }, t.observaciones) : null,
    t.tipo === "Salida" && t.paz_salvo_folio ? h("p", { class: "small" }, "Paz y salvo ", h("b", {}, t.paz_salvo_folio), " ", badge(t.paz_salvo_estado)) : null,
    t.motivo ? h("p", { class: "small muted" }, `Motivo: ${t.motivo}`) : null,
    admin && t.simultaneo_con ? h("p", { class: "small texto-error" }, `Ojo: el apartamento ${t.simultaneo_con} ya tiene un trasteo aprobado en esa franja.`) : null,
    t.estado === "Aprobado" && !t.puede_iniciar && t.motivo_no_puede_iniciar ? h("p", { class: `small ${t.motivo_no_puede_iniciar.includes("paz y salvo") ? "texto-error" : "muted"}` }, t.motivo_no_puede_iniciar) : null,
    t.inicio_real ? h("p", { class: "small muted" }, `Inició ${HORA(deUtc(t.inicio_real))}${t.fin_real ? ` · terminó ${HORA(deUtc(t.fin_real))}` : ""}`) : null,
    btns.length ? h("div", { class: "acciones-fila" }, ...btns) : null);
}

function pedirMotivo(titulo, texto, boton, peligro, alEnviar) {
  const campo = h("textarea", { id: "tr-motivo", placeholder: " ", maxlength: "200" });
  const ok = h("button", { class: `btn ${peligro ? "peligro" : ""}`, type: "submit", form: "f-motivo" }, boton);
  const m = modal(titulo, h("form", { id: "f-motivo", novalidate: true, onsubmit: (e) => {
    e.preventDefault();
    if (campo.value.trim().length < 3) return toast("Escribe el motivo (mínimo 3 letras).", "error");
    m.cerrar(); alEnviar(campo.value.trim());
  } }, h("p", { class: "muted", style: "margin-bottom:1rem" }, texto), h("div", { class: "field" }, campo, h("label", { for: "tr-motivo" }, "Motivo"))),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Volver"), ok] });
  campo.focus();
}

// ---------------------------------------------------------------- pantalla
export async function render(ctx) {
  const rol = ctx.usuario.rol, admin = rol === "Administrador", guardia = rol === "Guardia";
  let datos = [], filtro = admin ? "Pendiente" : "todos";
  const cont = h("div", { class: "lista-votaciones" });
  const resumen = h("div", { class: "kpis" });
  let chips = h("div");

  const pintar = () => {
    const abiertos = datos.filter((t) => ["Pendiente", "Aprobado", "En curso"].includes(t.estado));
    if (guardia) resumen.replaceChildren(kpi("Trasteos de hoy", datos.filter((t) => esHoy(deUtc(t.fecha_inicio))).length, { destacado: true }), kpi("Próximos 7 días", datos.length));
    else if (admin) resumen.replaceChildren(kpi("Por aprobar", datos.filter((t) => t.estado === "Pendiente").length, { destacado: true, alerta: true }), kpi("Aprobados", datos.filter((t) => t.estado === "Aprobado").length));
    else resumen.replaceChildren(kpi("Solicitudes abiertas", abiertos.length, { destacado: true }));
    if (admin) chips.replaceWith((chips = filtros([{ id: "Pendiente", texto: "Por aprobar", n: datos.filter((t) => t.estado === "Pendiente").length },
      { id: "Aprobado", texto: "Aprobados", n: datos.filter((t) => t.estado === "Aprobado").length }, { id: "todos", texto: "Todos", n: datos.length }], filtro, (f) => { filtro = f; pintar(); })));
    const lista = admin && filtro !== "todos" ? datos.filter((t) => t.estado === filtro) : datos;
    cont.replaceChildren(...(lista.length ? lista.map((t) => tarjeta(t, rol, cargar))
      : [estadoVacio(guardia ? "No hay trasteos autorizados" : admin ? "No hay trasteos en esta lista" : "Aún no has solicitado trasteos",
        guardia ? "Cuando la administración apruebe uno, te llega un aviso y aparece aquí." : admin ? "Las solicitudes de los residentes aparecen aquí." : "Pide uno con «Solicitar trasteo».")]));
  };
  async function cargar() { datos = await api("/trasteos"); pintar(); }
  await cargar();

  const texto = guardia ? "Trasteos aprobados por la administración. Verifica el horario y el paz y salvo antes de dejar pasar."
    : admin ? "Aprueba o rechaza las solicitudes. En las salidas el paz y salvo se comprueba solo."
    : "Solicita la entrada o salida de tu trasteo. La portería recibe el aviso cuando se aprueba.";
  return h("div", {}, cabecera("Trasteos", texto),
    !admin && !guardia ? h("div", { style: "margin-bottom:1rem" }, h("button", { class: "btn", onclick: () => formularioSolicitud(cargar) }, icono("mas", 18), "Solicitar trasteo")) : null,
    resumen, admin ? h("div", { style: "margin-bottom:.8rem" }, chips) : null, cont);
}
