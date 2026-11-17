// Pruebas del botón «Atrás» (frontend/js/atras.js) con un historial de navegador simulado. Se corren con:  node --test tests/js/
import test from "node:test";
import assert from "node:assert/strict";
import { crearAtras } from "../../frontend/js/atras.js";

// Historial mínimo que se comporta como el del navegador: pila de entradas, pushState corta lo que había «adelante»,
// back() mueve el puntero y dispara «popstate» (de forma asíncrona, como el navegador).
function navegador() {
  const entradas = [{ url: "#/inicio", state: null }];
  let i = 0;
  const oyentes = [];
  const historia = {
    get state() { return entradas[i].state; },
    pushState(state, _t, url) { entradas.splice(i + 1); entradas.push({ url: url ?? entradas[i].url, state }); i++; },
    replaceState(state) { entradas[i].state = state; },
    back() { if (i > 0) { i--; queueMicrotask(() => oyentes.forEach((fn) => fn({ state: entradas[i].state }))); } },
  };
  return {
    historia, escuchar: (t, fn) => t === "popstate" && oyentes.push(fn),
    get url() { return entradas[i].url; }, get largo() { return entradas.length; }, get indice() { return i; },
    // el usuario navega a otra ruta (cambia el #hash): agrega una entrada con otra URL
    ir(url) { historia.pushState(null, "", url); },
    // el usuario pulsa «Atrás»
    async atras() { historia.back(); await new Promise((r) => setTimeout(r, 0)); },
  };
}
const nuevo = () => { const nav = navegador(); let t = 1000; return { nav, atras: crearAtras({ historia: nav.historia, escuchar: nav.escuchar, ahora: () => ++t }) }; };

test("Atrás cierra el modal y NO sale de la pantalla", async () => {
  const { nav, atras } = nuevo();
  nav.ir("#/reservas");
  let cerrado = 0;
  atras.abrir(() => cerrado++);
  assert.equal(atras.abiertas, 1);
  await nav.atras();
  assert.equal(cerrado, 1);
  assert.equal(atras.abiertas, 0);
  assert.equal(nav.url, "#/reservas");          // sigue en la misma pantalla
});

test("tras cerrar con Atrás, otro Atrás sí retrocede de pantalla (sin toques de más)", async () => {
  const { nav, atras } = nuevo();
  nav.ir("#/reservas");
  atras.abrir(() => {});
  await nav.atras();                            // cierra el modal
  await nav.atras();                            // ahora sí vuelve al inicio
  assert.equal(nav.url, "#/inicio");
});

test("cerrar con la «X» consume la entrada: el siguiente Atrás retrocede de pantalla de una vez", async () => {
  const { nav, atras } = nuevo();
  nav.ir("#/reservas");
  const capa = atras.abrir(() => {});
  capa.soltar();                                // cierre por «X» / tocar fuera / Escape
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(nav.url, "#/reservas");
  await nav.atras();
  assert.equal(nav.url, "#/inicio");
});

test("abrir y cerrar muchas veces no llena el historial de entradas", async () => {
  const { nav, atras } = nuevo();
  nav.ir("#/reservas");
  const base = nav.largo;
  for (let n = 0; n < 5; n++) { const c = atras.abrir(() => {}); c.soltar(); await new Promise((r) => setTimeout(r, 0)); }
  await nav.atras();
  assert.equal(nav.url, "#/inicio");
  assert.ok(nav.largo <= base + 1);
});

test("dos capas (chat y modal): Atrás cierra primero la de arriba y luego la otra", async () => {
  const { nav, atras } = nuevo();
  const orden = [];
  atras.abrir(() => orden.push("chat"));
  atras.abrir(() => orden.push("modal"));
  await nav.atras();
  assert.deepEqual(orden, ["modal"]);
  await nav.atras();
  assert.deepEqual(orden, ["modal", "chat"]);
  assert.equal(nav.url, "#/inicio");
});

test("si el modal se cierra y en el mismo instante se navega, no se devuelve a la persona a la pantalla anterior", async () => {
  const { nav, atras } = nuevo();
  const capa = atras.abrir(() => {});
  nav.ir("#/cartera");                          // el botón del modal navegó…
  capa.soltar();                                // …y luego se cerró el modal
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(nav.url, "#/cartera");           // se queda donde la persona fue
});

test("la entrada «fantasma» que quedó debajo se salta sola al retroceder", async () => {
  const { nav, atras } = nuevo();
  const capa = atras.abrir(() => {});
  nav.ir("#/cartera");
  capa.soltar();                                // quedó una entrada fantasma entre #/inicio y #/cartera
  await nav.atras();                            // un solo Atrás debe llevar a #/inicio
  assert.equal(nav.url, "#/inicio");
});

test("una capa que falla al cerrarse no traba el botón Atrás", async () => {
  const { nav, atras } = nuevo();
  atras.abrir(() => { throw new Error("capa rota"); });
  await nav.atras();
  assert.equal(atras.abiertas, 0);
});

test("al recargar con una capa abierta, el marcador viejo se borra", () => {
  const nav = navegador();
  nav.historia.pushState({ capaAtras: 5 }, "");
  crearAtras({ historia: nav.historia, escuchar: nav.escuchar });
  assert.equal(nav.historia.state, null);
});
