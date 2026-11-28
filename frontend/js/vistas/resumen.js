// Pantalla de inicio: cambia según el rol de quien ingresó.
import { locale } from "../i18n.js";
import { api } from "../api.js";
import { tarjetaPorGestionar } from "../campana.js";
import { h, icono, badge, estadoVacio, kpi, propio, toast, dinero, deUtc, hace, placa, deLocal, conCarga, diaLocal } from "../ui.js";
import { cabecera, hoyLargo, mapaUsuarios, nombreDe } from "./comun.js";
import { itemReserva } from "./reservas.js";
import { cartelaResumen } from "./anuncios.js";

const primerNombre = (n) => propio(n.split(" ")[0]);
// «Bienvenido al apartamento 201.»; si el dato no es un número simple (p. ej. «Torre 2 - 201») se deja como viene.
const bienvenida = (a) => (a ? (/^\d+[A-Za-z]?$/.test(String(a)) ? `Bienvenido al apartamento ${a}.` : `Bienvenido a ${a}.`) : "Bienvenido a tu conjunto.");
const hoy0 = () => new Date(new Date().setHours(0, 0, 0, 0));
const esHoy = (r) => deLocal(r.fecha_reserva).toDateString() === new Date().toDateString();

// ---------- Administrador ----------
async function admin(ctx) {
  const [usuarios, reservas, danios, dentro, avisos, comercio, paq, todasPqrs, porAprobar] = await Promise.all([api("/usuarios/"), api("/reservas/listar", { params: { estado: "Pendiente" } }), api("/mantenimiento/listar-danios"), api("/porteria/vehiculos-dentro"), api("/anuncios/"), api("/comercio/resumen"), api("/paquetes/", { params: { estado: "En porteria" } }), api("/pqrs/", { params: { limite: 300 } }), api("/arrendamientos/", { params: { estado: "Pendiente" } })]);
  const mapa = mapaUsuarios(usuarios);
  const residentes = usuarios.filter((u) => u.rol === "Residente");
  const pendientes = reservas.filter((r) => r.estado === "Pendiente");
  const abiertos = danios.filter((d) => d.estado !== "Aprobado");        // v5.7: «Solucionado» aún espera la aprobación del administrador
  const pqrsAbiertas = todasPqrs.filter((p) => p.estado === "Radicada" || p.estado === "En tramite").length;
  const porAtender = pendientes.length + abiertos.length + comercio.por_revisar + porAprobar.length + pqrsAbiertas;   // todo lo que espera una acción del administrador

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
      kpi("Por atender hoy", porAtender, { destacado: true, nota: "Reservas, daños, PQRS, anuncios y arrendamientos" }),
      kpi("Reservas por aprobar", pendientes.length, { alerta: true, href: "#/reservas", marca: "m_reservas" }),
      kpi("Daños sin resolver", abiertos.length, { alerta: true, href: "#/mantenimiento", marca: "m_mantenimiento" }),
      kpi("Apartamentos en mora", residentes.filter((u) => !u.esta_al_dia).length, { alerta: true, href: "#/cartera", marca: "m_cartera" }),
      kpi("Vehículos dentro", dentro.length, { href: "#/porteria", marca: "m_porteria" }),
      kpi("Anuncios por revisar", comercio.por_revisar, { alerta: true, href: "#/comercio", marca: "m_comercio" }),
      kpi("Paquetes sin entregar", paq.length, { href: "#/paquetes", marca: "m_paquetes" }),
      kpi("Arrendamientos por aprobar", porAprobar.length, { alerta: true, href: "#/inquilinos", marca: "m_inquilinos" }),
      kpi("PQRS por atender", pqrsAbiertas, { alerta: true, href: "#/pqrs", marca: "m_pqrs" }),
      kpi("Residentes activos", residentes.filter((u) => u.esta_activo).length, { href: "#/residentes", marca: "m_residentes" })),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Por aprobar"), h("a", { class: "btn suave sm", href: "#/reservas" }, "Ver todas")), lista),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Daños recientes"), h("a", { class: "btn suave sm", href: "#/mantenimiento" }, "Gestionar")),
        h("div", { class: "lista" }, abiertos.length ? abiertos.slice(0, 5).map((d) => h("div", { class: "item" },
          h("div", {}), h("div", { class: "cuerpo" }, h("b", {}, d.titulo), h("span", {}, `${nombreDe(mapa, d.usuario_id)} · ${hace(deUtc(d.fecha_creacion))}`)), h("div", { class: "acciones" }, badge(d.estado)))) : [estadoVacio("Sin daños pendientes", "Todo está solucionado.")])),
      cartelaResumen(avisos)));
}

// ---------- Residente ----------
async function residente(ctx) {
  const [cuenta, mias, danios, avisos, paq, votos] = await Promise.all([api(`/administracion/estado-cuenta/${ctx.usuario.id}`), api("/reservas/mis-reservas"), api("/mantenimiento/listar-danios"), api("/anuncios/"), api("/paquetes/", { params: { estado: "En porteria" } }), api("/votaciones/pendientes").catch(() => ({ pendientes: 0 }))]);
  const proximas = mias.filter((r) => r.estado !== "Cancelada" && deLocal(r.fecha_reserva) >= hoy0()).sort((a, b) => deLocal(a.fecha_reserva) - deLocal(b.fecha_reserva)).slice(0, 3);
  const alDia = cuenta.saldo_pendiente === 0;
  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, bienvenida(cuenta.apartamento), { saludo: hoyLargo() }),
    votos.pendientes ? h("a", { class: "aviso-votacion escalona", href: "#/votaciones" }, icono("m_votaciones", 22),
      h("span", {}, h("b", {}, `Tienes ${votos.pendientes} votación(es) por responder`), h("small", {}, "Tu voto es secreto y toma un minuto.")), icono("flecha", 18)) : null,
    h("div", { class: "grid dos escalona" },
      h("section", { class: "cuenta" }, h("div", { class: "et" }, "Saldo de administración"), h("div", { class: "monto" }, dinero(cuenta.saldo_pendiente)),
        h("div", { class: "datos" }, alDia ? h("span", { class: "badge bosque" }, "Estás al día") : h("span", { class: "badge laton" }, "En mora · reservas bloqueadas"),
          h("a", { class: "btn sm claro", href: "#/cartera" }, alDia ? "Ver mi cuenta" : "Pagar ahora"))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Accesos rápidos")),
        h("div", { class: "lista" },
          h("a", { class: "btn suave block", href: "#/reservas" }, icono("m_reservas", 18), "Reservar una zona común"),
          h("a", { class: "btn suave block", href: "#/mantenimiento" }, icono("m_mantenimiento", 18), "Reportar un daño"),
          paq.length ? h("a", { class: "btn block", href: "#/paquetes" }, icono("m_paquetes", 18), `Tienes ${paq.length} ${paq.length === 1 ? "paquete" : "paquetes"} en portería`) : null,
          h("a", { class: "btn suave block", href: "#/visitas" }, icono("m_visitas", 18), "Avisar que viene una visita"),
          h("a", { class: "btn suave block", href: "#/pqrs" }, icono("m_pqrs", 18), "Quejas y sugerencias"),
          h("a", { class: "btn suave block", href: "#/documentos" }, icono("m_documentos", 18), "Reglamento y documentos"),
          h("a", { class: "btn suave block", href: "#/emergencias" }, icono("m_emergencias", 18), "Teléfonos de emergencia"),
          h("a", { class: "btn suave block", href: "#/comercio" }, icono("m_comercio", 18), "Comercio del conjunto"))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis próximas reservas"), h("a", { class: "btn suave sm", href: "#/reservas" }, "Ver todas")),
        h("div", { class: "lista" }, proximas.length ? proximas.map((r) => itemReserva(r)) : [estadoVacio("Sin reservas próximas", "Reserva el salón, la zona BBQ y más.")])),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis reportes"), h("a", { class: "btn suave sm", href: "#/mantenimiento" }, "Ver todos")),
        h("div", { class: "lista" }, danios.length ? danios.slice(0, 3).map((d) => h("div", { class: "item" }, h("div", {}), h("div", { class: "cuerpo" }, h("b", {}, d.titulo), h("span", {}, hace(deUtc(d.fecha_creacion)))), h("div", { class: "acciones" }, badge(d.estado)))) : [estadoVacio("Sin reportes", "Cuando reportes un daño verás su avance aquí.")])),
      cartelaResumen(avisos)));
}

// ---------- Inquilino ----------
async function inquilino(ctx) {
  const del = ctx.usuario.delegaciones ?? [];                      // lo que su propietario le dejó hacer: "pagar" y/o "votar"
  const [contrato, mias, danios, avisos, paq, votos] = await Promise.all([api("/arrendamientos/mio"), api("/reservas/mis-reservas"), api("/mantenimiento/listar-danios"), api("/anuncios/"),
    api("/paquetes/", { params: { estado: "En porteria" } }), del.includes("votar") ? api("/votaciones/pendientes").catch(() => ({ pendientes: 0 })) : null]);
  const proximas = mias.filter((r) => r.estado !== "Cancelada" && deLocal(r.fecha_reserva) >= hoy0()).sort((a, b) => deLocal(a.fecha_reserva) - deLocal(b.fecha_reserva)).slice(0, 3);
  const hasta = new Date(`${contrato.fecha_fin}T00:00:00`).toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric" });
  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, bienvenida(contrato.apartamento), { saludo: hoyLargo() }),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "cuenta" }, h("div", { class: "et" }, "Mi arrendamiento"), h("div", { class: "monto", style: "font-size:1.5rem" }, contrato.apartamento ?? "Mi apartamento"),
        h("div", { class: "datos" }, h("span", { class: contrato.dias_restantes <= 30 ? "badge laton" : "badge" }, contrato.dias_restantes <= 30 ? `Vence en ${contrato.dias_restantes} día(s)` : `Acceso hasta el ${hasta}`),
          h("span", { class: "small" }, `Propietario: ${propio(contrato.propietario_nombre)}`))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Accesos rápidos")),
        h("div", { class: "lista" },
          h("a", { class: "btn suave block", href: "#/reservas" }, icono("m_reservas", 18), "Reservar una zona común"),
          h("a", { class: "btn suave block", href: "#/mantenimiento" }, icono("m_mantenimiento", 18), "Reportar un daño"),
          paq.length ? h("a", { class: "btn block", href: "#/paquetes" }, icono("m_paquetes", 18), `Tienes ${paq.length} ${paq.length === 1 ? "paquete" : "paquetes"} en portería`) : null,
          votos?.pendientes ? h("a", { class: "btn block", href: "#/votaciones" }, icono("m_votaciones", 18), `Tienes ${votos.pendientes} ${votos.pendientes === 1 ? "votación" : "votaciones"} por votar`) : null,
          del.includes("pagar") ? h("a", { class: "btn suave block", href: "#/cartera" }, icono("m_cartera", 18), "Pagar la administración del apartamento") : null,
          h("a", { class: "btn suave block", href: "#/visitas" }, icono("m_visitas", 18), "Avisar que viene una visita"),
          h("a", { class: "btn suave block", href: "#/pqrs" }, icono("m_pqrs", 18), "Quejas y sugerencias"),
          h("a", { class: "btn suave block", href: "#/documentos" }, icono("m_documentos", 18), "Reglamento y circulares"),
          h("a", { class: "btn suave block", href: "#/emergencias" }, icono("m_emergencias", 18), "Teléfonos de emergencia"))),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis próximas reservas"), h("a", { class: "btn suave sm", href: "#/reservas" }, "Ver todas")),
        h("div", { class: "lista" }, proximas.length ? proximas.map((r) => itemReserva(r)) : [estadoVacio("Sin reservas próximas", "Reserva el salón, la zona BBQ y más.")])),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mis reportes"), h("a", { class: "btn suave sm", href: "#/mantenimiento" }, "Ver todos")),
        h("div", { class: "lista" }, danios.length ? danios.slice(0, 3).map((d) => h("div", { class: "item" }, h("div", {}), h("div", { class: "cuerpo" }, h("b", {}, d.titulo), h("span", {}, hace(deUtc(d.fecha_creacion)))), h("div", { class: "acciones" }, badge(d.estado)))) : [estadoVacio("Sin reportes", "Cuando reportes un daño verás su avance aquí.")])),
      cartelaResumen(avisos)));
}

// ---------- Guardia ----------
async function guardia(ctx) {
  const [dentro, reservas, avisos, paq, aPie] = await Promise.all([api("/porteria/vehiculos-dentro"), api("/reservas/listar", { params: { estado: "Aprobada", desde: diaLocal(), hasta: diaLocal() } }), api("/anuncios/"), api("/paquetes/", { params: { estado: "En porteria" } }), api("/visitantes-autorizados/dentro")]);
  const deHoy = reservas.filter((r) => r.estado === "Aprobada" && esHoy(r));
  return h("div", {},
    cabecera(`Hola, ${primerNombre(ctx.usuario.nombre_completo)}`, "Resumen del turno.", { saludo: hoyLargo() }),
    h("div", { class: "cta-guardia escalona" },
      h("a", { class: "btn block cta-escanear", href: "#/porteria" }, icono("qr", 24), "Ir a portería y escanear"),
      h("a", { class: "btn block cta-emergencia", href: "#/emergencias", "aria-label": "Teléfonos de emergencia" }, icono("m_emergencias", 24), "Teléfonos de emergencia")),
    h("div", { class: "kpis escalona" }, kpi("Vehículos dentro", dentro.length, { destacado: true, href: "#/porteria" }), kpi("Visitantes a pie dentro", aPie.length, { marca: "m_visitas" }), kpi("Paquetes sin entregar", paq.length, { href: "#/paquetes", marca: "m_paquetes" }), kpi("Reservas aprobadas hoy", deHoy.length, { href: "#/reservas", marca: "m_reservas" })),
    h("div", { class: "grid dos escalona" },
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "En el parqueadero")),
        h("div", { class: "lista" }, dentro.length ? dentro.slice(0, 5).map((v) => h("div", { class: "vehiculo" }, placa(v.placa), h("div", { class: "cuerpo" }, h("b", {}, v.apartamento_destino), h("div", { class: "small muted" }, hace(deUtc(v.fecha_ingreso)))))) : [estadoVacio("Portería despejada", "No hay visitantes dentro.")])),
      h("section", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Reservas de hoy")),
        h("div", { class: "lista" }, deHoy.length ? deHoy.map((r) => itemReserva(r)) : [estadoVacio("Sin eventos hoy", "No hay zonas comunes reservadas para hoy.")])),
      cartelaResumen(avisos)));
}

const POR_ROL = { Administrador: admin, Residente: residente, Inquilino: inquilino, Guardia: guardia };

// v5.7 · Debajo del saludo de cualquier rol aparece lo que sigue «por gestionar», aunque ya se hayan abierto sus avisos.
export const render = async (ctx) => {
  const [vista, aviso] = await Promise.all([POR_ROL[ctx.usuario.rol](ctx), tarjetaPorGestionar()]);
  if (aviso) vista.firstElementChild?.after(aviso);
  return vista;
};
