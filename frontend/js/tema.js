// Tema claro / oscuro y preferencias de la app (fondo, animaciones, tamaño de texto).
// Script clásico (no módulo) para aplicarse antes del primer pintado y evitar parpadeos.
(function () {
  var CLAVE = "ciudadela.tema", CLAVE_PREFS = "ciudadela.prefs";
  var PREDETERMINADAS = { fondo: "on", anim: "on", texto: "normal" };

  function leer(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function escribir(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  // Solo dos temas: "claro" (por defecto) y "oscuro".
  function guardada() { return leer(CLAVE) === "oscuro" ? "oscuro" : "claro"; }
  function prefs() {
    var p = {}; try { p = JSON.parse(leer(CLAVE_PREFS) || "{}") || {}; } catch (e) {}
    return { fondo: p.fondo === "off" ? "off" : "on", anim: p.anim === "off" ? "off" : "on",
             texto: p.texto === "grande" || p.texto === "enorme" ? "grande" : "normal" };
  }
  function aplicar() {
    var oscuro = guardada() === "oscuro";
    var h = document.documentElement, p = prefs();
    h.dataset.tema = oscuro ? "oscuro" : "claro";
    h.dataset.fondo = p.fondo; h.dataset.anim = p.anim; h.dataset.texto = p.texto;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", oscuro ? "#06122B" : "#07304A");
  }
  window.CiudadelaTema = {
    obtener: guardada,
    establecer: function (pref) { escribir(CLAVE, pref === "oscuro" ? "oscuro" : null); aplicar(); },
    prefs: prefs,
    establecerPref: function (clave, valor) {
      var p = prefs(); p[clave] = valor; escribir(CLAVE_PREFS, JSON.stringify(p)); aplicar();
    },
    restablecer: function () { escribir(CLAVE, null); escribir(CLAVE_PREFS, null); aplicar(); },
    predeterminadas: PREDETERMINADAS,
  };
  aplicar();

  // Sin zoom con los dedos (pellizco). iOS ignora user-scalable=no, por eso se bloquean los gestos.
  ["gesturestart", "gesturechange", "gestureend"].forEach(function (ev) {
    document.addEventListener(ev, function (e) { e.preventDefault(); }, { passive: false });
  });
  document.addEventListener("touchmove", function (e) {
    if (e.touches && e.touches.length > 1) e.preventDefault();
  }, { passive: false });
})();
