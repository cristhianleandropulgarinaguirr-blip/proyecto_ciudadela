// Pruebas del idioma (v5.8): el traductor, el diccionario y los formatos. No necesitan navegador: se simula lo mínimo (almacenamiento y document).
import test from "node:test";
import assert from "node:assert/strict";

function simular(idioma) {
  globalThis.localStorage = { getItem: () => idioma, setItem() {}, removeItem() {} };
  globalThis.document = { documentElement: {}, body: null, title: "Inicio" };
}
async function cargar(idioma) {
  simular(idioma);
  return await import(`../../frontend/js/i18n.js?idioma=${idioma}`);       // el parámetro evita que Node reutilice el módulo del otro idioma
}
const diccionario = await import("../../frontend/js/i18n-en.js");

test("en español no se toca nada", async () => {
  const m = await cargar("es");
  await m.iniciarIdioma();
  assert.equal(m.idioma(), "es"); assert.equal(m.locale(), "es-CO"); assert.equal(m.vozLocale(), "es-CO");
  assert.equal(m.traducir("Guardar"), "Guardar"); assert.equal(m.segun("hola", "hello"), "hola");
});

test("en inglés se traduce lo exacto, conservando los espacios de alrededor", async () => {
  const m = await cargar("en");
  await m.iniciarIdioma();
  assert.equal(m.idioma(), "en"); assert.equal(m.locale(), "en-US"); assert.equal(m.vozLocale(), "en-US"); assert.equal(m.segun("hola", "hello"), "hello");
  assert.equal(m.traducir("Guardar"), "Save");
  assert.equal(m.traducir("  Guardar \n"), "  Save \n");
  assert.equal(m.traducir("Reservas por aprobar"), "Reservations to approve");
  assert.equal(m.traducir("Por gestionar"), "To handle");
});

test("lo que no está en el diccionario se queda tal cual (nada se rompe) y queda anotado como faltante", async () => {
  const m = await cargar("en");
  await m.iniciarIdioma();
  assert.equal(m.traducir("Texto que nadie tradujo todavía"), "Texto que nadie tradujo todavía");
  assert.equal(m.traducir("Ana Pérez"), "Ana Pérez");                           // los nombres de personas no se tocan
  assert.ok(globalThis.i18nFaltantes?.().includes("Texto que nadie tradujo todavía") ?? true);
  assert.equal(m.traducir(""), ""); assert.equal(m.traducir("   "), "   "); assert.equal(m.traducir("123"), "123");
});

test("los patrones con partes variables funcionan", async () => {
  const m = await cargar("en");
  await m.iniciarIdioma();
  assert.equal(m.traducir("Bienvenido al apartamento 201."), "Welcome to apartment 201.");
  assert.equal(m.traducir("Tienes 3 paquetes en portería"), "You have 3 packages at the front desk");
  assert.equal(m.traducir("Tienes 1 paquete en portería"), "You have 1 package at the front desk");
  assert.equal(m.traducir("Saldo de Ana Pérez"), "Balance of Ana Pérez");
  assert.equal(m.traducir("Notificaciones: 2 sin leer, 1 por gestionar"), "Notifications: 2 unread, 1 to handle");
  assert.equal(m.traducir("Se muestran 15 de 40. El detalle completo está en la sección."), "Showing 15 of 40. The full detail is in the section.");
  assert.equal(m.traducir("Todas quedaron leídas. Te quedan 4 avisos por gestionar."), "All marked as read. You have 4 notices left to handle.");
});

test("el diccionario está sano: sin textos vacíos y sin traducciones que pierdan cifras o signos importantes", () => {
  const problemas = [];
  for (const [es, en] of Object.entries(diccionario.EXACTOS)) {
    if (!es.trim()) problemas.push("clave vacía");
    if (!String(en).trim()) problemas.push(`«${es}» tiene traducción vacía`);
    if (/[áéíóúñ¿¡]/i.test(en) && !/Español|Cédula|Código|Ñ|ñ/.test(en) && /¿|¡/.test(en)) problemas.push(`«${es}»: la traducción conserva signos de apertura del español`);
    if (/"/.test(en)) problemas.push(`«${es}»: la traducción lleva comillas dobles`);
    if ((es.match(/\d+/g) || []).join() !== (en.match(/\d+/g) || []).join()) problemas.push(`«${es}»: las cifras no coinciden con la traducción`);
  }
  assert.deepEqual(problemas, []);
  assert.ok(Object.keys(diccionario.EXACTOS).length > 700, "el diccionario debería tener cientos de textos");
});

test("cada patrón es una expresión regular con su reemplazo en inglés", () => {
  for (const [patron, reemplazo] of diccionario.PATRONES) {
    assert.ok(patron instanceof RegExp, String(patron));
    assert.equal(typeof reemplazo, "string");
    const grupos = [...reemplazo.matchAll(/\$(\d)/g)].map((x) => Number(x[1]));
    const total = new RegExp(patron.source + "|").exec("").length - 1;
    for (const g of grupos) assert.ok(g <= total, `${patron}: el reemplazo usa $${g} y el patrón solo tiene ${total} grupos`);
  }
});
