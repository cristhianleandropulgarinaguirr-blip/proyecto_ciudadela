// Paquetes y correspondencia.
// Endpoints: GET /paquetes/?estado= · GET /paquetes/destinatarios?q= · POST /paquetes/
//            PATCH /paquetes/{id}/entregar · PATCH /paquetes/{id}/anular · POST/GET /paquetes/{id}/foto
import { api, apiBlob } from "../api.js";
import { selectorFoto } from "../foto.js";
import { autoguardar } from "../autoguardado.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, hace, fmtFechaHora, kpi } from "../ui.js";
import { cabecera, filtros, avisarRegistro, alSincronizar } from "./comun.js";
import { leer, leerCopia, registrar, pendientes, superponerPaquetes, normal } from "../offline.js";
import { descargar, hoyArchivo } from "../descargas.js";

const TIPOS = ["Paquete", "Correspondencia", "Domicilio"];

// Miniatura de la foto del paquete: se pide solo cuando la tarjeta está por verse; al tocarla se amplía.
const observador = "IntersectionObserver" in window
  ? new IntersectionObserver((items) => items.forEach((it) => { if (it.isIntersecting) { observador.unobserve(it.target); it.target._cargar?.(); } }), { rootMargin: "200px" })
  : null;

function fotoPaquete(p) {
  const caja = h("button", { class: "paq-foto", type: "button", "aria-label": "Ver foto del paquete" }, icono("camara", 18));
  caja._cargar = async () => {
    try {
      const url = URL.createObjectURL(await apiBlob(`/paquetes/${p.id}/foto`, { params: { miniatura: true } }));
      caja.replaceChildren(h("img", { src: url, alt: "Foto del paquete" }));
      caja.onclick = async () => {
        const grande = h("img", { class: "visor", src: url, alt: "Foto del paquete" });
        modal(`${p.tipo} para ${p.destinatario_nombre}`, grande);
        try { grande.src = URL.createObjectURL(await apiBlob(`/paquetes/${p.id}/foto`)); } catch { /* se queda la miniatura */ }
      };
    } catch { caja.remove(); }
  };
  observador ? observador.observe(caja) : caja._cargar();
  return caja;
}

export async function render(ctx) {
  const rol = ctx.usuario.rol, esResidente = rol === "Residente", esPersonal = !esResidente;
  const cargar = () => leer("paquetes", () => api("/paquetes/", { params: { limite: 200 } }));
  let base = await cargar(), filtro = "En porteria", texto = "";
  let datos = superponerPaquetes(base, await pendientes());       // lo registrado sin internet aparece de inmediato, marcado «Pendiente»
  const lista = h("div", { class: "lista" }), resumen = h("div", { class: "kpis" });
  let chips = h("div");

  async function recargar() {
    try { base = await cargar(); } catch { /* sin conexión: se deja lo que había */ }
    datos = superponerPaquetes(base, await pendientes()); pintar();
  }

  function entregar(p) {
    const quien = h("input", { id: "pq-quien", placeholder: " ", maxlength: "60", autocomplete: "off" });
    const ok = h("button", { class: "btn", type: "submit", form: "f-entrega" }, icono("ok", 16), "Confirmar entrega");
    const m = modal("Entregar paquete", h("form", { id: "f-entrega", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      try {
        const entregado_a = quien.value.trim() || null;
        const r = await conCarga(ok, () => registrar("paquete_entrega", p.pendiente ? { ref: p.uuid, entregado_a } : { paquete_id: p.id, entregado_a }, { vista: { resumen: `Entrega de paquete para ${p.destinatario_nombre}` } }));
        if (avisarRegistro(r, "Entrega registrada")) { m.cerrar(); await recargar(); }
      } catch (err) { toast(err.message, "error"); }
    } },
      h("p", { class: "muted", style: "margin-bottom:1rem" }, `${p.tipo} para ${p.destinatario_nombre}${p.apartamento ? ` · ${p.apartamento}` : ""}.`),
      h("div", { class: "field" }, quien, h("label", { for: "pq-quien" }, "¿Quién lo recoge?"), h("div", { class: "ayuda" }, `Déjalo vacío si lo recoge ${p.destinatario_nombre}. Si es otra persona, escribe su nombre.`))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
    quien.focus();
  }

  function pintar() {
    const q = texto.trim().toLowerCase();
    const conteo = (f) => datos.filter((p) => f === "todos" || p.estado === f).length;
    resumen.replaceChildren(kpi(esResidente ? "Esperándote en portería" : "En portería sin entregar", conteo("En porteria"), { destacado: true }));
    chips.replaceWith((chips = filtros([{ id: "En porteria", texto: "En portería", n: conteo("En porteria") }, { id: "Entregado", texto: "Entregados", n: conteo("Entregado") }, { id: "todos", texto: "Todos", n: datos.length }], filtro, (f) => { filtro = f; pintar(); })));
    const v = datos.filter((p) => (filtro === "todos" || p.estado === filtro) && (!q || [p.destinatario_nombre, p.apartamento, p.remitente, p.descripcion].some((x) => (x ?? "").toLowerCase().includes(q))));
    lista.replaceChildren(...(v.length ? v.map((p) => {
      const llegada = deUtc(p.fecha_recepcion), pendiente = p.estado === "En porteria";
      const acc = [p.pendiente || p.entregaPendiente ? badge("Pendiente", "Guardado en este equipo; se enviará al volver el internet") : badge(p.estado)];
      if (esPersonal && pendiente && !p.entregaPendiente) acc.push(
        h("button", { class: "btn sm", onclick: () => entregar(p) }, icono("ok", 16), "Entregar"),
        p.pendiente ? null : h("button", { class: "btn peligro sm", onclick: async () => {
          if (!(await confirmar("¿Anular este registro?", "Úsalo solo si lo registraste por error (por ejemplo, apartamento equivocado). Queda en la auditoría.", "Sí, anular", true))) return;
          try { await api(`/paquetes/${p.id}/anular`, { metodo: "PATCH" }); toast("Registro anulado"); await recargar(); } catch (e) { toast(e.message, "error"); }
        } }, "Anular"));
      return h("div", { class: `item ${p.estado === "Anulado" ? "apagado" : ""}` }, p.tiene_foto ? fotoPaquete(p) : h("div", { class: `ico-caja ${pendiente ? "laton" : ""}` }, icono("caja")),
        h("div", { class: "cuerpo" }, h("b", {}, [p.tipo, p.remitente].filter(Boolean).join(" · ")),
          h("span", { style: "display:block" }, [esPersonal ? `${p.destinatario_nombre}${p.apartamento ? ` · ${p.apartamento}` : ""}` : null, p.descripcion].filter(Boolean).join(" · ") || null),
          h("span", { style: "display:block" }, `Llegó ${fmtFechaHora(llegada)} (${hace(llegada)})${p.recibido_por && esPersonal ? ` · lo recibió ${p.recibido_por}` : ""}`),
          p.estado === "Entregado" ? h("span", { style: "display:block" }, `Entregado a ${p.entregado_a} · ${fmtFechaHora(deUtc(p.fecha_entrega))}`) : null),
        h("div", { class: "acciones" }, ...acc));
    }) : [estadoVacio(filtro === "En porteria" ? (esResidente ? "Nada por recoger" : "Portería sin pendientes") : "Sin registros", esResidente ? "Cuando llegue un paquete o una carta para ti, lo verás aquí." : "No hay paquetes con este filtro.")]));
  }

  // ----- Formulario de registro (solo portería y administración) -----
  let panel = null;
  if (esPersonal) {
    let residentes = [], elegido = null, tipo = "Paquete", auto = null;   // `auto`: autoguardado del formulario (se crea más abajo)
    const buscar = h("input", { id: "pq-buscar", type: "search", placeholder: " ", autocomplete: "off" });
    const selector = h("div", { class: "selector-lista", role: "radiogroup", "aria-label": "Destinatario" });
    const remitente = h("input", { id: "pq-rem", placeholder: " ", maxlength: "60", autocomplete: "off" });
    const desc = h("input", { id: "pq-desc", placeholder: " ", maxlength: "120", autocomplete: "off" });
    const tipos = h("div", { class: "chips", role: "group", "aria-label": "Tipo" });
    const pintarTipos = () => tipos.replaceChildren(...TIPOS.map((t) => h("button", { class: "chip", type: "button", "aria-pressed": String(t === tipo), onclick: () => { tipo = t; pintarTipos(); auto?.programar(); } }, t)));
    const pintarSel = () => selector.replaceChildren(...(residentes.length ? residentes.map((r) => h("button", { type: "button", role: "radio", "aria-checked": String(elegido?.id === r.id), onclick: () => { elegido = r; pintarSel(); auto?.programar(); } },
      r.nombre_completo, h("small", {}, r.apartamento ?? "Sin apartamento"))) : [h("p", { class: "small muted", style: "padding:.6rem" }, "No hay residentes con ese nombre o apartamento.")]));
    // Sin internet se busca en la última lista de residentes guardada en este equipo.
    const buscarRes = async () => {
      const q = buscar.value.trim();
      try { residentes = q ? await api("/paquetes/destinatarios", { params: { q } }) : await leer("destinatarios", () => api("/paquetes/destinatarios")); }
      catch (e) {
        if (e.status !== 0 || !q) return toast(e.message, "error");
        const c = await leerCopia("destinatarios"), t = normal(q);
        residentes = (c?.datos ?? []).filter((r) => normal(r.nombre_completo).includes(t) || normal(r.apartamento).includes(t));
      }
      pintarSel();
    };
    let t; buscar.addEventListener("input", () => { clearTimeout(t); t = setTimeout(buscarRes, 250); });
    const foto = selectorFoto({ titulo: "Foto del paquete (opcional)", ayuda: "Sirve de evidencia de cómo llegó", clave: `paquete-${ctx.usuario.id}`,
      antesDeAbrir: () => auto?.foto(true), alCambiar: (f) => auto?.foto(!!f) });
    auto = autoguardar({ usuarioId: ctx.usuario.id, nombre: "paquete", campos: { buscar, remitente, desc },
      extra: () => ({ tipo, elegido: elegido ? { id: elegido.id, nombre_completo: elegido.nombre_completo, apartamento: elegido.apartamento ?? null } : null }),
      alRestaurar: (e) => { if (TIPOS.includes(e.tipo)) tipo = e.tipo; if (e.elegido?.id) elegido = e.elegido; } });
    const enviar = h("button", { class: "btn block", type: "submit" }, icono("mas", 18), "Registrar llegada");
    panel = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (!elegido) return toast("Elige a quién va dirigido.", "error");
      try {
        const dest = elegido;
        const r = await conCarga(enviar, () => registrar("paquete_registro", { destinatario_id: dest.id, tipo, remitente: remitente.value.trim() || null, descripcion: desc.value.trim() || null },
          { vista: { destinatario_nombre: dest.nombre_completo, apartamento: dest.apartamento ?? null, resumen: `Paquete para ${dest.nombre_completo}` }, foto: foto.archivo() }));
        if (!avisarRegistro(r, `Registrado para ${dest.nombre_completo}`)) return;      // si el servidor lo rechaza se conserva el formulario
        foto.limpiar();                  // la foto ya viaja con el registro (se sube sola, también si no hay internet)
        remitente.value = ""; desc.value = ""; elegido = null; auto.reiniciar(); pintarSel(); filtro = "En porteria"; await recargar();
      } catch (err) { toast(err.message, "error"); }
    } },
      h("div", { class: "card-titulo" }, h("h2", {}, "Registrar llegada")),
      tipos, h("div", { style: "height:.9rem" }),
      h("div", { class: "field" }, buscar, h("label", { for: "pq-buscar" }, "Buscar residente o apartamento")), selector,
      h("div", { class: "field" }, remitente, h("label", { for: "pq-rem" }, "Empresa o mensajero (opcional)")),
      h("div", { class: "field" }, desc, h("label", { for: "pq-desc" }, "Descripción (opcional)"), h("div", { class: "ayuda" }, "Ej. «Caja mediana, frágil»")),
      foto.el, enviar);
    pintarTipos(); await buscarRes();
    // Si el residente elegido no sale en la lista actual, se deja a la vista para que no parezca que se perdió la selección.
    if (auto.restaurado && elegido && !residentes.some((r) => r.id === elegido.id)) { residentes = [elegido, ...residentes]; pintarSel(); }
    auto.avisar();
  }

  pintar();
  alSincronizar(lista, recargar);
  const buscador = h("input", { type: "search", placeholder: esResidente ? "Buscar por remitente" : "Buscar residente, apartamento o remitente", "aria-label": "Buscar", oninput: (e) => { texto = e.target.value; pintar(); } });
  return h("div", {},
    cabecera(esResidente ? "Mis paquetes" : "Paquetes", esResidente ? "Mira si tienes algo esperándote en portería y cuándo lo recogiste." : "Registra lo que llega a portería y entrégalo dejando constancia."),
    h("div", { class: panel ? "grid lados escalona" : "escalona" }, panel,
      h("div", {}, resumen, h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, esResidente ? "Mis paquetes" : "Paquetes y correspondencia"), h("div", { class: "barra-mini" },
          rol === "Administrador" ? h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, "/reportes/paquetes.xlsx", `paquetes_${hoyArchivo()}.xlsx`, { aviso: "Paquetes exportados a Excel." }) }, icono("descarga", 16), "Excel") : null,
          h("div", { class: "buscador" }, icono("buscar"), buscador))),
        h("div", { style: "margin-bottom:1rem" }, chips), lista))));
}
