// Almacenamiento local (IndexedDB) para lo que NO cabe en localStorage: fotos, la cola de registros hechos sin internet
// y las copias de lectura de portería. Todo es «mejor esfuerzo»: si el navegador no lo permite (modo privado, cuota llena),
// las funciones devuelven null/[] y la app sigue funcionando como antes.
const NOMBRE = "ciudadela", VERSION = 1;
const TIENDAS = ["fotos", "cola", "snap"];
let abierta = null;

function abrir() {
  return (abierta ??= new Promise((ok, mal) => {
    if (!("indexedDB" in window)) return mal(new Error("sin IndexedDB"));
    const r = indexedDB.open(NOMBRE, VERSION);
    r.onupgradeneeded = () => { for (const t of TIENDAS) if (!r.result.objectStoreNames.contains(t)) r.result.createObjectStore(t); };
    r.onsuccess = () => { r.result.onversionchange = () => { r.result.close(); abierta = null; }; ok(r.result); };
    r.onerror = () => { abierta = null; mal(r.error); };
    r.onblocked = () => { abierta = null; mal(new Error("bloqueada")); };
  }));
}

async function tx(tienda, modo, fn) {
  const db = await abrir();
  return new Promise((ok, mal) => {
    const t = db.transaction(tienda, modo), s = t.objectStore(tienda);
    let salida;
    const req = fn(s);
    if (req) req.onsuccess = () => { salida = req.result; };
    t.oncomplete = () => ok(salida);
    t.onerror = () => mal(t.error);
    t.onabort = () => mal(t.error ?? new Error("abortada"));
  });
}

const seguro = (f, defecto) => async (...a) => { try { return await f(...a); } catch { return defecto; } };

export const almacen = {
  poner: seguro((tienda, clave, valor) => tx(tienda, "readwrite", (s) => s.put(valor, clave)).then(() => true), false),
  leer: seguro((tienda, clave) => tx(tienda, "readonly", (s) => s.get(clave)), null),
  borrar: seguro((tienda, clave) => tx(tienda, "readwrite", (s) => s.delete(clave)).then(() => true), false),
  contar: seguro((tienda) => tx(tienda, "readonly", (s) => s.count()), 0),
  /** Todas las entradas de una tienda, ordenadas por clave: [{ clave, valor }]. */
  todo: seguro(async (tienda) => {
    const db = await abrir();
    return new Promise((ok, mal) => {
      const filas = [], t = db.transaction(tienda, "readonly"), c = t.objectStore(tienda).openCursor();
      c.onsuccess = () => { const cur = c.result; if (cur) { filas.push({ clave: cur.key, valor: cur.value }); cur.continue(); } };
      t.oncomplete = () => ok(filas);
      t.onerror = () => mal(t.error);
    });
  }, []),
  vaciar: seguro((tienda) => tx(tienda, "readwrite", (s) => s.clear()).then(() => true), false),
};
