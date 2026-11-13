// Activa las fuentes de Google sin bloquear el primer pintado (sustituye al atributo onload que la política de seguridad no permite).
(() => {
  const pre = document.getElementById("fuentes-precarga");
  if (!pre) return;
  const hoja = document.createElement("link");
  hoja.rel = "stylesheet"; hoja.href = pre.href; hoja.media = "print";          // «print» = no bloquea el pintado
  hoja.addEventListener("load", () => { hoja.media = "all"; });
  document.head.append(hoja);
})();
