// Configuración personal: perfil y preferencias de apariencia (se guardan en este dispositivo).
import { h, icono, toast, conCarga, deUtc, hace, confirmar } from "../ui.js";
import { cabecera } from "./comun.js";
import { api } from "../api.js";
import { activarPush, desactivarPush, estadoPush, probarPush } from "../push.js";
import { modalCambiarClave } from "./clave.js";
import { alCambiarInstalacion, ayudaInstalar, instalar, puedeInstalar, yaInstalada } from "../instalar.js";

const T = () => window.CiudadelaTema;

// Grupo de botones tipo "segmentado" que guarda al elegir.
function segmentado(opciones, actual, alElegir) {
  const caja = h("div", { class: "segmentado", role: "group" });
  const pintar = (sel) => caja.replaceChildren(...opciones.map(([valor, texto, ic]) =>
    h("button", { type: "button", "aria-pressed": String(valor === sel), onclick: () => { pintar(valor); alElegir(valor); } }, ic ? icono(ic) : null, texto)));
  pintar(actual);
  return caja;
}
const interruptor = (activo, alCambiar, etiqueta) => {
  const i = h("input", { type: "checkbox", checked: activo, "aria-label": etiqueta, onchange: (e) => alCambiar(e.target.checked) });
  return h("label", { class: "switch" }, i, h("i"));
};
const fila = (titulo, texto, control) => h("div", { class: "opcion" }, h("div", { class: "t" }, h("b", {}, titulo), h("span", {}, texto)), control);

// Fila «Instalar la app»: botón si el navegador lo permite; si no, una explicación según el dispositivo.
function filaInstalar() {
  const control = h("div");
  const pintar = () => control.replaceChildren(puedeInstalar()
    ? h("button", { class: "btn sm", onclick: async () => { if (await instalar()) toast("¡Listo! Ciudadela quedó en tu pantalla principal."); } }, icono("descarga", 16), "Instalar")
    : h("span", { class: "small muted", style: "max-width:18rem;display:block;text-align:right" }, yaInstalada() ? "Instalada ✓" : ""));
  pintar();
  alCambiarInstalacion(pintar);
  return fila("Instalar la app", yaInstalada() ? "Ya la tienes instalada en este dispositivo." : puedeInstalar() ? "Ábrela desde tu pantalla principal, como cualquier app." : ayudaInstalar(), control);
}

// Fila «Avisos en el celular»: pide el permiso SOLO cuando la persona toca el botón.
function filaAvisos() {
  const caja = h("div");
  async function pintar() {
    const e = await estadoPush();
    const botones = [];
    if (e.estado === "inactivo") botones.push(h("button", { class: "btn sm", onclick: async (ev) => {
      try { await conCarga(ev.currentTarget, activarPush); toast("Avisos activados en este dispositivo."); } catch (err) { toast(err.message, "error"); }
      pintar();
    } }, icono("campana", 16), "Activar avisos"));
    if (e.estado === "activo") botones.push(
      h("button", { class: "btn suave sm", onclick: async (ev) => { try { await conCarga(ev.currentTarget, probarPush); toast("Te enviamos un aviso de prueba."); } catch (err) { toast(err.message, "error"); } } }, "Probar"),
      h("button", { class: "btn suave sm", onclick: async () => { await desactivarPush(); toast("Avisos desactivados en este dispositivo."); pintar(); } }, "Desactivar"));
    caja.replaceChildren(fila("Avisos en el celular", e.texto, h("div", { class: "barra-mini" }, ...botones)));
  }
  pintar();
  return caja;
}

// Dispositivos con la sesión abierta: para cerrar el que no reconozcas.
function tarjetaDispositivos() {
  const lista = h("div", { class: "lista" });
  async function cargar() {
    try {
      const ss = await api("/auth/sesiones");
      lista.replaceChildren(...ss.map((s) => h("div", { class: "item" }, h("div", { class: "ico-caja" }, icono("movil")),
        h("div", { class: "cuerpo" }, h("b", {}, `${s.dispositivo ?? "Dispositivo"}${s.actual ? " · este dispositivo" : ""}`),
          h("span", {}, `Último uso ${hace(deUtc(s.ultimo_uso))}${s.ip ? ` · IP ${s.ip}` : ""}`)),
        s.actual ? null : h("div", { class: "acciones" }, h("button", { class: "btn suave sm", onclick: async (ev) => {
          try { await conCarga(ev.currentTarget, () => api(`/auth/sesiones/${s.id}`, { metodo: "DELETE" })); toast("Sesión cerrada."); cargar(); } catch (e) { toast(e.message, "error"); }
        } }, "Cerrar")))));
      if (ss.length > 1) lista.append(h("button", { class: "btn peligro sm", style: "margin-top:.8rem", onclick: async () => {
        if (!(await confirmar("¿Cerrar las demás sesiones?", "Se cierra tu cuenta en todos los demás dispositivos. Este sigue abierto.", "Sí, cerrar", true))) return;
        try { const r = await api("/auth/cerrar-otras-sesiones", { metodo: "POST" }); toast(r.mensaje); cargar(); } catch (e) { toast(e.message, "error"); }
      } }, "Cerrar todas las demás"));
    } catch (e) { lista.replaceChildren(h("p", { class: "small muted" }, e.message)); }
  }
  cargar();
  return h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Dispositivos con tu sesión")),
    h("p", { class: "small muted", style: "margin-bottom:.8rem" }, "Si ves uno que no reconoces, ciérralo y cambia tu contraseña."), lista);
}

export async function render(ctx) {
  const u = await ctx.actualizarUsuario();
  const p = T().prefs();
  const dato = (et, v) => [h("dt", {}, et), h("dd", {}, v || "—")];

  return h("div", {},
    cabecera("Configuración", "Tu perfil y cómo quieres ver la aplicación en este dispositivo."),
    h("div", { class: "ajustes escalona" },
      h("section", { class: "card" },
        h("div", { class: "perfil" }, h("div", { class: "avatar" }, u.nombre_completo.split(/\s+/).slice(0, 2).map((x) => x[0]).join("").toUpperCase()),
          h("div", {}, h("h2", {}, u.nombre_completo), h("span", { class: "badge laton" }, u.rol))),
        h("dl", { class: "datos-perfil" }, ...dato("Correo", u.email), ...dato("Apartamento", u.apartamento), ...dato("Parqueadero", u.parqueadero_asignado === "Ninguno" ? "Sin asignar" : u.parqueadero_asignado),
          ...(u.rol === "Residente" ? dato("Estado de cartera", u.esta_al_dia ? "Al día" : "En mora") : []))),

      h("section", { class: "card" },
        h("div", { class: "card-titulo" }, h("h2", {}, "Apariencia")),
        fila("Tema", "Elige entre el modo claro o el oscuro.",
          segmentado([["claro", "Claro", "sol"], ["oscuro", "Oscuro", "luna"]], T().obtener(), (v) => T().establecer(v))),
        fila("Fondo ilustrado", "La ilustración del conjunto detrás del contenido.",
          interruptor(p.fondo === "on", (on) => T().establecerPref("fondo", on ? "on" : "off"), "Fondo ilustrado")),
        fila("Animaciones", "Transiciones y movimientos suaves. Desactívalas si prefieres una interfaz más quieta.",
          interruptor(p.anim === "on", (on) => T().establecerPref("anim", on ? "on" : "off"), "Animaciones")),
        filaInstalar(),
        filaAvisos(),
        fila("Tamaño del texto", "Hazlo más grande para leer con más comodidad.",
          segmentado([["normal", "Normal"], ["grande", "Grande"]], p.texto, (v) => T().establecerPref("texto", v)))),

      tarjetaDispositivos(),

      h("section", { class: "card" },
        h("div", { class: "card-titulo" }, h("h2", {}, "Sesión y datos")),
        fila("Contraseña", "Cámbiala si la compartiste o sospechas que otra persona la conoce.",
          h("button", { class: "btn suave sm", onclick: () => modalCambiarClave() }, "Cambiar contraseña")),
        fila("Restablecer apariencia", "Vuelve al tema claro y a los valores originales.",
          h("button", { class: "btn suave sm", onclick: () => { T().restablecer(); toast("Apariencia restablecida"); ctx.recargar(); } }, "Restablecer")),
        fila("Cerrar sesión", "Sales de este dispositivo; tus datos siguen guardados.",
          h("button", { class: "btn peligro sm", onclick: () => ctx.salir() }, icono("salir", 16), "Cerrar sesión")))));
}
