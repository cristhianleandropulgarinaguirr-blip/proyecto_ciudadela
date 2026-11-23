// v5.3 · Ventana emergente «Confirma tu contraseña» para las acciones sensibles del administrador (crear o desactivar usuarios, restablecer claves,
// coeficientes, importar y exportar datos). El servidor responde 403 + X-Reauth-Requerida; api.js llama aquí, y si la persona confirma se repite la acción.
// El pase dura unos minutos (solo en memoria): no se vuelve a pedir en cada clic.
import { api, sesion, cuandoPidaClave } from "./api.js";
import { h, modal, conCarga } from "./ui.js";

let abierta = null;

function pedirClave() {
  if (abierta) return abierta;                      // varias acciones a la vez comparten una sola ventana
  abierta = new Promise((resolve) => {
    let listo = false;
    const fin = (v) => { if (!listo) { listo = true; abierta = null; resolve(v); } };
    const error = h("div", { class: "msg-error", role: "alert", hidden: true });
    const clave = h("input", { type: "password", autocomplete: "current-password", required: true, placeholder: "Tu contraseña", "aria-label": "Tu contraseña" });
    const boton = h("button", { class: "btn", type: "submit" }, "Confirmar");
    const m = modal("Confirma tu contraseña", h("form", { novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (!clave.value) { error.textContent = "Escribe tu contraseña."; error.hidden = false; return; }
      try {
        await conCarga(boton, async () => { const r = await api("/auth/reautenticar", { metodo: "POST", json: { password: clave.value } }); sesion.guardarPase(r.reauth_token, r.expira_en); });
        fin(true); m.cerrar();
      } catch (err) { error.textContent = err.message; error.hidden = false; clave.select(); }
    } },
      h("p", { class: "muted", style: "margin-bottom:.8rem" }, "Es una acción delicada. Por seguridad, confirma tu contraseña para continuar (no te la volveremos a pedir por unos minutos)."),
      error, h("div", { class: "field lleno" }, clave), h("div", { class: "modal-pie", style: "margin-top:1rem" }, h("button", { class: "btn suave", type: "button", onclick: () => { fin(false); m.cerrar(); } }, "Cancelar"), boton)));
    document.getElementById("modal").addEventListener("close", () => fin(false), { once: true });
    setTimeout(() => clave.focus(), 50);
  });
  return abierta;
}

cuandoPidaClave(pedirClave);
