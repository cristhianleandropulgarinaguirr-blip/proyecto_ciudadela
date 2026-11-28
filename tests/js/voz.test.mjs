// Pruebas del dictado por voz (v5.8): qué campos se pueden dictar y cómo se arma el texto. El navegador real se prueba a mano (ver PASOS_V5.8.md).
import test from "node:test";
import assert from "node:assert/strict";

Object.defineProperty(globalThis, "navigator", { value: { userAgent: "node" }, configurable: true });      // en Node 22 `navigator` es de solo lectura
globalThis.localStorage = { getItem: () => "es", setItem() {} };
globalThis.document = { documentElement: {}, body: null, title: "", getElementById: () => null };      // ui.js busca el <dialog> al cargarse
globalThis.SpeechRecognition = class {};                       // para que el módulo se considere disponible
const { campoDictable, componerDictado, vozDisponible } = await import("../../frontend/js/voz.js");

const campo = (tagName, props = {}) => ({ tagName, type: props.type ?? "text", disabled: false, readOnly: false, hidden: false,
  name: props.name ?? "", id: props.id ?? "", placeholder: props.placeholder ?? "",
  hasAttribute: (a) => a in (props.attrs ?? {}), getAttribute: (a) => (props.attrs ?? {})[a] ?? null });

test("se puede dictar en textos libres y no en campos sensibles", () => {
  assert.equal(vozDisponible(), true);
  assert.equal(campoDictable(campo("TEXTAREA")), true);
  assert.equal(campoDictable(campo("INPUT", { type: "text", id: "titulo" })), true);
  assert.equal(campoDictable(campo("INPUT", { type: "search" })), true);
  for (const type of ["password", "email", "tel", "number", "date", "url", "file", "checkbox"]) assert.equal(campoDictable(campo("INPUT", { type })), false, type);
  for (const nombre of ["clave", "password", "pin", "codigo", "cedula", "documento", "telefono", "correo", "placa", "tarjeta", "referencia"])
    assert.equal(campoDictable(campo("INPUT", { type: "text", name: nombre })), false, nombre);
  assert.equal(campoDictable(campo("INPUT", { attrs: { autocomplete: "one-time-code" } })), false);
  assert.equal(campoDictable(campo("INPUT", { attrs: { inputmode: "numeric" } })), false);
  assert.equal(campoDictable(campo("TEXTAREA", { attrs: { "data-sin-voz": "" } })), false);          // exclusión manual
  assert.equal(campoDictable({ ...campo("TEXTAREA"), disabled: true }), false);
  assert.equal(campoDictable({ ...campo("TEXTAREA"), readOnly: true }), false);
  assert.equal(campoDictable(campo("SELECT")), false);
  assert.equal(campoDictable(null), false);
});

test("el texto dictado se arma bien: mayúscula inicial, espacios y lo que ya estaba escrito", () => {
  assert.deepEqual(componerDictado({ antes: "", despues: "", finales: "hay una gotera en el pasillo" }), { texto: "Hay una gotera en el pasillo", cursor: 28, truncado: false });
  assert.equal(componerDictado({ antes: "El ascensor", despues: "", finales: "no funciona" }).texto, "El ascensor no funciona");           // sin mayúscula a mitad de frase
  assert.equal(componerDictado({ antes: "Gotera en el piso 3. ", despues: "", finales: "es urgente" }).texto, "Gotera en el piso 3. Es urgente"); // sí tras un punto
  assert.equal(componerDictado({ antes: "Hola ", despues: "adiós", finales: "amigo" }).texto, "Hola amigo adiós");                       // inserta en el cursor, sin pegar palabras
  assert.equal(componerDictado({ antes: "", despues: "", finales: "primera", interino: "segunda" }).texto, "Primera segunda");          // lo provisional se ve mientras se habla
});

test("respeta el límite de caracteres del campo y avisa", () => {
  const r = componerDictado({ antes: "", despues: "", finales: "una frase demasiado larga para este campo", maximo: 10 });
  assert.equal(r.texto.length, 10); assert.equal(r.truncado, true); assert.equal(r.cursor, 10);
  assert.equal(componerDictado({ antes: "", despues: "", finales: "corto", maximo: 10 }).truncado, false);
});
