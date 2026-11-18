# Versión 4.4 · Chat del guardia, usuario al pie del menú y tarjetas más ligeras

Cambia el **backend** (solo el chat) y el **frontend**. **No hay migración de base de datos (Alembic) ni variables de entorno nuevas.**

## Qué cambió y dónde
| Archivo | Cambio |
|---|---|
| `app/routers/asistente.py` | Los dos endpoints del chat (`/asistente/chat/estado` y `/asistente/chat`) ahora aceptan también al **Guardia**. Los borradores de PQRS (`/asistente/residente`) siguen siendo solo de residentes, inquilinos y administración. La IA puede proponer la acción «porteria». Versión de la API: 4.4.0 (`app/main.py`). |
| `app/chat_datos.py` | Rol Guardia: guía propia (`GUIA_GUARDIA`), respuestas sin IA (`AYUDA_GUARDIA`), preguntas sugeridas de portería, enlaces permitidos (`ENLACES_GUARDIA`) y descripción para la IA. Nunca se le ofrecen Pagos, Votaciones, PQRS ni Daños, y no se le entregan las votaciones abiertas. Textos «toca tu avatar o tu nombre» (ya no siempre está arriba). |
| `frontend/js/app.js` | Barra inferior del guardia: Inicio · Portería · Paquetes · **Trasteos** · Más (Emergencias queda en «Más» y en el menú lateral). El chat se monta para todos los roles. Bloque de usuario (nombre, rol, Ajustes, Cerrar sesión) al pie del menú lateral. |
| `frontend/js/chat.js` | Bienvenida, preguntas y subtítulo del chat para el guardia. |
| `frontend/js/ui.js` | Íconos nuevos: `chevron` y `camion` (Trasteos ya no repite el ícono de Portería). |
| `frontend/estilos.css` | Bloque nuevo al final («VERSIÓN 4.4»): bloque de usuario del menú lateral, scroll del menú con sombra indicadora, modo compacto para pantallas bajas, tarjetas con transparencia simple (`--vidrio: 90%`) y menos carga en celulares. |
| `tests/test_chat.py`, `tests/test_v42_chat_roles.py` | Dos pruebas que exigían 403 para el guardia ahora esperan 200, y hay 9 pruebas nuevas del chat del guardia. |

## Cómo se ve ahora
- **Computador (≥ 1024 px):** nombre y rol al pie del menú izquierdo; arriba solo campana y tema. El menú con muchas opciones (administrador, residente) tiene scroll propio y el bloque de usuario siempre queda visible.
- **Celular y tableta:** el avatar (y el nombre en tableta) siguen en la barra superior.
- **Rendimiento:** las tarjetas normales no usan `blur`. En celular y tableta se apagan el `blur` de las dos tarjetas destacadas y el movimiento del fondo.

## Cómo volver atrás
Borrar el bloque «VERSIÓN 4.4» de `estilos.css` **y** la línea `h("div", { class: "sidebar-usuario" }, …)` de `app.js` (van juntos). El chat del guardia se quita revirtiendo `asistente.py`, `chat_datos.py` y la línea de `iniciarChat` en `app.js`.

## Qué hacer después (en este orden)
1. **Migración:** ninguna. No corras `alembic` por esta versión.
2. **Probar en local** (`iniciar-demo.bat`): entra con los 4 roles, en modo claro y oscuro, en computador y en celular. Con el guardia abre el chat y pregunta «¿Cómo registro un paquete?».
3. **Pruebas automáticas** (con el entorno virtual activo): `python -m pytest -q` → deben pasar 523. Y `node --test tests/js/atras.test.mjs`.
4. **Subir a GitHub:** `git add .` · `git commit -m "v4.4: chat del guardia, usuario al pie del menú, tarjetas ligeras"` · `git push`.
5. **Despliegue:** Render redespliega solo al recibir el push. Espera a que termine y revisa que el CI de GitHub quede en verde.
6. **Celular:** cierra la PWA por completo y ábrela dos veces para que el service worker instale la versión nueva (si no, verás la anterior).
7. **Probar en producción:** los 4 roles, el chat del guardia y el menú de cuenta en computador.
