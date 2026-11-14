// Arrendamientos. El propietario (Residente) registra y termina contratos de su inquilino; el administrador los aprueba o rechaza.
// Endpoints: GET/POST /arrendamientos/ · POST /arrendamientos/{id}/aprobar|rechazar|finalizar
import { api } from "../api.js";
import { h, icono, badge, iniciales, estadoVacio, toast, conCarga, modal, confirmar, fmtFechaCorta } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const hoyISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const fecha = (iso) => fmtFechaCorta(new Date(`${iso}T00:00:00`));   // fecha sin hora = día local

function vigencia(c) {
  if (c.estado === "Activo") return c.dias_restantes <= 30 ? `Acceso hasta el ${fecha(c.fecha_fin)} · quedan ${c.dias_restantes} día(s)` : `Acceso hasta el ${fecha(c.fecha_fin)}`;
  if (c.estado === "Pendiente") return `Contrato del ${fecha(c.fecha_inicio)} al ${fecha(c.fecha_fin)} · espera aprobación`;
  return `Contrato del ${fecha(c.fecha_inicio)} al ${fecha(c.fecha_fin)}${c.motivo_cierre ? ` · ${c.motivo_cierre}` : ""}`;
}

export async function render(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  let lista = await api("/arrendamientos/");
  let filtro = esAdmin ? "Pendiente" : "abiertos";
  const caja = h("div", { class: "lista" }); let chips = h("div");
  const abiertos = (c) => c.estado === "Pendiente" || c.estado === "Activo";

  async function recargar() { lista = await api("/arrendamientos/"); pintar(); }

  async function aprobar(c, btn) {
    try {
      const r = await conCarga(btn, () => api(`/arrendamientos/${c.id}/aprobar`, { metodo: "POST" }));
      const copiar = h("button", { class: "btn suave", onclick: async () => { try { await navigator.clipboard.writeText(r.password_temporal); toast("Clave copiada"); } catch { toast("No se pudo copiar; cópiala a mano.", "error"); } } }, "Copiar");
      const m = modal("Inquilino aprobado", h("div", {}, h("p", { class: "muted", style: "margin-bottom:1rem" }, r.mensaje),
        h("div", { class: "field" }, h("input", { id: "tmp-inq", readonly: true, value: r.password_temporal, class: "mono", placeholder: " ", onfocus: (e) => e.target.select() }), h("label", { for: "tmp-inq" }, "Clave temporal")),
        h("p", { class: "small muted" }, "Solo se muestra ahora. Si se pierde, restablécela desde Usuarios.")), { pie: [copiar, h("button", { class: "btn", onclick: () => m.cerrar() }, "Listo")] });
      await recargar();
    } catch (e) { toast(e.message, "error"); }
  }

  async function cerrar(c, rechazo = false) {
    const [titulo, texto, boton] = rechazo
      ? ["¿Rechazar este arrendamiento?", `${c.inquilino_nombre} no podrá ingresar a la aplicación.`, "Sí, rechazar"]
      : c.estado === "Pendiente" ? ["¿Cancelar el registro?", `Se cancela el registro de ${c.inquilino_nombre}.`, "Sí, cancelar"]
      : ["¿Terminar el arrendamiento?", `${c.inquilino_nombre} perderá el acceso de inmediato: se cierran sus sesiones, se revocan sus pases QR y se retiran sus visitantes autorizados.`, "Sí, terminar"];
    if (!(await confirmar(titulo, texto, boton, true))) return;
    try { await api(`/arrendamientos/${c.id}/${rechazo ? "rechazar" : "finalizar"}`, { metodo: "POST" }); toast(rechazo ? "Arrendamiento rechazado" : "Listo, el acceso quedó cerrado."); await recargar(); }
    catch (e) { toast(e.message, "error"); }
  }

  function tarjeta(c) {
    const acciones = [];
    if (esAdmin && c.estado === "Pendiente") acciones.push(h("button", { class: "btn sm", onclick: (e) => aprobar(c, e.currentTarget) }, icono("ok", 16), "Aprobar"),
      h("button", { class: "btn suave sm", onclick: () => cerrar(c, true) }, "Rechazar"));
    else if (abiertos(c)) acciones.push(h("button", { class: "btn suave sm", onclick: () => cerrar(c) }, c.estado === "Pendiente" ? "Cancelar" : "Terminar"));
    return h("div", { class: "item" }, h("div", { class: "avatar" }, iniciales(c.inquilino_nombre)),
      h("div", { class: "cuerpo" }, h("b", {}, c.inquilino_nombre), h("span", {}, c.inquilino_email),
        h("span", {}, esAdmin ? `${c.apartamento ?? "Sin apto."} · propietario: ${c.propietario_nombre}` : (c.apartamento ?? "")), h("span", {}, vigencia(c))),
      h("div", { class: "acciones" }, badge(c.estado), ...acciones));
  }

  function pintar() {
    const ops = esAdmin ? [["Pendiente", "Por aprobar"], ["Activo", "Activos"], ["todos", "Todos"]] : [["abiertos", "Vigentes"], ["todos", "Historial"]];
    const cuenta = (id) => lista.filter((c) => id === "todos" || (id === "abiertos" ? abiertos(c) : c.estado === id)).length;
    chips.replaceWith((chips = filtros(ops.map(([id, texto]) => ({ id, texto, n: cuenta(id) })), filtro, (f) => { filtro = f; pintar(); })));
    const v = lista.filter((c) => filtro === "todos" || (filtro === "abiertos" ? abiertos(c) : c.estado === filtro));
    caja.replaceChildren(...(v.length ? v.map(tarjeta) : [estadoVacio(esAdmin ? "Nada por aquí" : "Sin inquilinos", esAdmin ? "No hay arrendamientos en esta vista." : "Si arriendas tu apartamento, registra aquí a tu inquilino.")]));
  }

  function nuevo() {
    const f = {};
    const campo = (id, et, attrs = {}) => { f[id] = h("input", { id, placeholder: " ", ...attrs }); return h("div", { class: "field" }, f[id], h("label", { for: id }, et)); };
    const ok = h("button", { class: "btn", type: "submit", form: "f-inq" }, "Enviar para aprobación");
    const m = modal("Registrar inquilino", h("form", { id: "f-inq", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      const cuerpo = { nombre_completo: f.nombre.value.trim(), email: f.email.value.trim(), fecha_inicio: f.inicio.value, fecha_fin: f.fin.value };
      if (cuerpo.nombre_completo.length < 3) return toast("Escribe el nombre completo.", "error");
      if (!/^\S+@\S+\.\S+$/.test(cuerpo.email)) return toast("El correo no es válido.", "error");
      if (!cuerpo.fecha_inicio || !cuerpo.fecha_fin) return toast("Indica desde y hasta cuándo es el contrato.", "error");
      if (cuerpo.fecha_fin <= cuerpo.fecha_inicio) return toast("La fecha de fin debe ser posterior a la de inicio.", "error");
      try { await conCarga(ok, () => api("/arrendamientos/", { metodo: "POST", json: cuerpo })); m.cerrar(); toast("Enviado. La administración debe aprobarlo antes de que pueda ingresar."); filtro = "abiertos"; await recargar(); }
      catch (err) { toast(err.message, "error"); }
    } },
      campo("nombre", "Nombre completo del inquilino", { autocomplete: "off" }), campo("email", "Correo electrónico", { type: "email", autocomplete: "off" }),
      h("div", { class: "fila-campos" }, campo("inicio", "Inicio del contrato", { type: "date", value: hoyISO() }), campo("fin", "Fin del contrato", { type: "date", min: hoyISO() })),
      h("p", { class: "small muted" }, "Su acceso se cierra solo al terminar el contrato. Podrá reservar zonas, recibir paquetes, avisar visitas y radicar solicitudes; no ve cartera ni vota.")),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  }

  pintar();
  return h("div", {}, cabecera(esAdmin ? "Arrendamientos" : "Mis inquilinos", esAdmin ? "Aprueba los contratos que registran los propietarios." : "Registra a quien vive en tu apartamento por arrendamiento."),
    h("div", { class: "card" },
      esAdmin ? null : h("div", { class: "barra" }, h("div"), h("button", { class: "btn", onclick: nuevo }, icono("mas", 18), "Registrar inquilino")),
      h("div", { style: "margin-bottom:.5rem" }, chips), caja));
}
