# Versión 4.2 — Móvil, landing, asistente por rol, pagos de prueba y revisión de seguridad

**Hay una migración nueva (`0021`) y no hay dependencias nuevas** (`requirements.txt` no cambia). La migración se aplica sola al desplegar,
porque el comando de arranque de Render ya ejecuta `alembic upgrade head`.

Resultado de las pruebas: **514 pruebas de Python + 9 de JavaScript, todas en verde** (al empezar eran 470 de Python). Ver «Qué NO se pudo comprobar» al final.

---

## 1. Revisión de seguridad y limpieza

**Lo que se encontró bien (no se tocó):** cabeceras de seguridad y CSP, contraseñas con bcrypt, renovación de sesión con cookie HttpOnly, topes de intentos,
roles en cada ruta (solo dos páginas son públicas a propósito: el pase QR y la verificación del paz y salvo), subida de archivos validada, y **ningún uso
peligroso de `innerHTML`** con datos de personas (solo dibujos SVG fijos).

**Lo que se corrigió:**

| Hallazgo | Qué hacía | Corrección | Dónde |
|---|---|---|---|
| La IP del cliente se podía falsear | En Render, uvicorn confía en la cabecera `X-Forwarded-For` y toma el valor de la izquierda, que escribe quien hace la petición. Cambiándola en cada envío se evitaba el tope por IP del formulario «Solicitar demo». | Nuevo tope **global** (40 solicitudes por hora en total) que no depende de la IP. | `app/limitador.py`, `app/routers/demo.py` |
| `/docs` y `/openapi.json` visibles siempre | Cualquiera veía la lista completa de rutas internas. | Interruptor `DOCS_ACTIVAS` (por defecto `1`, para tu demo y el instructor). En la app de un cliente ya contratado ponlo en `0`. | `app/config.py`, `app/main.py`, `render.yaml`, `.env.example` |
| Código muerto | 5 funciones que nada llamaba (`ruta_imagen`, `ruta_documento`, `olvidar`, `es_la_marca_por_defecto`, `_tabla_de`). | Eliminadas, con revisión de que ni las pruebas las usaban. | `app/archivos.py`, `limitador.py`, `marca.py`, `seed_demo.py` |
| Archivos sueltos | Una captura de pantalla de 1,2 MB y 10 guías `PASOS_V*.md` en la raíz. | Captura eliminada; guías movidas a `docs/historial/` (README actualizado). | `docs/` |

El CSS y los JS no tenían nada huérfano. Las migraciones de Alembic no se tocaron.

## 2. Aviso de «Pendiente por sincronizar» (portería sin internet)

- **Qué:** una franja **ámbar fuerte** con un punto que late y el texto «N registro(s) SIN ENVIAR · están guardados solo en este equipo», con botón «Enviar ahora».
  Si no hay internet, la franja oscura de siempre muestra además una pastilla ámbar «N sin enviar».
- **Por qué así:** no depende solo del color (hay texto, número y movimiento), y el latido se apaga si el celular tiene activado «reducir movimiento».
- **Dónde:** `frontend/js/app.js` (función que pinta la franja) y `frontend/estilos.css` (`.banner-red.pendiente`, `.punto-alerta`, `.chip-pendiente`).

## 3. Botón «Atrás» del celular

- **Qué:** con un modal o el chat abierto, «Atrás» (botón o gesto) **cierra esa ventana** en vez de sacar a la persona de la pantalla. Si hay varias, cierra primero la de arriba.
- **Cómo:** al abrir una ventana se añade una entrada al historial con la misma URL (no choca con el enrutador `#/…`). Si la ventana se cierra con la «X», se consume esa entrada para no dejar «Atrás» doble.
- **Dónde:** `frontend/js/atras.js` (nuevo), conectado en `ui.js` (`modal()`, que cubre también el pase QR en ventana) y `chat.js`.
- **Pruebas:** `tests/js/atras.test.mjs` (9 casos con un historial de navegador simulado), ya incluido en el CI de GitHub.
- **Nota:** el carnet QR de «Mis visitas» es una pantalla, no una ventana flotante, así que ahí «Atrás» ya funcionaba como una pantalla normal.

## 4. Landing

- **WhatsApp:** el mensaje ahora es «Hola Cristhian, revisé la demo de Ciudadela Digital y me gustaría agendar una demostración para mi conjunto residencial.» (más nombre, conjunto, apartamentos y ciudad si la persona los escribió), codificado en la URL. El número lleva el 57 automáticamente.
  Nuevas variables: `DEMO_WHATSAPP=3224101828` y `DEMO_CONTACTO=Cristhian` (ya están en `render.yaml`).
- **Ancho máximo:** la landing ya centraba todo en 1160 px; ahora **1200 px** (`--ancho` en `landing/recursos/landing.css`).
- **Guía de instalación de la PWA:** sección nueva «Se instala como una app, sin tiendas» con pestañas **Android (Chrome), iPhone (Safari) y Computador (Chrome/Edge)**, 3 pasos dibujados con SVG propio cada una (sin imágenes externas, así no rompe la CSP). Se abre sola en la pestaña del dispositivo de la persona. Dónde: `landing/index.html`, `landing.css`, `landing.js`.

## 5. Asistente «Ciudabot» coherente con cada rol

- Hoy el asistente le hablaba a todos como si fueran residentes. Ahora el **servidor** decide el rol con la sesión (nunca con lo que escriba la persona) y adapta:
  preguntas de arranque, guía que recibe la IA, respuestas del modo básico, seguimientos y botones.
- **Administrador:** aprobar reservas, registrar pagos, publicar avisos, cargar Excel, arrendamientos, trasteos, etc., con los botones reales de su pantalla.
- **Residente:** reservar, pase QR, pagos, votaciones.
- **Inquilino:** según lo que su propietario le delegó. Sin permiso de pagar o votar, el bot explica por qué y **no le ofrece botones que no podría abrir**.
- **Dónde:** `app/chat_datos.py`, `app/routers/asistente.py`, `app/schemas/asistente.py`, `frontend/js/chat.js`. Pruebas: `tests/test_v42_chat_roles.py`.

## 6. Pagos de prueba tipo Wompi / PSE

- **Recorrido igual al real:** la app crea un intento con referencia `SIM-…` → eliges **PSE, Tarjeta o Nequi** → la «pasarela» (el servidor) decide Aprobado / Rechazado / Pendiente → comprobante en PDF.
- **Datos de prueba** (con botones que los llenan solos): tarjeta `4242…` aprueba, `4111…` rechaza, `…0002` queda pendiente; PSE con banco que aprueba/rechaza/valida; Nequi con celular que termina en 0 aprueba, 1 rechaza, 2 pendiente. Un «pendiente» se confirma solo a los pocos segundos, como el aviso de una pasarela real.
- **Reglas que ya valen para cuando sea real:** el frontend nunca dice «pagado» (lo decide el servidor); el saldo se descuenta **una sola vez** por intento; de la tarjeta solo viajan los 4 últimos dígitos y **nada** se guarda; cada persona solo ve sus intentos; tope de 20 pasos por persona cada 10 minutos; banner permanente «MODO DE PRUEBAS».
- **Dónde:** `app/routers/pagos_simulados.py`, `app/schemas/pagos_simulados.py`, `app/models.py` (`IntentoPago`), migración `0021` (con la protección RLS de Supabase, como la 0020), `frontend/js/vistas/pasarela.js`, `cartera.js`. Pruebas: `tests/test_v42_pagos_simulados.py`.
- El botón antiguo de pago instantáneo sigue existiendo en la API pero la pantalla ya no lo usa.

---

## Qué debes hacer para dejarlo funcionando (en este orden)

1. **Migración (local):** `alembic upgrade head` (crea la tabla `intentos_pago`). En Render se aplica sola al desplegar.
2. **Pruebas (local):** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
3. **GitHub:** sube los cambios (`git add -A`, `git commit -m "v4.2: móvil, landing, asistente por rol, pagos de prueba, seguridad"`, `git push`). El CI correrá las pruebas.
4. **Render (variables):** en el panel de tu servicio revisa:
   - `PAGOS_SIMULADOS` = `1` **solo mientras muestres la demo** (en `render.yaml` está en `0`; con `0` verá «Cómo pagar» por transferencia en vez de la pasarela de prueba).
   - `DEMO_WHATSAPP` = `3224101828` y `DEMO_CONTACTO` = `Cristhian` (si el servicio ya existía, `render.yaml` no las crea solo).
   - `DOCS_ACTIVAS` = `1` para tu demo; `0` en la app de un cliente ya contratado.
5. **Prueba en el celular real**, con la app instalada:
   - Con un modal o el chat abierto, pulsa «Atrás».
   - Registra algo en portería sin internet y mira la franja ámbar; vuelve el internet y mira que se envíe.
   - Abre el chat con un administrador, un residente y un inquilino.
   - Haz un pago de prueba con cada método.
   - Abre la landing en el celular y en un computador ancho; prueba el botón de WhatsApp y las pestañas de instalación.

## Qué NO se pudo comprobar (dilo con honestidad en tu presentación)

- **Ningún navegador real:** se probó la lógica con navegadores simulados (jsdom) y contra el servidor real, pero **no se vio el diseño** (colores, tamaños, cómo se ve el latido ámbar, los dibujos SVG de la guía). Revísalo con tus ojos en el celular y en el computador.
- **El botón «Atrás» en un celular real:** la lógica está probada con un historial simulado; el comportamiento exacto de cada navegador (Chrome Android, Safari iPhone) hay que confirmarlo en equipos reales.
- **El despliegue en Render y la migración sobre tu base de Supabase:** la migración se probó en SQLite; en PostgreSQL sigue el mismo patrón de la 0020, pero no se ejecutó contra tu base.
- **La IA real:** las pruebas simulan al proveedor; el comportamiento de las sugerencias con Gemini real conviene mirarlo con una pregunta de cada rol.
