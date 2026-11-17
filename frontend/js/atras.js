// Botón «Atrás» del celular (gesto o botón físico) para las capas flotantes: modales, carnet/pase en ventana y chat del asistente.
//
// Problema: en una PWA, «Atrás» retrocede por el historial del navegador. Con un modal abierto eso sacaba a la persona de la pantalla
// (o de la app) en lugar de cerrar el modal, que es lo que espera cualquiera en un celular.
//
// Solución: al abrir una capa se agrega UNA entrada al historial (misma URL, solo un marcador en history.state). Si la persona pulsa
// «Atrás», el navegador vuelve a la entrada anterior y aquí se cierra la capa. Si la capa se cierra por otro medio (la «X», tocar fuera,
// Escape, un botón), se consume esa entrada para que el historial quede limpio.
//
// Convive con el enrutador por #hash de app.js: pushState con la MISMA URL no dispara «hashchange», así que no se mezclan.
// Se usan marcadores crecientes (basados en la hora) para distinguir capas abiertas de «fantasmas» que quedaron en el historial.
//
// crearAtras() recibe las piezas del navegador, así se puede probar en Node sin un navegador de verdad (ver tests/js/atras.test.mjs).

export function crearAtras({ historia, escuchar, ahora = () => Date.now() }) {
  const capas = [];                   // [{ id, cerrar }] de la más antigua a la más nueva (la última es la de arriba)
  let ultimo = 0;
  const nuevoId = () => (ultimo = Math.max(ultimo + 1, ahora()));
  const marcador = (estado) => (estado && typeof estado.capaAtras === "number" ? estado.capaAtras : 0);

  // Si la página se recarga con una capa abierta, el navegador conserva el marcador en la entrada actual: se borra (sin mover el historial).
  if (marcador(historia.state)) historia.replaceState(null, "");

  escuchar("popstate", (e) => {
    const aterrizo = marcador(e.state ?? historia.state);
    const arriba = capas.at(-1);
    // La persona retrocedió más allá de la capa de arriba → se cierra esa capa (y solo esa).
    if (arriba && aterrizo < arriba.id) {
      capas.pop();
      try { arriba.cerrar(); } catch { /* una capa rota no debe trabar el botón Atrás */ }
      return;
    }
    // Se cayó sobre una entrada «fantasma» (una capa que ya se cerró por otro medio): se salta para no necesitar dos toques.
    if (aterrizo && !capas.some((c) => c.id === aterrizo)) historia.back();
  });

  return {
    /** Registra una capa recién abierta. `cerrar` debe cerrarla de verdad. Devuelve { soltar }: llámalo cuando la capa se cierre por cualquier medio. */
    abrir(cerrar) {
      const id = nuevoId();
      capas.push({ id, cerrar });
      historia.pushState({ capaAtras: id }, "");
      return {
        soltar() {
          const i = capas.findIndex((c) => c.id === id);
          if (i < 0) return;                                  // ya se cerró con «Atrás»: nada que limpiar
          capas.splice(i, 1);
          // Solo se consume la entrada si sigue siendo la actual. Si en el mismo instante se navegó a otra ruta, la entrada queda
          // debajo como «fantasma» y el manejador de popstate la salta cuando se llegue a ella.
          if (marcador(historia.state) === id) historia.back();
        },
      };
    },
    get abiertas() { return capas.length; },
  };
}

// Instancia para la app (solo en el navegador).
const real = typeof window !== "undefined" && window.history
  ? crearAtras({ historia: window.history, escuchar: (t, fn) => window.addEventListener(t, fn) })
  : null;

/** Registra una capa flotante abierta. Devuelve { soltar } (sin efecto si no hay navegador). */
export const abrirCapa = (cerrar) => (real ? real.abrir(cerrar) : { soltar() {} });
