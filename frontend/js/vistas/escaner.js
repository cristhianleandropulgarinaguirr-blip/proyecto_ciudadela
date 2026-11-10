// Escáner de QR para portería (guardia y administrador).
// Lee con la cámara (BarcodeDetector nativo; si el navegador no lo tiene, jsQR) o con un lector USB / escribiendo el código.
// Endpoints: POST /qr/escanear · GET /qr/escaneos
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, deUtc, hace, placa } from "../ui.js";

let jsqrPromesa = null;
const cargarJsQR = () => (jsqrPromesa ??= new Promise((ok, mal) => {
  if (window.jsQR) return ok(window.jsQR);
  const s = h("script", { src: "js/vendor/jsQR.js" });
  s.onload = () => ok(window.jsQR); s.onerror = () => mal(new Error("No se pudo cargar el lector de QR."));
  document.head.append(s);
}));

function tarjetaResultado(r) {
  const clase = r.ok ? "ok" : "mal";
  const detalle = [];
  if (r.persona) detalle.push(h("b", {}, r.persona.nombre_completo), h("span", {}, [r.persona.rol, r.persona.apartamento].filter(Boolean).join(" · ")),
    r.persona.parqueadero && r.persona.parqueadero !== "Ninguno" ? h("span", {}, `Parqueadero ${r.persona.parqueadero}`) : null);
  if (r.visitante) detalle.push(placa(r.visitante.placa), h("b", {}, r.visitante.nombre_visitante),
    h("span", {}, `Va para ${r.visitante.apartamento_destino} · autoriza ${r.visitante.autorizado_por}`));
  return h("div", { class: `resultado-qr ${clase}`, role: "alert" },
    h("div", { class: "titulo" }, icono(r.ok ? "ok" : "alerta", 22), h("b", {}, r.resultado)),
    h("p", {}, r.mensaje), detalle.length ? h("div", { class: "detalle" }, detalle) : null);
}

export function vistaEscaner() {
  const resultado = h("div", { class: "resultado-hueco", "aria-live": "assertive" });
  const bitacora = h("div", { class: "lista" });
  const video = h("video", { class: "visor-video", playsinline: true, muted: true, autoplay: true });
  const visor = h("div", { class: "visor", hidden: true }, video, h("div", { class: "marco" }, h("i"), h("i"), h("i"), h("i")));
  let stream = null, activo = false, ocupado = false, ultimo = "", ultimoT = 0;

  async function enviar(texto) {
    const t = texto.trim();
    if (!t || ocupado) return;
    if (t === ultimo && Date.now() - ultimoT < 3000) return;   // la cámara ve el mismo QR varios cuadros seguidos
    ocupado = true; ultimo = t; ultimoT = Date.now();
    try {
      const r = await api("/qr/escanear", { metodo: "POST", json: { codigo: t } });
      resultado.replaceChildren(tarjetaResultado(r));
      navigator.vibrate?.(r.ok ? 80 : [120, 60, 120]);
      cargarBitacora();
    } catch (e) { toast(e.message, "error"); }
    finally { ocupado = false; }
  }

  async function detener() {
    activo = false; stream?.getTracks().forEach((t) => t.stop()); stream = null; video.srcObject = null;
    visor.hidden = true; btnCamara.replaceChildren(icono("camara", 18), "Activar cámara"); btnCamara.dataset.on = "";
  }

  async function activar() {
    if (!window.isSecureContext) return toast("La cámara solo funciona con HTTPS (o en localhost). Usa el campo de abajo para escribir el código.", "error");
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false }); }
    catch { return toast("No se pudo abrir la cámara. Revisa el permiso del navegador.", "error"); }
    video.srcObject = stream; await video.play().catch(() => {});
    visor.hidden = false; activo = true; btnCamara.replaceChildren(icono("x", 18), "Apagar cámara"); btnCamara.dataset.on = "1";

    let leer;
    if ("BarcodeDetector" in window) {
      const det = new BarcodeDetector({ formats: ["qr_code"] });
      leer = async () => (await det.detect(video))[0]?.rawValue;
    } else {
      const jsQR = await cargarJsQR().catch((e) => { toast(e.message, "error"); detener(); });
      if (!jsQR) return;
      const lienzo = document.createElement("canvas"), cx = lienzo.getContext("2d", { willReadFrequently: true });
      leer = async () => {
        const w = video.videoWidth, hh = video.videoHeight; if (!w) return;
        const k = Math.min(1, 640 / w); lienzo.width = Math.round(w * k); lienzo.height = Math.round(hh * k);
        cx.drawImage(video, 0, 0, lienzo.width, lienzo.height);
        return jsQR(cx.getImageData(0, 0, lienzo.width, lienzo.height).data, lienzo.width, lienzo.height)?.data;
      };
    }
    const ciclo = async () => {
      if (!activo) return;
      if (!video.isConnected) return detener();                 // el guardia cambió de pantalla: se libera la cámara
      try { const v = await leer(); if (v) await enviar(v); } catch { /* cuadro sin QR */ }
      setTimeout(ciclo, 200);
    };
    ciclo();
  }

  const btnCamara = h("button", { class: "btn", type: "button", onclick: () => (activo ? detener() : activar()) }, icono("camara", 18), "Activar cámara");

  const entrada = h("input", { id: "codigo-manual", placeholder: " ", autocomplete: "off", spellcheck: "false", autocapitalize: "off" });
  const form = h("form", { novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    const b = form.querySelector("button");
    await conCarga(b, () => enviar(entrada.value)); entrada.value = ""; entrada.focus();
  } }, h("div", { class: "field" }, entrada, h("label", { for: "codigo-manual" }, "Código escrito o de lector USB")),
    h("button", { class: "btn suave block", type: "submit" }, "Validar código"));

  async function cargarBitacora() {
    try {
      const filas = await api("/qr/escaneos", { params: { limite: 8 } });
      bitacora.replaceChildren(...(filas.length ? filas.map((f) => h("div", { class: "item" },
        h("div", { class: `punto ${f.resultado === "Rechazado" ? "mal" : "ok"}` }),
        h("div", { class: "cuerpo" }, h("b", {}, f.resultado), h("span", {}, [f.detalle, f.titular].filter(Boolean).join(" · ") || "—")),
        h("div", { class: "acciones" }, h("span", { class: "small muted" }, `${hace(deUtc(f.fecha))} · ${f.escaneado_por}`))))
        : [estadoVacio("Sin escaneos todavía", "Aquí verás los últimos códigos leídos.")]));
    } catch { /* la bitácora es secundaria */ }
  }
  cargarBitacora();

  return h("div", { class: "grid lados" },
    h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Escanear QR")), visor, btnCamara,
      h("div", { style: "margin-top:1rem" }, form), resultado),
    h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Últimos escaneos")), bitacora));
}
