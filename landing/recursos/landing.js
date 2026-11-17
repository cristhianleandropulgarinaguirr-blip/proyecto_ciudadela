// Landing comercial · v4.0. Un solo archivo, sin librerías. Solo hace dos cosas:
//   1. «Solicitar demo»: valida el formulario y lo envía a POST /demo/solicitar (el servidor guarda el contacto y avisa a los administradores).
//   2. «Escribir por WhatsApp»: abre WhatsApp con un mensaje ya escrito; si la persona llenó sus datos y marcó la autorización, también guarda el contacto.
// Todo texto que se muestra se pone con textContent (nunca innerHTML con lo que escribió la persona).
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let marca = {};
  try { marca = JSON.parse(document.querySelector('meta[name="marca"]')?.content ?? "{}"); } catch { marca = {}; }

  const form = $("formulario"), estado = $("estado-form"), btnEnviar = $("btn-enviar"), btnWA = $("btn-whatsapp");
  const CAMPOS = { nombre: "f-nombre", conjunto: "f-conjunto", celular: "f-celular", correo: "f-correo", ciudad: "f-ciudad", apartamentos: "f-aptos", mensaje: "f-mensaje" };
  const ES_CELULAR = /^3\d{9}$/;
  const ES_CORREO = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  // ---------------------------------------------------------------- datos de contacto de la marca
  if (marca.whatsapp) btnWA.hidden = false;
  if (marca.correo_ventas) {
    const enlace = $("demo-correo-enlace");
    enlace.href = `mailto:${marca.correo_ventas}`;
    enlace.textContent = marca.correo_ventas;
    $("demo-correo").hidden = false;
  }

  // ---------------------------------------------------------------- utilidades
  const limpiar = (t) => (t || "").replace(/\s+/g, " ").trim();
  function soloCelular(valor) {
    let d = (valor || "").replace(/\D/g, "");
    if (d.length === 12 && d.startsWith("57")) d = d.slice(2);
    return d;
  }
  function leer() {
    return {
      nombre: limpiar($(CAMPOS.nombre).value), conjunto: limpiar($(CAMPOS.conjunto).value), celular: soloCelular($(CAMPOS.celular).value),
      correo: $(CAMPOS.correo).value.trim(), ciudad: limpiar($(CAMPOS.ciudad).value), apartamentos: $(CAMPOS.apartamentos).value.trim(),
      mensaje: limpiar($(CAMPOS.mensaje).value), acepto: $("f-acepto").checked,
    };
  }

  function marcarError(clave, texto) {
    const caja = clave === "acepto_datos" ? $("f-acepto").closest(".consentimiento") : $(CAMPOS[clave])?.closest(".campo");
    if (!caja) return;
    caja.classList.add("con-error");
    let msg = caja.querySelector(".campo-msg");
    if (!msg) { msg = document.createElement("p"); msg.className = "campo-msg"; caja.append(msg); }
    msg.textContent = texto;
  }
  function limpiarErrores() {
    form.querySelectorAll(".con-error").forEach((c) => c.classList.remove("con-error"));
    form.querySelectorAll(".campo-msg").forEach((m) => m.remove());
  }
  function decir(texto, clase = "") { estado.textContent = texto; estado.className = `estado-form ${clase}`.trim(); }

  // Devuelve {campo: mensaje} con los problemas (vacío = todo bien).
  function validar(d, { exigirConsentimiento = true } = {}) {
    const e = {};
    if (d.nombre.length < 2) e.nombre = "Escribe tu nombre.";
    if (d.conjunto.length < 2) e.conjunto = "Escribe el nombre del conjunto o de la administradora.";
    if (!ES_CELULAR.test(d.celular)) e.celular = "Escribe un celular colombiano de 10 dígitos que empiece por 3.";
    if (d.correo && !ES_CORREO.test(d.correo)) e.correo = "Revisa el correo: parece incompleto.";
    if (d.apartamentos && !(Number(d.apartamentos) >= 1 && Number(d.apartamentos) <= 5000)) e.apartamentos = "Escribe un número entre 1 y 5000.";
    if (exigirConsentimiento && !d.acepto) e.acepto_datos = "Marca la autorización para que podamos contactarte.";
    return e;
  }

  function cuerpo(d, origen) {
    const c = {
      nombre: d.nombre, conjunto: d.conjunto, celular: d.celular, origen, acepto_datos: d.acepto, sitio_web: $("f-sitio").value,
    };
    if (d.correo) c.correo = d.correo;
    if (d.ciudad) c.ciudad = d.ciudad;
    if (d.apartamentos) c.apartamentos = Number(d.apartamentos);
    if (d.mensaje) c.mensaje = d.mensaje;
    return c;
  }

  // El servidor (FastAPI) responde 422 con una lista [{loc: [...,"campo"], msg: "..."}]: se muestra cada mensaje junto a su campo.
  function errorDelServidor(detalle) {
    if (!Array.isArray(detalle)) return typeof detalle === "string" ? detalle : "No pudimos enviar tu solicitud. Revisa los datos e inténtalo de nuevo.";
    let primero = "";
    for (const it of detalle) {
      const campo = Array.isArray(it.loc) ? it.loc[it.loc.length - 1] : "";
      const texto = String(it.msg || "").replace(/^Value error, /, "");
      if (campo in CAMPOS || campo === "acepto_datos") marcarError(campo, texto);
      primero = primero || texto;
    }
    return primero || "Revisa los datos marcados.";
  }

  // ---------------------------------------------------------------- «Solicitar demo»
  async function enviar(origen, { silencioso = false } = {}) {
    const r = await fetch("/demo/solicitar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo(leer(), origen)), keepalive: silencioso });
    let datos = null;
    try { datos = await r.json(); } catch { datos = null; }
    return { ok: r.ok, status: r.status, datos };
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    limpiarErrores();
    decir("");
    const errores = validar(leer());
    const claves = Object.keys(errores);
    if (claves.length) {
      claves.forEach((k) => marcarError(k, errores[k]));
      decir("Revisa los campos marcados.", "mal");
      const primero = form.querySelector(".con-error input, .con-error textarea");
      primero?.focus();
      return;
    }
    btnEnviar.disabled = true;
    decir("Enviando…");
    try {
      const { ok, status, datos } = await enviar("formulario");
      if (ok) return mostrarListo(datos?.mensaje);
      decir(status === 422 ? errorDelServidor(datos?.detail) : (datos?.detail && typeof datos.detail === "string" ? datos.detail : "No pudimos enviar tu solicitud. Inténtalo de nuevo en unos minutos."), "mal");
    } catch {
      decir("No pudimos conectarnos. Revisa tu internet e inténtalo de nuevo." + (marca.whatsapp ? " También puedes escribirnos por WhatsApp." : ""), "mal");
    } finally {
      btnEnviar.disabled = false;
    }
  });

  function mostrarListo(mensaje) {
    const caja = document.createElement("div");
    caja.className = "formulario-enviado";
    caja.setAttribute("role", "status");
    const t = document.createElement("h3");
    t.textContent = "Solicitud recibida";
    const p = document.createElement("p");
    p.textContent = mensaje || "Te contactaremos para agendar la demostración.";
    caja.append(t, p);
    if (marca.whatsapp) {
      const a = document.createElement("a");
      a.className = "btn btn-contorno";
      a.href = enlaceWhatsApp(`${saludo()}, acabo de pedir una demostración de ${marca.nombre || "la app"}.`);
      a.target = "_blank"; a.rel = "noopener noreferrer";
      a.textContent = "Escribir por WhatsApp";
      caja.append(a);
    }
    form.replaceChildren(caja);
    caja.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  // ---------------------------------------------------------------- «Escribir por WhatsApp»
  // El texto va codificado en la URL (encodeURIComponent): tildes, «¿», espacios y saltos de línea llegan bien a WhatsApp.
  function enlaceWhatsApp(texto) { return `https://wa.me/${marca.whatsapp}?text=${encodeURIComponent(texto)}`; }
  const saludo = () => (marca.contacto ? `Hola ${marca.contacto}` : "Hola");

  btnWA.addEventListener("click", () => {
    if (!marca.whatsapp) return;
    limpiarErrores();
    const d = leer();
    const completo = Object.keys(validar(d, { exigirConsentimiento: false })).length === 0;
    const partes = [`${saludo()}, revisé la demo de ${marca.nombre || "la app"} y me gustaría agendar una demostración para mi conjunto residencial.`];
    if (d.nombre) partes.push(`Soy ${d.nombre}${d.conjunto ? ` de ${d.conjunto}` : ""}.`);
    if (d.apartamentos) partes.push(`Son ${d.apartamentos} apartamentos.`);
    if (d.ciudad) partes.push(`Estamos en ${d.ciudad}.`);
    // Se abre WhatsApp ANTES de cualquier otra cosa: el navegador solo permite abrir la ventana dentro del toque del botón.
    const url = enlaceWhatsApp(partes.join(" "));
    const ventana = window.open(url, "_blank", "noopener");
    if (!ventana) location.href = url;
    // Si dejó sus datos y autorizó, también queda guardado el contacto (sin bloquear nada: si falla, WhatsApp ya se abrió).
    if (completo && d.acepto) {
      enviar("whatsapp", { silencioso: true }).catch(() => {});
      decir("Abrimos WhatsApp y también guardamos tus datos.", "ok");
    } else if (completo) {
      decir("Abrimos WhatsApp. No guardamos tus datos porque no marcaste la autorización.");
    }
  });


  // ---------------------------------------------------------------- guía de instalación: pestañas (Android · iPhone · Computador)
  // Sin JavaScript se ven las tres guías seguidas; con JavaScript se muestra la del dispositivo de la persona (se puede cambiar).
  const pestanas = [...document.querySelectorAll(".pestana")];
  function elegirPestana(id, enfocar) {
    pestanas.forEach((p) => {
      const activa = p.dataset.panel === id;
      p.setAttribute("aria-selected", String(activa));
      p.tabIndex = activa ? 0 : -1;
      const panel = $(p.dataset.panel);
      if (panel) panel.hidden = !activa;
      if (activa && enfocar) p.focus();
    });
  }
  if (pestanas.length) {
    pestanas.forEach((p, i) => {
      p.addEventListener("click", () => elegirPestana(p.dataset.panel));
      p.addEventListener("keydown", (ev) => {                       // flechas ← → como en cualquier grupo de pestañas
        const paso = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
        if (!paso) return;
        ev.preventDefault();
        elegirPestana(pestanas[(i + paso + pestanas.length) % pestanas.length].dataset.panel, true);
      });
    });
    const ua = navigator.userAgent || "";
    elegirPestana(/iPhone|iPad|iPod/.test(ua) ? "ins-ios" : /Android/.test(ua) ? "ins-android" : "ins-escritorio");
  }

  // Al corregir un campo se le quita el aviso de error.
  form.addEventListener("input", (ev) => {
    const caja = ev.target.closest(".con-error");
    if (caja) { caja.classList.remove("con-error"); caja.querySelector(".campo-msg")?.remove(); }
  });
})();
