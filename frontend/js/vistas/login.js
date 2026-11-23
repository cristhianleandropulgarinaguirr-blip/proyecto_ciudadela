// Pantalla de inicio de sesión (POST /auth/login con formulario, como exige OAuth2PasswordRequestForm).
import { api, sesion } from "../api.js";
import { h, icono, logoCompleto, conCarga, botonTema } from "../ui.js";
import { marca } from "../marca.js";

// «Tu conjunto, siempre en orden.» → la parte después de la última coma va resaltada (como siempre); un eslogan sin coma se muestra entero.
function titular(eslogan) {
  const i = eslogan.lastIndexOf(",");
  return i < 0 ? [eslogan] : [eslogan.slice(0, i + 1) + " ", h("em", {}, eslogan.slice(i + 1).trim())];
}

export function vistaLogin(alIngresar) {
  const error = h("div", { class: "msg-error", role: "alert", hidden: true });
  const email = h("input", { id: "email", type: "email", placeholder: " ", autocomplete: "username", required: true, inputmode: "email" });
  const clave = h("input", { id: "clave", type: "password", placeholder: " ", autocomplete: "current-password", required: true });
  const ver = h("button", { type: "button", class: "btn suave icono sm lado", "aria-label": "Mostrar contraseña" }, icono("ojo"));
  ver.addEventListener("click", () => {
    const visible = clave.type === "text";
    clave.type = visible ? "password" : "text";
    ver.replaceChildren(icono(visible ? "ojo" : "ojoNo"));
    ver.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
  });
  const boton = h("button", { class: "btn block", type: "submit" }, "Ingresar", icono("flecha", 18));
  // v5.3 · segundo paso: aparece solo cuando el servidor lo pide (cuenta con verificación en dos pasos).
  const codigo = h("input", { id: "codigo2fa", type: "text", inputmode: "numeric", autocomplete: "one-time-code", placeholder: " ", maxlength: 20 });
  const campoCodigo = h("div", { class: "field", hidden: true }, codigo, h("label", { for: "codigo2fa" }, "Código de verificación"));
  const ayudaCodigo = h("p", { class: "small muted", hidden: true, style: "margin:-.4rem 0 1rem" }, "Abre tu app de autenticación y escribe el código de 6 dígitos. ¿Perdiste el celular? Usa uno de tus códigos de recuperación.");

  const form = h("form", { novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    error.hidden = true;
    if (!email.value.trim() || !clave.value) return fallar("Escribe tu correo y tu contraseña.");
    try {
      await conCarga(boton, async () => {
        const cabeceras = codigo.value.trim() ? { "X-Codigo-2FA": codigo.value.trim() } : undefined;
        const r = await api("/auth/login", { metodo: "POST", form: { username: email.value.trim(), password: clave.value }, cabeceras });
        sesion.guardar(r);          // token corto en esta pestaña; la renovación va en una cookie HttpOnly
      });
      alIngresar();
    } catch (err) {
      if (err.requiere2fa) {      // contraseña correcta: falta (o es incorrecto) el código del segundo paso
        const habiaCodigo = !campoCodigo.hidden;
        campoCodigo.hidden = ayudaCodigo.hidden = false; codigo.focus();
        if (habiaCodigo) { codigo.select(); return fallar(err.message); }
        error.hidden = true; return;
      }
      fallar(err.message);
    }
  } },
    h("h2", {}, "Bienvenido de nuevo"),
    h("p", { class: "sub" }, "Ingresa con la cuenta que te creó la administración."),
    error,
    h("div", { class: "field" }, email, h("label", { for: "email" }, "Correo electrónico")),
    h("div", { class: "field" }, clave, h("label", { for: "clave" }, "Contraseña"), ver),
    campoCodigo, ayudaCodigo,
    boton,
    h("p", { class: "nota-cierre" }, "¿Olvidaste tu contraseña o aún no tienes cuenta? Pídela en la administración de tu conjunto."));

  // Autocompletar del navegador: al recargar, Chrome/Edge rellenan correo y contraseña guardados, pero el CSS no se entera
  // (el campo sigue «vacío» para :placeholder-shown) y la etiqueta quedaba encima del texto. Aquí marcamos el campo como «lleno».
  const estaRelleno = (campo) => {
    if (campo.value) return true;
    for (const selector of [":-webkit-autofill", ":autofill"]) { try { if (campo.matches(selector)) return true; } catch { /* el navegador no conoce ese selector */ } }
    return false;
  };
  const sincronizar = () => [email, clave, codigo].forEach((campo) => campo.parentElement?.classList.toggle("lleno", estaRelleno(campo)));
  [email, clave, codigo].forEach((campo) => ["input", "change", "animationstart", "focus", "blur"].forEach((ev) => campo.addEventListener(ev, sincronizar)));
  [0, 100, 300, 800, 1500, 3000].forEach((ms) => setTimeout(sincronizar, ms));   // el autocompletar llega unos instantes después de pintar
  window.addEventListener("pageshow", sincronizar);

  function fallar(texto) {
    error.textContent = texto; error.hidden = false;
    form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
  }

  return h("div", { class: "login" },
    h("section", { class: "login-marca" },
      h("div", {}, logoCompleto(),
        h("h1", {}, ...titular(marca.eslogan)),
        h("p", {}, "Reservas, mantenimiento, cartera y portería en un solo lugar, para administradores, residentes y guardias.")),
      h("small", { style: "opacity:.6" }, "Control residencial inteligente")),
    h("section", { class: "login-form" }, botonTema("login-tema"), form));
}
