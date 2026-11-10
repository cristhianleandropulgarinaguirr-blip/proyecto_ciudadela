// Service worker de Ciudadela Digital (versión 2.8).
// Objetivo: que la app se pueda INSTALAR y abra rápido, sin arriesgar datos viejos.
//  - Archivos de la app (/app/…): red primero (siempre la versión más nueva) y, si no hay internet, la copia guardada.
//  - La API (/auth, /reservas, /paquetes…) NUNCA se guarda ni se intercepta: los datos de los residentes no se cachean.
const VERSION = "ciudadela-2.8.0";
const BASICOS = ["./", "estilos.css", "js/app.js", "img/logo.png", "img/icono.png", "img/favicon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => c.addAll(BASICOS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then((claves) => Promise.all(claves.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;       // fuentes de Google, etc.: el navegador se encarga
  if (!url.pathname.startsWith("/app/") || url.pathname.endsWith("/sw.js")) return;   // todo lo que no sea la app: sin tocar

  e.respondWith(
    fetch(req).then((res) => {
      if (res.ok) { const copia = res.clone(); caches.open(VERSION).then((c) => c.put(req, copia)); }
      return res;
    }).catch(async () => (await caches.match(req)) || (req.mode === "navigate" ? caches.match("./") : Response.error()))
  );
});
