// Asambleas de copropietarios (Ley 675 de 2001).
// Administrador: crea, convoca, instala y cierra; acredita asistentes, revisa poderes y consulta la bitácora de evidencia.
// Guardia: acredita en la puerta. Residente: ve la convocatoria, se conecta si es virtual, sube su poder y (V5.2) vota desde la app.
// Endpoints: /asambleas/… · /asambleas/{id}/votaciones/… · /unidades/…  (el servidor valida todas las reglas: aquí solo se muestran y se piden).
import { locale } from "../i18n.js";
import { api, apiBlob } from "../api.js";
import { h, icono, badge, estadoVacio, toast, conCarga, modal, confirmar, deUtc, fmtFechaHora, kpi, esqueleto } from "../ui.js";
import { descargar, guardarBlob } from "../descargas.js";
import { abrirCapa } from "../atras.js";
import { cabecera, filtros } from "./comun.js";

const pc = (n) => Number(n ?? 0).toLocaleString(locale(), { maximumFractionDigits: 4 });          // 0,8523 (coma decimal)
const largo = (s) => deUtc(s).toLocaleString(locale(), { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit" });
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

// ================================================================ votaciones dentro de la asamblea (V5.2 · Fase 3)
// Administrador: crea, abre y cierra cada pregunta y registra el voto de quien está presente en el lugar. Residente: vota desde la app si se conectó de forma virtual.
// El servidor valida TODO (quórum, padrón, 70 %, un voto por unidad, secreto): aquí solo se muestra y se pide. Mientras una pregunta está abierta no hay resultados parciales.
const MAYORIA_TXT = { Simple: "Mayoría simple", Calificada: "Mayoría calificada (70 %)" };
const hayDialogoAbierto = () => !!document.querySelector("dialog[open]");        // no se repinta mientras la persona está confirmando algo

/** Resultado congelado de una pregunta cerrada (lo ven todos). */
function resultadoVotacion(v) {
  const r = v.resultado;
  if (!r) return null;
  const ganadora = v.opciones.find((o) => o.id === r.ganadora)?.texto;
  const titular = !r.valida ? "Sin validez" : r.aprobada === true ? "Aprobada" : r.aprobada === false ? "No aprobada" : r.empate ? "Empate" : ganadora ? `Gana «${ganadora}»` : "Sin votos";
  const bien = r.valida && (r.aprobada === true || (r.aprobada == null && !r.empate && !!ganadora));
  const baseTxt = r.base === "conjunto" ? "del coeficiente de todo el conjunto" : "del coeficiente presente con derecho a voto";
  return h("div", { class: `asm-resumen ${bien ? "ok" : "mal"}` },
    h("b", {}, titular),
    r.aprobada != null ? h("p", { class: "small" }, `${pc(r.porcentaje_a_favor)} % a favor ${baseTxt}. Se necesitaba ${r.umbral === 70 ? "70 % o más" : "más del 50 %"}.`) : null,
    ...v.opciones.map((o) => {
      const p = r.base === "conjunto" ? o.porcentaje_conjunto : o.porcentaje_presentes;
      return h("div", { class: "asm-opcion-res" },
        h("div", { class: "small" }, h("b", {}, o.texto), ` · ${o.votos} unidad(es) · ${pc(o.coeficiente)} % del coeficiente`),
        h("div", { class: "asm-medidor fino", role: "img", "aria-label": `${o.texto}: ${pc(p)} por ciento` }, h("i", { class: o.texto === "A favor" || o.id === r.ganadora ? "ok" : "", style: `width:${Math.min(100, p)}%` })));
    }),
    r.motivos?.length ? h("ul", { class: "lista-simple" }, r.motivos.map((m) => h("li", {}, m))) : null,
    h("p", { class: "small muted" }, `Votaron ${r.unidades_votaron} de ${r.unidades_padron} unidades (${r.votos_app} por la app, ${r.votos_presenciales} presenciales) · quórum al abrir ${pc(r.quorum_apertura)} % y al cerrar ${pc(r.quorum_cierre)} %.`),
    v.resultado_hash ? h("p", { class: "small muted" }, "Huella SHA-256: ", h("code", { title: v.resultado_hash }, `${v.resultado_hash.slice(0, 16)}…`), " (queda también en la bitácora)") : null);
}

function modalNuevaVotacion(a, alHecho) {
  let tipo = "Decisión", mayoria = "Simple";
  const titulo = h("input", { id: "vt-titulo", placeholder: " ", maxlength: "160" });
  const desc = h("input", { id: "vt-desc", placeholder: " ", maxlength: "500" });
  const ops = h("textarea", { id: "vt-ops", rows: "4", placeholder: " ", maxlength: "1500" });
  const cajaOps = h("div", {}, campo("vt-ops", "Opciones o candidatos (uno por línea, de 2 a 12)", ops));
  const chipsTipo = h("div", { class: "chips", role: "group", "aria-label": "Tipo de votación" });
  const chipsMay = h("div", { class: "chips", role: "group", "aria-label": "Mayoría exigida" });
  const bloquea70 = a.modalidad !== "Presencial";
  const nota = h("p", { class: "small muted" });
  const pintar = () => {
    chipsTipo.replaceChildren(...[["Decisión", "Decisión (a favor / en contra)"], ["Elección", "Elección (candidatos)"]].map(([v, t]) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(tipo === v), onclick: () => { tipo = v; if (v === "Elección") mayoria = "Simple"; pintar(); } }, t)));
    chipsMay.replaceChildren(...[["Simple", "Simple (más del 50 %)"], ["Calificada", "Calificada (70 %)"]].map(([v, t]) =>
      h("button", { class: "chip", type: "button", disabled: tipo === "Elección" || (v === "Calificada" && bloquea70), "aria-pressed": String(mayoria === v), onclick: () => { mayoria = v; pintar(); } }, t)));
    cajaOps.style.display = tipo === "Elección" ? "" : "none";
    nota.textContent = tipo === "Elección" ? "En una elección gana la opción con más coeficiente. Si tu reglamento exige una mayoría específica, verifícala con el resultado."
      : bloquea70 ? "La mayoría calificada (70 %) no está disponible: la asamblea es virtual o mixta, y esas decisiones no se toman a distancia. Se bloquea también en segunda convocatoria." : "Calificada: 70 % o más del coeficiente de TODO el conjunto (no solo de los presentes).";
  };
  pintar();
  const ok = h("button", { class: "btn", type: "submit", form: "f-votacion" }, icono("ok", 16), "Crear");
  const m = modal("Nueva votación", h("form", { id: "f-votacion", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    const opciones = tipo === "Elección" ? ops.value.split("\n").map((x) => x.trim()).filter(Boolean) : [];
    try {
      await conCarga(ok, () => api(`/asambleas/${a.id}/votaciones`, { metodo: "POST", json: { titulo: titulo.value.trim(), descripcion: desc.value.trim() || null, tipo, mayoria, opciones } }));
      m.cerrar(); toast("Votación creada: ábrela cuando la asamblea esté en sesión."); alHecho();
    } catch (err) { toast(err.message, "error"); }
  } },
    campo("vt-titulo", "Qué se vota (p. ej. «¿Aprueba el presupuesto 2027?»)", titulo), campo("vt-desc", "Detalle de la propuesta (opcional)", desc),
    h("div", { class: "etiqueta-seccion" }, "Tipo"), chipsTipo, h("div", { class: "etiqueta-seccion" }, "Mayoría exigida"), chipsMay, nota, cajaOps),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
  titulo.focus();
}

function modalAnularVotacion(a, v, alHecho) {
  const motivo = h("input", { id: "an-motivo", placeholder: " ", maxlength: "200" });
  const ok = h("button", { class: "btn peligro", type: "submit", form: "f-anular" }, "Anular votación");
  const m = modal(`Anular · ${v.titulo}`, h("form", { id: "f-anular", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    try { await conCarga(ok, () => api(`/asambleas/${a.id}/votaciones/${v.id}/anular`, { metodo: "POST", json: { motivo: motivo.value.trim() } })); m.cerrar(); toast("Votación anulada."); alHecho(); }
    catch (err) { toast(err.message, "error"); }
  } }, h("p", { class: "muted" }, v.estado === "Abierta" ? "Está abierta: los votos ya emitidos no se tendrán en cuenta y se avisará a quienes votan desde la app." : "Se anula antes de abrirla."),
  campo("an-motivo", "Motivo (queda en la bitácora)", motivo)), { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Volver"), ok] });
  motivo.focus();
}

function tarjetaVotacionAdmin(a, v0, alCambiar) {
  let v = v0;
  const caja = h("div", { class: "card asm-votacion" });
  const accion = async (btn, ruta, titulo, aviso, ok) => {
    if (!(await confirmar(titulo, aviso, ok))) return;
    try {
      const r = await conCarga(btn, () => api(ruta, { metodo: "POST" }));
      if (r.advertencias?.length) modal("Ten en cuenta", h("ul", { class: "lista-simple" }, r.advertencias.map((w) => h("li", {}, w))));
      else toast("Listo.");
      alCambiar();
    } catch (err) { toast(err.message, "error"); }
  };
  const votoManual = async (f, o) => {
    if (!(await confirmar(`¿Registrar el voto de ${f.apartamento}?`, `Votó «${o.texto}». Este voto presencial queda a nombre de la unidad (no es secreto) y no se puede cambiar.`, "Sí, registrar"))) return;
    try { v = await api(`/asambleas/${a.id}/votaciones/${v.id}/votos-presenciales`, { metodo: "POST", json: { unidad_id: f.unidad_id, opcion_id: o.id } }); pintar(); }
    catch (err) { toast(err.message, "error"); }
  };
  async function refrescar() {
    if (v.estado !== "Abierta" || !caja.isConnected || hayDialogoAbierto()) return;
    try { v = await api(`/asambleas/${a.id}/votaciones/${v.id}`); pintar(); } catch { /* sin red: se reintenta */ }
  }
  function abiertaBloque() {
    const p = v.participacion ?? {};
    return h("div", {},
      h("p", { class: "asm-pct" }, `${p.unidades_votaron ?? 0} de ${p.unidades_padron ?? 0}`, h("small", {}, ` unidades han votado · ${pc(p.porcentaje)} % del coeficiente con voto`)),
      h("div", { class: "asm-medidor", role: "img", "aria-label": `Participación ${pc(p.porcentaje)} por ciento` }, h("i", { style: `width:${Math.min(100, p.porcentaje ?? 0)}%` })),
      h("p", { class: "small muted" }, `Quórum al abrir: ${pc(v.quorum_apertura)} %. Los resultados se muestran solo al cerrar (nadie ve parciales).`),
      h("div", { class: "etiqueta-seccion" }, "Quiénes pueden votar (padrón de esta votación)"),
      ...(v.padron ?? []).map((f) => h("div", { class: `asm-fila ${f.ya_voto ? "presente" : ""}` },
        h("div", { class: "asm-fila-txt" }, h("b", {}, f.apartamento), h("span", { class: "small muted" }, `${f.nombre} · ${pc(f.coeficiente)} %`),
          h("span", { class: "asm-chips" }, h("span", { class: "badge" }, f.via === "App" ? "Vota desde la app" : "Presencial"),
            f.ya_voto ? h("span", { class: "badge bosque" }, f.opcion_registrada ? `Votó: ${f.opcion_registrada}` : "Ya votó") : null,
            f.sin_medio ? h("span", { class: "badge arcilla" }, "Sin cuenta: no puede votar") : null,
            !f.sigue_presente ? h("span", { class: "badge laton" }, "Salió") : null)),
        f.via === "Manual" && !f.ya_voto && f.sigue_presente
          ? h("div", { class: "asm-fila-acc", style: "display:flex;flex-wrap:wrap;gap:.4rem" }, v.opciones.map((o) => h("button", { class: "btn sm suave", onclick: () => votoManual(f, o) }, o.texto))) : null)),
      h("div", { class: "acciones-fila", style: "margin-top:1rem" },
        h("button", { class: "btn sm", onclick: (e) => accion(e.currentTarget, `/asambleas/${a.id}/votaciones/${v.id}/cerrar`, "¿Cerrar la votación?", "Se valida el quórum de este momento, se calcula el resultado y queda congelado con su huella. No se puede deshacer.", "Sí, cerrar") }, "Cerrar votación y ver resultado"),
        h("button", { class: "btn suave sm", onclick: () => modalAnularVotacion(a, v, alCambiar) }, "Anular")));
  }
  function pintar() {
    poner(caja,
      h("div", { class: "card-titulo" }, h("h2", {}, `${v.numero}. ${v.titulo}`), badge(v.estado)),
      h("p", { class: "small muted" }, `${v.tipo} · ${v.tipo === "Decisión" ? MAYORIA_TXT[v.mayoria] : "gana la opción con más coeficiente"}`),
      v.descripcion ? h("p", {}, v.descripcion) : null,
      h("p", { class: "small muted" }, v.requisito),
      v.tipo === "Elección" && v.estado === "Borrador" ? h("p", { class: "small" }, "Opciones: ", v.opciones.map((o) => o.texto).join(" · ")) : null,
      v.estado === "Borrador" ? h("div", { class: "acciones-fila" },
        a.estado === "En sesión" ? h("button", { class: "btn sm", onclick: (e) => accion(e.currentTarget, `/asambleas/${a.id}/votaciones/${v.id}/abrir`, "¿Abrir la votación?", "Se congela quién puede votar: solo las unidades presentes y con derecho a voto ahora. Quien llegue después no votará esta pregunta. Se avisa a quienes votan desde la app.", "Sí, abrir") }, "Abrir votación")
          : h("span", { class: "small muted" }, a.estado === "Cerrada" ? "La asamblea terminó: esta propuesta no se sometió a votación." : "Podrás abrirla cuando la asamblea esté en sesión."),
        a.estado === "Cerrada" ? null : h("button", { class: "btn suave sm", onclick: () => modalAnularVotacion(a, v, alCambiar) }, "Anular")) : null,
      v.estado === "Abierta" ? abiertaBloque() : null,
      v.estado === "Cerrada" ? resultadoVotacion(v) : null,
      v.estado === "Anulada" ? h("p", { class: "small texto-error" }, `Anulada: ${v.motivo_anulacion ?? ""}`) : null);
  }
  pintar();
  if (v.estado === "Abierta") enVivo(caja, refrescar, 6000);
  return caja;
}

async function panelVotaciones(a, recargar) {
  const caja = h("div", {});
  async function cargar() {
    try {
      const lista = await api(`/asambleas/${a.id}/votaciones`);
      poner(caja,
        h("div", { class: "acciones-fila", style: "margin:0 0 1rem" }, ["Convocada", "En sesión"].includes(a.estado) ? h("button", { class: "btn", onclick: () => modalNuevaVotacion(a, cargar) }, icono("mas", 18), "Nueva votación") : null),
        h("p", { class: "small muted" }, "Cada pregunta se abre una por una. El asistente virtual vota él mismo desde la app (voto secreto); a quien está presente en el lugar le registras tú el voto (queda a su nombre)."),
        ...(lista.length ? lista.map((v) => tarjetaVotacionAdmin(a, v, cargar)) : [estadoVacio("Aún no hay votaciones", "Crea la primera con «Nueva votación».")]));
    } catch (e) { caja.replaceChildren(estadoVacio("No se pudieron cargar", e.message)); }
  }
  await cargar();
  return caja;
}

/** Residente: vota desde el celular las preguntas abiertas y ve los resultados de las cerradas. Se actualiza sola. */
function tarjetaVotaciones(a, { ms = 6000 } = {}) {
  const caja = h("div", { class: "card asm-votaciones" }, h("div", { class: "esq", style: "height:80px" }));
  const votar = async (v, m, o, btn) => {
    if (!(await confirmar(`¿Votar «${o.texto}»?`, `${m.apartamento} · ${pc(m.coeficiente)} %. Tu voto es secreto y no se puede cambiar ni repetir.`, "Sí, votar"))) return;
    try { await conCarga(btn, () => api(`/asambleas/${a.id}/votaciones/${v.id}/votar`, { metodo: "POST", json: { opcion_id: o.id, unidad_id: m.unidad_id } })); toast("Tu voto quedó registrado."); cargar(true); }
    catch (err) { toast(err.message, "error"); }
  };
  async function cargar(forzar = false) {
    if (!forzar && (hayDialogoAbierto() || !caja.isConnected)) return;
    try {
      const lista = await api(`/asambleas/${a.id}/votaciones`);
      const abiertas = lista.filter((x) => x.estado === "Abierta"), cerradas = lista.filter((x) => x.estado === "Cerrada").reverse();
      poner(caja, h("div", { class: "card-titulo" }, h("h2", {}, "Votaciones"), abiertas.length ? h("span", { class: "badge bosque" }, "Hay una votación abierta") : null),
        !lista.length ? h("p", { class: "muted" }, "Aún no hay votaciones. Cuando el administrador abra una, aparecerá aquí.") : null,
        ...abiertas.map((v) => h("div", { class: "asm-resumen" },
          h("b", {}, `${v.numero}. ${v.titulo}`), v.descripcion ? h("p", {}, v.descripcion) : null, h("p", { class: "small muted" }, v.requisito),
          ...(v.mis_unidades ?? []).map((m) => m.ya_voto ? h("p", {}, h("span", { class: "badge bosque" }, `${m.apartamento}: ya votaste`))
            : m.puede_votar ? h("div", {}, (v.mis_unidades.length > 1 ? h("p", { class: "small" }, `Votas por ${m.apartamento} (${pc(m.coeficiente)} %)`) : null),
              h("div", { class: "acciones-fila" }, v.opciones.map((o) => h("button", { class: "btn", onclick: (e) => votar(v, m, o, e.currentTarget) }, o.texto)))) : null),
          v.mensaje_votante ? h("p", { class: "small muted" }, v.mensaje_votante) : null)),
        ...cerradas.map((v) => h("div", { class: "asm-votacion-cerrada" }, h("p", {}, h("b", {}, `${v.numero}. ${v.titulo}`)), resultadoVotacion(v))),
        lista.some((x) => x.estado === "Anulada") ? h("p", { class: "small muted" }, "Alguna votación fue anulada por el administrador.") : null);
    } catch (e) { caja.replaceChildren(h("p", { class: "small muted" }, e.message)); }
  }
  cargar(true);
  enVivo(caja, () => cargar(), ms);
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
    accion("Cerrar asamblea", `/asambleas/${a.id}/cerrar`, { titulo: "¿Cerrar la asamblea?", ok: "Sí, cerrar", aviso: "Queda registrado el quórum final (los coeficientes presentes ahora) y la reunión se congela: ya no se acreditan asistentes ni se votan preguntas. Después redactas y sellas el acta." }));
  if (a.estado === "Cerrada") b.push(h("button", { class: "btn sm", onclick: () => recargar("acta") }, icono("archivo", 16), "Preparar el acta"));
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
  if (a.estado === "En sesión" || a.estado === "Cerrada") partes.push(tarjetaVotaciones(a));                       // V5.2: votar desde la app y ver resultados
  if (a.estado === "Cerrada") partes.push(tarjetaActa(a));                                                      // V5.4: el acta, cuando se publica
  partes.push(h("div", { class: "etiqueta-seccion" }, "Poder de representación"));
  return partes;
}

// ================================================================ acta de la asamblea (V5.4 · Fase 4, Art. 47 de la Ley 675 de 2001)
// El servidor decide todo (quién puede editar, cuándo se puede sellar, el plazo): aquí solo se muestra y se pide.
// Ciclo: redactar el borrador → (asamblea cerrada) sellar = congelar con huella → subir la copia firmada → publicar a los propietarios.
const fechaCorta = (iso) => new Date(`${iso}T12:00:00`).toLocaleDateString(locale(), { day: "numeric", month: "long", year: "numeric" });

function modalVerificarActa(r) {
  modal("Verificación de integridad", h("div", {},
    h("div", { class: `asm-resumen ${r.ok ? "ok" : "mal"}` }, h("b", {}, r.ok ? "El acta no ha sido alterada" : "¡Se detectó una alteración!"),
      h("p", { class: "small" }, r.ok ? "Todo coincide con lo que se congeló al sellar el acta." : "Alguien modificó información después de sellar el acta. Revisa lo marcado abajo y la base de datos antes de publicar.")),
    ...r.comprobaciones.map((c) => h("p", {}, h("span", { class: `badge ${c.ok ? "bosque" : "arcilla"}` }, c.ok ? "Correcto" : "Falló"), " ", h("b", {}, c.nombre), h("br"), h("span", { class: "small muted" }, c.detalle))),
    h("p", { class: "small muted" }, "Huella del acta (SHA-256): ", h("code", {}, r.huella))));
}

function modalSubirFirmada(a, reemplaza, alHecho) {
  const archivo = h("input", { id: "af-arch", type: "file", accept: "application/pdf" });
  const ok = h("button", { class: "btn", type: "submit", form: "f-firmada" }, icono("subir", 16), reemplaza ? "Reemplazar copia" : "Subir copia");
  const m = modal("Copia firmada del acta", h("form", { id: "f-firmada", novalidate: true, onsubmit: async (e) => {
    e.preventDefault();
    if (!archivo.files[0]) return toast("Adjunta el PDF escaneado con las firmas.", "error");
    const fd = new FormData(); fd.append("archivo", archivo.files[0]);
    try { await conCarga(ok, () => api(`/asambleas/${a.id}/acta/firmada`, { metodo: "POST", cuerpo: fd })); m.cerrar(); toast("Copia firmada guardada."); alHecho(); }
    catch (err) { toast(err.message, "error"); }
  } },
    h("p", { class: "small muted" }, "Imprime el acta definitiva, que la firmen el presidente y el secretario, escanéala y súbela aquí (PDF). Se guarda su huella SHA-256 en la bitácora. Puedes reemplazarla mientras el acta no esté publicada."),
    h("div", { class: "field archivo" }, h("label", { for: "af-arch", class: "fija" }, "PDF firmado"), archivo)),
  { pie: [h("button", { class: "btn suave", onclick: () => m.cerrar() }, "Cancelar"), ok] });
}

async function panelActa(a, recargar) {
  const caja = h("div", {});
  async function cargar() {
    let t;
    try { t = await api(`/asambleas/${a.id}/acta`); } catch (e) { return caja.replaceChildren(estadoVacio("No se pudo abrir el acta", e.message)); }
    const sellada = t.estado === "Sellada", cerrada = a.estado === "Cerrada";
    const paso = (hecho, texto) => h("li", { class: `asm-paso${hecho ? " hecho" : ""}` }, h("span", { class: `badge ${hecho ? "bosque" : ""}` }, hecho ? "Listo" : "Pendiente"), " ", texto);
    const recargarActa = () => cargar();
    const accion = (texto, ruta, { titulo, aviso, ok, peligro = false, clase = "", alVolver } = {}) => h("button", { class: `btn sm ${clase}`, onclick: async (e) => {
      const btn = e.currentTarget;
      if (titulo && !(await confirmar(titulo, aviso, ok ?? "Sí, continuar", peligro))) return;
      try { await conCarga(btn, () => api(ruta, { metodo: "POST" })); toast("Listo."); (alVolver ?? recargarActa)(); } catch (err) { toast(err.message, "error"); }
    } }, texto);

    const partes = [
      h("div", { class: `asm-resumen ${t.publicada ? "ok" : t.plazo_vencido ? "mal" : ""}` },
        h("b", {}, t.publicada ? "Acta publicada a los propietarios" : sellada ? "Acta sellada: falta firmarla y publicarla" : "Acta en borrador"),
        h("p", { class: "small" }, `Plazo para ponerla a disposición de los propietarios: ${fechaCorta(t.limite_publicacion)} (20 días hábiles desde la fecha de la reunión, Art. 47 de la Ley 675 de 2001).`)),
      t.advertencias?.length ? h("div", { class: "asm-resumen mal" }, h("ul", { class: "lista-simple" }, t.advertencias.map((w) => h("li", {}, w)))) : null,
      h("ol", { class: "asm-pasos" },
        paso(cerrada, "Cerrar la asamblea (queda congelada la reunión: asistentes y votaciones)"),
        paso(Boolean(t.presidente_nombre && t.secretario_nombre && t.desarrollo), "Completar presidente, secretario y desarrollo de la reunión"),
        paso(sellada, "Sellar el acta (se congela con su huella SHA-256)"),
        paso(t.tiene_firmada, "Subir la copia firmada por el presidente y el secretario"),
        paso(t.publicada, "Publicar el acta a los propietarios")),
    ];

    if (!sellada) {
      const f = {
        pres: h("input", { id: "ac-pres", placeholder: " ", maxlength: "120", value: t.presidente_nombre ?? "" }),
        sec: h("input", { id: "ac-sec", placeholder: " ", maxlength: "120", value: t.secretario_nombre ?? "" }),
        com: h("input", { id: "ac-com", placeholder: " ", maxlength: "500", value: t.comision ?? "" }),
        des: h("textarea", { id: "ac-des", placeholder: " ", rows: "10", maxlength: "20000" }),
      };
      f.des.value = t.desarrollo ?? "";
      const cuerpo = () => ({ presidente_nombre: f.pres.value, secretario_nombre: f.sec.value, comision: f.com.value, desarrollo: f.des.value });
      const guardar = () => api(`/asambleas/${a.id}/acta`, { metodo: "PUT", json: cuerpo() });
      const btnGuardar = h("button", { class: "btn", type: "button", onclick: async (e) => {
        try { await conCarga(e.currentTarget, guardar); toast("Borrador guardado."); recargarActa(); } catch (err) { toast(err.message, "error"); }
      } }, icono("editar", 16), "Guardar borrador");
      partes.push(h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Datos del acta")),
        h("p", { class: "small muted" }, "El acta indica la clase de asamblea, la convocatoria, el orden del día, los asistentes con su coeficiente y los votos emitidos: eso la aplicación lo toma solo de lo registrado. Tú completas quién presidió, quién fue secretario y qué se discutió y decidió."),
        campo("ac-pres", "Presidente de la reunión", f.pres), campo("ac-sec", "Secretario de la reunión", f.sec),
        campo("ac-com", "Comisión verificadora de la redacción del acta (si se designó)", f.com),
        campo("ac-des", "Desarrollo del orden del día y decisiones adoptadas", f.des),
        h("div", { class: "acciones-fila" }, btnGuardar,
          h("button", { class: "btn suave", type: "button", onclick: async (e) => {
            const btn = e.currentTarget;
            try { await guardar(); await descargar(btn, `/asambleas/${a.id}/acta/borrador.pdf`, `acta-borrador-${a.id}.pdf`); } catch (err) { toast(err.message, "error"); }
          } }, icono("descarga", 16), "Descargar borrador (PDF)"))));
      partes.push(h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Sellar el acta")),
        cerrada ? h("p", { class: "small muted" }, "Cuando el borrador esté completo, séllalo. Se guarda una copia congelada con su huella SHA-256 y queda en la bitácora. No se puede deshacer: después no cambia ni el texto ni la evidencia.")
          : h("p", { class: "small muted" }, "Podrás sellarla cuando cierres la asamblea. Mientras la reunión sigue, puedes ir redactando el borrador."),
        t.motivo_no_sellar && cerrada ? h("p", { class: "small texto-error" }, t.motivo_no_sellar) : null,
        h("div", { class: "acciones-fila" }, h("button", { class: "btn", type: "button", disabled: !t.puede_sellar, onclick: async (e) => {
          const btn = e.currentTarget;
          if (!(await confirmar("¿Sellar el acta?", "Se congela todo el contenido con su huella SHA-256. No se puede deshacer ni editar después. Se guardarán primero los cambios que tengas en pantalla.", "Sí, sellar", true))) return;
          try { await conCarga(btn, async () => { await guardar(); await api(`/asambleas/${a.id}/acta/sellar`, { metodo: "POST" }); }); toast("Acta sellada."); recargarActa(); } catch (err) { toast(err.message, "error"); }
        } }, "Sellar el acta"))));
    } else {
      partes.push(
        h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Acta sellada"), badge(t.publicada ? "Publicada" : "Sellada")),
          h("p", { class: "small muted" }, `Sellada el ${fmtFechaHora(deUtc(t.sellada_en))}. Huella (SHA-256): `, h("code", {}, t.contenido_hash)),
          t.tiene_firmada ? h("p", { class: "small muted" }, `Copia firmada subida el ${fmtFechaHora(deUtc(t.firmada_en))}.`) : null,
          t.publicada ? h("p", { class: "small muted" }, `Publicada el ${fmtFechaHora(deUtc(t.publicada_en))}.`) : null,
          h("div", { class: "acciones-fila" },
            h("button", { class: "btn sm", onclick: (e) => descargar(e.currentTarget, `/asambleas/${a.id}/acta.pdf`, `acta-asamblea-${a.id}.pdf`) }, icono("descarga", 16), "Acta definitiva (PDF)"),
            !t.publicada ? h("button", { class: "btn suave sm", onclick: () => modalSubirFirmada(a, t.tiene_firmada, recargarActa) }, icono("subir", 16), t.tiene_firmada ? "Reemplazar copia firmada" : "Subir copia firmada") : null,
            t.tiene_firmada ? h("button", { class: "btn suave sm", onclick: (e) => verArchivo(e.currentTarget, `/asambleas/${a.id}/acta/firmada`, `acta-firmada-${a.id}`) }, icono("archivo", 16), "Ver copia firmada") : null,
            h("button", { class: "btn suave sm", onclick: async (e) => { try { modalVerificarActa(await conCarga(e.currentTarget, () => api(`/asambleas/${a.id}/acta/verificar`))); } catch (err) { toast(err.message, "error"); } } }, "Verificar integridad"),
            !t.publicada ? accion("Publicar a los propietarios", `/asambleas/${a.id}/acta/publicar`, { titulo: "¿Publicar el acta?", ok: "Sí, publicar",
              aviso: t.tiene_firmada ? "Se avisará a los propietarios y podrán descargar el acta y la copia firmada. Después ya no se podrá cambiar la copia firmada." : "Todavía no subiste la copia firmada. Si publicas ahora, los propietarios verán el acta sin firmas y ya no podrás reemplazar la copia. ¿Continuar?" }) : null)),
        h("div", { class: "card" }, h("div", { class: "card-titulo" }, h("h2", {}, "Dignatarios y desarrollo")),
          h("p", {}, h("b", {}, "Presidente: "), t.presidente_nombre ?? "—"), h("p", {}, h("b", {}, "Secretario: "), t.secretario_nombre ?? "—"),
          t.comision ? h("p", {}, h("b", {}, "Comisión verificadora: "), t.comision) : null,
          t.desarrollo ? h("p", { style: "white-space:pre-wrap" }, t.desarrollo) : h("p", { class: "muted" }, "Sin desarrollo redactado.")));
    }
    poner(caja, partes);
  }
  await cargar();
  return caja;
}

/** Residente: el acta aparece cuando el administrador la publica (Art. 47: máximo 20 días hábiles después de la reunión). */
function tarjetaActa(a) {
  const caja = h("div", {});
  api(`/asambleas/${a.id}/acta`).then((t) => caja.replaceChildren(h("div", { class: "card" },
    h("div", { class: "card-titulo" }, h("h2", {}, "Acta de la asamblea"), badge("Publicada")),
    h("p", { class: "small muted" }, `Publicada el ${fmtFechaHora(deUtc(t.publicada_en))}. Huella de verificación: `, h("code", {}, t.contenido_hash.slice(0, 16))),
    h("div", { class: "acciones-fila" },
      h("button", { class: "btn sm", onclick: (e) => descargar(e.currentTarget, `/asambleas/${a.id}/acta.pdf`, `acta-asamblea-${a.id}.pdf`) }, icono("descarga", 16), "Descargar el acta (PDF)"),
      t.tiene_firmada ? h("button", { class: "btn suave sm", onclick: (e) => verArchivo(e.currentTarget, `/asambleas/${a.id}/acta/firmada`, `acta-firmada-${a.id}`) }, icono("archivo", 16), "Ver copia firmada") : null))))
    .catch((e) => { if (/publicad/i.test(e.message)) caja.replaceChildren(h("p", { class: "small muted" }, "El acta de esta asamblea aún no ha sido publicada. La administración debe ponerla a disposición dentro de los 20 días hábiles siguientes a la reunión.")); });
  return caja;
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
    const opciones = [{ id: "resumen", texto: "Resumen" }, { id: "asistencia", texto: "Asistencia" }, { id: "votaciones", texto: "Votaciones" }, { id: "poderes", texto: "Poderes" }, { id: "entregas", texto: "Entregas" }, { id: "acta", texto: "Acta" }, { id: "bitacora", texto: "Bitácora" }]
      .filter((o) => (a.estado !== "Borrador" || o.id === "resumen") && (o.id !== "acta" || ["En sesión", "Cerrada"].includes(a.estado)));
    const pintar = async (p) => {
      pestana = p;
      cuerpo.replaceChildren(esqueleto(80, 3));
      if (p === "resumen") poner(cuerpo, bloqueInfo(a), accionesAdmin(a, recargar, volver), bloqueOrden(a, true, recargar),
        a.morosos?.length ? h("div", { class: "card" }, h("div", { class: "etiqueta-seccion", style: "margin-top:0" }, `Unidades en mora al convocar (${a.morosos.length})`), h("ul", { class: "lista-simple" }, a.morosos.map((m) => h("li", {}, `${m.apartamento} · $ ${Number(m.saldo).toLocaleString(locale())}`)))) : null);
      else if (p === "asistencia") cuerpo.replaceChildren(await panelAsistencia(a, true, recargar));
      else if (p === "votaciones") cuerpo.replaceChildren(await panelVotaciones(a, recargar));
      else if (p === "poderes") cuerpo.replaceChildren(await panelPoderes(a, true, recargar));
      else if (p === "entregas") cuerpo.replaceChildren(await panelEntregas(a, recargar));
      else if (p === "acta") cuerpo.replaceChildren(await panelActa(a, recargar));
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
