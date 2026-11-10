// Tema claro / oscuro / automático y preferencias de la app (fondo, animaciones, tamaño de texto).
// Script clásico (no módulo) para aplicarse antes del primer pintado y evitar parpadeos.
(function () {
  var CLAVE = "ciudadela.tema", CLAVE_PREFS = "ciudadela.prefs";
  var oscuroSistema = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var PREDETERMINADAS = { fondo: "on", anim: "on", texto: "normal" };

  function leer(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function escribir(k, v) { try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) {} }

  function guardada() { var v = leer(CLAVE); return v === "claro" || v === "oscuro" ? v : "auto"; }
  function prefs() {
    var p = {}; try { p = JSON.parse(leer(CLAVE_PREFS) || "{}") || {}; } catch (e) {}
    return { fondo: p.fondo === "off" ? "off" : "on", anim: p.anim === "off" ? "off" : "on",
             texto: p.texto === "grande" || p.texto === "enorme" ? p.texto : "normal" };
  }
  function aplicar() {
    var oscuro = guardada() === "oscuro" || (guardada() === "auto" && oscuroSistema && oscuroSistema.matches);
    var h = document.documentElement, p = prefs();
    h.dataset.tema = oscuro ? "oscuro" : "claro";
    h.dataset.fondo = p.fondo; h.dataset.anim = p.anim; h.dataset.texto = p.texto;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", oscuro ? "#06122B" : "#07304A");
  }
  window.CiudadelaTema = {
    obtener: guardada,
    establecer: function (pref) { escribir(CLAVE, pref === "auto" ? null : pref); aplicar(); },
    prefs: prefs,
    establecerPref: function (clave, valor) {
      var p = prefs(); p[clave] = valor; escribir(CLAVE_PREFS, JSON.stringify(p)); aplicar();
    },
    restablecer: function () { escribir(CLAVE, null); escribir(CLAVE_PREFS, null); aplicar(); },
    predeterminadas: PREDETERMINADAS,
  };
  if (oscuroSistema && oscuroSistema.addEventListener) oscuroSistema.addEventListener("change", aplicar);
  aplicar();
})();
