// Marca del cliente (white-label, v4.0). El servidor la escribe en <meta name="marca"> al entregar la página; aquí solo se lee.
// Sin la etiqueta (o con datos dañados) se usan los valores de siempre: la app jamás se queda sin nombre.
const POR_DEFECTO = { nombre: "Ciudadela Digital", corto: "Ciudadela", eslogan: "Tu conjunto, siempre en orden.", descripcion: "", conjunto: "Ciudadela Digital",
  asistente: "Ciudabot", color: "", tema_claro: "#07304A", tema_oscuro: "#06122B", landing: false };

function leer() {
  try { return { ...POR_DEFECTO, ...JSON.parse(document.querySelector('meta[name="marca"]')?.content ?? "{}") }; } catch { return { ...POR_DEFECTO }; }
}

export const marca = leer();
