# Logos del cliente (white-label)

Esta carpeta es **opcional**. Si está vacía, la app usa los logos de siempre (Ciudadela Digital).

Para usar el logo de otro cliente, copia aquí archivos PNG con **exactamente estos nombres** (solo los que quieras cambiar; los demás siguen siendo los de siempre):

| Archivo | Para qué se usa | Tamaño recomendado |
|---|---|---|
| `icono.png` | Menú y login sobre fondo claro | 240 × 370, fondo transparente |
| `icono-crema.png` | Menú, login y landing sobre fondo oscuro (versión clara del icono) | 240 × 370, fondo transparente |
| `logo.png` | Logo completo, fondo claro | 720 × 433 |
| `logo-crema.png` | Logo completo para fondos oscuros (pantalla de ingreso) | 720 × 433 |
| `favicon.png` | Icono de la pestaña del navegador | 64 × 99 |
| `apple-touch-180.png` | Icono en iPhone al «Añadir a pantalla de inicio» | 180 × 180 |
| `pwa-192.png`, `pwa-512.png` | Icono de la app instalada en Android | 192 × 192 y 512 × 512 |
| `pwa-maskable-512.png` | Igual, con margen de seguridad para que Android lo recorte en círculo | 512 × 512 |

Cualquier otro archivo que pongas aquí **no se publica** (por seguridad solo se sirven los nombres de la tabla).

Después de cambiar un logo hay que **volver a desplegar** (o reiniciar el servidor): la app calcula la versión de su caché al arrancar y así todos los celulares descargan el logo nuevo.
