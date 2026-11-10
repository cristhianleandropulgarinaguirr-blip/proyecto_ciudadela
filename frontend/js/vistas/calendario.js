// Calendario mensual de disponibilidad de una zona común.
// Endpoint: GET /reservas/ocupacion?zona=&mes=AAAA-MM (solo devuelve el día y el estado, nunca quién reservó).
import { api } from "../api.js";
import { h, icono, toast } from "../ui.js";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const DIAS = ["L", "M", "M", "J", "V", "S", "D"];
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const textoDia = (isoDia) => {
  const [a, m, d] = isoDia.split("-").map(Number);
  return new Date(a, m - 1, d).toLocaleDateString("es-CO", { weekday: "long", day: "numeric", month: "long" });
};

/** `alElegir(isoDia)` se llama al tocar un día libre. Devuelve { nodo, cambiarZona(z), recargar(), limpiar() }. */
export function calendario({ zona, alElegir }) {
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const primerMes = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
  let mes = new Date(primerMes), elegido = null, ocupacion = new Map(), turno = 0, zonaActual = zona;

  const titulo = h("b", { class: "cal-titulo", "aria-live": "polite" });
  const rejilla = h("div", { class: "cal-rejilla" });
  const anterior = h("button", { class: "btn suave icono cal-nav izq", type: "button", "aria-label": "Mes anterior", onclick: () => cambiar(-1) }, icono("flecha"));
  const siguiente = h("button", { class: "btn suave icono cal-nav", type: "button", "aria-label": "Mes siguiente", onclick: () => cambiar(1) }, icono("flecha"));

  function pintar() {
    titulo.textContent = `${MESES[mes.getMonth()]} ${mes.getFullYear()}`;
    anterior.disabled = mes <= primerMes;
    const huecos = (new Date(mes.getFullYear(), mes.getMonth(), 1).getDay() + 6) % 7;   // la semana empieza el lunes
    const dias = new Date(mes.getFullYear(), mes.getMonth() + 1, 0).getDate();
    const celdas = DIAS.map((d) => h("div", { class: "cal-sem", "aria-hidden": "true" }, d));
    for (let i = 0; i < huecos; i++) celdas.push(h("div", { class: "cal-vacio", "aria-hidden": "true" }));
    for (let d = 1; d <= dias; d++) {
      const fecha = new Date(mes.getFullYear(), mes.getMonth(), d), k = iso(fecha), estado = ocupacion.get(k);
      const pasado = fecha < hoy, ocupado = estado === "Aprobada", espera = estado === "Pendiente";
      const clases = ["cal-dia", pasado && "pasado", ocupado && "ocupado", espera && "espera", elegido === k && "elegido", +fecha === +hoy && "hoy"].filter(Boolean).join(" ");
      celdas.push(h("button", { type: "button", class: clases, disabled: pasado || ocupado, "aria-pressed": String(elegido === k),
        "aria-label": `${d} de ${MESES[mes.getMonth()]}: ${pasado ? "ya pasó" : ocupado ? "ocupado" : espera ? "alguien ya lo pidió, aún sin aprobar" : "libre"}`,
        onclick: () => { elegido = k; alElegir(k); pintar(); } }, String(d)));
    }
    rejilla.replaceChildren(...celdas);
  }

  async function cargar() {
    const mio = ++turno, clave = `${mes.getFullYear()}-${String(mes.getMonth() + 1).padStart(2, "0")}`;
    try {
      const filas = await api("/reservas/ocupacion", { params: { zona: zonaActual, mes: clave } });
      if (mio !== turno) return;
      ocupacion = new Map(filas.map((f) => [f.dia, f.estado]));
    } catch (e) { if (mio === turno) { ocupacion = new Map(); toast("No pudimos ver la disponibilidad. Intenta de nuevo.", "error"); } }
    pintar();
  }
  function cambiar(delta) { mes = new Date(mes.getFullYear(), mes.getMonth() + delta, 1); pintar(); cargar(); }

  const nodo = h("div", { class: "calendario" },
    h("div", { class: "cal-cab" }, anterior, titulo, siguiente), rejilla,
    h("div", { class: "cal-leyenda", "aria-hidden": "true" }, h("span", { class: "l libre" }, "Libre"), h("span", { class: "l ocupado" }, "Ocupado"), h("span", { class: "l espera" }, "Alguien ya lo pidió")));
  pintar(); cargar();
  return {
    nodo,
    cambiarZona(z) { zonaActual = z; elegido = null; cargar(); },
    recargar: cargar,
    limpiar() { elegido = null; cargar(); },
  };
}
