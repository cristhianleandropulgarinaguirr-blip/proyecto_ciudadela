// Pasarela de pagos de PRUEBAS (tipo Wompi / PSE) — v4.2.
// Sirve para que el cliente VEA cómo será pagar en línea cuando se conecte una pasarela real. No mueve dinero.
// Endpoints: POST /pagos-simulados · POST /pagos-simulados/{ref}/pagar · GET /pagos-simulados/{ref}   (solo con PAGOS_SIMULADOS=1)
//
// Reglas que ya cumple y que también valdrán con la pasarela real:
//   · El resultado (aprobado / rechazado / pendiente) lo decide SIEMPRE el servidor: esta pantalla nunca dice «pagado» por su cuenta.
//   · De la tarjeta solo viajan los 4 últimos dígitos; el número completo, el vencimiento y el CVC se quedan en esta pantalla y se borran al cerrarla.
//   · Un pago «Pendiente» se consulta cada 2 segundos hasta que llegue la confirmación (como el aviso de una pasarela de verdad).
import { api } from "../api.js";
import { h, icono, modal, dinero, toast } from "../ui.js";
import { descargar } from "../descargas.js";

const METODOS = [
  { id: "PSE", titulo: "PSE", detalle: "Débito desde tu cuenta bancaria", icono: "escudo" },
  { id: "Tarjeta", titulo: "Tarjeta", detalle: "Crédito o débito", icono: "tarjeta" },
  { id: "Nequi", titulo: "Nequi", detalle: "Aprueba desde tu celular", icono: "telefono" },
];
const TARJETAS_PRUEBA = [
  { texto: "Una que aprueba", numero: "4242 4242 4242 4242" },
  { texto: "Una que rechaza", numero: "4111 1111 1111 1111" },
  { texto: "Una que queda pendiente", numero: "0000 0000 0000 0002" },
];
const NEQUI_PRUEBA = [
  { texto: "Aprueba", celular: "3001234560" },
  { texto: "Rechaza", celular: "3001234561" },
  { texto: "Queda pendiente", celular: "3001234562" },
];
const MAX_CONSULTAS = 15;            // 15 consultas × 2 s = 30 s esperando la confirmación de un pago pendiente
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
const digitos = (t) => String(t ?? "").replace(/\D/g, "");

/** Caja con etiqueta flotante (misma que el resto de la app). */
function campo(id, etiqueta, { tipo = "text", opciones, ...props } = {}) {
  const control = opciones
    ? h("select", { id, ...props }, opciones.map(([valor, texto]) => h("option", { value: valor }, texto)))
    : h("input", { id, type: tipo, placeholder: " ", autocomplete: "off", ...props });
  return { control, caja: h("div", { class: "field" }, control, h("label", { for: id }, etiqueta)) };
}

/** Botones pequeños que llenan los datos de prueba (para la demostración). */
const atajos = (titulo, lista, alElegir) => h("div", { class: "pp-atajos" }, h("span", {}, titulo),
  lista.map((a) => h("button", { type: "button", class: "chip", onclick: () => alElegir(a) }, a.texto)));

/**
 * Abre la pasarela de pruebas para pagar `valor` (COP). `alTerminar` se llama al cerrarla, para que la pantalla de atrás se actualice.
 */
export async function abrirPasarela({ valor, alTerminar }) {
  let intento;
  try { intento = await api("/pagos-simulados", { metodo: "POST", json: { valor } }); }
  catch (err) { toast(err.message, "error"); return; }

  const raiz = h("div", { class: "pp" });
  modal("Pagar administración", raiz);
  const dialogo = document.getElementById("modal");
  let procesando = false, vivo = true;
  const noCancelar = (e) => { if (procesando) e.preventDefault(); };        // mientras se procesa, Escape no cierra la ventana
  dialogo.addEventListener("cancel", noCancelar);
  dialogo.addEventListener("close", () => { vivo = false; dialogo.removeEventListener("cancel", noCancelar); alTerminar?.(); }, { once: true });
  const cerrar = () => { if (dialogo.open) dialogo.close(); };

  const aviso = () => h("div", { class: "pp-prueba", role: "note" }, icono("alerta", 18),
    h("div", {}, h("b", {}, "MODO DE PRUEBAS"), " · No se cobra dinero real. Así se verá el pago cuando conectemos Wompi o PSE."));
  const resumen = () => h("div", { class: "pp-resumen" }, h("span", {}, "Total a pagar"), h("b", {}, dinero(intento.valor)), h("small", {}, `Referencia ${intento.referencia}`));
  const mostrar = (...nodos) => { if (vivo) raiz.replaceChildren(aviso(), ...nodos); };

  // ------------------------------------------------------------ 1. elegir el método
  function pantallaMetodos() {
    mostrar(resumen(), h("p", { class: "pp-sub" }, "Elige cómo quieres pagar"),
      h("div", { class: "pp-metodos", role: "group", "aria-label": "Método de pago" },
        METODOS.map((m) => h("button", { type: "button", class: "pp-metodo", onclick: () => pantallaDatos(m.id) }, icono(m.icono, 24), h("b", {}, m.titulo), h("span", {}, m.detalle)))),
      h("button", { type: "button", class: "btn suave block", onclick: cerrar }, "Cancelar"));
  }

  // ------------------------------------------------------------ 2. datos del método elegido
  function pantallaDatos(metodo) {
    let leer, extras;                                                      // leer() devuelve { json } o { error }
    if (metodo === "PSE") {
      const banco = campo("pp-banco", "Banco", { opciones: intento.bancos.map((b) => [b.codigo, b.nombre]) });
      const persona = campo("pp-persona", "Tipo de persona", { opciones: [["natural", "Persona natural"], ["juridica", "Persona jurídica"]] });
      const tipoDoc = campo("pp-tdoc", "Tipo de documento", { opciones: [["CC", "Cédula de ciudadanía"], ["CE", "Cédula de extranjería"], ["NIT", "NIT"]] });
      const doc = campo("pp-doc", "Número de documento", { inputmode: "numeric", maxlength: "12" });
      extras = [banco.caja, persona.caja, tipoDoc.caja, doc.caja, h("p", { class: "ayuda" }, "Los datos del documento son de práctica: no se envían ni se guardan.")];
      leer = () => (digitos(doc.control.value).length < 5 ? { error: "Escribe un número de documento (puede ser inventado)." } : { json: { metodo: "PSE", banco: banco.control.value } });
    } else if (metodo === "Tarjeta") {
      const numero = campo("pp-num", "Número de la tarjeta", { inputmode: "numeric", maxlength: "19" });
      const vence = campo("pp-vence", "Vence (MM/AA)", { inputmode: "numeric", maxlength: "5" });
      const cvc = campo("pp-cvc", "CVC", { inputmode: "numeric", maxlength: "4" });
      const titular = campo("pp-titular", "Nombre en la tarjeta", { maxlength: "40" });
      numero.control.addEventListener("input", () => { numero.control.value = digitos(numero.control.value).slice(0, 16).replace(/(\d{4})(?=\d)/g, "$1 "); });
      vence.control.addEventListener("input", () => { const d = digitos(vence.control.value).slice(0, 4); vence.control.value = d.length > 2 ? `${d.slice(0, 2)}/${d.slice(2)}` : d; });
      const llenar = (a) => { numero.control.value = a.numero; vence.control.value = "12/30"; cvc.control.value = "123"; titular.control.value = "TITULAR DE PRUEBA"; };
      extras = [atajos("Tarjetas de prueba:", TARJETAS_PRUEBA, llenar), numero.caja, h("div", { class: "pp-dos" }, vence.caja, cvc.caja), titular.caja,
        h("p", { class: "ayuda" }, "Solo los 4 últimos dígitos viajan al servidor. El resto se borra al cerrar esta ventana.")];
      leer = () => {
        const n = digitos(numero.control.value);
        if (n.length < 13) return { error: "Escribe el número completo de la tarjeta." };
        if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(vence.control.value)) return { error: "La fecha de vencimiento debe ser MM/AA." };
        if (!/^\d{3,4}$/.test(cvc.control.value)) return { error: "El CVC tiene 3 o 4 números." };
        if (!titular.control.value.trim()) return { error: "Escribe el nombre que aparece en la tarjeta." };
        return { json: { metodo: "Tarjeta", terminacion: n.slice(-4) } };
      };
    } else {
      const celular = campo("pp-cel", "Celular de tu cuenta Nequi", { inputmode: "numeric", maxlength: "10" });
      celular.control.addEventListener("input", () => { celular.control.value = digitos(celular.control.value).slice(0, 10); });
      extras = [atajos("Números de prueba:", NEQUI_PRUEBA, (a) => { celular.control.value = a.celular; }), celular.caja,
        h("p", { class: "ayuda" }, "En la pasarela real te llegaría una notificación a la app de Nequi para aprobar el pago.")];
      leer = () => (/^3\d{9}$/.test(celular.control.value) ? { json: { metodo: "Nequi", celular: celular.control.value } } : { error: "El celular debe tener 10 números y empezar por 3." });
    }
    const pagar = h("button", { class: "btn arcilla block", type: "submit" }, `Pagar ${dinero(intento.valor)}`);
    mostrar(resumen(),
      h("form", { novalidate: true, autocomplete: "off", onsubmit: (e) => { e.preventDefault(); const r = leer(); if (r.error) return toast(r.error, "error"); enviar(r.json); } },
        h("p", { class: "pp-sub" }, METODOS.find((m) => m.id === metodo).detalle), extras, pagar,
        h("button", { type: "button", class: "btn texto block", style: "margin-top:.4rem", onclick: pantallaMetodos }, "Cambiar método")));
  }

  // ------------------------------------------------------------ 3. procesar (y esperar la confirmación si queda pendiente)
  async function enviar(json) {
    procesando = true;
    mostrar(h("div", { class: "pasarela", role: "status" }, h("div", { class: "spinner" }), h("b", {}, "Procesando tu pago…"), h("p", { class: "muted small" }, "No cierres esta ventana.")));
    try {
      let [r] = await Promise.all([api(`/pagos-simulados/${intento.referencia}/pagar`, { metodo: "POST", json }), esperar(1400)]);
      for (let i = 0; r.estado === "Pendiente" && vivo && i < MAX_CONSULTAS; i++) {
        mostrar(h("div", { class: "pasarela", role: "status" }, h("div", { class: "spinner" }), h("b", {}, "Esperando la confirmación…"),
          h("p", { class: "muted small" }, r.mensaje || "Tu entidad está validando el pago."), h("p", { class: "muted small" }, "Esto suele tardar unos segundos.")));
        await esperar(2000);
        if (!vivo) return;
        r = await api(`/pagos-simulados/${intento.referencia}`);
      }
      procesando = false;
      pantallaResultado(r);
    } catch (err) {
      procesando = false;
      toast(err.message, "error");
      if (vivo) pantallaMetodos();
    }
  }

  // ------------------------------------------------------------ 4. resultado (lo que dijo el servidor)
  function pantallaResultado(r) {
    const clase = { Aprobado: "ok", Rechazado: "mal", Pendiente: "espera", Expirado: "espera" }[r.estado] ?? "espera";
    const ico = { ok: "ok", mal: "x", espera: "reloj" }[clase];
    const titulo = { Aprobado: "Pago aprobado", Rechazado: "Pago rechazado", Pendiente: "Pago en validación", Expirado: "El tiempo se agotó" }[r.estado] ?? r.estado;
    const detalle = (k, v) => h("div", {}, h("dt", {}, k), h("dd", {}, v));
    const acciones = [];
    if (r.estado === "Aprobado" && r.pago_id) acciones.push(h("button", { class: "btn suave block", onclick: (e) => descargar(e.currentTarget, `/reportes/recibo/${r.pago_id}.pdf`, `comprobante_${r.referencia}.pdf`) }, icono("descarga", 18), "Descargar comprobante"));
    if (r.estado === "Rechazado" || r.estado === "Expirado") acciones.push(h("button", { class: "btn block", onclick: () => { cerrar(); abrirPasarela({ valor: intento.valor, alTerminar }); } }, "Intentar de nuevo"));
    acciones.push(h("button", { class: r.estado === "Aprobado" ? "btn block" : "btn suave block", onclick: cerrar }, r.estado === "Aprobado" ? "Listo" : "Cerrar"));
    mostrar(h("div", { class: "pp-resultado", role: "status" },
      h("div", { class: `pp-ico ${clase}` }, icono(ico, 34)),
      h("h3", {}, titulo),
      h("p", { class: "muted" }, r.mensaje || ""),
      r.estado === "Aprobado" ? h("p", { class: "pp-saldo" }, r.esta_al_dia ? "Tu apartamento quedó al día." : `Saldo restante: ${dinero(r.saldo_pendiente)}`) : null,
      r.estado === "Rechazado" ? h("p", { class: "pp-saldo" }, "No se descontó nada de tu saldo.") : null,
      r.estado === "Pendiente" ? h("p", { class: "pp-saldo" }, "Sigue en validación. Cuando se confirme, el pago aparecerá en Mis pagos.") : null,
      h("dl", { class: "pp-detalle" }, detalle("Referencia", r.referencia), r.metodo ? detalle("Método", r.metodo) : null, detalle("Valor", dinero(r.valor)), detalle("Estado", r.estado)),
      h("p", { class: "small muted" }, "Esto fue una prueba: no se movió dinero real."),
      acciones));
  }

  pantallaMetodos();
}
