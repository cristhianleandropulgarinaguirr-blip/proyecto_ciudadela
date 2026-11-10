// Pantalla de inicio: cambia según el rol de quien ingresó.
import { api } from "../api.js";
import { h, icono, badge, estadoVacio, kpi, toast, dinero, deUtc, hace, placa, deLocal, conCarga } from "../ui.js";
import { cabecera, hoyLargo, mapaUsuarios, nombreDe } from "./comun.js";
import { itemReserva } from "./reservas.js";
import { cartelaResumen } from "./anuncios.js";

const primerNombre = (n) => n.split(" ")[0];
const hoy0 = () => new Date(new Date().setHours(0, 0, 0, 0));
const esHoy = (r) => deLocal(r.fecha_reserva).toDateString() === new Date().toDateString();

// ---------- Administrador ----------
async function admin(ctx) {
  const [usuarios, reservas, danios, dentro, avisos, comercio, paq, todasPqrs] = await Promise.all([api("/usuarios/"), api("/reservas/listar"), api("/mantenimiento/listar-danios"), api("/porteria/vehiculos-dentro"), api("/anuncios/"), api("/comercio/resumen"), api("/paquetes/", { params: { estado: "En porteria" } }), api("/pqrs/", { params: { limite: 300 } })]);
  const mapa = mapaUsuarios(usuarios);
  const residentes = usuarios.filter((u) => u.rol === "Residente");
  const pendientes = reservas.filter((r) => r.estado === "Pendiente");
  const abiertos = danios.filter((d) => d.estado !== "Solucionado");

  const lista = h("div", { class: "lista" });
  const pintarPend = () => lista.replaceChildren(...(pendientes.length ? pendientes.slice(0, 5).map((r) => itemReserva(r, { quien: nombreDe(mapa, r.usuario_id), acciones: [
    h("button", { class: "btn sm", onclick: async (e) => {
      try { await conCarga(e.currentTarget, () => api(`/reservas/cambiar-estado/${r.id}`, { metodo: "PATCH", params: { nuevo_estado: "Aprobada" } })); toast("Reserva aprobada"); pendientes.splice(pendientes.indexOf(r), 1); pintarPend(); }
      catch (err) { toast(err.message, "error"); }
    } }, icono("ok", 16), "Aprobar")] }))
    : [estadoVacio("Todo al día", "No hay reservas esperando aprobación.")]));
  pintarPend();

  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, "Así va tu conjunto hoy.", { saludo: hoyLargo() }),
    h("div", { class: "kpis escalona" },
      kpi("Residentes activos", residentes.filter((u) => u.esta_activo).length, { destacado: true }),
      kpi("Reservas por aprobar", pendientes.length, { alerta: true }),
      kpi("Daños sin resolver", abiertos.length, { alerta: true }),
      kpi("Apartamentos en mora", residentes.filter((u) => !u.esta_al_dia).length, { alerta: true }),
      kpi("Vehículos dentro", dentro.length),
      kpi("Anuncios por revisar", comercio.por_revisar, { alerta: true }),
      kpi("Paquetes sin entregar", paq.length), kpi("PQRS por atender", todasPqrs.filter((p) => p.estado === "Radicada" || p.estado === "En tramite").length, { alerta: true })),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Por aprobar"), h("a", { class: "btn suave sm", href: "#/reservas" }, "Ver todas")), lista),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Daños recientes"), h("a", { class: "btn suave sm", href: "#/mantenimiento" }, "Gestionar")),
        h("div", { class: "lista" }, abiertos.length ? abiertos.slice(0, 5).map((d) => h("div", { class: "item" },
          h("div", {}), h("div", { class: "cuerpo" }, h("b", {}, d.titulo), h("span", {}, `${nombreDe(mapa, d.usuario_id)} · ${hace(deUtc(d.fecha_creacion))}`)), h("div", { class: "acciones" }, badge(d.estado)))) : [estadoVacio("Sin daños pendientes", "Todo está solucionado.")])),
      cartelaResumen(avisos)));
}

// ---------- Residente ----------
async function residente(ctx) {
  const [cuenta, mias, danios, avisos, paq] = await Promise.all([api(`/administracion/estado-cuenta/${ctx.usuario.id}`), api("/reservas/mis-reservas"), api("/mantenimiento/listar-danios"), api("/anuncios/"), api("/paquetes/", { params: { estado: "En porteria" } })]);
  const proximas = mias.filter((r) => r.estado !== "Cancelada" && deLocal(r.fecha_reserva) >= hoy0()).sort((a, b) => deLocal(a.fecha_reserva) - deLocal(b.fecha_reserva)).slice(0, 3);
  const alDia = cuenta.saldo_pendiente === 0;
  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, cuenta.apartamento ? `Bienvenido a ${cuenta.apartamento}.` : "Bienvenido a tu conjunto.", { saludo: hoyLargo() }),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "cuenta" }, h("div", { class: "et" }, "Saldo de administración"), h("div", { class: "monto" }, dinero(cuenta.saldo_pendiente)),
        h("div", { class: "datos" }, alDia ? h("span", { class: "badge" }, "Estás al día") : h("span", { class: "badge laton" }, "En mora · reservas bloqueadas"),
          h("a", { class: "btn sm", style: "--bg:var(--papel);--fg:var(--bosque)", href: "#/cartera" }, alDia ? "Ver mi cuenta" : "Pagar ahora"))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Accesos rápidos")),
        h("div", { class: "lista" },
          h("a", { class: "btn suave block", href: "#/reservas" }, icono("calendario", 18), "Reservar una zona común"),
          h("a", { class: "btn suave block", href: "#/mantenimiento" }, icono("llave", 18), "Reportar un daño"),
          paq.length ? h("a", { class: "btn block", href: "#/paquetes" }, icono("caja", 18), `Tienes ${paq.length} ${paq.length === 1 ? "paquete" : "paquetes"} en portería`) : null,
          h("a", { class: "btn suave block", href: "#/visitas" }, icono("identificacion", 18), "Avisar que viene una visita"),
          h("a", { class: "btn suave block", href: "#/pqrs" }, icono("mensaje", 18), "Quejas y sugerencias"),
          h("a", { class: "btn suave block", href: "#/documentos" }, icono("archivo", 18), "Reglamento y documentos"),
          h("a", { class: "btn suave block", href: "#/emergencias" }, icono("telefono", 18), "Teléfonos de emergencia"),
          h("a", { class: "btn suave block", href: "#/comercio" }, icono("tienda", 18), "Comercio del conjunto"))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis próximas reservas"), h("a", { class: "btn suave sm", href: "#/reservas" }, "Ver todas")),
        h("div", { class: "lista" }, proximas.length ? proximas.map((r) => itemReserva(r)) : [estadoVacio("Sin reservas próximas", "Reserva el salón, la zona BBQ y más.")])),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis reportes"), h("a", { class: "btn suave sm", href: "#/mantenimiento" }, "Ver todos")),
        h("div", { class: "lista" }, danios.length ? danios.slice(0, 3).map((d) => h("div", { class: "item" }, h("div", {}), h("div", { class: "cuerpo" }, h("b", {}, d.titulo), h("span", {}, hace(deUtc(d.fecha_creacion)))), h("div", { class: "acciones" }, badge(d.estado)))) : [estadoVacio("Sin reportes", "Cuando reportes un daño verás su avance aquí.")])),
      cartelaResumen(avisos)));
}

// ---------- Guardia ----------
async function guardia(ctx) {
  const [dentro, reservas, avisos, paq, aPie] = await Promise.all([api("/porteria/vehiculos-dentro"), api("/reservas/listar"), api("/anuncios/"), api("/paquetes/", { params: { estado: "En porteria" } }), api("/visitantes-autorizados/dentro")]);
  const deHoy = reservas.filter((r) => r.estado === "Aprobada" && esHoy(r));
  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, "Resumen del turno.", { saludo: hoyLargo() }),
    h("div", { class: "kpis escalona" }, kpi("Vehículos dentro", dentro.length, { destacado: true }), kpi("Visitantes a pie dentro", aPie.length), kpi("Paquetes sin entregar", paq.length), kpi("Reservas aprobadas hoy", deHoy.length)),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "En el parqueadero"), h("a", { class: "btn sm", href: "#/porteria" }, icono("qr", 16), "Ir a portería y escanear")),
        h("div", { class: "lista" }, dentro.length ? dentro.slice(0, 5).map((v) => h("div", { class: "vehiculo" }, placa(v.placa), h("div", { class: "cuerpo" }, h("b", {}, v.apartamento_destino), h("div", { class: "small muted" }, hace(deUtc(v.fecha_ingreso)))))) : [estadoVacio("Portería despejada", "No hay visitantes dentro.")])),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Reservas de hoy")),
        h("div", { class: "lista" }, deHoy.length ? deHoy.map((r) => itemReserva(r)) : [estadoVacio("Sin eventos hoy", "No hay zonas comunes reservadas para hoy.")])),
      cartelaResumen(avisos)));
}

export const render = (ctx) => ({ Administrador: admin, Residente: residente, Guardia: guardia })[ctx.usuario.rol](ctx);
