# Versión 4.3 · Vida en las tarjetas y correcciones de diseño

Solo cambia el **frontend**. No hay migración de base de datos (Alembic) ni variables nuevas.

## Qué cambió y dónde
| Archivo | Cambio |
|---|---|
| `frontend/estilos.css` | Bloque nuevo al final («VERSIÓN 4.3»). Para volver al look anterior basta borrarlo. Más el arreglo de `text-transform` del saludo. |
| `frontend/js/ui.js` | `kpi()` acepta `href`, `marca`, `nota` (todo opcional). Nueva función `propio()` para mostrar nombres con mayúscula inicial. |
| `frontend/js/vistas/resumen.js` | Contadores tocables con ícono de fondo; hero del administrador «Por atender hoy»; botón de escaneo del guardia arriba; nombres capitalizados; «Ver mi cuenta» legible en modo oscuro. |
| `frontend/js/vistas/mas.js` | No repite lo que ya está en la barra inferior; ícono en círculo. |
| `frontend/js/app.js` | Etiquetas cortas en la barra inferior; menú del avatar (Ajustes y Cerrar sesión); pasa `enBarra` a «Más». |

## Para dejarlo funcionando
1. Probar en local (`iniciar-demo.bat`) con los 4 roles, en claro y oscuro, y en el celular.
2. `git add . && git commit -m "v4.3: vida en las tarjetas y correcciones de diseño" && git push`.
3. Esperar que Render termine el despliegue y que el CI (GitHub Actions) quede en verde.
4. El service worker cambia solo de versión (el servidor la calcula con los archivos), no hay que subirla a mano. Cerrar la PWA del celular y abrirla dos veces para que instale la versión nueva.
5. Probar en producción.
