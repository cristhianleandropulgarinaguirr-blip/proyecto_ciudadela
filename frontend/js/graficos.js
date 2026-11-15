// Gráficos mínimos en SVG puro (sin librerías): pesan unos pocos KB en vez de los ~200 KB de una librería de gráficos y
// se pintan al instante. Los colores salen de clases CSS (.g-*) para que sigan el tema claro/oscuro y el color del rol.
// Cada función devuelve un nodo listo para insertar. Los textos se asignan con textContent (nunca innerHTML): son datos de la base.
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, texto) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (texto != null) n.textContent = texto;
  return n;
};
const envoltorio = (svg, descripcion) => {
  const caja = document.createElement("figure");
  caja.className = "grafico";
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", descripcion);
  caja.append(svg);
  return caja;
};

/** Barras horizontales con etiqueta a la izquierda y valor a la derecha. datos: [{ etiqueta, valor }] */
export function barrasHorizontales(datos, { formato = (n) => String(n), vacio = "Sin datos todavía" } = {}) {
  if (!datos.length) { const p = document.createElement("p"); p.className = "muted small"; p.textContent = vacio; return p; }
  const ancho = 360, fila = 30, izq = 112, der = 46;
  const max = Math.max(...datos.map((d) => d.valor), 1);
  const svg = el("svg", { viewBox: `0 0 ${ancho} ${datos.length * fila + 4}`, class: "g-svg" });
  datos.forEach((d, i) => {
    const y = i * fila + 2, largo = Math.max(2, Math.round(((ancho - izq - der) * d.valor) / max));
    svg.append(el("text", { x: 0, y: y + 17, class: "g-etiqueta" }, d.etiqueta.length > 17 ? `${d.etiqueta.slice(0, 16)}…` : d.etiqueta),
      el("rect", { x: izq, y: y + 4, width: ancho - izq - der, height: 16, rx: 5, class: "g-fondo" }),
      el("rect", { x: izq, y: y + 4, width: largo, height: 16, rx: 5, class: "g-barra" }),
      el("text", { x: ancho, y: y + 17, "text-anchor": "end", class: "g-valor" }, formato(d.valor)));
  });
  return envoltorio(svg, `Gráfico de barras: ${datos.map((d) => `${d.etiqueta} ${formato(d.valor)}`).join(", ")}`);
}

/** 24 barras verticales (una por hora). `resaltar` es el índice de la hora pico. */
export function barrasPorHora(valores, { resaltar = null } = {}) {
  const ancho = 360, alto = 130, base = 104, arriba = 8, paso = ancho / 24;
  const max = Math.max(...valores, 1);
  const svg = el("svg", { viewBox: `0 0 ${ancho} ${alto}`, class: "g-svg" });
  svg.append(el("line", { x1: 0, x2: ancho, y1: base, y2: base, class: "g-eje" }));
  valores.forEach((v, h) => {
    const largo = v ? Math.max(3, Math.round(((base - arriba) * v) / max)) : 0;
    const g = el("g");
    g.append(el("title", {}, `${String(h).padStart(2, "0")}:00 · ${v} ingreso${v === 1 ? "" : "s"}`),
      el("rect", { x: h * paso + 2, y: base - largo, width: paso - 4, height: largo, rx: 2.5, class: h === resaltar ? "g-barra pico" : "g-barra" }));
    svg.append(g);
    if (h % 3 === 0) svg.append(el("text", { x: h * paso + paso / 2, y: base + 16, "text-anchor": "middle", class: "g-eje-texto" }, String(h)));
  });
  const pico = resaltar != null ? ` Hora pico: ${resaltar}:00.` : "";
  return envoltorio(svg, `Ingresos de visitantes por hora del día, de 0 a 23.${pico}`);
}

/** Dona con un número grande al centro. partes: [{ etiqueta, valor, clase }] (clase: "g-p1" | "g-p2" | "g-p3"). */
export function dona(partes, { centro = "", subcentro = "" } = {}) {
  const r = 52, c = 2 * Math.PI * r, total = partes.reduce((s, p) => s + p.valor, 0);
  const svg = el("svg", { viewBox: "0 0 140 140", class: "g-svg g-dona" });
  svg.append(el("circle", { cx: 70, cy: 70, r, class: "g-fondo-anillo" }));
  let acumulado = 0;
  if (total > 0) {
    for (const p of partes.filter((x) => x.valor > 0)) {
      const largo = (p.valor / total) * c;
      svg.append(el("circle", { cx: 70, cy: 70, r, class: `g-anillo ${p.clase}`, "stroke-dasharray": `${largo} ${c - largo}`, "stroke-dashoffset": String(-acumulado), transform: "rotate(-90 70 70)" }));
      acumulado += largo;
    }
  }
  svg.append(el("text", { x: 70, y: 74, "text-anchor": "middle", class: "g-centro" }, centro), el("text", { x: 70, y: 92, "text-anchor": "middle", class: "g-subcentro" }, subcentro));
  return envoltorio(svg, `Gráfico circular: ${partes.map((p) => `${p.etiqueta} ${p.valor}`).join(", ")}`);
}

/** Leyenda (lista de colores) para acompañar a la dona. */
export function leyenda(partes) {
  const ul = document.createElement("ul");
  ul.className = "g-leyenda";
  for (const p of partes) {
    const li = document.createElement("li");
    const punto = document.createElement("i"); punto.className = `g-punto ${p.clase}`;
    const t = document.createElement("span"); t.textContent = `${p.etiqueta}: `;
    const b = document.createElement("b"); b.textContent = p.texto ?? String(p.valor);
    li.append(punto, t, b); ul.append(li);
  }
  return ul;
}
