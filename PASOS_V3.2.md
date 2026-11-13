# Versión 3.2 — qué cambió y cómo ponerla a funcionar

## Qué cambió
1. **Tarjetas con color y borde** (observación del instructor). Variables nuevas en `frontend/estilos.css`: `--tarjeta`, `--tarjeta-borde` y `--campo`.
   Claro: azul suave (Administrador), verde azulado suave (Residente) o crema (Guardia); borde de 1.5px. Oscuro: azul más claro que el fondo con borde azulado.
2. **Chat «Ciudabot»**: congestión de zonas con datos reales de reservas, guía de uso de la app, eventos de la Cartelera y votaciones abiertas (ver README). Si cambias cómo funciona una pantalla, actualiza `GUIA_APP` y `AYUDA_BASICA` en `app/chat_datos.py`. Archivos nuevos: `app/chat_datos.py`, `frontend/js/chat.js`, `tests/test_chat.py`.

## Pasos
1. **Migración de base de datos: NO hace falta** (no se agregaron tablas ni columnas).
2. Probar en tu PC: `pytest -q` (deben pasar 212 pruebas) y luego `iniciar.bat`.
3. Subir a GitHub: `git add .` · `git commit -m "v3.2: tarjetas con color y chat Ciudabot"` · `git push`.
4. Render despliega solo. Para que el chat use IA, revisa que exista la variable `IA_API_KEY` (opcional: `IA_LIMITE_CHAT_USUARIO`, `IA_LIMITE_CHAT_GLOBAL`).
5. Probar en el celular: cerrar y abrir la app para que se instale la versión nueva (la PWA se actualiza sola al cambiar los archivos) y revisar modo claro y oscuro con los tres roles.

## Opcional: reservas de ejemplo para la demostración
- Crear: `python -m app.demo_reservas --crear` (pide escribir SI; usa la base de datos del `.env`, así que en Render hazlo con cuidado).
- Borrar: `python -m app.demo_reservas --borrar` (elimina solo las de ejemplo y su usuario «Datos de ejemplo»; las reservas reales no se tocan).
