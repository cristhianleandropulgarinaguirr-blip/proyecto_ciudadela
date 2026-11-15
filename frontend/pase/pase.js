// Página pública del pase de visitante. Sin librerías ni módulos: un solo archivo pequeño.
//   · Lee el token de la URL (/pase/<token>) y pide sus datos a /pase-publico/<token>.
//   · Mantiene la pantalla encendida (Screen Wake Lock) mientras se muestra el QR: una web NO puede subir el brillo del celular,
//     pero sí evitar que se apague justo cuando el guardia lo va a escanear. El QR va en negro sobre blanco puro para leerse bien.
//   · Se actualiza sola cada 20 s (por si el pase pasa a «Dentro», «Usado» o se revoca) y solo mientras la pestaña está visible.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const partes = location.pathname.split("/").filter(Boolean);
  const token = partes[0] === "pase" ? partes[1] : "";
  const API = `/pase-publico/${encodeURIComponent(token)}`;
  let temporizador = null, bloqueo = null, imagenCargada = false;

  const ESTADOS = {
    Activo: ["Pase válido: muéstraselo al guardia", "ok"],
    Dentro: ["Ya ingresaste: al salir, muestra el mismo QR", "aviso"],
    Usado: ["Este pase ya se usó", "mal"],
    Vencido: ["Este pase venció", "mal"],
    Revocado: ["Este pase fue cancelado", "mal"],
  };

  function mostrarError(titulo, texto) {
    $("tarjeta").hidden = true; $("error").hidden = false;
    $("conjunto").textContent = "Pase de ingreso";
    if (titulo) $("error-titulo").textContent = titulo;
    if (texto) $("error-texto").textContent = texto;
    detener();
  }

  function fechaLarga(iso) {
    if (!iso) return "Sin límite";
    // El servidor guarda la hora en UTC sin zona: se le agrega la «Z» para que el navegador la convierta a la hora local.
    const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
    return d.toLocaleString("es-CO", { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  }

  function pintar(datos) {
    const { conjunto, pase } = datos;
    document.title = `Pase · ${conjunto.nombre}`;
    $("conjunto").textContent = conjunto.nombre;
    const [texto, clase] = ESTADOS[pase.estado] || [pase.estado, "aviso"];
    const estado = $("estado"); estado.textContent = texto; estado.className = `estado ${clase}`;

    $("visitante").textContent = pase.visitante || "Visitante";
    $("placa").textContent = pase.placa || "—";
    $("destino").textContent = pase.apartamento;
    $("validez").textContent = fechaLarga(pase.valido_hasta);

    // QR: solo se pide la imagen si el pase sirve; se carga una vez (no cambia mientras el pase sea el mismo).
    $("qr-caja").hidden = !pase.sirve;
    if (pase.sirve && !imagenCargada) { $("qr").src = `${API}/imagen`; imagenCargada = true; }
    if (!pase.sirve) { $("qr").removeAttribute("src"); imagenCargada = false; }

    $("pin-caja").hidden = !pase.pin;
    $("pin").textContent = pase.pin || "";

    $("acciones").hidden = !pase.puede_avisar;
    $("btn-camino").disabled = pase.en_camino;
    $("btn-camino").textContent = pase.en_camino ? "Ya avisaste que vas en camino" : "Estoy en camino";
    $("btn-llegue").disabled = pase.llegue;
    $("btn-llegue").textContent = pase.llegue ? "Ya avisaste que llegaste" : "Ya llegué a la portería";

    const mapas = conjunto.mapas;
    $("mapas").hidden = !mapas || !pase.sirve;
    if (mapas) { $("mapa-google").href = mapas.google; $("mapa-waze").href = mapas.waze; }
    $("direccion").textContent = conjunto.direccion || "";

    $("error").hidden = true; $("tarjeta").hidden = false;
    pase.sirve ? mantenerPantallaEncendida() : soltarPantalla();
  }

  async function cargar() {
    if (!token) return mostrarError();
    try {
      const r = await fetch(API, { headers: { Accept: "application/json" }, cache: "no-store" });
      if (r.status === 404) return mostrarError();
      if (r.status === 429) return;                       // demasiadas consultas: se reintenta en el siguiente ciclo
      if (!r.ok) throw new Error();
      pintar(await r.json());
    } catch {
      // Sin internet: si ya hay un pase en pantalla se deja tal cual (el QR sigue visible, que es lo importante).
      if ($("tarjeta").hidden) mostrarError("Sin conexión", "No pudimos cargar tu pase. Revisa tu internet e intenta de nuevo.");
    }
  }

  async function avisar(tipo, boton) {
    const msg = $("mensaje"); msg.className = "mensaje"; msg.textContent = "";
    boton.disabled = true;
    try {
      const r = await fetch(`${API}/aviso`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.detail || "No se pudo enviar el aviso.");
      msg.textContent = j.mensaje; await cargar();
    } catch (e) { msg.className = "mensaje mal"; msg.textContent = e.message; boton.disabled = false; }
  }

  async function mantenerPantallaEncendida() {
    if (bloqueo || !("wakeLock" in navigator) || document.hidden) return;
    try { bloqueo = await navigator.wakeLock.request("screen"); bloqueo.addEventListener("release", () => { bloqueo = null; }); } catch { /* no es crítico */ }
  }
  function soltarPantalla() { bloqueo?.release().catch(() => {}); bloqueo = null; }

  function iniciar() { detener(); temporizador = setInterval(() => { if (!document.hidden) cargar(); }, 20000); }
  function detener() { if (temporizador) clearInterval(temporizador); temporizador = null; }

  document.addEventListener("visibilitychange", () => { if (!document.hidden) { cargar(); mantenerPantallaEncendida(); } });
  $("btn-camino").addEventListener("click", (e) => avisar("en_camino", e.currentTarget));
  $("btn-llegue").addEventListener("click", (e) => avisar("llegue", e.currentTarget));
  cargar().then(iniciar);
})();
