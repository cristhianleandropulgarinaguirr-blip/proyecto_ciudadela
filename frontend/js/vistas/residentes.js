// Gestión de usuarios (solo administrador).
// Endpoints: GET /usuarios/ · POST /usuarios/ · PATCH /usuarios/{id}/activo?esta_activo= · PATCH /usuarios/{id}/parqueadero
import { api } from "../api.js";
import { h, icono, badge, iniciales, estadoVacio, toast, conCarga, modal, confirmar } from "../ui.js";
import { cabecera, filtros } from "./comun.js";

const ROLES = ["Residente", "Inquilino", "Guardia", "Administrador"];
const PLURAL = { Residente: "Residentes", Inquilino: "Inquilinos", Guardia: "Guardias", Administrador: "Administradores" };
const CREABLES = ROLES.filter((r) => r !== "Inquilino");   // los inquilinos se registran con un contrato (pantalla «Arrendamientos»)

function clavePronunciable() {
  const a = new Uint32Array(14); crypto.getRandomValues(a);
  const set = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(a, (n) => set[n % set.length]).join("");
}

export async function render(ctx) {
  let usuarios = await api("/usuarios/");
  let filtro = "todos", texto = "";
  const cuerpo = h("tbody"); let chips = h("div");

  function pintar() {
    const q = texto.trim().toLowerCase();
    const v = usuarios.filter((u) => (filtro === "todos" || u.rol === filtro) && (!q || `${u.nombre_completo} ${u.email} ${u.apartamento ?? ""}`.toLowerCase().includes(q)));
    chips.replaceWith((chips = filtros([{ id: "todos", texto: "Todos", n: usuarios.length }, ...ROLES.map((r) => ({ id: r, texto: PLURAL[r], n: usuarios.filter((u) => u.rol === r).length }))], filtro, (f) => { filtro = f; pintar(); })));
    cuerpo.replaceChildren(...v.map((u) => {
      const yo = u.id === ctx.usuario.id;
      const sw = h("input", { type: "checkbox", checked: u.esta_activo, disabled: yo, "aria-label": `Activo: ${u.nombre_completo}`,
        onchange: async (e) => {
          try { const r = await api(`/usuarios/${u.id}/activo`, { metodo: "PATCH", params: { esta_activo: e.target.checked } }); Object.assign(u, r); toast(r.esta_activo ? "Usuario activado" : "Usuario desactivado"); }
          catch (err) { e.target.checked = !e.target.checked; toast(err.message, "error"); }
        } });
      return h("tr", {},
        h("td", { class: "ancho" }, h("div", { class: "persona" }, h("div", { class: "avatar" }, iniciales(u.nombre_completo)),
          h("div", {}, h("b", {}, u.nombre_completo, yo ? " (tú)" : ""), h("span", {}, u.email)))),
        h("td", { "data-et": "Rol" }, h("span", { class: `badge ${u.rol === "Administrador" ? "laton" : u.rol === "Guardia" ? "borde" : u.rol === "Inquilino" ? "violeta" : "bosque"}` }, u.rol)),
        h("td", { "data-et": "Apartamento" }, u.apartamento ?? "—"),
        h("td", { "data-et": "Parqueadero" }, h("button", { class: "btn suave sm", onclick: () => editarParqueadero(u) }, u.parqueadero_asignado)),
        h("td", { "data-et": "Cartera" }, u.rol === "Residente" ? (u.esta_al_dia ? badge("Al día", "Al día") : badge("En mora", "En mora")) : "—"),
        h("td", { "data-et": "Activo" }, h("div", { class: "acciones-celda" }, h("label", { class: "switch" }, sw, h("i")),
          yo ? null : h("button", { class: "btn suave sm", title: "Genera una contraseña temporal", onclick: () => restablecerClave(u) }, "Restablecer clave"))));
    }));
    vacio.hidden = v.length > 0;
  }
  const vacio = estadoVacio("Sin resultados", "Prueba con otro nombre o filtro."); vacio.hidden = true;

  async function restablecerClave(u) {
    if (!(await confirmar("¿Restablecer la contraseña?", `${u.nombre_completo} dejará de poder entrar con su clave actual y recibirá una temporal.`, "Sí, restablecer", true))) return;
    try {
      const r = await api(`/usuarios/${u.id}/restablecer-password`, { metodo: "POST" });
      const copiar = h("button", { class: "btn suave", onclick: async () => { try { await navigator.clipboard.writeText(r.password_temporal); toast("Clave copiada"); } catch { toast("No se pudo copiar; cópiala a mano.", "error"); } } }, "Copiar");
      const m = modal("Contraseña temporal", h("div", {}, h("p", { class: "muted", style: "margin-bottom:1rem" }, r.mensaje),
        h("div", { class: "field" }, h("input", { id: "tmp", readonly: true, value: r.password_temporal, class: "mono", placeholder: " ", onfocus: (e) => e.target.select() }), h("label", { for: "tmp" }, "Clave temporal")),
        h("p", { class: "small muted" }, "Solo se muestra ahora. Si la pierdes, vuelve a restablecerla.")), { pie: [copiar, h("button", { class: "btn", onclick: () => m.cerrar() }, "Listo")] });
    } catch (e) { toast(e.message, "error"); }
  }

  function editarParqueadero(u) {
    const val = h("input", { id: "pq", placeholder: " ", maxlength: "20", value: u.parqueadero_asignado === "Ninguno" ? "" : u.parqueadero_asignado });
    const ok = h("button", { class: "btn", type: "submit", form: "f-pq" }, "Guardar");
    const m = modal(`Parqueadero de ${u.nombre_completo}`, h("form", { id: "f-pq", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (!val.value.trim()) return toast("Escribe el código del parqueadero (ej. P-202).", "error");
      try { Object.assign(u, await conCarga(ok, () => api(`/usuarios/${u.id}/parqueadero`, { metodo: "PATCH", json: { parqueadero_asignado: val.value.trim() } }))); toast("Parqueadero asignado"); m.cerrar(); pintar(); }
      catch (err) { toast(err.message, "error"); }
    } }, h("div", { class: "field" }, val, h("label", { for: "pq" }, "Código (ej. P-202)"))),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  }

  function nuevoUsuario() {
    const f = {};
    const campo = (id, et, attrs = {}) => { f[id] = h("input", { id, placeholder: " ", ...attrs }); return h("div", { class: "field" }, f[id], h("label", { for: id }, et)); };
    const rol = h("select", { id: "rol" }, CREABLES.map((r) => h("option", { value: r }, r)));
    const generar = h("button", { type: "button", class: "btn suave sm lado", onclick: () => { f.password.type = "text"; f.password.value = clavePronunciable(); } }, "Generar");
    const ok = h("button", { class: "btn", type: "submit", form: "f-nuevo" }, "Crear usuario");
    const m = modal("Nuevo usuario", h("form", { id: "f-nuevo", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      const cuerpo = { nombre_completo: f.nombre.value.trim(), email: f.email.value.trim(), password: f.password.value, rol: rol.value, apartamento: f.apto.value.trim() || null };
      if (cuerpo.nombre_completo.length < 3) return toast("Escribe el nombre completo.", "error");
      if (!/^\S+@\S+\.\S+$/.test(cuerpo.email)) return toast("El correo no es válido.", "error");
      if (cuerpo.password.length < 8) return toast("La contraseña debe tener al menos 8 caracteres.", "error");
      try { const u = await conCarga(ok, () => api("/usuarios/", { metodo: "POST", json: cuerpo })); usuarios = [...usuarios, u]; pintar(); m.cerrar(); toast(`Usuario creado: ${u.nombre_completo}`); }
      catch (err) { toast(err.message, "error"); }
    } },
      campo("nombre", "Nombre completo", { autocomplete: "off" }), campo("email", "Correo electrónico", { type: "email", autocomplete: "off" }),
      h("div", { class: "fila-campos" }, h("div", { class: "field" }, rol, h("label", { for: "rol" }, "Rol")), campo("apto", "Apartamento (opcional)")),
      h("div", { class: "field" }, (f.password = h("input", { id: "password", type: "password", placeholder: " ", autocomplete: "new-password" })), h("label", { for: "password" }, "Contraseña inicial"), generar),
      h("p", { class: "small muted" }, "Compártela con la persona; podrá usarla para ingresar de inmediato.")),
    { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  }

  const buscar = h("input", { type: "search", placeholder: "Buscar por nombre, correo o apto.", "aria-label": "Buscar usuarios", oninput: (e) => { texto = e.target.value; pintar(); } });
  pintar();
  return h("div", {}, cabecera("Usuarios", "Crea cuentas, asigna parqueaderos y activa o desactiva accesos."),
    h("div", { class: "card" },
      h("div", { class: "barra" }, h("div", { class: "buscador" }, icono("buscar"), buscar), h("button", { class: "btn", onclick: nuevoUsuario }, icono("mas", 18), "Nuevo usuario")),
      h("div", { style: "margin-bottom:.5rem" }, chips),
      h("div", { class: "tabla-wrap" }, h("table", { class: "tabla" },
        h("thead", {}, h("tr", {}, ["Usuario", "Rol", "Apartamento", "Parqueadero", "Cartera", "Activo"].map((t) => h("th", {}, t)))), cuerpo)), vacio));
}
