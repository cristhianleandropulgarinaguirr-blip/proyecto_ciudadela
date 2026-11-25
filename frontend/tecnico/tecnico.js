// Página pública del técnico de mantenimiento (rol Mantenimiento). Sin librerías ni módulos: un solo archivo pequeño.
//   · Lee el token de la URL (/tecnico/<token>) y pide los datos mínimos del reporte a /tecnico-publico/<token>.
//   · El técnico solo puede pasar el reporte a «En reparación» o «Solucionado», con una nota y una foto de evidencia.
//   · La foto se reduce en el celular antes de subirla (las fotos de cámara pesan 3-12 MB y el servidor acepta máximo 5 MB).
//   · Todo texto del servidor se escribe con textContent (nunca innerHTML): lo que escribió el residente no puede inyectar código.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const partes = location.pathname.split("/").filter(Boolean);
  const token = partes[0] === "tecnico" ? partes[1] : "";
  const API = `/tecnico-publico/${encodeURIComponent(token)}`;

  const LADO_MAX = 1600, CALIDAD = 0.82, LIMITE_MB = 5, MIN_NOTA_SOLUCIONADO = 5;
  const ESTADOS = { Abierto: "Abierto", "En Revision": "En revisión", "En Reparacion": "En reparación", Solucionado: "Solucionado" };
  const FINALES = {
    Vencido: ["Este enlace venció", "El tiempo de este enlace terminó. Si todavía falta trabajo, pídele al administrador que te envíe uno nuevo."],
    Revocado: ["El administrador anuló este enlace", "Ya no puedes actualizar este reporte desde aquí. Si crees que es un error, comunícate con el administrador."],
    Cerrado: ["Este trabajo ya quedó cerrado", "El reporte está solucionado y el enlace se cerró. ¡Gracias por tu trabajo!"],
  };
  let archivo = null, urlVista = null, enviando = false, datosActuales = null;

  function ocultarTodo() { ["tarjeta", "final", "error"].forEach((id) => { $(id).hidden = true; }); }

  function mostrarError(titulo, texto) {
    ocultarTodo(); $("error").hidden = false;
    $("conjunto").textContent = "Mantenimiento";
    if (titulo) $("error-titulo").textContent = titulo;
    if (texto) $("error-texto").textContent = texto;
  }

  function fecha(iso, conHora = true) {
    if (!iso) return "—";
    // El servidor guarda la hora en UTC sin zona: se le agrega la «Z» para que el navegador la convierta a la hora local.
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    return d.toLocaleString("es-CO", conHora ? { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" });
  }

  // ---------------------------------------------------------------- pintar
  function pintarHistorial(evidencias) {
    const lista = $("lista-historial"); lista.replaceChildren();
    evidencias.forEach((ev) => {
      const li = document.createElement("li");
      const b = document.createElement("b"); b.textContent = ESTADOS[ev.estado] || ev.estado;
      li.append(b, ` · ${fecha(ev.fecha)}${ev.tiene_foto ? " · con foto" : ""}`);
      if (ev.nota) { const p = document.createElement("div"); p.textContent = ev.nota; li.append(p); }
      lista.append(li);
    });
    $("historial").hidden = evidencias.length === 0;
  }

  function pintar(datos) {
    datosActuales = datos;
    const { conjunto, enlace, reporte } = datos;
    document.title = `Mantenimiento · ${conjunto.nombre}`;
    $("conjunto").textContent = conjunto.nombre;

    if (!enlace.sirve || !reporte) {
      const [titulo, texto] = FINALES[enlace.estado] || FINALES.Vencido;
      ocultarTodo(); $("final").hidden = false;
      $("final-titulo").textContent = titulo; $("final-texto").textContent = texto;
      return;
    }
    ocultarTodo(); $("tarjeta").hidden = false;

    const estado = $("estado");
    estado.textContent = `Estado actual: ${ESTADOS[reporte.estado] || reporte.estado}`;
    estado.className = `estado${reporte.estado === "Solucionado" ? " ok" : ""}`;
    $("titulo").textContent = reporte.titulo;
    $("descripcion").textContent = reporte.descripcion;
    $("apartamento").textContent = reporte.apartamento;      // lo único del residente que llega a esta página
    $("reportado").textContent = fecha(reporte.reportado, false);
    $("vence").textContent = fecha(enlace.valido_hasta);

    // La foto se pide solo si existe; en miniatura primero, y completa al tocarla.
    $("foto-caja").hidden = !reporte.tiene_foto;
    if (reporte.tiene_foto && !$("foto").getAttribute("src")) {
      $("foto").addEventListener("error", () => { $("foto-caja").hidden = true; }, { once: true });
      $("foto").src = `${API}/foto?miniatura=true`;
    }

    pintarHistorial(reporte.evidencias || []);

    // Solo se ofrecen los estados a los que el técnico puede llegar desde donde está el reporte.
    const permitidos = reporte.estados_permitidos || [];
    $("form").hidden = permitidos.length === 0;
    const reparacion = $("op-reparacion"), solucionado = $("op-solucionado");
    reparacion.classList.toggle("apagada", !permitidos.includes("En Reparacion"));
    reparacion.querySelector("input").disabled = !permitidos.includes("En Reparacion");
    solucionado.classList.toggle("apagada", !permitidos.includes("Solucionado"));
    solucionado.querySelector("input").disabled = !permitidos.includes("Solucionado");
    if (permitidos.length === 1) {                       // una sola opción: ya queda elegida
      (permitidos[0] === "Solucionado" ? solucionado : reparacion).querySelector("input").checked = true;
    }
    actualizarPistas();
  }

  function estadoElegido() { const r = document.querySelector('input[name="estado"]:checked'); return r ? r.value : ""; }

  function actualizarPistas() {
    const sol = estadoElegido() === "Solucionado";
    const nota = $("nota-pista"), foto = $("foto-pista");
    nota.textContent = sol ? "(obligatoria: cuenta qué hiciste)" : "(opcional)"; nota.classList.toggle("obligatorio", sol);
    foto.textContent = sol ? "(obligatoria)" : "(opcional)"; foto.classList.toggle("obligatorio", sol);
  }

  // ---------------------------------------------------------------- foto
  async function decodificar(f) {
    try { return { bmp: await createImageBitmap(f, { imageOrientation: "from-image" }) }; } catch { /* se prueba con <img> */ }
    const url = URL.createObjectURL(f);
    try { const img = new Image(); img.src = url; await img.decode(); return { bmp: img, liberar: () => URL.revokeObjectURL(url) }; }
    catch { URL.revokeObjectURL(url); throw new Error("No pudimos leer esa imagen. Prueba con otra foto (JPG, PNG o WEBP)."); }
  }

  /** Reduce y comprime la foto: así nunca supera los 5 MB y el envío con datos móviles es mucho más rápido. */
  async function comprimir(f) {
    const { bmp, liberar } = await decodificar(f);
    const ancho = bmp.width || bmp.naturalWidth, alto = bmp.height || bmp.naturalHeight;
    const escala = Math.min(1, LADO_MAX / Math.max(ancho, alto));
    if (f.size <= 700 * 1024 && escala === 1 && /^image\/(jpeg|png|webp)$/.test(f.type)) { bmp.close?.(); liberar?.(); return f; }
    const w = Math.round(ancho * escala), h = Math.round(alto * escala);
    const lienzo = document.createElement("canvas"); lienzo.width = w; lienzo.height = h;
    const ctx = lienzo.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, w, h); ctx.drawImage(bmp, 0, 0, w, h);
    bmp.close?.(); liberar?.();
    const blob = await new Promise((ok) => lienzo.toBlob(ok, "image/jpeg", CALIDAD));
    lienzo.width = lienzo.height = 0;                    // libera la memoria del lienzo ya (celulares con poca RAM)
    if (!blob) throw new Error("No pudimos procesar la foto. Intenta de nuevo.");
    if (blob.size > LIMITE_MB * 1024 * 1024) throw new Error(`La foto sigue superando los ${LIMITE_MB} MB. Intenta con otra.`);
    return new File([blob], `evidencia-${Date.now()}.jpg`, { type: "image/jpeg" });
  }

  function quitarFoto() {
    archivo = null;
    if (urlVista) { URL.revokeObjectURL(urlVista); urlVista = null; }
    $("vista-img").removeAttribute("src"); $("vista").hidden = true;
    $("archivo-camara").value = ""; $("archivo-galeria").value = "";
  }

  async function alElegirFoto(e) {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    mensaje("");
    try {
      const lista = await comprimir(f);
      quitarFoto(); archivo = lista; urlVista = URL.createObjectURL(lista);
      $("vista-img").src = urlVista; $("vista").hidden = false;
    } catch (err) { mensaje(err.message, true); }
  }

  // ---------------------------------------------------------------- enviar
  function mensaje(texto, mal = false) { const m = $("mensaje"); m.textContent = texto; m.className = `mensaje${mal ? " mal" : ""}`; }

  async function enviar(e) {
    e.preventDefault();
    if (enviando) return;
    const estado = estadoElegido(), nota = $("nota").value.trim();
    if (!estado) return mensaje("Elige primero qué pasó: «Estoy reparando» o «Ya quedó solucionado».", true);
    if (estado === "Solucionado") {
      if (nota.length < MIN_NOTA_SOLUCIONADO) return mensaje("Para marcarlo como solucionado escribe una nota breve de lo que hiciste.", true);
      if (!archivo) return mensaje("Para marcarlo como solucionado sube la foto de evidencia.", true);
    }
    const fd = new FormData(); fd.append("nuevo_estado", estado); fd.append("nota", nota);
    if (archivo) fd.append("archivo_foto", archivo);
    const boton = $("enviar"); enviando = true; boton.disabled = true; boton.textContent = "Enviando…"; mensaje("");
    try {
      const r = await fetch(`${API}/estado`, { method: "POST", body: fd });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "No se pudo enviar la actualización. Revisa tu internet e intenta de nuevo.");
      $("nota").value = ""; quitarFoto(); document.querySelectorAll('input[name="estado"]').forEach((x) => { x.checked = false; });
      await cargar();
      if (!$("tarjeta").hidden) mensaje(j.mensaje);          // sigue abierto (En reparación): se confirma aquí
      else { $("final-titulo").textContent = "¡Listo, gracias!"; $("final-texto").textContent = j.mensaje; }   // se cerró (Solucionado)
    } catch (err) { mensaje(err.message === "Failed to fetch" ? "Sin conexión. Revisa tu internet e intenta de nuevo." : err.message, true); }
    finally { enviando = false; boton.disabled = false; boton.textContent = "Enviar actualización"; }
  }

  // ---------------------------------------------------------------- carga
  async function cargar() {
    if (!token) return mostrarError();
    try {
      const r = await fetch(API, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.status === 404) return mostrarError();
      if (r.status === 429) return mostrarError("Demasiadas consultas", "Espera un minuto y vuelve a abrir el enlace.");
      if (!r.ok) throw new Error();
      pintar(await r.json());
    } catch {
      if (!datosActuales) mostrarError("Sin conexión", "No pudimos cargar el reporte. Revisa tu internet e intenta de nuevo.");
    }
  }

  $("foto-btn").addEventListener("click", (e) => {
    const caja = e.currentTarget, grande = caja.classList.toggle("grande");
    $("foto").src = `${API}/foto${grande ? "" : "?miniatura=true"}`;          // completa al ampliar, miniatura al cerrar
  });
  document.querySelectorAll('input[name="estado"]').forEach((x) => x.addEventListener("change", actualizarPistas));
  $("archivo-camara").addEventListener("change", alElegirFoto);
  $("archivo-galeria").addEventListener("change", alElegirFoto);
  $("quitar-foto").addEventListener("click", quitarFoto);
  $("form").addEventListener("submit", enviar);
  cargar();
})();
