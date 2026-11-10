// Asistente de IA (v2.9). SOLO prepara BORRADORES: nunca radica ni publica nada por su cuenta.
// La persona revisa el borrador, lo corrige si quiere y lo envía con el formulario de siempre (con sus mismas validaciones).
// Endpoints: GET /asistente/estado · POST /asistente/residente · POST /asistente/anuncio
import { api } from "./api.js";
import { h, icono, badge, modal, toast, conCarga, deUtc, hace } from "./ui.js";

const PRIVACIDAD = "No escribas cédulas, teléfonos ni contraseñas. Tu texto se envía a un servicio de IA externo solo para redactar el borrador.";
const TIPO_PQRS = { Peticion: "Petición", Queja: "Queja", Reclamo: "Reclamo", Sugerencia: "Sugerencia" };

// ---- ¿Está disponible? (si no hay clave de IA en el servidor, los botones ni aparecen y todo sigue igual) ----
let estado = null, estadoEn = 0;
export async function estadoAsistente(forzar = false) {
  if (!forzar && estado && Date.now() - estadoEn < 60000) return estado;
  try { estado = await api("/asistente/estado"); } catch { estado = { disponible: false, restantes: 0, limite_diario: 0 }; }
  estadoEn = Date.now();
  return estado;
}
const textoRestantes = (e) => (e.restantes > 0 ? `Te quedan ${e.restantes} consultas hoy.` : "Ya usaste todas tus consultas de hoy.");

// ---- Borrador «en tránsito» (solo en memoria) cuando el asistente lleva a otro formulario ----
let pendiente = null;
export function tomarBorrador(clase) {
  if (pendiente?.clase !== clase) return null;
  const datos = pendiente.datos; pendiente = null;
  return datos;
}

const aviso = (texto, clase = "") => h("div", { class: `aviso-ia ${clase}`, role: clase === "error" ? "alert" : null }, icono("alerta", 18), h("span", {}, texto));

// =========================================================== Residente: PQRS y daños
export function botonResidente(contexto, alUsar) {
  const caja = h("div", { class: "asistente-caja" });
  estadoAsistente().then((e) => {
    if (e.disponible) caja.replaceChildren(h("button", { class: "btn suave block", type: "button", onclick: () => abrirResidente(contexto, alUsar) }, icono("chispa", 18), "Ayúdame a redactarlo"));
  });
  return caja;
}

function abrirResidente(contexto, alUsar) {
  const mensaje = h("textarea", { id: "as-msg", placeholder: " ", maxlength: "600", rows: "5" });
  const cuenta = h("span", { class: "small muted" }, "0/600");
  mensaje.addEventListener("input", () => { cuenta.textContent = `${mensaje.value.length}/600`; });
  const restantes = h("span", { class: "small muted" });
  const resultado = h("div", { class: "asistente-res", "aria-live": "polite" });
  const preparar = h("button", { class: "btn", type: "submit", form: "f-asistente" }, icono("chispa", 18), "Preparar borrador");
  estadoAsistente(true).then((e) => { restantes.textContent = textoRestantes(e); });

  const m = modal("Asistente de IA", h("form", { id: "f-asistente", novalidate: true, onsubmit: async (ev) => {
    ev.preventDefault();
    const texto = mensaje.value.trim();
    if (texto.length < 10) return toast("Cuéntame un poco más (mínimo 10 caracteres).", "error");
    resultado.replaceChildren();
    try {
      const r = await conCarga(preparar, () => api("/asistente/residente", { metodo: "POST", json: { mensaje: texto } }));
      estadoAsistente(true).then((e) => { restantes.textContent = textoRestantes(e); });
      resultado.replaceChildren(...mostrar(r));
    } catch (err) { resultado.replaceChildren(aviso(err.message, "error")); }
  } },
    h("p", { class: "muted" }, "Cuéntame con tus palabras qué pasó. Preparo un borrador y tú lo revisas y lo envías."),
    aviso(PRIVACIDAD),
    h("div", { class: "field" }, mensaje, h("label", { for: "as-msg" }, "¿Qué pasó o qué necesitas?")),
    h("div", { class: "asistente-pie" }, cuenta, restantes), resultado),
  { pie: [h("button", { class: "btn suave", type: "button", onclick: () => m.cerrar() }, "Cerrar"), preparar] });

  function mostrar(r) {
    if (r.intencion === "emergencia") {
      return [aviso(r.mensaje, "peligro"), h("button", { class: "btn arcilla block", type: "button", onclick: () => { m.cerrar(); location.hash = "#/emergencias"; } }, "Ver teléfonos de emergencia")];
    }
    if (r.intencion === "estado") {
      return [h("p", { class: "muted" }, r.mensaje), ...r.solicitudes.map((s) => h("a", { class: "asistente-fila", href: s.enlace, onclick: () => m.cerrar() },
        h("div", {}, h("b", {}, `${s.referencia} · ${s.titulo}`), h("span", { class: "small muted" }, `${s.clase} · ${hace(deUtc(s.fecha))}`)), badge(s.estado)))];
    }
    if (r.intencion === "pqrs" || r.intencion === "danio") {
      const esPqrs = r.intencion === "pqrs", b = esPqrs ? r.pqrs : r.danio, titulo = esPqrs ? b.asunto : b.titulo;
      const aqui = r.intencion === contexto;
      const usar = () => {
        m.cerrar();
        if (aqui) { alUsar(b); toast("Borrador cargado. Revísalo y envíalo cuando estés de acuerdo."); }
        else { pendiente = { clase: r.intencion, datos: b }; location.hash = esPqrs ? "#/pqrs" : "#/mantenimiento"; }
      };
      return [h("p", { class: "muted" }, r.mensaje),
        h("div", { class: "borrador" }, esPqrs ? h("span", { class: "badge" }, TIPO_PQRS[b.tipo]) : h("span", { class: "badge laton" }, "Daño en zona común"), h("h3", {}, titulo), h("p", {}, b.descripcion)),
        aqui ? null : h("p", { class: "small muted" }, esPqrs ? "Esto parece una petición o queja, así que te llevo al formulario de solicitudes." : "Esto parece un daño en una zona común, así que te llevo al formulario de daños."),
        h("p", { class: "small muted" }, "Es un borrador hecho por IA: puede tener errores. Nada se envía hasta que lo envíes tú."),
        h("button", { class: "btn block", type: "button", onclick: usar }, aqui ? "Usar este borrador" : "Llevar este borrador al formulario")];
    }
    return [h("p", { class: "muted" }, r.mensaje)];
  }
  mensaje.focus();
}

// =========================================================== Administrador: borrador de anuncio
export function panelAnuncioIA(aplicar) {
  const caja = h("div", { class: "asistente-caja" });
  estadoAsistente().then((e) => { if (e.disponible) caja.replaceChildren(construir(e)); });

  function construir(e) {
    const instruccion = h("textarea", { id: "as-instr", placeholder: " ", maxlength: "800", rows: "3" });
    const salida = h("div", { class: "asistente-res", "aria-live": "polite" });
    const restantes = h("p", { class: "small muted" }, textoRestantes(e));
    const generar = h("button", { class: "btn suave sm", type: "button" }, icono("chispa", 16), "Generar borrador");
    generar.onclick = async () => {
      const texto = instruccion.value.trim();
      if (texto.length < 10) return toast("Describe el aviso con un poco más de detalle.", "error");
      salida.replaceChildren();
      try {
        const d = await conCarga(generar, () => api("/asistente/anuncio", { metodo: "POST", json: { instruccion: texto } }));
        aplicar(d);
        estadoAsistente(true).then((x) => { restantes.textContent = textoRestantes(x); });
        salida.replaceChildren(
          h("div", { class: "aviso-ia ok" }, icono("ok", 18), h("span", {}, `Borrador listo abajo. Si lo publicas, llegará a ${d.destinatarios} ${d.destinatarios === 1 ? "persona" : "personas"}. Revísalo antes de publicar.`)),
          ...d.advertencias.map((a) => aviso(a)));
      } catch (err) { salida.replaceChildren(aviso(err.message, "error")); }
    };
    return h("details", { class: "asistente-panel" },
      h("summary", {}, icono("chispa", 16), "Redactar con IA"),
      h("p", { class: "small muted" }, "Cuéntame qué debe saber la comunidad (qué, cuándo y dónde). La IA llena el formulario con un borrador; tú lo revisas y decides si publicar."),
      aviso(PRIVACIDAD),
      h("div", { class: "field" }, instruccion, h("label", { for: "as-instr" }, "Describe el aviso")),
      generar, restantes, salida);
  }
  return caja;
}
