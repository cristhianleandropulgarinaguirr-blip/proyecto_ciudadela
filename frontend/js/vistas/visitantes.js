// Visitantes autorizados: personas de confianza que el residente deja registradas para que portería las deje pasar.
// Endpoints: GET/POST /visitantes-autorizados/ · PATCH/DELETE /visitantes-autorizados/{id}
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaHora, fmtFechaCorta } from "../ui.js";
import { cabecera } from "./comun.js";

export const TIPOS = [["Familiar", "Familiar"], ["Amigo", "Amigo"], ["Servicio domestico", "Servicio doméstico"], ["Cuidador", "Cuidador"], ["Contratista", "Contratista"], ["Otro", "Otro"]];
export const etiquetaTipo = (t) => TIPOS.find(([k]) => k === t)?.[1] ?? t;
const hoyISO = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const fechaDe = (iso) => new Date(`${iso}T00:00:00`);   // fecha sin hora = día local

export async function render(ctx, { sinCabecera = false } = {}) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  const cargar = async () => (await api("/visitantes-autorizados/", { params: esAdmin ? { todos: true } : undefined })).filter((v) => v.notas !== "Visita de hoy");   // las de un día viven en la pestaña «Hoy»
  let datos = await cargar(), texto = "";
  const lista = h("div", { class: "lista" });

  function formulario(existente) {
    const campo = (id, et, el, ayuda) => h("div", { class: "field" }, el, h("label", { for: id }, et), ayuda ? h("div", { class: "ayuda" }, ayuda) : null);
    const nombre = h("input", { id: "va-nombre", placeholder: " ", maxlength: "60", autocomplete: "off", value: existente?.nombre ?? "" });
    const doc = h("input", { id: "va-doc", class: "mono", placeholder: " ", maxlength: "20", inputmode: "text", autocomplete: "off", spellcheck: "false", value: existente?.documento ?? "", disabled: !!existente });
    const tipo = h("select", { id: "va-tipo" }, TIPOS.map(([v, t]) => h("option", { value: v, selected: (existente?.tipo ?? "Familiar") === v }, t)));
    const hasta = h("input", { id: "va-hasta", type: "date", min: hoyISO(), placeholder: " ", value: existente?.vigente_hasta ?? "" });
    const notas = h("input", { id: "va-notas", placeholder: " ", maxlength: "120", value: existente?.notas ?? "" });
    const guardar = h("button", { class: "btn", type: "submit", form: "f-vauto" }, existente ? "Guardar cambios" : "Autorizar");
    const m = modal(existente ? "Editar visitante" : "Autorizar un visitante", h("form", { id: "f-vauto", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (nombre.value.trim().length < 3) return toast("Escribe el nombre completo.", "error");
      if (!existente && !/^[A-Za-z0-9]{5,15}$/.test(doc.value.replace(/[\s.\-]/g, ""))) return toast("El documento debe tener entre 5 y 15 letras o números.", "error");
      const cuerpo = { nombre: nombre.value.trim(), tipo: tipo.value, vigente_hasta: hasta.value || null, notas: notas.value.trim() || null };
      try {
        await conCarga(guardar, () => existente
          ? api(`/visitantes-autorizados/${existente.id}`, { metodo: "PATCH", json: cuerpo })
          : api("/visitantes-autorizados/", { metodo: "POST", json: { ...cuerpo, documento: doc.value } }));
        m.cerrar(); toast(existente ? "Visitante actualizado" : "Visitante autorizado. Portería ya puede verificarlo."); datos = await cargar(); pintar();
      } catch (err) { toast(err.message, "error"); }
    } },
      campo("va-nombre", "Nombre completo", nombre),
      campo("va-doc", "Documento (cédula o pasaporte)", doc, existente ? "El documento no se puede cambiar." : "Portería lo usa para verificar a la persona."),
      h("div", { class: "fila-campos" }, campo("va-tipo", "Relación", tipo), campo("va-hasta", "Autorizado hasta (opcional)", hasta)),
      campo("va-notas", "Nota para portería (opcional)", notas, "Ej. «Viene martes y jueves por la mañana»")),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
    nombre.focus();
  }

  function pintar() {
    const q = texto.trim().toLowerCase();
    const v = datos.filter((x) => !q || x.nombre.toLowerCase().includes(q) || x.documento.toLowerCase().includes(q) || (x.anfitrion_nombre ?? "").toLowerCase().includes(q));
    lista.replaceChildren(...(v.length ? v.map((x) => h("div", { class: `item ${x.vigente ? "" : "apagado"}` },
      h("div", { class: "ico-caja" }, icono("identificacion")),
      h("div", { class: "cuerpo" }, h("b", {}, x.nombre),
        h("span", {}, [etiquetaTipo(x.tipo), h("span", { class: "doc" }, `CC ${x.documento}`)].flatMap((p, i) => (i ? [" · ", p] : [p]))),
        h("span", { style: "display:block" }, [
          esAdmin ? `${x.anfitrion_nombre}${x.apartamento ? ` · ${x.apartamento}` : ""} · ` : "",
          x.vigente_hasta ? (x.vigente ? `Hasta ${fmtFechaCorta(fechaDe(x.vigente_hasta))}` : `Venció el ${fmtFechaCorta(fechaDe(x.vigente_hasta))}`) : "Sin vencimiento",
          x.ultimo_ingreso ? ` · Último ingreso ${fmtFechaHora(deUtc(x.ultimo_ingreso))}` : " · Aún no ha ingresado"].join("")),
        x.notas ? h("span", { style: "display:block" }, x.notas) : null),
      h("div", { class: "acciones" },
        x.dentro ? badge("Dentro", "Dentro del conjunto") : (x.vigente ? null : badge("Vencido")),
        h("button", { class: "btn suave sm", onclick: () => formulario(x) }, icono("editar", 16), "Editar"),
        h("button", { class: "btn peligro sm", onclick: async () => {
          if (!(await confirmar("¿Retirar la autorización?", `${x.nombre} ya no podrá ingresar. Su historial de ingresos se conserva.`, "Sí, retirar", true))) return;
          try { await api(`/visitantes-autorizados/${x.id}`, { metodo: "DELETE" }); toast("Autorización retirada"); datos = await cargar(); pintar(); }
          catch (e) { toast(e.message, "error"); }
        } }, "Retirar"))))
      : [estadoVacio(datos.length ? "Sin coincidencias" : "Aún no tienes visitantes autorizados", datos.length ? "Prueba con otro nombre o documento." : "Agrega a tu familia, empleada o cuidador para que portería los deje pasar sin llamarte.")]));
  }

  pintar();
  const buscar = h("input", { type: "search", placeholder: "Buscar por nombre o documento", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  return h("div", {},
    sinCabecera ? null : cabecera("Visitantes", esAdmin ? "Personas autorizadas por los residentes del conjunto." : "Deja autorizadas a las personas que te visitan seguido: portería las verifica por su documento."),
    h("div", { class: "barra" }, h("div", { class: "buscador" }, icono("buscar"), buscar), h("button", { class: "btn", onclick: () => formulario(null) }, icono("mas", 18), "Autorizar visitante")),
    h("div", { class: "card escalona" }, lista));
}
