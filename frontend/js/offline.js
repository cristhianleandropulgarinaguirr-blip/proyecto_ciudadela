// Portería sin internet (versión 3.1).
//
// IDEA: «bandeja de salida» (outbox). Cada registro de portería (ingreso/salida de vehículo, ingreso/salida de visitante a pie,
// paquete recibido/entregado) se GUARDA PRIMERO en este equipo con un identificador único y la hora real; después se envía a
// POST /porteria/sincronizar. Con internet pasa en un instante y la persona no nota nada distinto; sin internet queda en la cola
// y se envía sola cuando vuelva la conexión. Como el identificador viaja con el registro, reenviar NUNCA lo duplica.
//
// También guarda copias de lectura (vehículos dentro, paquetes, visitantes autorizados…) para poder consultar y buscar sin conexión.
// Todo se asocia al usuario que inició sesión; las copias se borran al cerrar sesión y la cola solo la envía quien la creó.
import { almacen } from "./almacen.js";
import { api, vaciarCache } from "./api.js";
import { red } from "./red.js";

let uid = null;
let listo = false;
const oyentes = new Set();
const resultados = new Map();            // uuid → { estado, mensaje, id } de las operaciones de esta sesión

const nuevoUuid = () => crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
const claveCola = (o) => `${String(o.creado).padStart(15, "0")}-${o.uuid}`;
export const normal = (t) => String(t ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

// ---------------------------------------------------------------- cola
async function todasLasOps() {
  return (await almacen.todo("cola")).map((f) => f.valor).filter((o) => o.usuarioId === uid);
}
export async function pendientes() { return (await todasLasOps()).filter((o) => o.tipo !== "foto"); }
export async function fotosPorSubir() { return (await todasLasOps()).filter((o) => o.tipo === "foto").length; }

async function emitir() {
  const n = (await pendientes()).length, f = await fotosPorSubir();
  oyentes.forEach((fn) => { try { fn(n, f); } catch { /* un oyente no rompe a los demás */ } });
}
/** fn(pendientes, fotosPorSubir) cada vez que cambia la cola. */
export const alCambiarCola = (fn) => { oyentes.add(fn); return () => oyentes.delete(fn); };
export const resultadoDe = (uuid) => resultados.get(uuid) ?? null;

async function quitar(op) { await almacen.borrar("cola", claveCola(op)); if (op.fotoId) { /* la foto se conserva hasta que suba */ } }

async function agregarConflicto(op, mensaje) {
  const k = `${uid}:conflictos`;
  const previos = (await almacen.leer("snap", k))?.datos ?? [];
  previos.unshift({ uuid: op.uuid, tipo: op.tipo, resumen: op.vista?.resumen ?? "", mensaje, fecha: new Date().toISOString() });
  await almacen.poner("snap", k, { t: Date.now(), datos: previos.slice(0, 20) });
}
export const conflictos = async () => (await almacen.leer("snap", `${uid}:conflictos`))?.datos ?? [];
export const descartarConflictos = () => almacen.borrar("snap", `${uid}:conflictos`);

/** Envía un lote. Devuelve false si hay que parar (sin red o error del servidor): lo pendiente se queda en la cola. */
async function enviarLote(lote) {
  let res;
  try {
    res = await api("/porteria/sincronizar", { metodo: "POST", timeout: 30000,
      json: { operaciones: lote.map(({ uuid, tipo, datos, ocurrido_en }) => ({ uuid, tipo, datos, ocurrido_en })) } });
  } catch (e) {
    if (e.status === 422) {          // el servidor no entendió algún registro: se aísla para que uno malo no bloquee a los demás
      if (lote.length > 1) { for (const op of lote) if (!(await enviarLote([op]))) return false; return true; }
      await quitar(lote[0]); await agregarConflicto(lote[0], "El registro guardado no es válido."); resultados.set(lote[0].uuid, { estado: "rechazada", mensaje: "El registro no es válido." });
      return true;
    }
    return false;                    // sin red, 5xx o sesión vencida (el login se muestra solo): se reintenta luego
  }
  const porUuid = new Map(lote.map((o) => [o.uuid, o]));
  for (const r of res.resultados) {
    const op = porUuid.get(r.uuid); if (!op) continue;
    if (r.estado === "ok" || r.estado === "duplicada") {
      resultados.set(op.uuid, { estado: "ok", id: r.id });
      await quitar(op);
      if (op.fotoId && r.id) await almacen.poner("cola", `foto-${op.uuid}`, { tipo: "foto", uuid: `foto-${op.uuid}`, usuarioId: uid, paqueteId: r.id, fotoId: op.fotoId, creado: Date.now() });
    } else if (r.estado === "rechazada") {
      resultados.set(op.uuid, { estado: "rechazada", mensaje: r.mensaje });
      await quitar(op); await agregarConflicto(op, r.mensaje ?? "El servidor no aceptó el registro.");
      if (op.fotoId) await almacen.borrar("fotos", op.fotoId);
    }                                // "reintentar": se queda en la cola
  }
  return true;
}

async function subirFotos() {
  for (const job of (await todasLasOps()).filter((o) => o.tipo === "foto")) {
    const blob = await almacen.leer("fotos", job.fotoId);
    if (!blob) { await almacen.borrar("cola", job.uuid); continue; }
    try {
      const fd = new FormData(); fd.append("archivo", blob, "foto.jpg");
      await api(`/paquetes/${job.paqueteId}/foto`, { metodo: "POST", cuerpo: fd, timeout: 60000 });
      await almacen.borrar("cola", job.uuid); await almacen.borrar("fotos", job.fotoId);
    } catch (e) {
      if (e.status === 0 || e.status === 401 || e.status >= 500) return;               // se reintenta luego
      await almacen.borrar("cola", job.uuid); await almacen.borrar("fotos", job.fotoId);   // 400/404/413: reintentar no sirve
    }
  }
}

let enCurso = null;
/** Envía todo lo pendiente (una sincronización a la vez). Devuelve cuántos registros siguen pendientes. */
export function sincronizar() {
  return (enCurso ??= (async () => {
    try {
      if (!uid) return 0;
      const ops = await pendientes();
      let hubo = false;
      for (let i = 0; i < ops.length; i += 50) { if (!(await enviarLote(ops.slice(i, i + 50)))) break; hubo = true; }
      await subirFotos();
      if (hubo) { vaciarCache(); window.dispatchEvent(new CustomEvent("ciudadela:sincronizado")); }
      await emitir();
      return (await pendientes()).length;
    } finally { enCurso = null; }
  })());
}

/**
 * Registra una operación de portería. Siempre la guarda primero en el equipo y luego intenta enviarla.
 * Devuelve { estado: "ok" | "rechazada" | "pendiente", mensaje?, uuid }.
 *   ok → ya está en el servidor · rechazada → el servidor la entendió pero no es válida (mensaje) · pendiente → sin conexión, queda guardada.
 * `vista` son datos solo para MOSTRAR la operación mientras está pendiente (nombre, apartamento…); no se envían al servidor.
 */
export async function registrar(tipo, datos, { vista = {}, foto = null } = {}) {
  const op = { uuid: nuevoUuid(), tipo, datos, vista, usuarioId: uid, ocurrido_en: new Date().toISOString(), creado: Date.now() };
  if (foto) { op.fotoId = `foto-${op.uuid}`; await almacen.poner("fotos", op.fotoId, foto); }
  const guardada = await almacen.poner("cola", claveCola(op), op);
  if (!guardada) {                                     // el navegador no deja guardar: se envía directo (sin cola no hay modo sin internet)
    await enviarLote([op]);
    const r = resultados.get(op.uuid);
    if (r) return { ...r, uuid: op.uuid };
    const e = new Error("Sin conexión con el servidor. Revisa tu internet."); e.status = 0; throw e;
  }
  await emitir();
  await sincronizar();
  const r = resultados.get(op.uuid);
  if (r) return { ...r, uuid: op.uuid };
  return { estado: "pendiente", uuid: op.uuid };
}

// ---------------------------------------------------------------- copias de lectura
export async function guardarCopia(clave, datos) { await almacen.poner("snap", `${uid}:${clave}`, { t: Date.now(), datos }); }
export async function leerCopia(clave) { return (await almacen.leer("snap", `${uid}:${clave}`)) ?? null; }

/** Lee del servidor y guarda una copia; si no hay internet, devuelve la última copia. Otros errores se propagan. */
export async function leer(clave, fn) {
  try { const datos = await fn(); guardarCopia(clave, datos); return datos; }
  catch (e) {
    if (e.status === 0) { const c = await leerCopia(clave); if (c) return c.datos; }
    throw e;
  }
}

// ---------------------------------------------------------------- superponer lo pendiente sobre lo que muestra la pantalla
const delTipo = (ops, ...t) => ops.filter((o) => t.includes(o.tipo));

export function superponerVehiculos(lista, ops) {
  let salida = [...lista];
  for (const o of delTipo(ops, "vehiculo_ingreso", "vehiculo_salida")) {
    if (o.tipo === "vehiculo_ingreso") {
      const placa = o.datos.placa.toUpperCase();
      if (!salida.some((v) => v.placa === placa)) salida.push({ id: `local-${o.uuid}`, uuid: o.uuid, placa, apartamento_destino: o.datos.apartamento, fecha_ingreso: o.ocurrido_en, estado: "Dentro", pendiente: true });
    } else {
      salida = salida.filter((v) => !((o.datos.vehiculo_id && v.id === o.datos.vehiculo_id) || (o.datos.ref && v.uuid === o.datos.ref) || (o.datos.placa && v.placa === o.datos.placa.toUpperCase() && !v.pendiente && !o.datos.vehiculo_id && !o.datos.ref)));
    }
  }
  return salida;
}

export function superponerVisitantesDentro(lista, ops) {
  let salida = [...lista];
  for (const o of delTipo(ops, "visitante_ingreso", "visitante_salida")) {
    if (o.tipo === "visitante_ingreso") {
      if (!salida.some((a) => a.visitante_id === o.datos.visitante_id)) salida.push({ id: `local-${o.uuid}`, uuid: o.uuid, visitante_id: o.datos.visitante_id, nombre: o.vista.nombre ?? "Visitante", documento: o.vista.documento ?? "", tipo: o.vista.tipo ?? "Otro",
        anfitrion_nombre: o.vista.anfitrion_nombre ?? "", apartamento: o.vista.apartamento ?? null, fecha_ingreso: o.ocurrido_en, fecha_salida: null, pendiente: true });
    } else {
      salida = salida.filter((a) => !((o.datos.acceso_id && a.id === o.datos.acceso_id) || (o.datos.ref && a.uuid === o.datos.ref) || (o.datos.visitante_id && a.visitante_id === o.datos.visitante_id)));
    }
  }
  return salida;
}

export function superponerPaquetes(lista, ops) {
  const salida = lista.map((p) => ({ ...p }));
  for (const o of delTipo(ops, "paquete_registro", "paquete_entrega")) {
    if (o.tipo === "paquete_registro") {
      salida.unshift({ id: `local-${o.uuid}`, uuid: o.uuid, tipo: o.datos.tipo ?? "Paquete", remitente: o.datos.remitente ?? null, descripcion: o.datos.descripcion ?? null, estado: "En porteria",
        destinatario_nombre: o.vista.destinatario_nombre ?? "Residente", apartamento: o.vista.apartamento ?? null, fecha_recepcion: o.ocurrido_en, recibido_por: null, tiene_foto: false, pendiente: true });
    } else {
      const p = salida.find((x) => (o.datos.paquete_id && x.id === o.datos.paquete_id) || (o.datos.ref && x.uuid === o.datos.ref));
      if (p) { p.estado = "Entregado"; p.entregado_a = o.datos.entregado_a || p.destinatario_nombre; p.fecha_entrega = o.ocurrido_en; p.entregaPendiente = true; }
    }
  }
  return salida;
}

// ---------------------------------------------------------------- visitantes autorizados (búsqueda sin conexión)
const hoyColombia = () => new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10);

/** Baja la lista liviana de visitantes vigentes para poder buscarlos sin conexión. Solo portería/administración. */
export async function actualizarVisitantes() {
  try { await guardarCopia("visitantes-vigentes", await api("/visitantes-autorizados/sincronizacion")); } catch { /* sin red: se queda la copia anterior */ }
}

/** Marca como «dentro» (o no) los resultados de una búsqueda según lo que haya pendiente de enviar. */
export function superponerBusqueda(lista, ops) {
  const dentroPend = new Set(delTipo(ops, "visitante_ingreso").map((o) => o.datos.visitante_id));
  const salioPend = new Set(delTipo(ops, "visitante_salida").map((o) => o.datos.visitante_id).filter(Boolean));
  return lista.map((v) => ({ ...v, dentro: (v.dentro && !salioPend.has(v.id)) || (dentroPend.has(v.id) && !salioPend.has(v.id)) }));
}

export async function buscarVisitantesLocal(q, ops = []) {
  const copia = await leerCopia("visitantes-vigentes");
  const t = normal(q.trim()), limpio = q.replace(/[^a-z0-9]/gi, "").toUpperCase();
  const lista = (copia?.datos ?? [])
    .filter((v) => normal(v.nombre).includes(t) || (limpio.length >= 3 && String(v.documento).toUpperCase().includes(limpio)))
    .slice(0, 15)
    .map((v) => ({ ...v, vigente: !v.vigente_hasta || v.vigente_hasta.slice(0, 10) >= hoyColombia() }));
  return superponerBusqueda(lista, ops);
}

// ---------------------------------------------------------------- ciclo de vida
/** Se llama al iniciar sesión. Arranca los disparadores de sincronización (una sola vez). */
export function iniciarOffline(usuario) {
  uid = usuario.id;
  if (!listo) {
    listo = true;
    red.alCambiar((enLinea) => { if (enLinea) sincronizar(); });
    document.addEventListener("visibilitychange", () => { if (!document.hidden && red.enLinea) sincronizar(); });
    setInterval(async () => { if (uid && red.enLinea && !document.hidden && ((await pendientes()).length || (await fotosPorSubir()))) sincronizar(); }, 30000);
  }
  emitir();
  sincronizar();
  if (usuario.rol === "Guardia" || usuario.rol === "Administrador") actualizarVisitantes();
}

/** Al cerrar sesión: se borran las copias de lectura y las fotos de borrador (datos de personas). La cola NO se borra: es trabajo sin enviar. */
export async function limpiarAlSalir() {
  uid = null;
  await almacen.vaciar("snap");
  for (const f of await almacen.todo("fotos")) if (String(f.clave).startsWith("borrador:")) await almacen.borrar("fotos", f.clave);
}

/** ¿Hay trabajo sin enviar de esta persona? (para advertir antes de cerrar sesión). */
export async function hayPendientes() { return (await pendientes()).length + (await fotosPorSubir()); }
