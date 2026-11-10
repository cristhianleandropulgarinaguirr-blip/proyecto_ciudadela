// Bitácora de auditoría (solo administrador). Endpoint: GET /auditoria/?entidad=&limite=&desplazar=
import { api } from "../api.js";
import { h, icono, estadoVacio, toast, deUtc, fmtFechaHora, conCarga } from "../ui.js";
import { descargar, hoyArchivo } from "../descargas.js";
import { cabecera, filtros } from "./comun.js";

const ENTIDADES = [["todas", "Todo"], ["Reserva", "Reservas"], ["Usuario", "Usuarios"], ["Cartera", "Cartera"], ["Daño", "Daños"], ["Anuncio", "Cartelera"], ["Comercio", "Comercio"], ["Visitante", "Visitantes"], ["Paquete", "Paquetes"], ["Emergencia", "Emergencias"], ["PQRS", "PQRS"], ["Documento", "Documentos"], ["Reporte", "Reportes"], ["Seguridad", "Seguridad"]];
const TAM = 40;

export async function render() {
  let filtro = "todas", filas = [], hayMas = false;
  const lista = h("div", { class: "lista" }), mas = h("button", { class: "btn suave block", hidden: true }, "Ver más");
  let chips = h("div");

  async function cargar(desde = 0) {
    const params = { limite: TAM, desplazar: desde };
    if (filtro !== "todas") params.entidad = filtro;
    const nuevos = await api("/auditoria/", { params });
    filas = desde ? [...filas, ...nuevos] : nuevos; hayMas = nuevos.length === TAM; pintar();
  }
  function pintar() {
    chips.replaceWith((chips = filtros(ENTIDADES.map(([id, t]) => ({ id, texto: t })), filtro, (f) => { filtro = f; cargar().catch((e) => toast(e.message, "error")); })));
    lista.replaceChildren(...(filas.length ? filas.map((f) => h("div", { class: "item aud-item" },
      h("span", { class: "badge borde aud-ent" }, f.entidad),
      h("div", { class: "cuerpo" }, h("b", {}, f.accion), h("span", {}, [f.detalle, `Por ${f.actor}`].filter(Boolean).join(" · "))),
      h("div", { class: "acciones" }, h("span", { class: "small muted" }, fmtFechaHora(deUtc(f.fecha)))))) : [estadoVacio("Sin registros", "Cuando alguien haga cambios importantes aparecerán aquí.")]));
    mas.hidden = !hayMas;
  }
  mas.onclick = () => conCarga(mas, () => cargar(filas.length)).catch((e) => toast(e.message, "error"));
  await cargar();
  return h("div", {}, cabecera("Auditoría", "Quién hizo qué y cuándo: un respaldo para la administración ante cualquier reclamo."),
    h("div", { class: "card" }, h("div", { class: "filtros-fila", style: "margin-bottom:1rem" }, chips, h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, "/reportes/auditoria.xlsx", `auditoria_${hoyArchivo()}.xlsx`, { params: filtro === "todas" ? undefined : { entidad: filtro }, aviso: "Auditoría exportada a Excel." }) }, icono("descarga", 16), "Exportar a Excel")), lista, h("div", { style: "margin-top:1rem" }, mas)));
}
