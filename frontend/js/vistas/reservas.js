// Reservas de zonas comunes.
// Endpoints: POST /reservas/registrar · GET /reservas/mis-reservas · GET /reservas/listar (admin/guardia)
//            PATCH /reservas/cambiar-estado/{id} (admin) · PATCH /reservas/{id}/cancelar (dueño/admin)
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, confirmar, deLocal, fmtHora, fmtFechaLarga } from "../ui.js";
import { cabecera, filtros, bloqueFecha } from "./comun.js";
import { calendario, textoDia } from "./calendario.js";

const ZONAS = [
  { nombre: "Salón Comunal", detalle: "Hasta 60 personas" },
  { nombre: "Zona BBQ", detalle: "Hasta 20 personas" },
  { nombre: "Piscina", detalle: "Uso por turnos" },
  { nombre: "Gimnasio", detalle: "Clases y eventos" },
  { nombre: "Cancha múltiple", detalle: "Fútbol y baloncesto" },
  { nombre: "Sala de juegos", detalle: "Hasta 15 personas" },
];

const HORAS = Array.from({ length: 17 }, (_, i) => i + 6).map((h24) => [`${String(h24).padStart(2, "0")}:00`, `${((h24 + 11) % 12) + 1}:00 ${h24 < 12 ? "a. m." : "p. m."}`]);   // 6:00 a. m. a 10:00 p. m.

// Fila reutilizable (también la usa el resumen). `acciones` es un arreglo de botones ya creados.
export function itemReserva(r, { quien, acciones = [] } = {}) {
  const f = deLocal(r.fecha_reserva);
  const pasada = f < new Date(new Date().setHours(0, 0, 0, 0));
  return h("div", { class: `item ${pasada ? "pasada" : ""}` },
    bloqueFecha(f),
    h("div", { class: "cuerpo" }, h("b", {}, r.zona_comun),
      h("span", {}, `${fmtFechaLarga(f)} · ${fmtHora(f)}`, quien ? ` · ${quien}` : "")),
    h("div", { class: "acciones" }, badge(r.estado), ...acciones));
}

export async function render(ctx) {
  const { usuario } = ctx;
  const esAdmin = usuario.rol === "Administrador";
  const puedeReservar = usuario.rol !== "Guardia";
  const [lista, perfil] = await Promise.all([
    api(esAdmin || usuario.rol === "Guardia" ? "/reservas/listar" : "/reservas/mis-reservas"),
    ctx.actualizarUsuario(),
  ]);
  const veQuien = esAdmin || usuario.rol === "Guardia";
  // El guardia entra directo a lo aprobado: es lo que debe validar en la zona.
  let datos = lista, filtro = usuario.rol === "Guardia" ? "aprobada" : "todas", zona = ZONAS[0].nombre;
  const contenedor = h("div", { class: "lista" });

  async function accion(btn, fn, msg) {
    try { await conCarga(btn, fn); toast(msg); datos = await api(esAdmin || usuario.rol === "Guardia" ? "/reservas/listar" : "/reservas/mis-reservas"); pintar(); }
    catch (e) { toast(e.message, "error"); }
  }

  function pintar() {
    const manana = new Date(new Date().setHours(0, 0, 0, 0));
    const visibles = datos.filter((r) => filtro === "todas" || r.estado.toLowerCase() === filtro)
      .sort((a, b) => {
        const fa = deLocal(a.fecha_reserva), fb = deLocal(b.fecha_reserva);
        const pa = fa < manana, pb = fb < manana;
        return pa !== pb ? (pa ? 1 : -1) : pa ? fb - fa : fa - fb;   // próximas primero, pasadas al final
      });
    conteo.forEach((c) => { c.n = datos.filter((r) => c.id === "todas" || r.estado.toLowerCase() === c.id).length; });
    chips.replaceWith((chips = filtros(conteo, filtro, (f) => { filtro = f; pintar(); })));
    contenedor.replaceChildren(...(visibles.length ? visibles.map((r) => {
      const acciones = [];
      if (esAdmin && r.estado !== "Aprobada") acciones.push(h("button", { class: "btn sm", onclick: (e) => accion(e.currentTarget, () => api(`/reservas/cambiar-estado/${r.id}`, { metodo: "PATCH", params: { nuevo_estado: "Aprobada" } }), "Reserva aprobada") }, icono("ok", 16), "Aprobar"));
      if (r.estado !== "Cancelada" && (esAdmin || r.usuario_id === usuario.id)) acciones.push(h("button", { class: "btn peligro sm", onclick: async (e) => {
        const btn = e.currentTarget;
        if (await confirmar("¿Cancelar esta reserva?", `${r.zona_comun} · ${fmtFechaLarga(deLocal(r.fecha_reserva))}`, "Sí, cancelar", true))
          accion(btn, () => api(`/reservas/${r.id}/cancelar`, { metodo: "PATCH" }), "Reserva cancelada");
      } }, "Cancelar"));
      return itemReserva(r, { quien: veQuien ? [r.usuario_nombre ?? `Residente #${r.usuario_id}`, r.apartamento].filter(Boolean).join(" · ") : null, acciones });
    }) : [estadoVacio("Sin reservas aquí", puedeReservar ? "Cuando solicites una zona común aparecerá en esta lista." : "No hay reservas con este filtro.")]));
  }

  const conteo = [{ id: "todas", texto: "Todas" }, { id: "pendiente", texto: "Pendientes" }, { id: "aprobada", texto: "Aprobadas" }, { id: "cancelada", texto: "Canceladas" }];
  let chips = h("div");

  // ----- Formulario de nueva reserva: 1) zona  2) día en el calendario  3) hora -----
  let panel = null;
  if (puedeReservar) {
    let diaElegido = null;
    const cal = calendario({ zona, alElegir: (d) => { diaElegido = d; resumenSel(); } });
    const hora = h("select", { id: "hora" }, HORAS.map(([v, t]) => h("option", { value: v, selected: v === "14:00" }, t)));
    const elegida = h("p", { class: "cal-elegida", "aria-live": "polite" });
    const resumenSel = () => {
      const t = HORAS.find(([v]) => v === hora.value)?.[1];
      elegida.textContent = diaElegido ? `Elegiste: ${textoDia(diaElegido)} a las ${t}` : "Toca un día libre en el calendario.";
    };
    hora.addEventListener("change", resumenSel);
    const botonera = h("div", { class: "zonas", role: "radiogroup", "aria-label": "Zona común" });
    const pintarZonas = () => botonera.replaceChildren(...ZONAS.map((z) =>
      h("button", { type: "button", class: "zona", role: "radio", "aria-checked": String(z.nombre === zona), onclick: () => { if (zona === z.nombre) return; zona = z.nombre; diaElegido = null; pintarZonas(); cal.cambiarZona(zona); resumenSel(); } },
        h("b", {}, z.nombre), h("span", {}, z.detalle))));
    pintarZonas(); resumenSel();
    const enviar = h("button", { class: "btn block", type: "submit", disabled: !perfil.esta_al_dia }, "Solicitar reserva");
    panel = h("form", { class: "card sticky", novalidate: true, onsubmit: async (e) => {
      e.preventDefault();
      if (!diaElegido) return toast("Toca en el calendario el día que quieres.", "error");
      try {
        await conCarga(enviar, () => api("/reservas/registrar", { metodo: "POST", json: { zona_comun: zona, fecha_reserva: `${diaElegido}T${hora.value}:00` } }));
        toast("Solicitud enviada. La administración la revisará."); diaElegido = null; resumenSel(); cal.limpiar();
        datos = await api(esAdmin ? "/reservas/listar" : "/reservas/mis-reservas"); pintar();
      } catch (err) { toast(err.message, "error"); }
    } },
      h("div", { class: "card-titulo" }, h("h2", {}, "Nueva reserva")),
      perfil.esta_al_dia ? null : h("div", { class: "aviso mora" }, icono("alerta"),
        h("div", {}, "Tu apartamento registra saldo en mora. ", h("a", { href: "#/cartera" }, "Ponte al día"), " para volver a reservar.")),
      h("p", { class: "paso" }, "1. ¿Qué zona quieres?"), botonera,
      h("p", { class: "paso" }, "2. ¿Qué día?"), cal.nodo,
      h("p", { class: "paso" }, "3. ¿A qué hora?"), h("div", { class: "field" }, hora, h("label", { for: "hora" }, "Hora de inicio")),
      elegida, enviar);
  }

  pintar();
  const lista_ui = h("div", { class: "card" },
    h("div", { class: "card-titulo" }, h("h2", {}, esAdmin || !puedeReservar ? "Todas las reservas" : "Mis reservas")),
    h("div", { style: "margin-bottom:1rem" }, chips), contenedor);

  return h("div", {},
    cabecera("Reservas", esAdmin ? "Aprueba o cancela las solicitudes de zonas comunes." : !puedeReservar ? "Consulta quién tiene reservada cada zona común para validar a quien llega." : "Reserva las zonas comunes de tu conjunto en segundos."),
    h("div", { class: panel ? "grid lados escalona" : "grid escalona" }, panel, lista_ui));
}
