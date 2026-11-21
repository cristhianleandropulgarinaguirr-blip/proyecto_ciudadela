// Cartera / recaudo de administración.
// Endpoints: GET /administracion/estado-cuenta/{id} · PATCH /administracion/registrar-deuda/{id}?saldo_pendiente=
//            Pago en línea de PRUEBAS (tipo Wompi/PSE, solo con PAGOS_SIMULADOS=1): ver pasarela.js  →  POST /pagos-simulados · /{ref}/pagar · GET /{ref}
//            POST /administracion/registrar-pago/{id}?valor_pagado=&referencia=   (administrador: pago real recibido)
//            GET  /administracion/config-pagos · GET /administracion/cartera (administrador: todos los residentes en UNA petición)
//            POST /paz-y-salvo · GET /paz-y-salvo · GET /paz-y-salvo/{id}/pdf   (paz y salvo con QR de verificación)
import { api, apiBlob } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, dinero, kpi, deUtc, fmtFechaHora } from "../ui.js";
import { cabecera } from "./comun.js";
import { descargar, guardarBlob, hoyArchivo } from "../descargas.js";
import { abrirPasarela } from "./pasarela.js";

// ---------- Paz y salvo con QR (residente, inquilino con permiso y administrador) ----------
const ESTADO_PAZ = { Vigente: "bosque", Vencido: "borde", Revocado: "laton", "No vigente": "laton" };
const nombrePdf = (p) => `paz_y_salvo_${p.folio}.pdf`;

/** Genera el certificado (solo si el apartamento está al día) y lo descarga. `usuarioId` solo lo usa el administrador. */
async function generarPaz(boton, { destino, usuarioId } = {}) {
  const json = {}; if (destino?.trim()) json.destino = destino.trim(); if (usuarioId) json.usuario_id = usuarioId;
  try {
    const p = await conCarga(boton, () => api("/paz-y-salvo", { metodo: "POST", json }));
    guardarBlob(await apiBlob(`/paz-y-salvo/${p.id}/pdf`), nombrePdf(p));
    toast(`Paz y salvo ${p.folio} generado. Tiene un QR para verificarlo.`);
    return p;
  } catch (err) { toast(err.message, "error"); return null; }
}

async function copiarEnlaceVerificacion(p) {
  try { await navigator.clipboard.writeText(`${location.origin}${p.enlace}`); toast("Enlace de verificación copiado."); }
  catch { toast("No se pudo copiar el enlace.", "error"); }
}

// ---------- Residente: su estado de cuenta + pago ----------
async function vistaResidente(ctx) {
  let cuenta = await api(`/administracion/estado-cuenta/${ctx.usuario.id}`);
  let pagos = await api("/administracion/mis-pagos");
  const cfg = await api("/administracion/config-pagos").catch(() => ({ pagos_simulados: false, instrucciones: "" }));
  let pazs = await api("/paz-y-salvo").catch(() => []);
  const raiz = h("div", { class: "grid dos escalona" });
  const botonComprobante = (p, clase = "btn suave sm") => h("button", { class: clase, onclick: (e) => descargar(e.currentTarget, `/reportes/recibo/${p.id}.pdf`, `comprobante_${p.comprobante}.pdf`) }, icono("descarga", 16), "Comprobante");

  // Pago real: el residente paga por fuera y el administrador registra el valor recibido.
  const comoPagar = () => h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Cómo pagar")),
    h("p", { style: "margin-bottom:.8rem" }, cfg.instrucciones || "Paga por transferencia y avisa en la administración."),
    h("p", { class: "small muted" }, "Cuando la administración registre tu pago, aparece aquí abajo con su comprobante en PDF."));

  function tarjetaPaz(alDia) {
    const destino = h("input", { id: "paz-destino", type: "text", maxlength: "80", placeholder: " " });
    const boton = h("button", { class: "btn", type: "submit" }, icono("descarga", 18), "Generar y descargar");
    return h("div", { class: "card", style: "grid-column: 1 / -1" }, h("div", { class: "card-titulo" }, h("h2", {}, "Paz y salvo")),
      alDia
        ? h("form", { novalidate: true, onsubmit: async (e) => { e.preventDefault(); const p = await generarPaz(boton, { destino: destino.value }); if (p) { pazs = await api("/paz-y-salvo").catch(() => pazs); pintar(); } } },
            h("p", { class: "muted small", style: "margin-bottom:.8rem" }, "Certificado en PDF para mudanzas o trámites bancarios. Lleva un código QR: quien lo reciba lo escanea y comprueba en línea que es auténtico y está vigente."),
            h("div", { class: "field" }, destino, h("label", { for: "paz-destino" }, "¿Para qué lo necesitas? (opcional)")), boton)
        : h("div", { class: "aviso" }, icono("alerta"), h("div", {}, "Para generar el paz y salvo el apartamento debe estar al día con la administración.")),
      pazs.length ? h("div", { class: "lista", style: "margin-top:.9rem" }, pazs.slice(0, 5).map((p) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("escudo")),
        h("div", { class: "cuerpo" }, h("b", {}, p.folio, p.destino ? ` · ${p.destino}` : ""), h("span", {}, `${fmtFechaHora(deUtc(p.fecha_emision))} · válido hasta ${fmtFechaHora(deUtc(p.valido_hasta))}`)),
        h("div", { class: "acciones" }, h("span", { class: `badge ${ESTADO_PAZ[p.estado] ?? ""}` }, p.estado),
          h("button", { class: "btn suave sm", title: "Copiar el enlace de verificación", onclick: () => copiarEnlaceVerificacion(p) }, "Enlace"),
          h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, `/paz-y-salvo/${p.id}/pdf`, nombrePdf(p)) }, icono("descarga", 16), "PDF"))))) : null);
  }

  function pintar() {
    const alDia = cuenta.saldo_pendiente === 0;
    const monto = h("input", { id: "monto", type: "number", inputmode: "numeric", min: "1", max: String(cuenta.saldo_pendiente), placeholder: " ", value: String(cuenta.saldo_pendiente) });
    const pagar = h("button", { class: "btn arcilla block", type: "submit" }, "Pagar ahora");
    const form = h("form", { class: "card", novalidate: true, onsubmit: (e) => { e.preventDefault(); iniciarPago(Number(monto.value), pagar); } },
      h("div", { class: "card-titulo" }, h("h2", {}, "Pagar administración")),
      h("div", { class: "field" }, monto, h("label", { for: "monto" }, "Valor a pagar (COP)")),
      h("div", { class: "rapidos" },
        h("button", { type: "button", class: "chip", onclick: () => { monto.value = cuenta.saldo_pendiente; } }, `Todo · ${dinero(cuenta.saldo_pendiente)}`),
        cuenta.saldo_pendiente > 1 ? h("button", { type: "button", class: "chip", onclick: () => { monto.value = Math.ceil(cuenta.saldo_pendiente / 2); } }, "La mitad") : null),
      pagar, h("p", { class: "small muted", style: "margin-top:.8rem" }, "Modo de pruebas: eliges PSE, tarjeta o Nequi, pero no se cobra dinero real."));

    raiz.replaceChildren(
      h("section", { class: "cuenta" },
        h("div", { class: "et" }, cuenta.apartamento ?? "Mi apartamento"),
        h("div", { class: "monto" }, dinero(cuenta.saldo_pendiente)),
        h("div", { class: "datos" }, h("span", {}, `Cuota mensual: ${dinero(cuenta.valor_administracion)}`), alDia ? badge("Al día", "Al día") : h("span", { class: "badge laton" }, "En mora"))),
      alDia
        ? h("div", { class: "card" }, h("div", { class: "aviso ok" }, icono("ok"), h("div", {}, "Estás al día con la administración. Puedes reservar zonas comunes sin restricciones.")),
            h("a", { class: "btn", href: "#/reservas" }, "Reservar una zona", icono("flecha", 18)))
        : cfg.pagos_simulados ? form : comoPagar(),
      h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Estado de cuenta")),
        h("p", { class: "muted small", style: "margin-bottom:.8rem" }, "Descárgalo en PDF para tus trámites. Si estás al día, indica que el apartamento está a paz y salvo."),
        h("button", { class: "btn suave", onclick: (e) => descargar(e.currentTarget, `/reportes/estado-cuenta/${ctx.usuario.id}.pdf`, `estado_de_cuenta_${hoyArchivo()}.pdf`) }, icono("descarga", 18), "Descargar PDF")),
      tarjetaPaz(alDia),
      h("div", { class: "card", style: "grid-column: 1 / -1" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis pagos")),
        pagos.length ? h("div", { class: "lista" }, pagos.map((p) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("tarjeta")),
          h("div", { class: "cuerpo" }, h("b", {}, dinero(p.valor)), h("span", {}, `${fmtFechaHora(deUtc(p.fecha))} · ${p.comprobante}`),
            h("span", { style: "display:block" }, p.saldo_posterior === 0 ? "Quedaste al día" : `Saldo después: ${dinero(p.saldo_posterior)}`)),
          h("div", { class: "acciones" }, botonComprobante(p)))))
          : estadoVacio("Aún no has hecho pagos aquí", "Cuando pagues, cada pago queda guardado con su comprobante en PDF.")));
  }

  // v4.2: el pago en línea es una pasarela de PRUEBAS tipo Wompi/PSE (pasarela.js). Al cerrarla se recarga el saldo y la lista de pagos.
  async function iniciarPago(valor, boton) {
    if (!Number.isInteger(valor) || valor <= 0) return toast("Ingresa un valor válido.", "error");
    if (valor > cuenta.saldo_pendiente) return toast(`El valor no puede superar tu saldo (${dinero(cuenta.saldo_pendiente)}).`, "error");
    await conCarga(boton, () => abrirPasarela({
      valor,
      alTerminar: async () => {
        try { cuenta = await api(`/administracion/estado-cuenta/${ctx.usuario.id}`); pagos = await api("/administracion/mis-pagos"); ctx.actualizarUsuario(); } catch { /* se queda con lo que había */ }
        pintar();
      },
    }));
  }

  pintar();
  return h("div", {}, cabecera("Mis pagos", "Mira cuánto debes, paga la administración y descarga tus comprobantes."), raiz);
}

// ---------- Administrador: cartera de todos los residentes ----------
async function vistaAdmin() {
  // v3.6: UNA sola petición con todos los residentes y sus saldos (antes: el listado de usuarios + el estado de cuenta de cada residente, 201 peticiones con 200 residentes).
  let filas = (await api("/administracion/cartera")).map((f) => ({ u: { id: f.usuario_id, nombre_completo: f.nombre_completo }, c: f }));
  const cuerpo = h("tbody"), resumen = h("div", { class: "kpis" });

  function pintar() {
    const total = filas.reduce((s, f) => s + f.c.saldo_pendiente, 0);
    const mora = filas.filter((f) => f.c.saldo_pendiente > 0).length;
    resumen.replaceChildren(
      kpi("Cartera total", total, { destacado: true, formato: dinero }),
      kpi("Apartamentos en mora", mora, { alerta: true }),
      kpi("Recaudo mensual esperado", filas.reduce((s, f) => s + f.c.valor_administracion, 0), { formato: dinero }));
    cuerpo.replaceChildren(...filas.map(({ u, c }) => h("tr", {},
      h("td", { class: "ancho" }, h("div", { class: "persona" }, h("div", {}, h("b", {}, u.nombre_completo), h("span", {}, c.apartamento ?? "Sin apartamento")))),
      h("td", { "data-et": "Cuota" }, dinero(c.valor_administracion)),
      h("td", { "data-et": "Saldo", class: "der" }, h("b", {}, dinero(c.saldo_pendiente))),
      h("td", { "data-et": "Estado" }, c.esta_al_dia ? badge("Al día", "Al día") : badge("En mora", "En mora")),
      h("td", { class: "ancho der" }, h("div", { class: "acciones-cartera" },
        // Columna 1: «Registrar pago» (si debe) o «Paz y salvo» (si está al día) · Columna 2: «Registrar saldo» · Columna 3: «PDF». Así todas las filas quedan alineadas.
        c.saldo_pendiente > 0
          ? h("button", { class: "btn sm", onclick: () => registrarPago(u, c) }, "Registrar pago")
          : h("button", { class: "btn suave sm", title: "Generar el paz y salvo con QR", onclick: (e) => generarPaz(e.currentTarget, { usuarioId: u.id }) }, icono("escudo", 16), "Paz y salvo"),
        h("button", { class: "btn suave sm", onclick: () => editarDeuda(u, c) }, "Registrar saldo"),
        h("button", { class: "btn suave sm", title: "Estado de cuenta en PDF", "aria-label": `Estado de cuenta de ${u.nombre_completo} en PDF`, onclick: (e) => descargar(e.currentTarget, `/reportes/estado-cuenta/${u.id}.pdf`, `estado_de_cuenta_${(c.apartamento ?? u.id).toString().replace(/\s+/g, "_")}.pdf`) }, icono("descarga", 16), "PDF"))))));
  }

  function registrarPago(u, c) {
    const valor = h("input", { id: "pago-valor", type: "number", min: "1", max: String(c.saldo_pendiente), inputmode: "numeric", placeholder: " ", value: String(c.saldo_pendiente) });
    const ref = h("input", { id: "pago-ref", type: "text", maxlength: "60", placeholder: " " });
    const guardar = h("button", { class: "btn", type: "submit", form: "f-pago" }, "Registrar pago");
    const m = modal(`Pago de ${u.nombre_completo}`, h("form", { id: "f-pago", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      const n = Number(valor.value);
      if (!Number.isInteger(n) || n <= 0) return toast("Ingresa un valor válido.", "error");
      if (n > c.saldo_pendiente) return toast(`No puede superar el saldo (${dinero(c.saldo_pendiente)}).`, "error");
      try {
        const params = { valor_pagado: n }; if (ref.value.trim()) params.referencia = ref.value.trim();
        const r = await conCarga(guardar, () => api(`/administracion/registrar-pago/${u.id}`, { metodo: "POST", params }));
        const nuevo = await api(`/administracion/estado-cuenta/${u.id}`);
        filas = filas.map((f) => (f.u.id === u.id ? { u, c: nuevo } : f)); pintar(); m.cerrar();
        toast(r.mensaje);
      } catch (err) { toast(err.message, "error"); }
    } },
      h("p", { class: "muted small", style: "margin-bottom:1rem" }, `Saldo actual: ${dinero(c.saldo_pendiente)}. Registra lo que recibiste por transferencia o en efectivo; el residente recibe su comprobante y un aviso.`),
      h("div", { class: "field" }, valor, h("label", { for: "pago-valor" }, "Valor recibido (COP)")),
      h("div", { class: "field" }, ref, h("label", { for: "pago-ref" }, "Referencia del comprobante (opcional)"))),
      { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
  }

  function editarDeuda(u, c) {
    const valor = h("input", { id: "saldo", type: "number", min: "0", inputmode: "numeric", placeholder: " ", value: String(c.saldo_pendiente) });
    const guardar = h("button", { class: "btn", type: "submit", form: "f-deuda" }, "Guardar");
    const m = modal(`Saldo de ${u.nombre_completo}`, h("form", { id: "f-deuda", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      const n = Number(valor.value);
      if (!Number.isInteger(n) || n < 0) return toast("Ingresa un valor igual o mayor a 0.", "error");
      try {
        const nuevo = await conCarga(guardar, () => api(`/administracion/registrar-deuda/${u.id}`, { metodo: "PATCH", params: { saldo_pendiente: n } }));
        filas = filas.map((f) => (f.u.id === u.id ? { u, c: nuevo } : f)); pintar(); m.cerrar();
        toast(n === 0 ? "Apartamento al día." : "Saldo registrado. Queda en mora.");
      } catch (err) { toast(err.message, "error"); }
    } },
      h("p", { class: "muted small", style: "margin-bottom:1rem" }, "Si el saldo es mayor a 0 el apartamento queda en mora y no podrá reservar zonas comunes."),
      h("div", { class: "field" }, valor, h("label", { for: "saldo" }, "Saldo pendiente (COP)"))),
      { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), guardar] });
  }

  pintar();
  const excel = h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, "/reportes/cartera.xlsx", `cartera_${hoyArchivo()}.xlsx`, { aviso: "Cartera exportada a Excel." }) }, icono("descarga", 16), "Exportar a Excel");
  return h("div", {}, cabecera("Cartera", "Seguimiento del recaudo de administración por apartamento."), resumen,
    h("div", { class: "barra" }, h("span", {}), h("a", { class: "btn suave sm", href: "#/importar" }, icono("subir", 16), "Cargar desde Excel"), excel),
    h("div", { class: "card" }, filas.length
      ? h("div", { class: "tabla-wrap tabla-ancha" }, h("table", { class: "tabla" },
          h("thead", {}, h("tr", {}, h("th", {}, "Residente"), h("th", {}, "Cuota"), h("th", { class: "der" }, "Saldo"), h("th", {}, "Estado"), h("th", {}))), cuerpo))
      : estadoVacio("Aún no hay residentes", "Crea residentes desde la sección Usuarios.")));
}

// El inquilino (con el pago delegado) ve y paga la cuenta del APARTAMENTO, que es del propietario: se usa el id del propietario para consultarla.
async function vistaInquilino(ctx) {
  const c = await api("/arrendamientos/mio");
  const vista = await vistaResidente({ ...ctx, usuario: { ...ctx.usuario, id: c.propietario_id } });
  vista.prepend(h("p", { class: "small muted", style: "grid-column: 1 / -1" },
    `Estás viendo la cuenta de tu apartamento (propietario: ${c.propietario_nombre}). Lo que pagues queda a nombre del apartamento y se le avisa a él.`));
  return vista;
}

export const render = (ctx) => (ctx.usuario.rol === "Administrador" ? vistaAdmin() : ctx.usuario.rol === "Inquilino" ? vistaInquilino(ctx) : vistaResidente(ctx));
