// Indicadores (KPIs) del administrador: cartera, zonas más reservadas, tiempo de respuesta de PQRS y flujo de visitantes por hora.
// Endpoint: GET /dashboard/kpis  (todo calculado en el servidor con consultas agregadas; ~1 KB de respuesta, guardado 60 s)
import { api } from "../api.js";
import { h, icono, kpi, dinero, toast, conCarga, deUtc, hace } from "../ui.js";
import { cabecera } from "./comun.js";
import { barrasHorizontales, barrasPorHora, dona, leyenda } from "../graficos.js";

const hora12 = (n) => (n == null ? "—" : new Date(2000, 0, 1, n).toLocaleTimeString("es-CO", { hour: "numeric", minute: "2-digit" }));
const tiempo = (horas) => {
  if (horas == null) return "Sin respuestas aún";
  if (horas < 1) return `${Math.round(horas * 60)} min`;
  return horas < 48 ? `${horas.toFixed(1).replace(".0", "")} h` : `${(horas / 24).toFixed(1).replace(".0", "")} días`;
};
const tarjeta = (titulo, sub, ...contenido) => h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, titulo)), sub ? h("p", { class: "muted small", style: "margin:-.2rem 0 .8rem" }, sub) : null, ...contenido);

export async function render() {
  let datos = await api("/dashboard/kpis");
  const raiz = h("div", {});

  function pintar() {
    const { cartera: c, reservas: r, pqrs: p, visitantes: v, operacion: o } = datos;
    const partesCartera = [{ etiqueta: "Al día", valor: c.al_dia, clase: "g-p1", texto: `${c.al_dia}` }, { etiqueta: "En mora", valor: c.en_mora, clase: "g-p3", texto: `${c.en_mora}` }];
    raiz.replaceChildren(
      h("div", { class: "kpis" },
        kpi("Cartera al día", Math.round(c.pct_al_dia), { destacado: true, formato: (n) => `${n}%` }),
        kpi("Saldo total pendiente", c.saldo_total, { formato: dinero }),
        kpi("Apartamentos en mora", c.en_mora, { alerta: true }),
        kpi("Respuesta promedio PQRS", 0, { formato: () => tiempo(p.horas_promedio_respuesta) })),
      h("div", { class: "grid dos" },
        tarjeta("Cartera", `${c.unidades} apartamento${c.unidades === 1 ? "" : "s"} activos`,
          h("div", { class: "dona-fila" }, dona(partesCartera, { centro: `${Math.round(c.pct_al_dia)}%`, subcentro: "al día" }), leyenda(partesCartera)),
          h("a", { class: "btn suave sm", href: "#/cartera", style: "margin-top:.8rem" }, "Ver cartera", icono("flecha", 16))),
        tarjeta("Zonas más reservadas", `Reservas aprobadas en los últimos ${r.dias} días`,
          barrasHorizontales(r.por_zona.map((z) => ({ etiqueta: z.zona, valor: z.total })), { vacio: "Aún no hay reservas aprobadas en este período." }),
          r.pendientes ? h("p", { class: "small", style: "margin-top:.6rem" }, h("a", { href: "#/reservas" }, `${r.pendientes} reserva${r.pendientes === 1 ? "" : "s"} por aprobar`)) : null),
        tarjeta("Flujo de visitantes por hora", `Ingresos de los últimos ${v.dias} días (hora de Colombia)`,
          v.total ? barrasPorHora(v.por_hora, { resaltar: v.hora_pico }) : h("p", { class: "muted small" }, "Aún no hay ingresos registrados en este período."),
          v.total ? h("p", { class: "small", style: "margin-top:.5rem" }, `Hora pico: `, h("b", {}, hora12(v.hora_pico)), ` · ${v.total} ingreso${v.total === 1 ? "" : "s"} en total`) : null),
        tarjeta("PQRS", `Tiempo entre radicar y responder (últimos ${p.dias} días)`,
          h("div", { class: "kpis", style: "margin-bottom:0" }, kpi("Promedio de respuesta", 0, { formato: () => tiempo(p.horas_promedio_respuesta) }), kpi("Abiertas ahora", p.abiertas, { alerta: true })),
          h("p", { class: "muted small", style: "margin-top:.6rem" }, `Calculado con ${p.respondidas} PQRS respondida${p.respondidas === 1 ? "" : "s"}.`),
          h("a", { class: "btn suave sm", href: "#/pqrs", style: "margin-top:.4rem" }, "Ver PQRS", icono("flecha", 16))),
        tarjeta("Pendientes de hoy", "Lo que está esperando una acción",
          h("div", { class: "lista" },
            [["Vehículos dentro", o.vehiculos_dentro, "#/porteria"], ["Paquetes sin entregar", o.paquetes_sin_entregar, "#/paquetes"],
             ["Daños sin resolver", o.danios_sin_resolver, "#/mantenimiento"], ["Arrendamientos por aprobar", o.arrendamientos_por_aprobar, "#/inquilinos"]]
              .map(([texto, n, ruta]) => h("a", { class: "item", href: ruta }, h("div", { class: "cuerpo" }, h("b", {}, texto)), h("span", { class: `badge ${n ? "laton" : ""}` }, String(n))))))),
      h("p", { class: "small muted", style: "margin-top:.8rem" }, `Actualizado ${hace(deUtc(datos.generado))}. Los datos se guardan un minuto para que la pantalla cargue al instante.`));
  }

  pintar();
  const refrescar = h("button", { class: "btn suave sm", onclick: (e) => conCarga(e.currentTarget, async () => { datos = await api("/dashboard/kpis", { params: { refrescar: true } }); pintar(); toast("Indicadores actualizados."); }).catch((err) => toast(err.message, "error")) }, "Actualizar ahora");
  return h("div", {}, cabecera("Indicadores", "Cómo va el conjunto de un vistazo."), h("div", { class: "barra" }, h("span", {}), refrescar), raiz);
}
