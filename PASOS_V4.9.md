# Versión 4.9 · Íconos duotono para todos los módulos + letras más legibles para los abuelos

Cada módulo (Visitas, Paquetes, Trasteos, Arrendamientos, Daños, Documentos, Votaciones, Cartelera, Comercio, Emergencias, Indicadores, Portería, Usuarios, Cargar datos, Auditoría, Ajustes…) tiene ahora **su propio ícono**, dibujado en estilo duotono (línea + relleno suave del color del rol) dentro de un contenedor tipo *squircle*. Además se agrandaron las letras pequeñas y se oscurecieron los grises. **No hay migración nueva, ni dependencias nuevas, ni cambios en el backend.** Pruebas: 576 en Python y 9 en Node, todas en verde (igual que en la v4.8).

## Qué se cambió y dónde
| Archivo | Cambio | Por qué |
|---|---|---|
| `frontend/js/ui.js` | (1) 22 íconos nuevos con nombre `m_…` (uno por módulo, más Inicio y Más), trazo 1.75 y forma suave con `class="du"`. (2) `icono()` ahora usa un **sprite SVG**: cada ícono se define una sola vez como `<symbol>` y cada llamada dibuja un `<use>`. (3) Si algo vacía el `<body>`, el sprite se reconecta solo. | Un único sitio donde viven los dibujos; las ~100 llamadas existentes a `icono("nombre")` siguen funcionando sin tocarlas. Los íconos funcionales (✓, ✕, flecha…) no cambian. |
| `frontend/js/app.js` | Solo el campo `icono:` de cada ruta (22 líneas): ahora apunta a `m_<id>`. | Barra inferior, menú lateral y pantalla «Más» cambian juntos y siempre muestran el mismo ícono para el mismo módulo. |
| `frontend/js/vistas/resumen.js` | Los accesos rápidos y las tarjetas de indicadores del Inicio usan el ícono de **su** módulo (según su enlace `#/…`). | Antes dos módulos distintos compartían ícono (p. ej. Arrendamientos y Residentes). |
| `frontend/estilos.css` | (1) Bloque nuevo `v4.9` al final: sprite oculto, relleno duotono, variables `--ico-tint / --ico-bg / --ico-border / --ico-glow`, rojo fijo para Emergencias, efectos al tocar y legibilidad. (2) Ediciones marcadas «v4.9»: `--tinta-2` y `--tinta-3` (grises), etiquetas del menú, y `.mas-ico` (de círculo a squircle de 54 px, radio 16 px). | Ver las secciones de abajo. |
| `frontend/sw.js` | **No se tocó.** | El servidor calcula la versión del caché con un hash de todos los archivos del frontend: pasó solo de `ciudadela-9dbdb31f8424` a `ciudadela-7f2f5c08bb4a`. Los celulares descargan lo nuevo solos. |

## Cómo funcionan los colores
Los colores de los íconos **no son valores nuevos copiados a mano**: se calculan a partir de los que ya tenía cada rol (`--bosque` y `--rol-rgb`). Así Administrador (azul), Residente (verde azulado), Guardia (ámbar) e Inquilino (violeta), el modo oscuro y la marca blanca quedan sincronizados solos. **Emergencias es la única excepción**: siempre rojo alerta (`#dc2626` en claro, `#f87171` en oscuro), sin importar el rol.

## Qué mejoró en legibilidad (medido, no a ojo)
| Elemento | Antes | Ahora |
|---|---|---|
| Gris secundario, modo claro | contraste 5,1 : 1 | 8,0 : 1 |
| Gris terciario, modo claro | 4,8 : 1 | 7,1 : 1 |
| Gris terciario, modo oscuro | **4,4 : 1** (bajo el mínimo AA de 4,5) | 7,4 : 1 |
| Etiquetas del menú | 11 px, algo transparentes | 12,5 px, más opacas |
| Letra más pequeña de lectura (Residente / Inquilino) | 10,9 px / 12 px | 12,5 px / 13,1 px |
Unas 30 reglas de texto que estaban entre 11 y 13 px subieron a 12–14 px. Se dejó igual la letra decorativa de la placa de vehículo.
**Ya existe** en *Ajustes → Tamaño del texto → Grande* un interruptor que agranda todo un 12,5 %. Los cambios nuevos se combinan bien con él.

## Peso
Los 22 íconos nuevos pesan **4.070 bytes (3,97 KB)** y unos **1,2 KB** al viajar comprimidos. Sin librerías externas ni imágenes.

## Qué hacer después (en este orden)
1. **Mira cómo queda en tu computador.** Descomprime el zip y arranca como siempre (`.\iniciar.bat`). Abre la pantalla **Más** con cada rol, en modo claro y oscuro.
2. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`. Deben dar 576 y 9 en verde.
3. **GitHub (importante):** el repositorio tiene una versión **más vieja que la v4.8**, así que primero guarda la v4.8 sola y luego la v4.9, para poder volver atrás si algo no te gusta.
   - Descomprime la v4.8 sobre tu carpeta y borra a mano `app/avisos_whatsapp.py` y `frontend/js/vistas/demos.js` si aún existen. Luego `git add .`, `git commit -m "v4.8"`, `git push`.
   - Después descomprime este zip (v4.9) sobre la carpeta, acepta reemplazar, y haz `git add .`, `git commit -m "v4.9 íconos duotono y letras más legibles"`, `git push`.
4. **Render:** al subir a GitHub el despliegue se hace solo (si tienes el auto-deploy activado); si no, entra a Render y pulsa *Manual Deploy → Deploy latest commit*. Espera a que diga *Live*. No hay variables nuevas que agregar.
5. **Prueba final en el celular, ya desplegado:** abre la app y entra con cada rol. Revisa la barra inferior, la pantalla **Más** y el **Inicio**. Si todavía ves los íconos viejos, cierra la app por completo y ábrela otra vez una vez (el celular instala la versión nueva en segundo plano).

## Cómo volver atrás
`git revert` del commit de la v4.9. No hay migración que deshacer. Para deshacer solo el estilo, borra el bloque `v4.9 · Íconos duotono + legibilidad` al final de `estilos.css` y las ediciones marcadas «v4.9».

## Límites honestos
- Revisé la app con un navegador de pruebas (Chromium sin pantalla) en 4 roles × 2 temas, a 360, 390 y 1280 px. **No la probé en un celular real**; revísala tú en el tuyo.
- En mis pruebas no se cargaron las tipografías de Google Fonts (no hay internet allí): se vieron con una letra de respaldo. La forma de los íconos no depende de eso, pero el texto puede verse un poco distinto en tu celular.
- A 360 px de ancho aparecen 3 pequeños desbordes horizontales (Arrendamientos del administrador, la pestaña de Portería y un botón del Inicio del inquilino). **Ya estaban igual en la v4.8**; no los causa esta versión y no los toqué.
- El relleno duotono es deliberadamente suave (22 % en claro, 24 % en oscuro) para que la app se vea sobria. Si lo quieres más marcado, solo cambia `--ico-op` en el bloque `v4.9`.
