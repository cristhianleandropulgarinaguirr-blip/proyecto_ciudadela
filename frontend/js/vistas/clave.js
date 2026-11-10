// Cambio de contraseña (POST /auth/cambiar-password). Si `obligatorio` es true el modal no se puede cerrar:
// se usa cuando el administrador restableció la clave y la persona debe crear una propia.
import { api } from "../api.js";
import { h, modal, toast, conCarga } from "../ui.js";

export function modalCambiarClave({ obligatorio = false, alCambiar } = {}) {
  const campo = (id, et, auto) => h("div", { class: "field" }, h("input", { id, type: "password", placeholder: " ", autocomplete: auto, maxlength: "64" }), h("label", { for: id }, et));
  const actual = campo("cp-actual", obligatorio ? "Contraseña temporal" : "Contraseña actual", "current-password");
  const nueva = campo("cp-nueva", "Nueva contraseña (mín. 8 caracteres)", "new-password");
  const repite = campo("cp-repite", "Repite la nueva contraseña", "new-password");
  const val = (c) => c.querySelector("input").value;
  const ok = h("button", { class: "btn", type: "submit", form: "f-clave" }, "Guardar contraseña");
  const m = modal(obligatorio ? "Crea tu contraseña" : "Cambiar contraseña", h("form", { id: "f-clave", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (val(nueva).length < 8) return toast("La nueva contraseña debe tener al menos 8 caracteres.", "error");
    if (val(nueva) !== val(repite)) return toast("Las contraseñas nuevas no coinciden.", "error");
    try {
      await conCarga(ok, () => api("/auth/cambiar-password", { metodo: "POST", json: { password_actual: val(actual), password_nueva: val(nueva) } }));
      m.cerrar(); toast("Contraseña actualizada"); alCambiar?.();
    } catch (err) { toast(err.message, "error"); }
  } },
    obligatorio ? h("p", { class: "muted", style: "margin-bottom:1rem" }, "La administración restableció tu acceso. Escribe la clave temporal que te dieron y elige una propia.") : null,
    actual, nueva, repite),
  { pie: [obligatorio ? null : h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok].filter(Boolean) });
  if (obligatorio) {
    const d = document.getElementById("modal");
    d.classList.add("modal-fijo");
    d.addEventListener("cancel", (ev) => ev.preventDefault());   // la tecla Esc no lo cierra
    d.onclick = null;
    d.addEventListener("close", () => d.classList.remove("modal-fijo"), { once: true });
  }
  actual.querySelector("input").focus();
  return m;
}
