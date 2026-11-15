// Carga masiva desde Excel/CSV (solo administrador): censo de residentes y cartera mensual.
// Flujo: 1) descargar la plantilla · 2) subir el archivo y REVISAR (vista previa: no guarda nada) · 3) importar.
// Endpoints: GET /importaciones/plantilla/{tipo} · POST /importaciones/{tipo}/vista-previa · POST /importaciones/{tipo}/aplicar?omitir_errores=
import { api } from "../api.js";
import { h, icono, badge, kpi, estadoVacio, toast, conCarga, confirmar, dinero } from "../ui.js";
import { cabecera, filtros } from "./comun.js";
import { descargar, guardarBlob, hoyArchivo, tamanoLegible } from "../descargas.js";

const TIPOS = {
  residentes: {
    nombre: "Censo de residentes", icono: "usuarios", plantilla: "plantilla_residentes.xlsx",
    que: "Crea de una vez las cuentas de todos los residentes (con una clave temporal) y actualiza los datos de los que ya existen.",
    pasos: ["Descarga la plantilla y llénala: nombre, correo y apartamento (parqueadero y cuota son opcionales).", "Súbela y revisa la vista previa: verás cuántas cuentas se crean y qué filas tienen errores.",
      "Al importar, descarga las claves temporales y entrégalas a cada residente. Deberán cambiarlas al ingresar."],
  },
  cartera: {
    nombre: "Cartera mensual", icono: "tarjeta", plantilla: "plantilla_cartera.xlsx",
    que: "Actualiza el saldo de cada apartamento con lo que dice tu software contable (Siigo, World Office, Alegra…). Saldo mayor a 0 = en mora; 0 = al día.",
    pasos: ["Exporta la cartera de tu software contable a Excel o CSV (o usa nuestra plantilla): basta con una columna de correo o apartamento y una de saldo.",
      "Súbela y revisa la vista previa: verás quién entra o sale de mora y qué filas no se reconocen.", "Los apartamentos que no estén en el archivo no se tocan."],
  },
};
const ACCION = { crear: ["Nuevo", "bosque"], actualizar: ["Actualiza", "violeta"], sin_cambios: ["Sin cambios", "borde"], error: ["Error", "laton"] };

// Los textos que empiezan por = + - @ se neutralizan para que Excel nunca los lea como fórmulas.
const celdaCsv = (v) => { let t = String(v ?? ""); if (/^[=+\-@\t\r]/.test(t)) t = `'${t}`; return `"${t.replace(/"/g, '""')}"`; };
const csvDeClaves = (lista) => `\uFEFF${["Nombre;Correo;Apartamento;Clave temporal", ...lista.map((c) => [c.nombre_completo, c.email, c.apartamento, c.clave_temporal].map(celdaCsv).join(";"))].join("\r\n")}\r\n`;

export async function render() {
  let tipo = "residentes", archivo = null, previa = null, resultado = null, filtro = "todo";
  const raiz = h("div", {});

  const entrada = h("input", { type: "file", id: "archivo-importar", accept: ".xlsx,.csv,.txt", class: "oculto-visual", onchange: (e) => {
    archivo = e.target.files[0] ?? null; previa = null; resultado = null; pintar();
  } });

  function cambiarTipo(t) { tipo = t; archivo = null; previa = null; resultado = null; filtro = "todo"; entrada.value = ""; pintar(); }
  const formData = () => { const fd = new FormData(); fd.append("archivo", archivo, archivo.name); return fd; };

  async function revisar(boton) {
    try { previa = await conCarga(boton, () => api(`/importaciones/${tipo}/vista-previa`, { metodo: "POST", cuerpo: formData(), timeout: 60000 })); filtro = previa.errores ? "error" : "todo"; pintar(); }
    catch (err) { toast(err.message, "error"); }
  }

  async function importar(boton) {
    const validas = previa.crear + previa.actualizar;
    const texto = tipo === "residentes"
      ? `Se crearán ${previa.crear} cuenta${previa.crear === 1 ? "" : "s"} y se actualizarán ${previa.actualizar}.${previa.errores ? ` Se omitirán ${previa.errores} fila(s) con errores.` : ""}`
      : `Se actualizará el saldo de ${previa.actualizar} apartamento${previa.actualizar === 1 ? "" : "s"}.${previa.errores ? ` Se omitirán ${previa.errores} fila(s) con errores.` : ""} Quienes queden con saldo mayor a 0 no podrán reservar zonas comunes.`;
    if (!validas && !previa.sin_cambios) return toast("No hay filas válidas para importar.", "error");
    if (!(await confirmar("¿Importar ahora?", texto, "Sí, importar"))) return;
    try {
      resultado = await conCarga(boton, () => api(`/importaciones/${tipo}/aplicar`, { metodo: "POST", cuerpo: formData(), params: { omitir_errores: previa.errores > 0 }, timeout: 90000 }));
      archivo = null; previa = null; entrada.value = ""; pintar();
      toast("Importación terminada.");
    } catch (err) { toast(err.message, "error"); }
  }

  const bloqueTipos = () => filtros(Object.entries(TIPOS).map(([id, t]) => ({ id, texto: t.nombre })), tipo, cambiarTipo);

  function pasoArchivo() {
    const t = TIPOS[tipo];
    return h("div", { class: "card" },
      h("div", { class: "card-titulo" }, h("h2", {}, t.nombre)),
      h("p", { style: "margin-bottom:.6rem" }, t.que),
      h("ol", { class: "pasos-importar" }, t.pasos.map((p) => h("li", {}, p))),
      h("div", { class: "acciones-fila", style: "margin-top:.8rem" },
        h("button", { class: "btn suave", onclick: (e) => descargar(e.currentTarget, `/importaciones/plantilla/${tipo}`, t.plantilla) }, icono("descarga", 16), "Descargar plantilla"),
        h("label", { class: "btn suave", for: "archivo-importar" }, icono("subir", 16), archivo ? "Cambiar archivo" : "Elegir archivo"),
        archivo ? h("button", { class: "btn", onclick: (e) => revisar(e.currentTarget) }, icono("ojo", 16), "Revisar archivo") : null),
      archivo ? h("p", { class: "small", style: "margin-top:.6rem" }, icono("archivo", 14), ` ${archivo.name} · ${tamanoLegible(archivo.size)}`)
              : h("p", { class: "small muted", style: "margin-top:.6rem" }, "Acepta Excel (.xlsx) o CSV, hasta 1.000 filas y 2 MB. Primero solo se revisa: no se guarda nada."));
  }

  function vistaPrevia() {
    const p = previa, validas = p.crear + p.actualizar;
    const lista = p.filas.filter((f) => (filtro === "todo" ? true : filtro === "error" ? f.accion === "error" : f.accion === "crear" || f.accion === "actualizar"));
    const cuerpo = h("tbody", {}, lista.map((f) => {
      const [txt, clase] = ACCION[f.accion];
      const detalle = tipo === "cartera" && f.accion !== "error" ? `${dinero(f.saldo_anterior)} → ${dinero(f.saldo_nuevo)}` : f.mensaje;
      return h("tr", {},
        h("td", { "data-et": "Fila" }, String(f.fila)),
        h("td", { "data-et": "Resultado" }, h("span", { class: `badge ${clase}` }, txt)),
        h("td", { class: "ancho", "data-et": "Persona" }, h("div", {}, h("b", {}, f.nombre || f.email || f.apartamento || "—"), h("span", { class: "small muted", style: "display:block" }, [f.email, f.apartamento].filter((x) => x && x !== f.nombre).join(" · ")))),
        h("td", { "data-et": "Detalle", class: f.accion === "error" ? "texto-error" : "" }, detalle || "—"));
    }));
    return h("div", { class: "card" },
      h("div", { class: "card-titulo" }, h("h2", {}, "Vista previa"), h("span", { class: "small muted" }, p.archivo)),
      h("div", { class: "kpis" }, kpi("Filas leídas", p.total), tipo === "residentes" ? kpi("Cuentas nuevas", p.crear, { destacado: true }) : kpi("Saldos a actualizar", p.actualizar, { destacado: true }),
        tipo === "residentes" ? kpi("A actualizar", p.actualizar) : kpi("Sin cambios", p.sin_cambios), kpi("Con errores", p.errores, { alerta: true })),
      p.errores ? h("div", { class: "aviso", style: "margin-bottom:.8rem" }, icono("alerta"), h("div", {}, `${p.errores} fila(s) tienen errores y NO se importarán. Corrige el archivo y vuelve a subirlo, o importa solo las ${validas} fila(s) válidas.`)) : null,
      filtros([{ id: "todo", texto: "Todas", n: p.filas.length }, { id: "error", texto: "Errores", n: p.errores }, { id: "cambios", texto: "Cambios", n: validas }], filtro, (f) => { filtro = f; pintar(); }),
      lista.length ? h("div", { class: "tabla-wrap", style: "margin-top:.6rem" }, h("table", { class: "tabla" },
        h("thead", {}, h("tr", {}, h("th", {}, "Fila"), h("th", {}, "Resultado"), h("th", {}, "Persona"), h("th", {}, "Detalle"))), cuerpo)) : estadoVacio("Nada en este filtro", "Cambia el filtro para ver las demás filas."),
      p.filas_omitidas ? h("p", { class: "small muted" }, `Se muestran las primeras filas; ${p.filas_omitidas} más válidas no se listan pero sí se importarán.`) : null,
      h("div", { class: "acciones-fila", style: "margin-top:1rem" },
        validas || p.sin_cambios ? h("button", { class: "btn", onclick: (e) => importar(e.currentTarget) }, p.errores ? `Importar solo las ${validas} filas válidas` : "Importar ahora") : null,
        h("button", { class: "btn suave", onclick: () => { archivo = null; previa = null; entrada.value = ""; pintar(); } }, "Cancelar")));
  }

  function vistaResultado() {
    const r = resultado, claves = r.credenciales ?? [];
    return h("div", { class: "card" },
      h("div", { class: "card-titulo" }, h("h2", {}, "Importación terminada")),
      h("div", { class: "aviso ok", style: "margin-bottom:.8rem" }, icono("ok"), h("div", {},
        tipo === "residentes" ? `Se crearon ${r.crear} cuenta(s) y se actualizaron ${r.actualizar}.` : `Se actualizaron ${r.actualizar} saldo(s): ${r.entraron_en_mora} entraron en mora y ${r.salieron_de_mora} quedaron al día.`,
        r.errores ? ` ${r.errores} fila(s) se omitieron por errores.` : "")),
      claves.length ? h("div", {},
        h("div", { class: "aviso", style: "margin-bottom:.8rem" }, icono("alerta"), h("div", {}, h("b", {}, "Claves temporales: se muestran UNA sola vez. "), "Descárgalas ahora y entrégalas a cada residente de forma privada. Cada persona debe cambiar su clave al ingresar. Borra el archivo cuando termines.")),
        h("div", { class: "acciones-fila" },
          h("button", { class: "btn", onclick: () => guardarBlob(new Blob([csvDeClaves(claves)], { type: "text/csv;charset=utf-8" }), `claves_temporales_${hoyArchivo()}.csv`) }, icono("descarga", 16), `Descargar ${claves.length} clave(s) en CSV`),
          h("button", { class: "btn suave", onclick: async () => { if (await confirmar("¿Ocultar las claves?", "Después de ocultarlas ya no se pueden volver a ver (tendrías que usar «Restablecer clave» en Usuarios).", "Sí, ocultar", true)) { resultado.credenciales = []; pintar(); } } }, "Ya las descargué, ocultar")),
        h("div", { class: "tabla-wrap", style: "margin-top:.8rem" }, h("table", { class: "tabla" },
          h("thead", {}, h("tr", {}, h("th", {}, "Residente"), h("th", {}, "Apartamento"), h("th", {}, "Clave temporal"))),
          h("tbody", {}, claves.map((c) => h("tr", {}, h("td", { class: "ancho", "data-et": "Residente" }, h("b", {}, c.nombre_completo), h("span", { class: "small muted", style: "display:block" }, c.email)),
            h("td", { "data-et": "Apartamento" }, c.apartamento ?? "—"), h("td", { "data-et": "Clave" }, h("code", { class: "mono" }, c.clave_temporal))))))))
        : null,
      h("div", { class: "acciones-fila", style: "margin-top:1rem" },
        tipo === "residentes" ? h("a", { class: "btn suave", href: "#/residentes" }, "Ver usuarios", icono("flecha", 16)) : h("a", { class: "btn suave", href: "#/cartera" }, "Ver cartera", icono("flecha", 16)),
        h("button", { class: "btn suave", onclick: () => { resultado = null; pintar(); } }, "Importar otro archivo")));
  }

  function pintar() {
    raiz.replaceChildren(bloqueTipos(), h("div", { style: "height:.8rem" }), resultado ? vistaResultado() : pasoArchivo(), previa && !resultado ? vistaPrevia() : null, entrada);
  }
  pintar();
  return h("div", {}, cabecera("Cargar datos desde Excel", "Sube el censo de apartamentos o la cartera del mes sin digitar uno por uno."), raiz);
}
