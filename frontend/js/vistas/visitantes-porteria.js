// Portería · visitantes a pie autorizados. Endpoints: GET /visitantes-autorizados/buscar?q= · POST /{id}/ingreso
//   PATCH /visitantes-autorizados/accesos/{id}/salida · GET /visitantes-autorizados/dentro · GET /visitantes-autorizados/accesos
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, deUtc, hace, fmtHora, fmtFechaHora, kpi } from "../ui.js";
import { etiquetaTipo } from "./visitantes.js";
import { descargar, hoyArchivo } from "../descargas.js";

export async function vistaVisitantesPorteria(esAdmin = false) {
  let dentro = await api("/visitantes-autorizados/dentro"), recientes = await api("/visitantes-autorizados/accesos", { params: { limite: 15 } });
  let resultados = null, termino = "";
  const kpis = h("div", { class: "kpis" }), cajaDentro = h("div", { class: "lista" }), cajaRes = h("div", { class: "resultado-busqueda" }), cajaHist = h("div", { class: "lista" });

  async function refrescar() {
    [dentro, recientes] = await Promise.all([api("/visitantes-autorizados/dentro"), api("/visitantes-autorizados/accesos", { params: { limite: 15 } })]);
    if (termino.length >= 3) resultados = await api("/visitantes-autorizados/buscar", { params: { q: termino } });
    pintar();
  }

  function pintar() {
    kpis.replaceChildren(kpi("Visitantes a pie dentro", dentro.length, { destacado: true }));
    cajaDentro.replaceChildren(...(dentro.length ? dentro.map((a) => {
      const ing = deUtc(a.fecha_ingreso);
      const salir = h("button", { class: "btn suave sm", onclick: async () => {
        try { await conCarga(salir, () => api(`/visitantes-autorizados/accesos/${a.id}/salida`, { metodo: "PATCH" })); toast(`Salida registrada: ${a.nombre}`); await refrescar(); }
        catch (e) { toast(e.message, "error"); }
      } }, "Registrar salida");
      return h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("identificacion")),
        h("div", { class: "cuerpo" }, h("b", {}, a.nombre), h("span", {}, `Visita a ${a.apartamento ?? a.anfitrion_nombre} · ingresó ${fmtHora(ing)} (${hace(ing)})`)),
        h("div", { class: "acciones" }, salir));
    }) : [estadoVacio("Nadie dentro", "No hay visitantes a pie en el conjunto.")]));

    cajaRes.replaceChildren(...(resultados === null ? [] : resultados.length ? resultados.map((v) => {
      const puede = v.vigente && !v.dentro;
      const entrar = h("button", { class: "btn sm", disabled: !puede, onclick: async () => {
        try { await conCarga(entrar, () => api(`/visitantes-autorizados/${v.id}/ingreso`, { metodo: "POST" })); toast(`Ingreso registrado: ${v.nombre}`); await refrescar(); }
        catch (e) { toast(e.message, "error"); }
      } }, icono("ok", 16), "Registrar ingreso");
      return h("div", { class: `item ${v.vigente ? "" : "apagado"}` }, h("div", { class: "ico-caja laton" }, icono("identificacion")),
        h("div", { class: "cuerpo" }, h("b", {}, v.nombre), h("span", {}, `${etiquetaTipo(v.tipo)} · CC ${v.documento}`),
          h("span", { style: "display:block" }, `Autorizado por ${v.anfitrion_nombre}${v.apartamento ? ` · ${v.apartamento}` : ""}`),
          v.notas ? h("span", { style: "display:block" }, `Nota: ${v.notas}`) : null),
        h("div", { class: "acciones" }, v.dentro ? badge("Dentro", "Ya está dentro") : v.vigente ? null : badge("Vencido", "Autorización vencida"), entrar));
    }) : [estadoVacio("No está autorizado", "Ningún residente ha autorizado a esta persona. Llama al apartamento antes de dejarla pasar.")]));

    cajaHist.replaceChildren(...(recientes.length ? recientes.map((a) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("reloj")),
      h("div", { class: "cuerpo" }, h("b", {}, a.nombre), h("span", {}, `${a.apartamento ?? a.anfitrion_nombre} · entró ${fmtFechaHora(deUtc(a.fecha_ingreso))}${a.fecha_salida ? ` · salió ${fmtHora(deUtc(a.fecha_salida))}` : ""}`),
        h("span", { style: "display:block" }, [a.ingreso_registrado_por ? `Registró ${a.ingreso_registrado_por}` : null].filter(Boolean).join(""))),
      h("div", { class: "acciones" }, a.fecha_salida ? null : badge("Dentro")))) : [estadoVacio("Sin movimientos", "Aquí quedan los ingresos de visitantes a pie.")]));
  }

  let t, turno = 0;
  const buscar = h("input", { id: "vp-q", type: "search", placeholder: " ", autocomplete: "off", "aria-label": "Nombre o documento", oninput: (e) => {
    clearTimeout(t); termino = e.target.value.trim();
    t = setTimeout(async () => {
      const mio = ++turno;
      if (termino.length < 3) { resultados = null; return pintar(); }
      try { const r = await api("/visitantes-autorizados/buscar", { params: { q: termino } }); if (mio === turno) { resultados = r; pintar(); } }
      catch (err) { toast(err.message, "error"); }
    }, 300);
  } });
  pintar();
  return h("div", { class: "grid lados escalona" },
    h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Verificar visitante")),
      h("div", { class: "field" }, buscar, h("label", { for: "vp-q" }, "Nombre o documento"), h("div", { class: "ayuda" }, "Escribe al menos 3 caracteres. Si no aparece, nadie lo autorizó.")), cajaRes),
    h("div", {}, kpis,
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Dentro del conjunto")), cajaDentro),
      h("section", { class: "card", style: "margin-top:1rem" }, h("div", { class: "card-titulo" }, h("h2", {}, "Últimos movimientos"),
        esAdmin ? h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, "/reportes/visitantes.xlsx", `visitantes_a_pie_${hoyArchivo()}.xlsx`, { aviso: "Ingresos exportados a Excel." }) }, icono("descarga", 16), "Excel") : null), cajaHist)));
}
