// Selector de foto reutilizable: «Tomar foto» (abre la cámara) + «Elegir de la galería».
//  - Celular/tableta: usa la cámara nativa del sistema (input con `capture`).
//  - Computador: abre la cámara web dentro del mismo formulario (getUserMedia); si no hay o se niega el permiso, cae a la galería.
//  - Toda foto se reduce y comprime en el navegador antes de subir: así nunca supera el límite de 5 MB y el envío es mucho más rápido.
import { h, icono, toast } from "./ui.js";

const TIPOS_ACEPTADOS = "image/jpeg,image/png,image/webp,image/heic,image/heif";
const LADO_MAX = 1600;      // px del lado más largo
const CALIDAD = 0.82;       // JPEG
const LIMITE_MB = 5;        // el servidor rechaza más de esto

const esTactil = () => matchMedia("(pointer: coarse)").matches;

/** Reduce y comprime una imagen. Devuelve un File JPEG (o el original si ya es liviano y pequeño). */
export async function comprimirImagen(archivo) {
  let bmp;
  try { bmp = await createImageBitmap(archivo, { imageOrientation: "from-image" }); }
  catch { throw new Error("No pudimos leer esa imagen. Prueba con otra foto (JPG, PNG o WEBP)."); }
  const escala = Math.min(1, LADO_MAX / Math.max(bmp.width, bmp.height));
  const liviana = archivo.size <= 700 * 1024 && escala === 1 && /^image\/(jpeg|png|webp)$/.test(archivo.type);
  if (liviana) { bmp.close?.(); return archivo; }
  const w = Math.round(bmp.width * escala), alto = Math.round(bmp.height * escala);
  const lienzo = document.createElement("canvas");
  lienzo.width = w; lienzo.height = alto;
  const ctx = lienzo.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, alto);          // PNG con transparencia → fondo blanco
  ctx.drawImage(bmp, 0, 0, w, alto); bmp.close?.();
  const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", CALIDAD));
  if (!blob) throw new Error("No pudimos procesar la foto. Intenta de nuevo.");
  if (blob.size > LIMITE_MB * 1024 * 1024) throw new Error(`La foto sigue superando los ${LIMITE_MB} MB. Intenta con otra.`);
  return new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg" });
}

/**
 * selectorFoto({ titulo, ayuda, alCambiar })
 * Devuelve { el, archivo(), limpiar() }. `el` se agrega al formulario; `archivo()` entrega el File listo para FormData (o null).
 */
export function selectorFoto({ titulo = "Agregar foto", ayuda = "Toma una foto o elígela de tu galería", alCambiar, antesDeAbrir } = {}) {
  let archivo = null, urlVista = null, flujo = null;

  const inputGaleria = h("input", { type: "file", accept: TIPOS_ACEPTADOS, class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  const inputCamara = h("input", { type: "file", accept: "image/*", capture: "environment", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  const zona = h("div", { class: "foto-zona" });
  const caja = h("div", { class: "foto-sel" }, zona, inputGaleria, inputCamara);

  function soltarVista() { if (urlVista) { URL.revokeObjectURL(urlVista); urlVista = null; } }
  function apagarCamara() { flujo?.getTracks().forEach((t) => t.stop()); flujo = null; }

  async function recibir(f) {
    if (!f) return;
    zona.classList.add("procesando");
    try { archivo = await comprimirImagen(f); }
    catch (e) { toast(e.message, "error"); return; }
    finally { zona.classList.remove("procesando"); }
    pintar(); alCambiar?.(archivo);
  }
  inputGaleria.addEventListener("change", () => { recibir(inputGaleria.files[0]); inputGaleria.value = ""; });
  inputCamara.addEventListener("change", () => { recibir(inputCamara.files[0]); inputCamara.value = ""; });
  // Si la persona cierra la cámara o la galería sin elegir nada, se avisa con la foto que haya (o ninguna).
  inputGaleria.addEventListener("cancel", () => alCambiar?.(archivo));
  inputCamara.addEventListener("cancel", () => alCambiar?.(archivo));

  // Arrastrar y soltar (computador)
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("sobre"); }));
  zona.addEventListener("drop", (e) => recibir(e.dataTransfer.files[0]));

  function limpiar() { apagarCamara(); soltarVista(); archivo = null; pintar(); alCambiar?.(null); }

  // `antesDeAbrir` avisa justo antes de salir a la cámara/galería: en el celular el sistema puede cerrar la página mientras tanto.
  const abrirGaleria = () => { antesDeAbrir?.(); inputGaleria.click(); };

  async function abrirCamara() {
    antesDeAbrir?.();
    if (esTactil() || !navigator.mediaDevices?.getUserMedia) return inputCamara.click();   // celular: cámara nativa
    try {
      flujo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false });
    } catch { toast("No pudimos abrir la cámara. Revisa el permiso o elige una foto de la galería.", "error"); return inputGaleria.click(); }
    const video = h("video", { class: "foto-video", autoplay: true, playsinline: true });
    video.muted = true; video.srcObject = flujo;
    const capturar = h("button", { type: "button", class: "btn", onclick: async () => {
      if (!video.videoWidth) return;
      const l = document.createElement("canvas"); l.width = video.videoWidth; l.height = video.videoHeight;
      l.getContext("2d").drawImage(video, 0, 0);
      const blob = await new Promise((ok) => l.toBlob(ok, "image/jpeg", 0.92));
      apagarCamara();
      recibir(new File([blob], "captura.jpg", { type: "image/jpeg" }));
    } }, icono("camara", 18), "Capturar");
    zona.replaceChildren(video, h("div", { class: "foto-acciones" }, capturar,
      h("button", { type: "button", class: "btn suave", onclick: () => { apagarCamara(); pintar(); } }, "Cancelar")));
  }

  function botones() {
    return h("div", { class: "foto-acciones" },
      h("button", { type: "button", class: "btn suave", onclick: abrirCamara }, icono("camara", 18), "Tomar foto"),
      h("button", { type: "button", class: "btn suave", onclick: abrirGaleria }, icono("subir", 18), "Galería"));
  }

  function pintar() {
    soltarVista();
    if (!archivo) {
      zona.replaceChildren(h("b", {}, titulo), h("span", { class: "small muted" }, ayuda), botones());
      return;
    }
    urlVista = URL.createObjectURL(archivo);
    zona.replaceChildren(
      h("img", { src: urlVista, alt: "Vista previa de la foto" }),
      h("span", { class: "small muted" }, `${Math.max(1, Math.round(archivo.size / 1024))} KB · lista para enviar`),
      h("div", { class: "foto-acciones" },
        h("button", { type: "button", class: "btn suave", onclick: abrirCamara }, icono("camara", 18), "Otra foto"),
        h("button", { type: "button", class: "btn peligro", onclick: limpiar }, icono("x", 18), "Quitar")));
  }
  pintar();

  return { el: caja, archivo: () => archivo, limpiar };
}
