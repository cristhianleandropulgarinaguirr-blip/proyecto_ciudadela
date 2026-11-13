// Selector de foto reutilizable: «Tomar foto» (abre la cámara) + «Elegir de la galería».
//  - Celular/tableta: usa la cámara nativa del sistema (input con `capture`).
//  - Computador: abre la cámara web dentro del mismo formulario (getUserMedia); si no hay o se niega el permiso, cae a la galería.
//  - Toda foto se reduce y comprime en el navegador antes de subir: así nunca supera el límite de 5 MB y el envío es mucho más rápido.
//
// Robustez en el celular (versión 3.1): al abrir la cámara nativa el sistema puede cerrar la página para liberar memoria.
//  - La SESIÓN no se pierde (ver api.js: la cookie de renovación la recupera sin pedir la clave).
//  - La foto, apenas se toma y comprime, se guarda en IndexedDB (si se pasa `clave`): si la página se recarga antes de enviar el
//    formulario, la foto reaparece sola.
//  - Si el sistema cerró la página MIENTRAS estaba la cámara abierta, la foto no llegó a existir: al volver se avisa (`avisoCamara`).
import { almacen } from "./almacen.js";
import { h, icono, toast } from "./ui.js";

const TIPOS_ACEPTADOS = "image/jpeg,image/png,image/webp,image/heic,image/heif";
const LADO_MAX = 1600;      // px del lado más largo
const CALIDAD = 0.82;       // JPEG
const LIMITE_MB = 5;        // el servidor rechaza más de esto
const VIGENCIA_BORRADOR_MS = 12 * 3600e3;
const MARCA = "ciudadela.camara";

const esTactil = () => matchMedia("(pointer: coarse)").matches;
const marcar = (clave) => { try { localStorage.setItem(MARCA, JSON.stringify({ t: Date.now(), clave: clave ?? "" })); } catch { /* nada */ } };
const desmarcar = () => { try { localStorage.removeItem(MARCA); } catch { /* nada */ } };

/** Al abrir la app: si el sistema la cerró mientras la cámara estaba abierta, explica qué pasó (y que la sesión sigue activa). */
export function avisoCamara() {
  try {
    const m = JSON.parse(localStorage.getItem(MARCA) ?? "null");
    desmarcar();
    if (m && Date.now() - m.t < 15 * 60e3) toast("El teléfono cerró la app un momento al abrir la cámara. Tu sesión sigue activa: toma la foto de nuevo.", "error");
  } catch { /* sin aviso */ }
}

/** Decodifica una imagen. createImageBitmap es lo más rápido y ahorra memoria; si falla (formatos raros), se prueba con <img>. */
async function decodificar(archivo) {
  try { return { bmp: await createImageBitmap(archivo, { imageOrientation: "from-image" }) }; } catch { /* se prueba con <img> */ }
  const url = URL.createObjectURL(archivo);
  try {
    const img = new Image(); img.src = url; await img.decode();
    return { bmp: img, liberar: () => URL.revokeObjectURL(url) };
  } catch { URL.revokeObjectURL(url); throw new Error("No pudimos leer esa imagen. Prueba con otra foto (JPG, PNG o WEBP)."); }
}

/** Reduce y comprime una imagen. Devuelve un File JPEG (o el original si ya es liviano y pequeño). */
export async function comprimirImagen(archivo) {
  const { bmp, liberar } = await decodificar(archivo);
  const ancho = bmp.width || bmp.naturalWidth, alto0 = bmp.height || bmp.naturalHeight;
  const escala = Math.min(1, LADO_MAX / Math.max(ancho, alto0));
  const liviana = archivo.size <= 700 * 1024 && escala === 1 && /^image\/(jpeg|png|webp)$/.test(archivo.type);
  if (liviana) { bmp.close?.(); liberar?.(); return archivo; }
  const w = Math.round(ancho * escala), alto = Math.round(alto0 * escala);
  const lienzo = document.createElement("canvas");
  lienzo.width = w; lienzo.height = alto;
  const ctx = lienzo.getContext("2d");
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, alto);          // PNG con transparencia → fondo blanco
  ctx.drawImage(bmp, 0, 0, w, alto); bmp.close?.(); liberar?.();
  const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", CALIDAD));
  lienzo.width = lienzo.height = 0;                              // libera la memoria del lienzo ya (importante en celulares con poca RAM)
  if (!blob) throw new Error("No pudimos procesar la foto. Intenta de nuevo.");
  if (blob.size > LIMITE_MB * 1024 * 1024) throw new Error(`La foto sigue superando los ${LIMITE_MB} MB. Intenta con otra.`);
  return new File([blob], `foto-${Date.now()}.jpg`, { type: "image/jpeg" });
}

/**
 * selectorFoto({ titulo, ayuda, alCambiar, antesDeAbrir, clave })
 * Devuelve { el, archivo(), limpiar() }. `el` se agrega al formulario; `archivo()` entrega el File listo para FormData (o null).
 * `clave` (opcional, p. ej. «paquete-15»): activa la recuperación de la foto si la página se recarga antes de enviar.
 */
export function selectorFoto({ titulo = "Agregar foto", ayuda = "Toma una foto o elígela de tu galería", alCambiar, antesDeAbrir, clave } = {}) {
  let archivo = null, urlVista = null, flujo = null, vigilante = null;
  const llave = clave ? `borrador:${clave}` : null;

  const inputGaleria = h("input", { type: "file", accept: TIPOS_ACEPTADOS, class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  const inputCamara = h("input", { type: "file", accept: "image/*", capture: "environment", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
  const zona = h("div", { class: "foto-zona" });
  const caja = h("div", { class: "foto-sel" }, zona, inputGaleria, inputCamara);

  function soltarVista() { if (urlVista) { URL.revokeObjectURL(urlVista); urlVista = null; } }
  function apagarCamara() { flujo?.getTracks().forEach((t) => t.stop()); flujo = null; clearInterval(vigilante); vigilante = null; }
  const guardarBorrador = () => { if (llave && archivo) almacen.poner("fotos", llave, { archivo, t: Date.now() }); };
  const borrarBorrador = () => { if (llave) almacen.borrar("fotos", llave); };

  async function recibir(f) {
    desmarcar();
    if (!f) return;
    zona.classList.add("procesando");
    try { archivo = await comprimirImagen(f); }
    catch (e) { toast(e.message, "error"); return; }
    finally { zona.classList.remove("procesando"); }
    guardarBorrador();
    pintar(); alCambiar?.(archivo);
  }
  inputGaleria.addEventListener("change", () => { recibir(inputGaleria.files[0]); inputGaleria.value = ""; });
  inputCamara.addEventListener("change", () => { recibir(inputCamara.files[0]); inputCamara.value = ""; });
  // Si la persona cierra la cámara o la galería sin elegir nada, se avisa con la foto que haya (o ninguna).
  const alCancelar = () => { desmarcar(); alCambiar?.(archivo); };
  inputGaleria.addEventListener("cancel", alCancelar);
  inputCamara.addEventListener("cancel", alCancelar);

  // Arrastrar y soltar (computador)
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("sobre"); }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove("sobre"); }));
  zona.addEventListener("drop", (e) => recibir(e.dataTransfer.files[0]));

  function limpiar() { apagarCamara(); soltarVista(); archivo = null; borrarBorrador(); pintar(); alCambiar?.(null); }

  // Salir a la cámara/galería: en el celular el sistema puede cerrar la página mientras tanto. Se deja una marca para poder avisarlo al volver.
  const avisarSalida = () => { marcar(clave); antesDeAbrir?.(); };
  const abrirGaleria = () => { avisarSalida(); inputGaleria.click(); };

  async function abrirCamara() {
    avisarSalida();
    if (esTactil() || !navigator.mediaDevices?.getUserMedia) return inputCamara.click();   // celular: cámara nativa
    try {
      flujo = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 } }, audio: false });
    } catch (e) {
      desmarcar();
      toast(e?.name === "NotAllowedError" ? "La cámara está bloqueada. Permítela en el navegador o elige una foto de la galería." : "No pudimos abrir la cámara. Elige una foto de la galería.", "error");
      return inputGaleria.click();
    }
    desmarcar();
    const video = h("video", { class: "foto-video", autoplay: true, playsinline: true });
    video.muted = true; video.srcObject = flujo;
    // La cámara web nunca debe quedar prendida: se apaga si el formulario sale de la pantalla o la pestaña se oculta.
    vigilante = setInterval(() => { if (!caja.isConnected) apagarCamara(); }, 1500);
    const capturar = h("button", { type: "button", class: "btn", onclick: async () => {
      if (!video.videoWidth) return;
      const l = document.createElement("canvas"); l.width = video.videoWidth; l.height = video.videoHeight;
      l.getContext("2d").drawImage(video, 0, 0);
      const blob = await new Promise((ok) => l.toBlob(ok, "image/jpeg", 0.92));
      apagarCamara();
      if (!blob) { toast("No pudimos capturar la foto. Intenta de nuevo.", "error"); return pintar(); }
      recibir(new File([blob], "captura.jpg", { type: "image/jpeg" }));
    } }, icono("camara", 18), "Capturar");
    zona.replaceChildren(video, h("div", { class: "foto-acciones" }, capturar,
      h("button", { type: "button", class: "btn suave", onclick: () => { apagarCamara(); pintar(); } }, "Cancelar")));
  }
  document.addEventListener("visibilitychange", () => { if (document.hidden && flujo) { apagarCamara(); pintar(); } });

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

  // Recuperación: si la página se recargó con una foto ya tomada, reaparece.
  if (llave) almacen.leer("fotos", llave).then((g) => {
    if (!g?.archivo || archivo) return;
    if (Date.now() - g.t > VIGENCIA_BORRADOR_MS) return almacen.borrar("fotos", llave);
    archivo = g.archivo; desmarcar(); pintar(); alCambiar?.(archivo);
    toast("Recuperamos la foto que habías tomado.");
  });

  return { el: caja, archivo: () => archivo, limpiar };
}
