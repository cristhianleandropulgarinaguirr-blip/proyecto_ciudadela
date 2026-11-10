// Pantalla de inicio de sesión (POST /auth/login con formulario, como exige OAuth2PasswordRequestForm).
import { api, sesion } from "../api.js";
import { h, icono, logoCompleto, conCarga, botonTema } from "../ui.js";

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

  const form = h("form", { novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    error.hidden = true;
    if (!email.value.trim() || !clave.value) return fallar("Escribe tu correo y tu contraseña.");
    try {
      await conCarga(boton, async () => {
        const r = await api("/auth/login", { metodo: "POST", form: { username: email.value.trim(), password: clave.value } });
        sesion.guardar(r.access_token);
      });
      alIngresar();
    } catch (err) { fallar(err.message); }
  } },
    h("h2", {}, "Bienvenido de nuevo"),
    h("p", { class: "sub" }, "Ingresa con la cuenta que te creó la administración."),
    error,
    h("div", { class: "field" }, email, h("label", { for: "email" }, "Correo electrónico")),
    h("div", { class: "field" }, clave, h("label", { for: "clave" }, "Contraseña"), ver),
    boton,
    h("p", { class: "nota-cierre" }, "¿Olvidaste tu contraseña o aún no tienes cuenta? Pídela en la administración de tu conjunto."));

  function fallar(texto) {
    error.textContent = texto; error.hidden = false;
    form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
  }

  return h("div", { class: "login" },
    h("section", { class: "login-marca" },
      h("div", {}, logoCompleto(),
        h("h1", {}, "Tu conjunto, ", h("em", {}, "siempre en orden.")),
        h("p", {}, "Reservas, mantenimiento, cartera y portería en un solo lugar, para administradores, residentes y guardias.")),
      h("small", { style: "opacity:.6" }, "Control residencial inteligente")),
    h("section", { class: "login-form" }, botonTema("login-tema"), form));
}
