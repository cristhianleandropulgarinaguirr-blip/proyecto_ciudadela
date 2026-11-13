// Portería: control de vehículos visitantes.
// Endpoints: POST /porteria/vehiculo-ingreso?placa=&apartamento= · PATCH /porteria/vehiculo-salida/{id} · GET /porteria/vehiculos-dentro
import { api } from "../api.js";
import { h, icono, badge, placa, estadoVacio, toast, conCarga, deUtc, hace, fmtHora, kpi } from "../ui.js";
import { cabecera, avisarRegistro, alSincronizar } from "./comun.js";
import { leer, registrar, pendientes, superponerVehiculos } from "../offline.js";
import { vistaHistorial } from "./historial.js";
import { vistaEscaner } from "./escaner.js";
import { vistaVisitantesPorteria } from "./visitantes-porteria.js";

const PLACA = /^[A-Za-z]{3}[0-9]{2}[A-Za-z0-9]$/;   // misma regla que la API: ABC123 (carro) · ABC12D (moto)

async function panelActual() {
  const cargarBase = () => leer("vehiculos-dentro", () => api("/porteria/vehiculos-dentro"));
  let base = await cargarBase();
  let dentro = superponerVehiculos(base, await pendientes());      // lo registrado sin internet aparece de inmediato, marcado «Pendiente»
  let texto = "";
  async function recargar() {
    try { base = await cargarBase(); } catch { /* se deja lo que había */ }
    dentro = superponerVehiculos(base, await pendientes()); pintar();
  }
  const lista = h("div", { class: "lista" }), resumen = h("div", { class: "kpis" });

  function pintar() {
    const q = texto.trim().toUpperCase();
    const v = dentro.filter((x) => !q || x.placa.includes(q) || x.apartamento_destino.toUpperCase().includes(q));
    resumen.replaceChildren(kpi("Vehículos dentro", dentro.length, { destacado: true }));
    lista.replaceChildren(...(v.length ? v.map((x) => {
      const ingreso = deUtc(x.fecha_ingreso);
      const salir = h("button", { class: "btn suave sm", onclick: async () => {
        try {
          const r = await conCarga(salir, () => registrar("vehiculo_salida", x.pendiente ? { ref: x.uuid, placa: x.placa } : { vehiculo_id: x.id, placa: x.placa }, { vista: { resumen: `Salida de ${x.placa}` } }));
          if (avisarRegistro(r, `Salida registrada: ${x.placa}`)) await recargar();
        } catch (e) { toast(e.message, "error"); }
      } }, "Registrar salida");
      return h("div", { class: "vehiculo" }, placa(x.placa),
        h("div", { class: "cuerpo" }, h("b", {}, x.apartamento_destino), x.pendiente ? badge("Pendiente", "Guardado en este equipo; se enviará al volver el internet") : null,
          h("div", { class: "small muted", "data-ingreso": ingreso.toISOString() }, `Ingresó ${fmtHora(ingreso)} · ${hace(ingreso)}`)),
        h("div", { class: "acciones" }, salir));
    }) : [estadoVacio(dentro.length ? "Sin coincidencias" : "Portería despejada", dentro.length ? "Prueba con otra placa o apartamento." : "No hay visitantes dentro del conjunto.")]));
  }

  // Los "hace X min" se refrescan solos mientras la vista esté en pantalla.
  const reloj = setInterval(() => {
    if (!lista.isConnected) return clearInterval(reloj);
    lista.querySelectorAll("[data-ingreso]").forEach((el) => { const d = new Date(el.dataset.ingreso); el.textContent = `Ingresó ${fmtHora(d)} · ${hace(d)}`; });
  }, 30000);

  // ----- Formulario de ingreso con placa en vivo -----
  const inPlaca = h("input", { id: "placa", class: "mono", placeholder: " ", maxlength: "6", autocapitalize: "characters", autocomplete: "off", spellcheck: "false", required: true });
  const vista = h("div", { class: "placa-vista" }, placa(""));
  const ayuda = h("div", { class: "ayuda" }, "Carro: ABC123 · Moto: ABC12D");
  const campoPlaca = h("div", { class: "field" }, inPlaca, h("label", { for: "placa" }, "Placa"), ayuda);
  inPlaca.addEventListener("input", () => {
    inPlaca.value = inPlaca.value.toUpperCase().replace(/[^A-Z0-9]/g, "");
    vista.replaceChildren(placa(inPlaca.value));
    const mal = inPlaca.value.length === 6 && !PLACA.test(inPlaca.value);
    campoPlaca.classList.toggle("error", mal); ayuda.classList.toggle("err", mal);
  });
  const apto = h("input", { id: "apto", placeholder: " ", maxlength: "50", required: true });
  const enviar = h("button", { class: "btn block", type: "submit" }, icono("mas", 18), "Registrar ingreso");
  const form = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (!PLACA.test(inPlaca.value)) return toast("La placa no tiene un formato válido.", "error");
    if (!apto.value.trim()) return toast("Indica el apartamento de destino.", "error");
    try {
      const placaNueva = inPlaca.value;
      const r = await conCarga(enviar, () => registrar("vehiculo_ingreso", { placa: placaNueva, apartamento: apto.value.trim() }, { vista: { resumen: `Ingreso de ${placaNueva}` } }));
      if (!avisarRegistro(r, `Ingreso registrado: ${placaNueva}`)) return;      // si el servidor lo rechaza (p. ej. ya estaba dentro) se conserva el formulario
      form.reset(); vista.replaceChildren(placa("")); await recargar(); inPlaca.focus();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("div", { class: "card-titulo" }, h("h2", {}, "Registrar ingreso")), vista, campoPlaca,
    h("div", { class: "field" }, apto, h("label", { for: "apto" }, "Apartamento de destino")), enviar);

  const buscar = h("input", { type: "search", placeholder: "Buscar placa o apartamento", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  pintar();
  alSincronizar(lista, recargar);
  return h("div", {},
    h("div", { class: "grid lados escalona" }, form,
      h("div", {}, resumen, h("div", { class: "card" },
        h("div", { class: "card-titulo" }, h("h2", {}, "Dentro del conjunto"), h("div", { class: "buscador" }, icono("buscar"), buscar)), lista))));
}

// Dos pestañas: lo que está pasando ahora y el historial completo.
export async function render(ctx) {
  const panel = h("div");
  let actual = "ahora";
  const tabs = h("div", { class: "tabs", role: "tablist" });
  async function mostrar(cual) {
    actual = cual;
    tabs.replaceChildren(...[["ahora", "Vehículos"], ["visitantes", "Visitantes a pie"], ["escaner", "Escanear QR"], ["historial", "Historial"]].map(([id, texto]) =>
      h("button", { class: "tab", role: "tab", "aria-selected": String(id === actual), onclick: () => id !== actual && mostrar(id) }, texto)));
    panel.replaceChildren(h("div", { class: "esq", style: "height:160px" }));
    try {
      const nodo = cual === "ahora" ? await panelActual() : cual === "visitantes" ? await vistaVisitantesPorteria(ctx.usuario.rol === "Administrador") : cual === "escaner" ? vistaEscaner() : vistaHistorial(ctx);
      if (cual === actual) panel.replaceChildren(nodo);
    } catch (e) { toast(e.message, "error"); }
  }
  await mostrar("ahora");
  return h("div", {}, cabecera("Portería", "Registra la entrada y salida de vehículos, escanea QR y consulta el historial completo."), tabs, panel);
}
