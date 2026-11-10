// Mi QR: el carnet permanente y los pases para visitantes.
// Endpoints: GET /qr/mi-carnet · POST /qr/mi-carnet/renovar · GET/POST /qr/visitantes · POST /qr/visitantes/{id}/revocar
//            GET /qr/{id}/imagen?formato=png (protegida: se pide con el token y se muestra como blob)
import { api, apiBlob } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaHora, placa, logoCompleto } from "../ui.js";
import { cabecera } from "./comun.js";

const PLACA = /^[A-Za-z]{3}[0-9]{2}[A-Za-z0-9]$/;
const HORAS = [[2, "2 horas"], [6, "6 horas"], [12, "12 horas"], [24, "1 día"], [48, "2 días"], [72, "3 días"]];

// <img> del QR con su carga protegida. Devuelve el nodo y una función para obtener el blob (compartir / descargar).
function imagenQR(codigo) {
  const img = h("img", { class: "qr-img", alt: `Código QR de ${codigo.propietario_nombre}`, width: 240, height: 240 });
  const caja = h("div", { class: "qr-caja" }, h("div", { class: "spinner" }), img);
  let blob = null;
  const pedir = async () => (blob ??= await apiBlob(`/qr/${codigo.id}/imagen`, { params: { formato: "png" } }));
  pedir().then((b) => { img.src = URL.createObjectURL(b); caja.classList.add("lista-qr"); })
    .catch(() => caja.replaceChildren(estadoVacio("No se pudo cargar el QR", "Intenta de nuevo.")));
  return { nodo: caja, blob: pedir };
}

async function descargar(blobFn, nombre) {
  const a = h("a", { href: URL.createObjectURL(await blobFn()), download: nombre });
  document.body.append(a); a.click(); a.remove();
}
async function compartir(blobFn, nombre, texto) {
  const archivo = new File([await blobFn()], nombre, { type: "image/png" });
  if (navigator.canShare?.({ files: [archivo] })) {
    try { await navigator.share({ files: [archivo], text: texto }); } catch { /* el usuario canceló */ }
  } else { await descargar(blobFn, nombre); toast("Imagen descargada. Envíala por WhatsApp o donde prefieras."); }
}

// ---------------------------------------------------------------- carnet
export async function pestanaCarnet(ctx) {
  let c = await api("/qr/mi-carnet");
  const u = ctx.usuario, cont = h("div");
  function pintar() {
    const { nodo, blob } = imagenQR(c);
    const renovar = h("button", { class: "btn suave sm", onclick: async () => {
      if (!(await confirmar("¿Renovar tu carnet?", "Tu QR actual dejará de funcionar de inmediato y se generará uno nuevo.", "Sí, renovar"))) return;
      try { c = await conCarga(renovar, () => api("/qr/mi-carnet/renovar", { metodo: "POST" })); toast("Carnet renovado"); pintar(); }
      catch (e) { toast(e.message, "error"); }
    } }, "Renovar código");
    cont.replaceChildren(h("div", { class: "grid lados" },
      h("section", { class: "carnet" },
        h("div", { class: "carnet-cab" }, logoCompleto()),
        nodo,
        h("div", { class: "carnet-datos" }, h("b", {}, u.nombre_completo),
          h("span", {}, [u.rol, u.apartamento].filter(Boolean).join(" · ")),
          u.parqueadero_asignado && u.parqueadero_asignado !== "Ninguno" ? h("span", {}, `Parqueadero ${u.parqueadero_asignado}`) : null)),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Cómo usarlo")),
        h("ol", { class: "lista-pasos" },
          h("li", {}, "Abre esta pantalla y muéstrasela al guardia cuando te lo pida."),
          h("li", {}, "El guardia lo escanea y confirma que eres quien dices ser."),
          h("li", {}, "El QR no contiene tus datos: solo un código secreto que la portería valida.")),
        h("div", { class: "acciones-fila" },
          h("button", { class: "btn suave sm", onclick: () => descargar(blob, "mi-carnet-ciudadela.png") }, icono("descarga", 16), "Descargar"),
          renovar),
        h("p", { class: "small muted", style: "margin-top:.8rem" }, "Si perdiste el celular o compartiste el QR por error, renueva el código."))));
  }
  pintar();
  return cont;
}

// ---------------------------------------------------------------- pases de visitante
function mostrarPase(p) {
  const { nodo, blob } = imagenQR(p);
  const texto = `Pase de ingreso para ${p.nombre_visitante} (${p.placa}). Muéstrale este QR al guardia al llegar y al salir. Válido hasta ${fmtFechaHora(deUtc(p.valido_hasta))}.`;
  modal(`Pase de ${p.nombre_visitante}`, h("div", { class: "pase-modal" }, nodo,
    h("div", { class: "pase-datos" }, placa(p.placa), h("span", { class: "small muted" }, `Sirve para ingresar hasta ${fmtFechaHora(deUtc(p.valido_hasta))}`)),
    h("div", { class: "acciones-fila" },
      h("button", { class: "btn", onclick: () => compartir(blob, `pase-${p.placa}.png`, texto) }, icono("compartir", 16), "Compartir"),
      h("button", { class: "btn suave", onclick: () => descargar(blob, `pase-${p.placa}.png`) }, icono("descarga", 16), "Descargar"))));
}

export async function pestanaVehiculo(ctx) {
  let pases = await api("/qr/visitantes");
  const lista = h("div", { class: "lista" });

  function pintar() {
    lista.replaceChildren(...(pases.length ? pases.map((p) => {
      const vivo = p.estado === "Activo" || p.estado === "Dentro";
      return h("div", { class: `vehiculo pase ${vivo ? "" : "apagado"}` }, placa(p.placa),
        h("div", { class: "cuerpo" }, h("b", {}, p.nombre_visitante),
          h("div", { class: "small muted" }, p.estado === "Dentro" ? "Está dentro del conjunto" : p.valido_hasta ? `Ingresar antes de ${fmtFechaHora(deUtc(p.valido_hasta))}` : "")),
        h("div", { class: "acciones" }, badge(p.estado, p.estado === "Dentro" ? "Dentro" : undefined),
          vivo ? h("button", { class: "btn suave sm", onclick: () => mostrarPase(p) }, icono("qr", 16), "Ver QR") : null,
          p.estado === "Activo" ? h("button", { class: "btn peligro sm", onclick: async () => {
            if (!(await confirmar("¿Revocar este pase?", `El QR de ${p.nombre_visitante} dejará de funcionar.`, "Sí, revocar", true))) return;
            try { Object.assign(p, await api(`/qr/visitantes/${p.id}/revocar`, { metodo: "POST" })); toast("Pase revocado"); pintar(); }
            catch (e) { toast(e.message, "error"); }
          } }, "Revocar") : null));
    }) : [estadoVacio("Aún no tienes pases", "Crea uno cuando esperes una visita con vehículo.")]));
  }

  function nuevo() {
    const nombre = h("input", { id: "pv-nombre", placeholder: " ", maxlength: "60", autocomplete: "off" });
    const pl = h("input", { id: "pv-placa", class: "mono", placeholder: " ", maxlength: "6", autocapitalize: "characters", autocomplete: "off", spellcheck: "false" });
    pl.addEventListener("input", () => { pl.value = pl.value.toUpperCase().replace(/[^A-Z0-9]/g, ""); });
    const horas = h("select", { id: "pv-horas" }, HORAS.map(([v, t]) => h("option", { value: v, selected: v === 12 }, t)));
    const ok = h("button", { class: "btn", type: "submit", form: "f-pase" }, "Crear pase");
    const m = modal("Nuevo pase de visitante", h("form", { id: "f-pase", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (nombre.value.trim().length < 3) return toast("Escribe el nombre del visitante.", "error");
      if (!PLACA.test(pl.value)) return toast("La placa no es válida (ej. ABC123 o ABC12D).", "error");
      try {
        const p = await conCarga(ok, () => api("/qr/visitantes", { metodo: "POST", json: { nombre_visitante: nombre.value.trim(), placa: pl.value, horas_validez: Number(horas.value) } }));
        pases = [p, ...pases]; pintar(); m.cerrar(); mostrarPase(p);
      } catch (err) { toast(err.message, "error"); }
    } },
      h("div", { class: "field" }, nombre, h("label", { for: "pv-nombre" }, "Nombre del visitante")),
      h("div", { class: "field" }, pl, h("label", { for: "pv-placa" }, "Placa del vehículo"), h("div", { class: "ayuda" }, "Carro: ABC123 · Moto: ABC12D")),
      h("div", { class: "field" }, horas, h("label", { for: "pv-horas" }, "Puede ingresar durante")),
      h("p", { class: "small muted" }, "Al llegar, el guardia escanea el QR y registra el ingreso; al salir lo escanea de nuevo y registra la salida.")),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
    nombre.focus();
  }

  pintar();
  return h("div", {}, h("div", { class: "barra" }, h("p", { class: "muted" }, "Invita a alguien sin llamar a portería: le envías el QR y entra con su placa registrada."),
    h("button", { class: "btn", onclick: nuevo }, icono("mas", 18), "Nuevo pase")), lista);
}

export async function render(ctx) {
  const panel = h("div"), tabs = h("div", { class: "tabs", role: "tablist" });
  let actual = "carnet";
  async function mostrar(cual) {
    actual = cual;
    tabs.replaceChildren(...[["carnet", "Mi carnet"], ["visitantes", "Pases con vehículo"]].map(([id, t]) =>
      h("button", { class: "tab", role: "tab", "aria-selected": String(id === actual), onclick: () => id !== actual && mostrar(id) }, t)));
    panel.replaceChildren(h("div", { class: "esq", style: "height:200px" }));
    try { const nodo = cual === "carnet" ? await pestanaCarnet(ctx) : await pestanaVehiculo(ctx); if (cual === actual) panel.replaceChildren(nodo); }
    catch (e) { toast(e.message, "error"); }
  }
  await mostrar("carnet");
  return h("div", {}, cabecera("Mi QR", "Tu identificación digital y los pases de un solo uso para visitas con vehículo. Para personas frecuentes usa Visitantes."), tabs, panel);
}
