// Historial de portería: todas las entradas y salidas de vehículos, con quién las registró.
// Endpoints: GET /porteria/historial?placa&apartamento&estado&desde&hasta&pagina&limite
//            GET /porteria/historial/exportar (CSV, solo administrador)
import { api, apiBlob } from "../api.js";
import { h, icono, estadoVacio, toast, conCarga, deUtc, fmtFechaHora, duracion, badge } from "../ui.js";
import { filtros } from "./comun.js";

const LIMITE = 20;
const dia = (valor, finDelDia) => new Date(`${valor}T${finDelDia ? "23:59:59.999" : "00:00:00"}`).toISOString();   // día local -> UTC

export function vistaHistorial(ctx) {
  const esAdmin = ctx.usuario.rol === "Administrador";
  const f = { placa: "", apartamento: "", estado: "", desde: "", hasta: "", pagina: 1 };
  const cuerpo = h("tbody"), resumen = h("span", { class: "small muted" }), pie = h("div", { class: "paginacion" });
  const aviso = h("div");
  let cargando = 0, ultimaConsulta = null;

  function parametros(extra = {}) {
    const p = {};
    if (f.placa) p.placa = f.placa;
    if (f.apartamento) p.apartamento = f.apartamento;
    if (f.estado) p.estado = f.estado;
    if (f.desde) p.desde = dia(f.desde, false);
    if (f.hasta) p.hasta = dia(f.hasta, true);
    return { ...p, ...extra };
  }

  async function cargar() {
    const mio = ++cargando;
    try {
      const r = await api("/porteria/historial", { params: parametros({ pagina: f.pagina, limite: LIMITE }) });
      if (mio !== cargando) return;
      ultimaConsulta = r;
      pintar(r);
    } catch (e) { if (mio === cargando) toast(e.message, "error"); }
  }

  function pintar(r) {
    const desde = r.total ? (r.pagina - 1) * r.limite + 1 : 0, hasta = Math.min(r.total, r.pagina * r.limite);
    const paginas = Math.max(1, Math.ceil(r.total / r.limite));
    resumen.textContent = r.total ? `Mostrando ${desde}–${hasta} de ${r.total} movimientos` : "";
    cuerpo.replaceChildren(...r.items.map((v) => {
      const ing = deUtc(v.fecha_ingreso), sal = v.fecha_salida ? deUtc(v.fecha_salida) : null;
      return h("tr", {},
        h("td", { "data-et": "Placa" }, h("span", { class: "placa-mini" }, v.placa)),
        h("td", { "data-et": "Apartamento" }, v.apartamento_destino),
        h("td", { "data-et": "Entrada" }, fmtFechaHora(ing), v.ingreso_registrado_por ? h("span", { class: "registro-por" }, `Registró ${v.ingreso_registrado_por}`) : null),
        h("td", { "data-et": "Salida" }, sal ? [fmtFechaHora(sal), v.salida_registrada_por ? h("span", { class: "registro-por" }, `Registró ${v.salida_registrada_por}`) : null] : badge("Dentro", "En el conjunto")),
        h("td", { "data-et": "Permanencia" }, duracion(v.duracion_minutos)));
    }));
    aviso.replaceChildren(...(r.items.length ? [] : [estadoVacio("Sin movimientos", "No hay registros con estos filtros.")]));
    pie.replaceChildren(h("span", { class: "small muted" }, `Página ${r.pagina} de ${paginas}`),
      h("div", { class: "btn-grupo" },
        h("button", { class: "btn suave sm", disabled: r.pagina <= 1, onclick: () => { f.pagina--; cargar(); } }, "Anterior"),
        h("button", { class: "btn suave sm", disabled: r.pagina >= paginas, onclick: () => { f.pagina++; cargar(); } }, "Siguiente")));
    pie.hidden = r.total <= r.limite;
  }

  let t;
  const buscar = () => { clearTimeout(t); t = setTimeout(() => { f.pagina = 1; cargar(); }, 300); };
  const campo = (id, et, attrs, clave, transformar = (v) => v) => {
    const el = h("input", { id, placeholder: " ", autocomplete: "off", ...attrs, oninput: (e) => { f[clave] = transformar(e.target.value); buscar(); } });
    return h("div", { class: "field" }, el, h("label", { for: id }, et));
  };
  let chipsEstado = h("div");
  const pintarChips = () => chipsEstado.replaceWith((chipsEstado = filtros([{ id: "", texto: "Todos" }, { id: "Dentro", texto: "Dentro" }, { id: "Salido", texto: "Salieron" }], f.estado, (v) => { f.estado = v; f.pagina = 1; cargar(); })));
  pintarChips();

  const exportar = h("button", { class: "btn suave sm", onclick: async (e) => {
    try {
      const blob = await conCarga(e.currentTarget, () => apiBlob("/porteria/historial/exportar", { params: parametros() }));
      const a = h("a", { href: URL.createObjectURL(blob), download: `historial_vehiculos_${new Date().toISOString().slice(0, 10)}.csv` });
      document.body.append(a); a.click(); a.remove(); toast("Historial exportado. Ábrelo con Excel.");
    } catch (err) { toast(err.message, "error"); }
  } }, icono("descarga", 16), "Exportar a Excel");

  const nodo = h("div", {},
    h("div", { class: "card" },
      h("div", { class: "filtros" },
        campo("h-placa", "Placa", { maxlength: "6", class: "mono", autocapitalize: "characters" }, "placa", (v) => v.toUpperCase().replace(/[^A-Z0-9]/g, "")),
        campo("h-apto", "Apartamento", { maxlength: "50" }, "apartamento", (v) => v.trim()),
        campo("h-desde", "Desde", { type: "date" }, "desde"),
        campo("h-hasta", "Hasta", { type: "date" }, "hasta")),
      h("div", { class: "filtros-fila" }, chipsEstado, esAdmin ? exportar : null),
      h("div", { style: "margin-bottom:.5rem" }, resumen),
      h("div", { class: "tabla-wrap" }, h("table", { class: "tabla" },
        h("thead", {}, h("tr", {}, ["Placa", "Apartamento", "Entrada", "Salida", "Permanencia"].map((t) => h("th", {}, t)))), cuerpo)),
      aviso, pie));
  cargar();
  return nodo;
}
