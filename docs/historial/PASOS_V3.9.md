# Versión 3.9 — Correcciones de interfaz

No hay migración de base de datos en esta versión (no cambia ninguna tabla).

## 1. Qué se corrigió, dónde y por qué

| # | Problema | Causa real | Dónde se arregló |
|---|---|---|---|
| 1 | Al recargar el login, el correo/contraseña que el navegador rellena se montaban sobre la etiqueta | El CSS sube la etiqueta con `:placeholder-shown`; con el autocompletado el campo «parece vacío» para el CSS | `frontend/estilos.css` (reglas `:-webkit-autofill` y `.field.lleno`) y `frontend/js/vistas/login.js` (marca el campo como lleno) |
| 2 | «Indicadores» (y lo que va debajo) se veía cortado y no se podía bajar | El menú lateral tenía `overflow: visible` y altura fija de pantalla: lo que no cabía quedaba escondido | `frontend/estilos.css`: el menú lateral ahora tiene scroll propio |
| 3 | Cartera: «Paz y salvo», «Registrar saldo» y «PDF» desordenados | Los botones no estaban en un contenedor con reglas; se acomodaban según el espacio | `frontend/js/vistas/cartera.js` + `estilos.css` (`.acciones-cartera`): 3 columnas fijas, iguales en todas las filas |
| 4 | Modo oscuro de Residente, Inquilino y Guardia: letras invisibles | Las tarjetas de cada rol tenían su color CLARO y el modo oscuro no las reemplazaba, pero el texto sí era claro (claro sobre claro) | `frontend/estilos.css`: colores oscuros de tarjeta por rol en modo oscuro |
| 5 | Óvalos que no se ven en modo claro | Botones «suaves» y de «peligro» e insignias tenían borde casi del mismo color que la tarjeta | `frontend/estilos.css`: bordes y fondos con contraste (botones, fichas e insignias) |
| 6 | Auditoría llena de «Usó el chat de IA» | Cada mensaje del chat escribía una fila en la bitácora | `app/routers/asistente.py`: se quitó esa anotación |

Sobre el punto 6: se quitó solo la fila de **auditoría**. El conteo diario del chat (`UsoAsistente`) se mantiene a propósito, porque es lo que aplica el tope diario y protege la cuota de la IA; es una tabla aparte y liviana. Los borradores de IA (PQRS, daños y anuncios) **siguen** auditándose.

Prueba nueva: `tests/test_chat.py::test_el_chat_no_llena_la_auditoria_pero_si_cuenta_el_uso_diario`. Resultado de la batería completa: 385 pruebas pasaron.

## 2. Cómo dejarlo funcionando (en este orden)

1. **Copia el proyecto completo** sobre tu carpeta local (no archivos sueltos).
2. **Local:** reinicia el servidor (`Ctrl+C` y `uvicorn` de nuevo). El service worker se recalcula al arrancar. En el navegador haz `Ctrl+Shift+R`; si sigue la versión vieja: F12 → *Application* → *Service Workers* → **Unregister** y *Storage* → **Clear site data**.
3. **Pruebas:** `pytest -q` (deben pasar todas).
4. **GitHub:**
   ```
   git add .
   git commit -m "v3.9: menu con scroll, modo oscuro por rol, autocompletar, cartera alineada y chat sin auditoria"
   git push
   ```
5. **Render:** el despliegue arranca solo al hacer push. Espera a que diga *Live*. No hay migración nueva, así que el comando de inicio (`alembic upgrade head && ...`) no cambia nada.
6. **Celular:** abre la app, y si ves lo anterior, ciérrala por completo y vuelve a abrirla (el service worker instala la versión nueva en la segunda apertura). Si es una PWA instalada: Ajustes del navegador → borrar datos del sitio.
7. **Qué revisar:**
   - Login: recarga con credenciales guardadas; la etiqueta debe quedar arriba del texto.
   - Admin (escritorio): el menú lateral se desplaza con la rueda hasta «Usuarios».
   - Admin → Cartera: los tres botones alineados en cada fila.
   - Residente, Inquilino y Guardia en modo oscuro: pestaña «Más» y las tarjetas con texto legible.
   - Modo claro: «Cerrar sesión», «Cerrar todas las demás» y las insignias con borde.
   - Chat: usa el Ciudabot y confirma que Auditoría no muestra filas nuevas.
