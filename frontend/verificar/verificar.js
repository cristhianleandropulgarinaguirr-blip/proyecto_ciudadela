// Página pública de verificación del paz y salvo (/verificar/<codigo>). Un solo archivo, sin librerías.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const partes = location.pathname.split("/").filter(Boolean);
  const codigo = partes[0] === "verificar" ? partes[1] : "";

  const ESTADOS = {
    Vigente: ["ok", "✓", "Documento válido", "Este paz y salvo es auténtico y está vigente."],
    Vencido: ["aviso", "!", "Documento vencido", "Es auténtico, pero ya pasó su fecha de validez. Pide uno nuevo."],
    "No vigente": ["mal", "✕", "Documento no vigente", "Este documento ya no es válido. Confirma con la administración del conjunto."],
  };
  const fecha = (iso, conHora) => {
    if (!iso) return "—";
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);   // el servidor guarda UTC sin zona
    return d.toLocaleString("es-CO", conHora ? { day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit" } : { day: "numeric", month: "long", year: "numeric" });
  };

  function error(titulo, texto) {
    $("tarjeta").hidden = true; $("error").hidden = false; $("conjunto").textContent = "Paz y salvo";
    if (titulo) $("error-titulo").textContent = titulo;
    if (texto) $("error-texto").textContent = texto;
  }

  function pintar({ conjunto, documento: d }) {
    document.title = `Paz y salvo ${d.folio} · ${conjunto.nombre}`;
    $("conjunto").textContent = conjunto.nombre;
    const [clase, icono, titulo, texto] = ESTADOS[d.estado] || ESTADOS["No vigente"];
    $("sello").className = `sello ${clase === "ok" ? "" : clase}`;
    $("icono").textContent = icono; $("titulo-estado").textContent = titulo; $("texto-estado").textContent = texto;
    $("folio").textContent = d.folio; $("titular").textContent = d.titular || "—"; $("apartamento").textContent = d.apartamento || "—";
    $("fila-destino").hidden = !d.destino; $("destino").textContent = d.destino || "";
    $("emision").textContent = fecha(d.fecha_emision, true); $("validez").textContent = fecha(d.valido_hasta, false);
    $("error").hidden = true; $("tarjeta").hidden = false;
  }

  async function cargar() {
    if (!codigo) return error();
    try {
      const r = await fetch(`/verificacion-publica/${encodeURIComponent(codigo)}`, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.status === 404) return error();
      if (r.status === 429) return error("Demasiadas consultas", "Espera un minuto e inténtalo de nuevo.");
      if (!r.ok) throw new Error();
      pintar(await r.json());
    } catch { error("Sin conexión", "No pudimos verificar el documento. Revisa tu internet e intenta de nuevo."); }
  }
  cargar();
})();
