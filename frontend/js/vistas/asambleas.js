// Asambleas de copropietarios (Ley 675 de 2001).
// Administrador: crea, convoca, instala y cierra; acredita asistentes, revisa poderes y consulta la bitácora de evidencia.
// Guardia: acredita en la puerta. Residente: ve la convocatoria, se conecta si es virtual y sube su poder.
// Endpoints: /asambleas/… · /unidades/…  (el servidor valida todas las reglas: aquí solo se muestran y se piden).
import { api, apiBlob } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaHora, kpi, esqueleto } from "../ui.js";
import { descargar, guardarBlob } from "../descargas.js";
import { abrirCapa } from "../atras.js";
import { cabecera, filtros } from "./comun.js";

const pc = (n) => Number(n ?? 0).toLocaleString("es-CO", { maximumFractionDigits: 4 });          // 0,8523 (coma decimal)
const largo = (s) => deUtc(s).toLocaleString("es-CO", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit" });
const aLocal = (d) => new Date(d - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);   // valor de un <input type="datetime-local">
const campo = (id, etiqueta, el) => h("div", { class: "field" }, el, h("label", { for: id }, etiqueta));
const ORDEN_TIPO = `1. Verificación del quórum.
2. Lectura y aprobación del orden del día.
3. Designación del presidente y del secretario de la asamblea.
4. Designación de la comisión verificadora del acta.
5. Informe de gestión del administrador.
6. Presentación y aprobación de los estados financieros.
7. Presentación y aprobación del presupuesto.
8. Elección del consejo de administración y del comité de convivencia.
9. Proposiciones y varios.`;

/** replaceChildren/append convierten `null` en el TEXTO «null»; esto ignora los vacíos (como hace h()). */
const poner = (el, ...hijos) => { el.replaceChildren(...hijos.flat(Infinity).filter((x) => x != null && x !== false)); return el; };
const anexar = (el, ...hijos) => { el.append(...hijos.flat(Infinity).filter((x) => x != null && x !== false)); return el; };

/** Ejecuta `fn` cada `ms` mientras `nodo` siga en pantalla (al salir de la vista deja de consultar solo). */
function enVivo(nodo, fn, ms) {
  const t = setInterval(() => { if (!nodo.isConnected) clearInterval(t); else fn(); }, ms);
}

/** Abre un archivo protegido (poder): se pide con el token y se guarda, porque un enlace normal no lleva la sesión. */
async function verArchivo(boton, ruta, nombre) {
  try {
    const blob = await conCarga(boton, () => apiBlob(ruta));
    const ext = blob.type === "application/pdf" ? "pdf" : blob.type === "image/png" ? "png" : blob.type === "image/webp" ? "webp" : "jpg";
    guardarBlob(blob, `${nombre}.${ext}`);
  } catch (e) { toast(e.message, "error"); }
}

// ================================================================ quórum
/** Tarjeta de quórum con una marca en el 50 %. Se actualiza sola mientras esté en pantalla. */
function tarjetaQuorum(id, { ms = 10000 } = {}) {
  const caja = h("div", { class: "card asm-quorum" }, h("div", { class: "esq", style: "height:90px" }));
  async function actualizar() {
    try {
      const q = await api(`/asambleas/${id}/quorum`);
      const ok = q.hay_quorum;
      poner(caja,
        h("div", { class: "card-titulo" }, h("h2", {}, "Quórum"), h("span", { class: `badge ${ok ? "bosque" : "laton"}` }, ok ? "Hay quórum" : "Sin quórum")),
        h("div", { class: "asm-medidor", role: "img", "aria-label": `Quórum ${pc(q.porcentaje)} por ciento` },
          h("i", { class: ok ? "ok" : "", style: `width:${Math.min(100, q.porcentaje)}%` }), h("span", { class: "marca-50", title: "50 %" })),
        h("p", { class: "asm-pct" }, `${pc(q.porcentaje)} %`, h("small", {}, ` del coeficiente · ${q.unidades_presentes} de ${q.unidades_total} unidades`)),
        h("p", { class: "small muted" }, (ok ? "Más de la mitad de los coeficientes está presente (Art. 45, Ley 675)." : `Faltan ${pc(q.faltan_para_quorum)} % para superar el 50 %.`)
          + (q.virtuales ? ` ${q.presenciales} presencial(es) y ${q.virtuales} virtual(es).` : "")),
        !q.base_completa ? h("p", { class: "small texto-error" }, q.problema_base) : null);
    } catch (e) { caja.replaceChildren(h("p", { class: "small muted" }, e.message)); }
  }
  actualizar(); enVivo(caja, actualizar, ms);
  caja.actualizar = actualizar;               // para refrescarla al instante después de acreditar a alguien
  return caja;
}

/** Pantalla completa para proyectar: quórum en grande. Se cierra con la X, Escape o el botón «Atrás» del celular. */
function pantallaGrande(a) {
  const cuerpo = h("div", { class: "asm-pantalla-cuerpo" });
  const capa = h("div", { class: "asm-pantalla", role: "dialog", "aria-label": "Quórum en pantalla grande" },
    h("button", { class: "btn suave icono asm-pantalla-x", "aria-label": "Cerrar pantalla grande", onclick: () => cerrar() }, icono("x")), cuerpo);
  let atras = null, vivo = true;
  const cerrar = () => { vivo = false; document.removeEventListener("keydown", tecla); capa.remove(); atras?.soltar(); };
  const tecla = (e) => { if (e.key === "Escape") cerrar(); };
  document.addEventListener("keydown", tecla);
  document.body.append(capa);
  atras = abrirCapa(cerrar);
  async function actualizar() {
    if (!vivo) return;
    try {
      const q = await api(`/asambleas/${a.id}/quorum`);
      cuerpo.replaceChildren(
        h("p", { class: "asm-pantalla-tit" }, q.titulo),
        h("div", { class: "asm-pantalla-pct" }, `${pc(q.porcentaje)} %`),
        h("div", { class: "asm-medidor grande" }, h("i", { class: q.hay_quorum ? "ok" : "", style: `width:${Math.min(100, q.porcentaje)}%` }), h("span", { class: "marca-50", title: "50 %" })),
        h("p", { class: `asm-pantalla-estado ${q.hay_quorum ? "ok" : ""}` }, q.hay_quorum ? "HAY QUÓRUM" : `FALTA ${pc(q.faltan_para_quorum)} % PARA EL QUÓRUM`),
        h("p", { class: "asm-pantalla-sub" }, `${q.unidades_presentes} de ${q.unidades_total} unidades presentes` + (q.virtuales ? ` · ${q.virtuales} virtuales` : "")),
        h("p", { class: "asm-pantalla-sub" }, q.estado === "En sesión" ? `Asamblea en sesión · ${q.convocatoria_numero}.ª convocatoria` : q.estado));
    } catch { /* se reintenta en el próximo ciclo */ }
  }
  actualizar();
  const t = setInterval(() => { if (!vivo || !capa.isConnected) clearInterval(t); else actualizar(); }, 5000);
}

// ================================================================ unidades y coeficientes (administrador)
async function modalUnidades() {
  const caja = h("div", {}, esqueleto(70, 4));
  const m = modal("Unidades y coeficientes", caja);
  async function cargar() {
    let r;
    try { r = await api("/unidades/"); } catch (e) { return caja.replaceChildren(h("p", { class: "muted" }, e.message)); }
    const nuevoApto = h("input", { id: "un-apto", placeholder: " ", maxlength: "40" });
    const nuevoCoef = h("input", { id: "un-coef", placeholder: " ", inputmode: "decimal" });
    const nuevoDue = h("input", { id: "un-due", placeholder: " ", maxlength: "120" });
    const agregar = h("button", { class: "btn sm", type: "button" }, icono("mas", 16), "Agregar unidad");
    agregar.onclick = async () => {
      const coef = Number(nuevoCoef.value.replace(",", "."));
      if (!nuevoApto.value.trim() || !(coef > 0)) return toast("Escribe la unidad y su coeficiente (mayor que 0).", "error");
      try { await conCarga(agregar, () => api("/unidades/", { metodo: "POST", json: { apartamento: nuevoApto.value.trim(), coeficiente: coef, propietario_nombre: nuevoDue.value.trim() || null } })); toast("Unidad registrada"); await cargar(); document.getElementById("modal")?.scrollTo(0, 0); }
      catch (e) { toast(e.message, "error"); }
    };
    const filas = r.items.map((u) => {
      const inp = h("input", { value: u.coeficiente ?? "", inputmode: "decimal", disabled: !u.editable_coeficiente, "aria-label": `Coeficiente de ${u.apartamento}`, class: "asm-coef" });
      const guardar = u.editable_coeficiente ? h("button", { class: "btn suave sm", type: "button", onclick: async (e) => {
        const coef = Number(String(inp.value).replace(",", "."));
        if (!(coef > 0)) return toast("El coeficiente debe ser mayor que 0.", "error");
        try { await conCarga(e.currentTarget, () => api(`/unidades/${u.id}`, { metodo: "PATCH", json: { coeficiente: coef } })); toast("Guardado"); cargar(); } catch (err) { toast(err.message, "error"); }
      } }, "Guardar") : null;
      return h("div", { class: "asm-fila" },
        h("div", { class: "asm-fila-txt" }, h("b", {}, u.apartamento), h("span", { class: "small muted" }, u.propietario_nombre ?? "Sin propietario registrado"),
          h("span", { class: "asm-chips" }, u.tiene_cuenta ? h("span", { class: "badge bosque" }, "Con cuenta") : h("span", { class: "badge laton" }, "Sin cuenta"), u.en_mora ? h("span", { class: "badge arcilla" }, "En mora") : null)),
        h("div", { class: "asm-fila-acc" }, inp, h("span", { class: "small muted" }, "%"), guardar));
    });
    caja.replaceChildren(
      h("div", { class: `asm-resumen ${r.completo ? "ok" : "mal"}` }, h("b", {}, `${pc(r.total)} %`), ` de 100 % · ${r.unidades} unidades`,
        h("p", { class: "small" }, r.completo ? "Listo: la base del quórum está completa." : r.problema)),
      h("p", { class: "small muted" }, "Los apartamentos con residentes en la app se editan en «Usuarios» (el cambio se refleja aquí solo). Agrega aquí a los propietarios que no usan la app: así su coeficiente cuenta en el quórum."),
      h("div", { class: "etiqueta-seccion" }, "Agregar propietario sin cuenta"),
      campo("un-apto", "Unidad (p. ej. Torre 3 Apt 303)", nuevoApto), campo("un-coef", "Coeficiente en % (p. ej. 0,8523)", nuevoCoef), campo("un-due", "Nombre del propietario (opcional)", nuevoDue), agregar,
      h("div", { class: "etiqueta-seccion" }, "Todas las unidades"), ...filas);
  }
  cargar();
  return m;
}

// ================================================================ crear / editar
function modalAsamblea(a, alGuardar) {
  const editando = !!a;
  let tipo = a?.tipo ?? "Ordinaria", modalidad = a?.modalidad ?? "Presencial", mora = a?.restringe_mora ?? false;
  const por = new Date(Date.now() + 20 * 86400e3); por.setHours(19, 0, 0, 0);
  const titulo = h("input", { id: "as-titulo", placeholder: " ", maxlength: "120", value: a?.titulo ?? "" });
  const fecha = h("input", { id: "as-fecha", type: "datetime-local", value: aLocal(a ? deUtc(a.fecha_sesion) : por) });
  const segunda = h("input", { id: "as-seg", type: "datetime-local", value: a ? aLocal(deUtc(a.fecha_segunda)) : "" });
  const lugar = h("input", { id: "as-lugar", placeholder: " ", maxlength: "150", value: a?.lugar ?? "" });
  const url = h("input", { id: "as-url", placeholder: " ", maxlength: "300", value: a?.url_videollamada ?? "", inputmode: "url" });
  const instr = h("textarea", { id: "as-instr", placeholder: " ", maxlength: "500" }, a?.instrucciones_virtual ?? "");
  const orden = h("textarea", { id: "as-orden", placeholder: " ", maxlength: "6000", rows: "9" }, a?.orden_del_dia ?? ORDEN_TIPO);
  const chips = (opciones, valor, alCambiar, etiqueta) => {
    const c = h("div", { class: "chips", role: "group", "aria-label": etiqueta });
    const pintar = () => c.replaceChildren(...opciones.map((o) => h("button", { class: "chip", type: "button", "aria-pressed": String(o === valor), onclick: () => { valor = o; alCambiar(o); pintar(); } }, o)));
    pintar(); return c;
  };
  const plazo = h("p", { class: "small muted" });
  const bloqueVirtual = h("div", {}, campo("as-url", "Enlace de la videollamada", url), campo("as-instr", "Cómo conectarse (medios tecnológicos)", instr));
  const bloqueLugar = h("div", {}, campo("as-lugar", "Lugar de la reunión", lugar));
  const pintarModalidad = () => { bloqueVirtual.hidden = modalidad === "Presencial"; bloqueLugar.hidden = modalidad === "Virtual"; };
  const pintarPlazo = () => { plazo.textContent = tipo === "Ordinaria" ? "La ordinaria se convoca con mínimo 15 días calendario completos de anticipación (Art. 39) y exige adjuntar los estados financieros." : "La extraordinaria solo trata los temas del orden del día. Revisa en tu reglamento la anticipación mínima."; };
  pintarModalidad(); pintarPlazo();
  const ok = h("button", { class: "btn", type: "submit", form: "f-asamblea" }, icono("ok", 16), editando ? "Guardar cambios" : "Crear borrador");
  const m = modal(editando ? "Editar asamblea" : "Nueva asamblea", h("form", { id: "f-asamblea", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (titulo.value.trim().length < 5) return toast("Escribe el título (mínimo 5 letras).", "error");
    if (!fecha.value) return toast("Indica la fecha y hora de la primera convocatoria.", "error");
    if (orden.value.trim().length < 10) return toast("Escribe el orden del día.", "error");
    const cuerpo = { titulo: titulo.value.trim(), tipo, modalidad, fecha_sesion: new Date(fecha.value).toISOString(), orden_del_dia: orden.value.trim(), restringe_mora: mora,
      lugar: modalidad === "Virtual" ? null : lugar.value.trim() || null, url_videollamada: modalidad === "Presencial" ? null : url.value.trim() || null,
      instrucciones_virtual: modalidad === "Presencial" ? null : instr.value.trim() || null };
    if (segunda.value) cuerpo.fecha_segunda = new Date(segunda.value).toISOString();
    try {
      await conCarga(ok, () => api(editando ? `/asambleas/${a.id}` : "/asambleas/", { metodo: editando ? "PATCH" : "POST", json: cuerpo }));
      m.cerrar(); toast(editando ? "Cambios guardados" : "Borrador creado. Revísalo y conviócalo cuando esté listo."); alGuardar();
    } catch (err) { toast(err.message, "error"); }
  } },
    campo("as-titulo", "Título (p. ej. Asamblea ordinaria 2026)", titulo),
    h("div", { class: "etiqueta-seccion" }, "Tipo"), chips(["Ordinaria", "Extraordinaria"], tipo, (v) => { tipo = v; pintarPlazo(); }, "Tipo de asamblea"), plazo,
    h("div", { class: "etiqueta-seccion" }, "Modalidad"), chips(["Presencial", "Virtual", "Mixta"], modalidad, (v) => { modalidad = v; pintarModalidad(); }, "Modalidad"),
    h("div", { style: "margin-top:1rem" }), campo("as-fecha", "Primera convocatoria", fecha), bloqueLugar, bloqueVirtual,
    campo("as-seg", "Segunda convocatoria (opcional)", segunda),
    h("p", { class: "small muted" }, "Si la dejas vacía se calcula sola: tercer día hábil siguiente, a las 8 p. m., con los festivos de Colombia (Art. 41)."),
    h("div", { class: "etiqueta-seccion" }, "Orden del día"), campo("as-orden", "Un punto por línea", orden),
    h("label", { class: "check" }, h("input", { type: "checkbox", checked: mora, onchange: (e) => { mora = e.target.checked; } }),
      h("span", {}, h("b", {}, "El reglamento le quita el voto a quien está en mora"), h("small", {}, "Déjalo apagado si tu reglamento no lo dice: la ley no lo prohíbe por sí sola.")))),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  titulo.focus();
}

// ================================================================ acreditación (administrador y guardia)
function modalAcreditar(a, u, alHecho) {
  const nombre = h("input", { id: "ac-nombre", placeholder: " ", maxlength: "120", value: u.propietario_nombre ?? "" });
  const doc = h("input", { id: "ac-doc", placeholder: " ", maxlength: "30", inputmode: "numeric" });
  let modalidad = a.modalidad === "Virtual" ? "Virtual" : "Presencial";
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Cómo asiste" });
  const pintar = () => chips.replaceChildren(...["Presencial", "Virtual"].map((o) => h("button", { class: "chip", type: "button", disabled: a.modalidad !== "Mixta" && a.modalidad !== o, "aria-pressed": String(modalidad === o), onclick: () => { modalidad = o; pintar(); } }, o)));
  pintar();
  const ok = h("button", { class: "btn", type: "submit", form: "f-acred" }, icono("ok", 16), "Acreditar");
  const m = modal(`Acreditar · ${u.apartamento}`, h("form", { id: "f-acred", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (!nombre.value.trim()) return toast("Escribe el nombre de quien asiste.", "error");
    try {
      const r = await conCarga(ok, () => api(`/asambleas/${a.id}/asistentes`, { metodo: "POST", json: { unidad_id: u.unidad_id, tipo: "Propietario", nombre: nombre.value.trim(), documento: doc.value.trim() || null, modalidad } }));
      m.cerrar(); toast(`Acreditado. Quórum: ${pc(r.quorum.porcentaje)} %${r.quorum.hay_quorum ? " · ya hay quórum" : ""}`); alHecho();
    } catch (err) { toast(err.message, "error"); }
  } },
    h("p", { class: "muted" }, `Coeficiente: ${pc(u.coeficiente)} %`, u.en_mora ? " · la unidad figura en mora" : ""),
    campo("ac-nombre", "Quién asiste", nombre), campo("ac-doc", "Documento (opcional)", doc),
    a.modalidad === "Mixta" ? h("div", {}, h("div", { class: "etiqueta-seccion" }, "Cómo asiste"), chips) : null),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  nombre.focus();
}

async function panelAsistencia(a, esAdmin, recargar) {
  const caja = h("div", {});
  const quorum = tarjetaQuorum(a.id);
  const buscar = h("input", { type: "search", placeholder: "Buscar unidad o propietario…", "aria-label": "Buscar unidad", class: "asm-buscar" });
  const lista = h("div", { class: "asm-lista" });
  const aviso = h("div", {});
  let unidades = [], asistentes = new Map(), abierto = a.registro_abierto, estado = a.estado;   // «abierto» se refresca solo: la hora puede llegar con la pantalla ya abierta
  async function cargar() {
    try {
      const [u, as, q] = await Promise.all([api(`/asambleas/${a.id}/unidades`), api(`/asambleas/${a.id}/asistentes`), api(`/asambleas/${a.id}/quorum`)]);
      unidades = u; asistentes = new Map(as.map((x) => [x.unidad_id, x])); abierto = q.registro_abierto; estado = q.estado; pintar();
    } catch (e) { lista.replaceChildren(h("p", { class: "muted" }, e.message)); }
  }
  const refrescar = () => { cargar(); quorum.actualizar(); };
  function pintar() {
    aviso.replaceChildren(...(!abierto ? [h("p", { class: "card asm-aviso" }, icono("reloj", 18), estado === "Convocada" ? " El registro de asistentes abre 3 horas antes de la reunión." : ` La asamblea está «${estado}»: ya no se registra asistencia.`)] : []));
    const q = buscar.value.trim().toLowerCase();
    const filas = unidades.filter((u) => !q || `${u.apartamento} ${u.propietario_nombre ?? ""}`.toLowerCase().includes(q));
    lista.replaceChildren(...(filas.length ? filas.map((u) => {
      const p = asistentes.get(u.unidad_id);
      const acciones = [];
      if (u.presente) acciones.push(h("button", { class: "btn suave sm", onclick: async (e) => { try { const r = await conCarga(e.currentTarget, () => api(`/asambleas/${a.id}/asistentes/${p.id}/salida`, { metodo: "POST" })); toast(`Salida registrada. Quórum: ${pc(r.quorum.porcentaje)} %`); refrescar(); } catch (err) { toast(err.message, "error"); } } }, "Registrar salida"));
      else {
        acciones.push(h("button", { class: "btn sm", disabled: !abierto, onclick: () => modalAcreditar(a, u, refrescar) }, "Acreditar"));
        if (u.poder_id) acciones.push(h("button", { class: "btn suave sm", disabled: !abierto, onclick: async (e) => {
          const btn = e.currentTarget;
          if (!(await confirmar("¿Acreditar al apoderado?", `${u.apoderado_nombre} representará a ${u.apartamento} con un poder aprobado.`, "Sí, acreditar"))) return;
          try { const r = await conCarga(btn, () => api(`/asambleas/${a.id}/asistentes`, { metodo: "POST", json: { unidad_id: u.unidad_id, tipo: "Apoderado", poder_id: u.poder_id, modalidad: a.modalidad === "Virtual" ? "Virtual" : "Presencial" } })); toast(`Apoderado acreditado. Quórum: ${pc(r.quorum.porcentaje)} %`); refrescar(); }
          catch (err) { toast(err.message, "error"); }
        } }, "Apoderado"));
      }
      return h("div", { class: `asm-fila ${u.presente ? "presente" : ""}` },
        h("div", { class: "asm-fila-txt" }, h("b", {}, u.apartamento), h("span", { class: "small muted" }, `${u.propietario_nombre ?? "—"} · ${pc(u.coeficiente)} %`),
          h("span", { class: "asm-chips" },
            u.presente ? h("span", { class: "badge bosque" }, `Presente · ${p?.modalidad_ingreso ?? ""}${p?.es_apoderado ? " · apoderado" : ""}`) : u.ha_estado ? h("span", { class: "badge borde" }, "Ya salió") : null,
            u.poder_id && !u.presente ? h("span", { class: "badge laton" }, `Poder: ${u.apoderado_nombre}`) : null,
            u.en_mora ? h("span", { class: "badge arcilla" }, "En mora") : null, !u.tiene_cuenta ? h("span", { class: "badge borde" }, "Sin cuenta") : null)),
        h("div", { class: "asm-fila-acc" }, ...acciones));
    }) : [h("p", { class: "muted" }, "No hay unidades que coincidan.")]));
  }
  buscar.oninput = pintar;
  cargar(); enVivo(caja, cargar, 15000);
  anexar(caja, quorum, aviso, h("div", { class: "etiqueta-seccion" }, "Unidades"), buscar, lista);
  return caja;
}

// ================================================================ poderes
function modalSubirPoder(a, unidades, alHecho) {
  const nombre = h("input", { id: "pd-nombre", placeholder: " ", maxlength: "120" });
  const doc = h("input", { id: "pd-doc", placeholder: " ", maxlength: "30", inputmode: "numeric" });
  const archivo = h("input", { id: "pd-arch", type: "file", accept: "application/pdf,image/jpeg,image/png,image/webp" });
  const unidad = unidades ? h("select", { id: "pd-unidad" }, h("option", { value: "" }, "Escoge la unidad…"), ...unidades.map((u) => h("option", { value: u.id }, `${u.apartamento}${u.propietario_nombre ? ` · ${u.propietario_nombre}` : ""}`))) : null;
  const ok = h("button", { class: "btn", type: "submit", form: "f-poder" }, icono("subir", 16), "Subir poder");
  const m = modal("Subir un poder", h("form", { id: "f-poder", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (unidad && !unidad.value) return toast("Escoge la unidad que otorga el poder.", "error");
    if (nombre.value.trim().length < 3 || doc.value.trim().length < 5) return toast("Escribe el nombre y el documento del apoderado.", "error");
    if (!archivo.files[0]) return toast("Adjunta el poder firmado (PDF o foto).", "error");
    const fd = new FormData();
    fd.append("apoderado_nombre", nombre.value.trim()); fd.append("apoderado_documento", doc.value.trim()); fd.append("archivo", archivo.files[0]);
    if (unidad) fd.append("unidad_id", unidad.value);
    try { await conCarga(ok, () => api(`/asambleas/${a.id}/poderes`, { metodo: "POST", cuerpo: fd })); m.cerrar(); toast("Poder enviado. El administrador lo revisará antes de la reunión."); alHecho(); }
    catch (err) { toast(err.message, "error"); }
  } },
    h("p", { class: "small muted" }, `Escribe a quién autorizas y adjunta el poder escrito y firmado (PDF o foto). Cada persona puede representar hasta ${a.max_poderes} unidad(es). El administrador y el personal del conjunto no pueden recibir poderes.`),
    unidad ? campo("pd-unidad", "Unidad que otorga el poder", unidad) : null,
    campo("pd-nombre", "Nombre completo del apoderado", nombre), campo("pd-doc", "Número de documento del apoderado", doc),
    h("div", { class: "field archivo" }, h("label", { for: "pd-arch", class: "fija" }, "Poder firmado (PDF o foto)"), archivo)),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  nombre.focus();
}

function modalRechazar(a, p, alHecho) {
  const motivo = h("input", { id: "rz-motivo", placeholder: " ", maxlength: "200" });
  const ok = h("button", { class: "btn arcilla", type: "submit", form: "f-rechazo" }, "Rechazar poder");
  const m = modal("Rechazar poder", h("form", { id: "f-rechazo", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (motivo.value.trim().length < 3) return toast("Escribe el motivo para que el propietario pueda corregirlo.", "error");
    try { await conCarga(ok, () => api(`/asambleas/${a.id}/poderes/${p.id}/rechazar`, { metodo: "POST", json: { motivo: motivo.value.trim() } })); m.cerrar(); toast("Poder rechazado. Se avisó al propietario."); alHecho(); }
    catch (err) { toast(err.message, "error"); }
  } }, h("p", { class: "muted" }, `${p.apartamento} · apoderado: ${p.apoderado_nombre}`), campo("rz-motivo", "Motivo (p. ej. falta la firma)", motivo)),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  motivo.focus();
}

async function panelPoderes(a, esAdmin, recargar) {
  const caja = h("div", {});
  const lista = h("div", { class: "asm-lista" });
  const abierto = ["Convocada", "En sesión"].includes(a.estado);
  async function cargar() {
    let datos;
    try { datos = await api(`/asambleas/${a.id}/poderes`); } catch (e) { return lista.replaceChildren(h("p", { class: "muted" }, e.message)); }
    lista.replaceChildren(...(datos.length ? datos.map((p) => h("article", { class: "card asm-poder" },
      h("div", { class: "card-titulo" }, h("h2", {}, p.apartamento), badge(p.estado)),
      h("p", {}, "Apoderado: ", h("b", {}, p.apoderado_nombre), ` · doc. ${p.apoderado_documento}`),
      esAdmin ? h("p", { class: "small muted" }, `Subido por ${p.subido_por ?? "—"} · este apoderado tiene ${p.poderes_del_apoderado} poder(es) aprobado(s)`) : null,
      p.motivo ? h("p", { class: "small texto-error" }, `Motivo del rechazo: ${p.motivo}`) : null,
      h("div", { class: "acciones-fila" },
        h("button", { class: "btn suave sm", onclick: (e) => verArchivo(e.currentTarget, `/asambleas/${a.id}/poderes/${p.id}/archivo`, `poder-${p.id}`) }, icono("descarga", 16), "Ver archivo"),
        esAdmin && p.estado === "Pendiente" ? h("button", { class: "btn sm", onclick: async (e) => { try { await conCarga(e.currentTarget, () => api(`/asambleas/${a.id}/poderes/${p.id}/aprobar`, { metodo: "POST", json: {} })); toast("Poder aprobado"); cargar(); } catch (err) { toast(err.message, "error"); } } }, "Aprobar") : null,
        esAdmin && p.estado !== "Rechazado" ? h("button", { class: "btn peligro sm", onclick: () => modalRechazar(a, p, cargar) }, p.estado === "Aprobado" ? "Revocar" : "Rechazar") : null))
    ) : [estadoVacio("Aún no hay poderes", esAdmin ? "Los propietarios los suben desde la app, o puedes subirlos tú por quien no la usa." : "Si no puedes asistir, sube tu poder escrito y firmado.")]));
  }
  cargar();
  let unidades = null;
  const subir = abierto ? h("button", { class: "btn", onclick: async () => {
    if (esAdmin && !unidades) { try { unidades = (await api("/unidades/")).items.filter((u) => u.activa); } catch (e) { return toast(e.message, "error"); } }
    modalSubirPoder(a, esAdmin ? unidades : null, cargar);
  } }, icono("subir", 18), "Subir un poder") : null;
  anexar(caja, subir ? h("div", { style: "margin-bottom:1rem" }, subir) : null, lista);
  return caja;
}

// ================================================================ entregas y bitácora (administrador)
async function panelEntregas(a, recargar) {
  const caja = h("div", {});
  async function cargar() {
    let datos;
    try { datos = await api(`/asambleas/${a.id}/entregas`); } catch (e) { return caja.replaceChildren(h("p", { class: "muted" }, e.message)); }
    const pend = datos.filter((d) => d.estado === "Pendiente").length;
    caja.replaceChildren(
      h("p", { class: "muted" }, pend ? `${pend} propietario(s) no tienen cuenta en la app y aún no se les entrega la convocatoria. Descárgala en PDF, entrégala y registra aquí cuándo y cómo.` : "Todos los propietarios fueron avisados."),
      ...datos.map((d) => h("div", { class: "asm-fila" },
        h("div", { class: "asm-fila-txt" }, h("b", {}, d.apartamento), h("span", { class: "small muted" }, d.propietario_nombre ?? "—"),
          h("span", { class: "asm-chips" }, h("span", { class: `badge ${d.estado === "Pendiente" ? "arcilla" : "bosque"}` }, d.estado === "App" ? "Avisado por la app" : d.estado === "Manual" ? "Entrega manual" : "Pendiente"), d.detalle && d.estado === "Manual" ? h("span", { class: "small muted" }, d.detalle) : null)),
        d.estado === "Pendiente" ? h("div", { class: "asm-fila-acc" }, h("button", { class: "btn sm", onclick: () => modalEntrega(a, d, cargar) }, "Registrar entrega")) : null)));
  }
  cargar();
  return caja;
}

function modalEntrega(a, d, alHecho) {
  let canal = "Físico";
  const nota = h("input", { id: "en-nota", placeholder: " ", maxlength: "120" });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Canal de entrega" });
  const pintar = () => chips.replaceChildren(...["Físico", "Correo", "WhatsApp", "Otro"].map((o) => h("button", { class: "chip", type: "button", "aria-pressed": String(canal === o), onclick: () => { canal = o; pintar(); } }, o)));
  pintar();
  const ok = h("button", { class: "btn", type: "submit", form: "f-entrega" }, icono("ok", 16), "Registrar");
  const m = modal(`Entrega · ${d.apartamento}`, h("form", { id: "f-entrega", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    try { await conCarga(ok, () => api(`/asambleas/${a.id}/entregas-manuales`, { metodo: "POST", json: { unidad_id: d.unidad_id, canal, nota: nota.value.trim() || null } })); m.cerrar(); toast("Entrega registrada"); alHecho(); }
    catch (err) { toast(err.message, "error"); }
  } }, h("div", { class: "etiqueta-seccion" }, "Cómo se entregó"), chips, campo("en-nota", "Nota (opcional, p. ej. «recibió Marta»)", nota)),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
}

async function panelBitacora(a) {
  const caja = h("div", {}, esqueleto(60, 4));
  try {
    const b = await api(`/asambleas/${a.id}/bitacora`);
    caja.replaceChildren(
      h("div", { class: `asm-resumen ${b.integra ? "ok" : "mal"}` }, h("b", {}, b.integra ? "Cadena íntegra" : "¡Se detectó una alteración!"),
        h("p", { class: "small" }, b.integra ? `${b.total} eventos encadenados con huella SHA-256: ninguno ha sido modificado ni borrado.` : `La cadena se rompe en el evento n.º ${b.secuencia_danada}. Alguien modificó o eliminó registros directamente en la base de datos.`)),
      ...b.eventos.map((e) => h("div", { class: "asm-evento" },
        h("div", {}, h("span", { class: "badge" }, e.tipo), " ", h("b", {}, e.unidad ?? ""), h("span", { class: "small muted" }, ` ${e.actor ? `· ${e.actor}` : ""}`)),
        e.detalle ? h("p", { class: "small" }, e.detalle) : null,
        h("p", { class: "small muted" }, `#${e.secuencia} · ${fmtFechaHora(deUtc(e.creado_en))} · `, h("code", {}, e.hash.slice(0, 12))))));
  } catch (e) { caja.replaceChildren(h("p", { class: "muted" }, e.message)); }
  return caja;
}

// ================================================================ detalle
function bloqueInfo(a) {
  return h("div", { class: "card asm-info" },
    h("div", { class: "card-titulo" }, h("h2", {}, a.titulo), badge(a.estado)),
    h("p", { class: "muted" }, `${a.tipo} · ${a.modalidad}`),
    h("p", {}, icono("calendario", 16), " ", h("b", {}, "Primera convocatoria: "), largo(a.fecha_sesion)),
    h("p", {}, icono("reloj", 16), " ", h("b", {}, "Segunda convocatoria: "), largo(a.fecha_segunda), h("span", { class: "small muted" }, " · se delibera con cualquier número plural de propietarios (Art. 41).")),
    a.lugar ? h("p", {}, icono("lugar", 16), " ", h("b", {}, "Lugar: "), a.lugar) : null,
    a.url_videollamada ? h("p", {}, icono("pantalla", 16), " ", h("b", {}, "Videollamada: "), h("a", { href: a.url_videollamada, target: "_blank", rel: "noopener noreferrer" }, "Abrir enlace")) : null,
    a.instrucciones_virtual ? h("p", { class: "small muted" }, a.instrucciones_virtual) : null,
    a.instalada_en ? h("p", { class: "small" }, `Instalada con la ${a.convocatoria_numero}.ª convocatoria · quórum inicial ${pc(a.quorum_inicial)} %${a.quorum_final != null ? ` · quórum final ${pc(a.quorum_final)} %` : ""}`) : null,
    a.sin_quorum_en && !a.instalada_en ? h("p", { class: "small texto-error" }, "La primera convocatoria no logró quórum: la reunión pasa a la segunda convocatoria.") : null);
}

function bloqueOrden(a, esAdmin, recargar) {
  return h("div", { class: "card" },
    h("div", { class: "etiqueta-seccion", style: "margin-top:0" }, "Orden del día"), h("p", { class: "asm-orden" }, a.orden_del_dia),
    h("div", { class: "etiqueta-seccion" }, "Documentos de la convocatoria"),
    a.documentos.length ? h("div", { class: "asm-docs" }, a.documentos.map((d) => h("div", { class: "asm-doc" },
      h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, `/documentos/${d.id}/descargar`, `${d.titulo}.pdf`) }, icono("descarga", 16), d.titulo), h("span", { class: "small muted" }, d.categoria),
      esAdmin && a.estado === "Borrador" ? h("button", { class: "btn suave sm icono", "aria-label": `Quitar ${d.titulo}`, onclick: async () => { try { await api(`/asambleas/${a.id}/documentos/${d.id}`, { metodo: "DELETE" }); recargar(); } catch (e) { toast(e.message, "error"); } } }, icono("x", 16)) : null)))
      : h("p", { class: "small muted" }, a.tipo === "Ordinaria" && esAdmin ? "Aún no hay documentos. La asamblea ordinaria exige adjuntar los estados financieros." : "No hay documentos adjuntos."));
}

async function modalAdjuntar(a, alHecho) {
  const caja = h("div", {}, esqueleto(50, 3));
  const m = modal("Adjuntar documento", caja);
  try {
    const docs = (await api("/documentos/")).filter((d) => !a.documentos.some((x) => x.id === d.id));
    caja.replaceChildren(h("p", { class: "small muted" }, "Escoge un PDF ya subido en «Documentos». Para la asamblea ordinaria, adjunta los estados financieros (categoría «Financiero»)."),
      ...(docs.length ? docs.map((d) => h("div", { class: "asm-fila" }, h("div", { class: "asm-fila-txt" }, h("b", {}, d.titulo), h("span", { class: "small muted" }, d.categoria)),
        h("div", { class: "asm-fila-acc" }, h("button", { class: "btn sm", onclick: async (e) => { try { await conCarga(e.currentTarget, () => api(`/asambleas/${a.id}/documentos`, { metodo: "POST", json: { documento_id: d.id } })); m.cerrar(); toast("Documento adjuntado"); alHecho(); } catch (err) { toast(err.message, "error"); } } }, "Adjuntar"))))
        : [estadoVacio("No hay documentos para adjuntar", "Sube primero el PDF en la sección «Documentos».")]));
  } catch (e) { caja.replaceChildren(h("p", { class: "muted" }, e.message)); }
}

function accionesAdmin(a, recargar, volver) {
  const accion = (texto, ruta, { titulo, aviso, peligro = false, ok, clase = "" } = {}) => h("button", { class: `btn sm ${clase}`, onclick: async (e) => {
    const btn = e.currentTarget;            // se guarda ANTES del await: después de esperar, el navegador lo deja en null
    if (titulo && !(await confirmar(titulo, aviso, ok ?? "Sí, continuar", peligro))) return;
    try { const r = await conCarga(btn, () => api(ruta, { metodo: "POST" })); mostrarResultado(r); recargar(); } catch (err) { toast(err.message, "error"); }
  } }, texto);
  const mostrarResultado = (r) => {
    const adv = r?.advertencias ?? [];
    if (adv.length) modal("Convocatoria enviada", h("div", {}, h("p", {}, "La convocatoria quedó registrada y se avisó a los propietarios con cuenta. Ten en cuenta:"), h("ul", { class: "lista-simple" }, adv.map((w) => h("li", {}, w)))));
    else toast(`Listo: la asamblea quedó «${(r?.asamblea ?? r)?.estado ?? "actualizada"}».`);
  };
  const b = [];
  if (a.estado === "Borrador") b.push(
    h("button", { class: "btn suave sm", onclick: () => modalAsamblea(a, recargar) }, icono("editar", 16), "Editar"),
    h("button", { class: "btn suave sm", onclick: () => modalAdjuntar(a, recargar) }, icono("archivo", 16), "Adjuntar documento"),
    accion("Convocar", `/asambleas/${a.id}/convocar`, { titulo: "¿Enviar la convocatoria?", ok: "Sí, convocar", aviso: "Se avisará a todos los propietarios y quedará guardada la huella de lo enviado. Después no se podrá editar: si algo cambia, se cancela y se crea otra." }));
  if (a.fecha_convocatoria && a.estado !== "Borrador") b.push(h("button", { class: "btn suave sm", onclick: (e) => descargar(e.currentTarget, `/asambleas/${a.id}/convocatoria.pdf`, `convocatoria-${a.id}.pdf`) }, icono("descarga", 16), "Convocatoria PDF"));
  if (a.estado === "Convocada") {
    b.push(accion("Instalar asamblea", `/asambleas/${a.id}/instalar`, { titulo: "¿Instalar la asamblea?", ok: "Sí, instalar", aviso: "Se valida el quórum y queda registrado el quórum inicial. Primera convocatoria: más del 50 % de los coeficientes." }));
    if (!a.sin_quorum_en) b.push(accion("Declarar sin quórum", `/asambleas/${a.id}/sin-quorum`, { titulo: "¿Declarar que no hubo quórum?", ok: "Sí, declarar", peligro: true, aviso: "Pasa la reunión a la segunda convocatoria. Los asistentes registrados se liberan y deberán acreditarse de nuevo." }));
  }
  if (a.estado === "En sesión") b.push(
    h("button", { class: "btn sm", onclick: () => pantallaGrande(a) }, icono("pantalla", 16), "Pantalla grande"),
    accion("Cerrar asamblea", `/asambleas/${a.id}/cerrar`, { titulo: "¿Cerrar la asamblea?", ok: "Sí, cerrar", aviso: "Queda registrado el quórum final (los coeficientes presentes ahora). Después no se registran más movimientos." }));
  if (["Borrador", "Convocada"].includes(a.estado)) b.push(accion("Cancelar", `/asambleas/${a.id}/cancelar`, { titulo: "¿Cancelar la asamblea?", ok: "Sí, cancelar", peligro: true, clase: "peligro", aviso: a.estado === "Convocada" ? "Se avisará a todos los propietarios que ya no se realizará." : "El borrador quedará como cancelado." }));
  return h("div", { class: "acciones-fila" }, b);
}

function vistaResidente(a, recargar) {
  const partes = [bloqueInfo(a), bloqueOrden(a, false, recargar)];
  const mi = a.mi_unidad ?? {};
  const abierto = ["Convocada", "En sesión"].includes(a.estado);
  const virtual = a.modalidad !== "Presencial";
  const acc = [];
  if (a.estado === "Cancelada") acc.push(h("p", { class: "texto-error" }, "Esta asamblea fue cancelada."));
  else if (!abierto) acc.push(h("p", { class: "muted" }, a.estado === "Cerrada" ? "La asamblea ya terminó." : ""));
  else {
    if (mi.presente) acc.push(h("p", {}, h("span", { class: "badge bosque" }, "Estás conectado"), " Tu coeficiente cuenta en el quórum."));
    if (virtual && a.registro_abierto && !mi.presente) acc.push(h("button", { class: "btn", onclick: async (e) => { try { const r = await conCarga(e.currentTarget, () => api(`/asambleas/${a.id}/ingresar`, { metodo: "POST" })); toast(`Conectado. Quórum: ${pc(r.quorum.porcentaje)} %.${a.url_videollamada ? " Abre el enlace de la videollamada." : ""}`); recargar(); } catch (err) { toast(err.message, "error"); } } }, icono("pantalla", 18), "Conectarme a la asamblea"));
    if (virtual && mi.presente) acc.push(h("button", { class: "btn suave", onclick: async (e) => { const btn = e.currentTarget; if (!(await confirmar("¿Salir de la asamblea?", "Tu coeficiente dejará de contar en el quórum. Puedes volver a conectarte.", "Sí, salir"))) return; try { await conCarga(btn, () => api(`/asambleas/${a.id}/salir`, { metodo: "POST" })); toast("Saliste de la asamblea"); recargar(); } catch (err) { toast(err.message, "error"); } } }, "Salir de la asamblea"));
    if (virtual && !a.registro_abierto) acc.push(h("p", { class: "muted" }, "Podrás conectarte desde 3 horas antes de la reunión."));
    if (!virtual) acc.push(h("p", { class: "muted" }, "La reunión es presencial: preséntate en el lugar indicado con tu documento y el administrador te acreditará."));
  }
  partes.push(h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Mi participación"), mi.apartamento ? h("span", { class: "badge" }, mi.apartamento) : null), ...acc));
  if (abierto || a.estado === "Cerrada") partes.push(tarjetaQuorum(a.id, { ms: 15000 }));
  partes.push(h("div", { class: "etiqueta-seccion" }, "Poder de representación"));
  return partes;
}

async function mostrarDetalle(raiz, ctx, id, pestana = "resumen", volver) {
  raiz.replaceChildren(h("button", { class: "btn suave sm", onclick: volver }, icono("flecha", 16), "Volver"), esqueleto(120, 3));
  let a;
  try { a = await api(`/asambleas/${id}`); } catch (e) { return raiz.replaceChildren(h("button", { class: "btn suave sm", onclick: volver }, "Volver"), estadoVacio("No se pudo abrir", e.message)); }
  const rol = ctx.usuario.rol, esAdmin = rol === "Administrador", esGuardia = rol === "Guardia";
  const recargar = (p = pestana) => mostrarDetalle(raiz, ctx, id, p, volver);
  const volverBtn = h("button", { class: "btn suave sm", style: "margin-bottom:1rem", onclick: volver }, icono("flecha", 16), "Volver a Asambleas");
  volverBtn.firstChild.style.transform = "rotate(180deg)";
  const cuerpo = h("div", {});
  if (esAdmin) {
    const opciones = [{ id: "resumen", texto: "Resumen" }, { id: "asistencia", texto: "Asistencia" }, { id: "poderes", texto: "Poderes" }, { id: "entregas", texto: "Entregas" }, { id: "bitacora", texto: "Bitácora" }]
      .filter((o) => a.estado !== "Borrador" || o.id === "resumen");
    const pintar = async (p) => {
      pestana = p;
      cuerpo.replaceChildren(esqueleto(80, 3));
      if (p === "resumen") poner(cuerpo, bloqueInfo(a), accionesAdmin(a, recargar, volver), bloqueOrden(a, true, recargar),
        a.morosos?.length ? h("div", { class: "card" }, h("div", { class: "etiqueta-seccion", style: "margin-top:0" }, `Unidades en mora al convocar (${a.morosos.length})`), h("ul", { class: "lista-simple" }, a.morosos.map((m) => h("li", {}, `${m.apartamento} · $ ${Number(m.saldo).toLocaleString("es-CO")}`)))) : null);
      else if (p === "asistencia") cuerpo.replaceChildren(await panelAsistencia(a, true, recargar));
      else if (p === "poderes") cuerpo.replaceChildren(await panelPoderes(a, true, recargar));
      else if (p === "entregas") cuerpo.replaceChildren(await panelEntregas(a, recargar));
      else cuerpo.replaceChildren(await panelBitacora(a));
    };
    raiz.replaceChildren(volverBtn, opciones.length > 1 ? filtros(opciones, pestana, pintar) : h("span"), cuerpo);
    pintar(pestana);
  } else if (esGuardia) {
    raiz.replaceChildren(volverBtn, bloqueInfo(a), h("div", { class: "etiqueta-seccion" }, "Acreditación"), cuerpo);
    cuerpo.replaceChildren(await panelAsistencia(a, false, recargar));
  } else {
    raiz.replaceChildren(volverBtn, ...vistaResidente(a, recargar));
    raiz.append(await panelPoderes(a, false, recargar));
  }
}

// ================================================================ lista
export async function render(ctx) {
  const rol = ctx.usuario.rol, esAdmin = rol === "Administrador";
  const raiz = h("div", {});
  const lista = h("div", { class: "asm-lista" });
  async function mostrarLista() {
    poner(raiz, cabecera("Asambleas", esAdmin ? "Convoca, registra la asistencia y deja la evidencia de cada asamblea de copropietarios." : rol === "Guardia" ? "Acredita a los asistentes en la puerta." : "Las reuniones de la asamblea general del conjunto."),
      esAdmin ? h("div", { class: "acciones-fila", style: "margin:0 0 1rem" }, h("button", { class: "btn", onclick: () => modalAsamblea(null, mostrarLista) }, icono("mas", 18), "Nueva asamblea"),
        h("button", { class: "btn suave", onclick: modalUnidades }, icono("usuarios", 18), "Unidades y coeficientes")) : null, lista);
    lista.replaceChildren(esqueleto(90, 3));
    try {
      const datos = await api("/asambleas/");
      const proximas = datos.filter((x) => ["Convocada", "En sesión"].includes(x.estado)).length;
      poner(lista, esAdmin || proximas ? h("div", { class: "kpis" }, kpi("Convocadas o en sesión", proximas, { destacado: true })) : null,
        ...(datos.length ? datos.map((x) => h("button", { class: "card asm-tarjeta", type: "button", onclick: () => mostrarDetalle(raiz, ctx, x.id, "resumen", mostrarLista) },
          h("div", { class: "card-titulo" }, h("h2", {}, x.titulo), badge(x.estado)),
          h("p", { class: "muted" }, `${x.tipo} · ${x.modalidad}`), h("p", { class: "small" }, icono("calendario", 14), " ", largo(x.fecha_sesion)),
          x.registro_abierto ? h("span", { class: "badge bosque" }, "Registro abierto") : null))
          : [estadoVacio("Aún no hay asambleas", esAdmin ? "Crea la primera con «Nueva asamblea»." : "Cuando la administración convoque una asamblea, la verás aquí.")]));
    } catch (e) { lista.replaceChildren(estadoVacio("No se pudieron cargar", e.message)); }
  }
  await mostrarLista();
  return raiz;
}
