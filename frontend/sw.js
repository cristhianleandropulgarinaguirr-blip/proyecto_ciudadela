// Service worker de Ciudadela Digital (versión 3.0).
// Objetivo: que la app abra al instante y siga siendo segura con los datos.
//  - Archivos de la app (/app/…): se guardan TODOS al instalar y se sirven desde el celular (cache-first) → abre en milisegundos, incluso sin internet.
//    El servidor entrega este archivo con un código de versión calculado a partir de los archivos: si algo cambia, la versión cambia
//    y se instala una caché nueva completa (nunca se mezclan archivos viejos con nuevos).
//  - Fuentes de Google: caché «sirve lo guardado y actualiza en segundo plano».
//  - La API (/auth, /reservas, /paquetes…) NUNCA se guarda ni se intercepta: los datos de los residentes no se cachean.
const VERSION = "ciudadela-__VERSION__";
const ARCHIVOS = __ARCHIVOS__;
const CACHE_FUENTES = "ciudadela-fuentes";

self.addEventListener("install", (e) => {
  // «reload»: salta la caché HTTP del navegador para guardar siempre la copia fresca del servidor.
  e.waitUntil(caches.open(VERSION)
    .then((c) => c.addAll(ARCHIVOS.map((a) => new Request(a, { cache: "reload" }))))
    .then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves.filter((k) => k !== VERSION && k !== CACHE_FUENTES).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Fuentes de Google: sirve lo guardado y refresca en segundo plano.
  if (url.hostname === "fonts.googleapis.com" || url.hostname === "fonts.gstatic.com") {
    e.respondWith(caches.open(CACHE_FUENTES).then(async (c) => {
      const guardada = await c.match(req);
      const red = fetch(req).then((res) => { if (res.ok || res.type === "opaque") c.put(req, res.clone()); return res; }).catch(() => guardada);
      return guardada || red;
    }));
    return;
  }

  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith("/app/") || url.pathname.endsWith("/sw.js")) return;   // todo lo que no sea la app: sin tocar

  e.respondWith((async () => {
    const c = await caches.open(VERSION);
    // Navegación (abrir la app): siempre el «index» guardado, sea cual sea el #hash o la query.
    const guardada = await c.match(req.mode === "navigate" ? "./" : req, { ignoreSearch: true });
    if (guardada) return guardada;
    try {
      const res = await fetch(req);
      if (res.ok) c.put(req, res.clone());
      return res;
    } catch { return req.mode === "navigate" ? (await c.match("./")) || Response.error() : Response.error(); }
  })());
});
