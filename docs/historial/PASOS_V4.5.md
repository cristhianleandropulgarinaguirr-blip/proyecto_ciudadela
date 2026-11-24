# Versión 4.5 · Botón «Teléfonos de emergencia» para el guardia

Cambia **solo el frontend**. **No hay migración (Alembic), ni cambios de backend, ni variables de entorno nuevas.**

## Qué cambió y dónde
| Archivo | Cambio |
|---|---|
| `frontend/js/vistas/resumen.js` | En el Inicio del guardia, debajo/al lado de «Ir a portería y escanear», hay un botón nuevo **«Teléfonos de emergencia»** que abre `#/emergencias`. Los dos botones van dentro de un contenedor `.cta-guardia`. |
| `frontend/js/vistas/porteria.js` | Solo para el rol Guardia: botón más pequeño «Teléfonos de emergencia» bajo el título de Portería (donde pasa la mayor parte del turno). |
| `frontend/estilos.css` | Bloque nuevo al final («VERSIÓN 4.5»): `.cta-guardia`, `.cta-emergencia`, `.cta-emergencia-mini`. Usa los colores de peligro (arcilla) ya existentes, por lo que se adapta a modo claro y oscuro. |

## Cómo se ve
- **Celular:** los dos botones apilados (escanear arriba, emergencias abajo).
- **Computador/tableta (≥ 640 px):** los dos botones lado a lado.
- Al tocarlo se abre la lista de contactos; cada número tiene botón «llamar» (`tel:`).

## Cómo volver atrás
Revertir las líneas del `h("div", { class: "cta-guardia" …` en `resumen.js`, la línea del botón en `porteria.js` y borrar el bloque «VERSIÓN 4.5» de `estilos.css`.

## Qué hacer después (en este orden)
1. **Migración:** ninguna. No corras `alembic`.
2. **Probar en local** (`.\iniciar-demo.bat`, ejecútalo con **punto y barra**): entra como Guardia, revisa Inicio y Portería, en modo claro, oscuro y celular.
3. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
4. **GitHub:** `git add .` · `git commit -m "v4.5: botón de teléfonos de emergencia para el guardia"` · `git push`.
5. **Despliegue:** Render redespliega solo; espera a que termine y revisa el CI.
6. **Celular:** cierra la PWA por completo y ábrela dos veces para que se instale la versión nueva.
7. **Producción:** entra como Guardia y toca el botón.
