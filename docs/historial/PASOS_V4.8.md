# Versión 4.8 · Aviso de demo por Telegram (para ti) + WhatsApp con los datos ya escritos (para el cliente)

CallMeBot (v4.7) tiene el cupo lleno y no deja crear claves nuevas, así que el aviso automático pasó a **Telegram**. **No hay migración nueva ni dependencias nuevas.** Pruebas: 576 en Python y 9 en JavaScript, en verde.

## Cómo queda el flujo (y quién usa qué)
- **El cliente solo usa WhatsApp.** No necesita Telegram ni instalar nada. Llena el formulario en la landing y, al terminar, ve el botón **«Enviar mis datos por WhatsApp»**: se abre WhatsApp con todos sus datos ya escritos hacia tu número y solo toca «Enviar».
- **Tú usas Telegram solo para enterarte.** En cuanto el cliente envía el formulario te llega una notificación al celular con nombre, conjunto, celular, correo, ciudad, apartamentos, mensaje y un enlace «Escríbele por WhatsApp» que abre el chat con ese cliente. Te llega aunque el cliente no toque «Enviar» en WhatsApp.
- **Siempre queda una copia** en Supabase (tabla `solicitudes_demo`) por si Telegram falla.
- Ningún administrador de la app ve estas solicitudes (cambio de la v4.7).

## Qué se cambió y dónde
| Archivo | Cambio | Por qué |
|---|---|---|
| `app/avisos_demo.py` (nuevo; reemplaza a `avisos_whatsapp.py`) | Envía el aviso a la API de bots de Telegram, sin lanzar errores y sin escribir el token en el registro. | Telegram es oficial, gratis y no depende de cupos. |
| `app/routers/demo.py` | Usa el nuevo módulo. Guarda primero y avisa después de responder. | Un fallo de Telegram nunca le llega al cliente. |
| `app/config.py` | Variables `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` (se quitaron las de CallMeBot). | Configuración en un solo lugar. |
| `landing/recursos/landing.js` | El último paso del formulario ofrece el botón de WhatsApp con todos los datos. | Que el mensaje llegue completo a tu WhatsApp sin que el cliente escriba nada. |
| `render.yaml`, `.env.example` | Variables de Telegram en la plantilla del servicio de la demo. | Para no olvidarlas al desplegar. |

## Cómo activar Telegram (una sola vez, ~5 minutos; solo en TU celular)
1. Instala Telegram en tu celular y crea tu cuenta (solo tú).
2. Busca **@BotFather** (con la marca azul de verificado) y escríbele `/newbot`. Pon un nombre (p. ej. «Ciudadela Avisos») y un usuario que termine en `bot` (p. ej. `ciudadela_avisos_bot`).
3. BotFather te da un **token** (algo como `123456789:AAF...`). Es secreto: quien lo tenga controla el bot. No lo subas a GitHub ni lo pegues en capturas.
4. Busca tu bot por su usuario, ábrelo y escríbele **`/start`** (sin esto el bot no puede escribirte).
5. En el navegador del computador abre `https://api.telegram.org/bot` + TU_TOKEN + `/getUpdates` (todo pegado, sin espacios). Busca `"chat":{"id":` y copia el número que sigue: es tu **chat id**. Si la respuesta sale vacía, escríbele otro mensaje al bot y recarga.

## Qué hacer después (en este orden)
1. **Probar en tu computador.** En tu `.env` agrega `LANDING_ACTIVA=1`, `DEMO_WHATSAPP=3224101828`, `TELEGRAM_BOT_TOKEN=...` y `TELEGRAM_CHAT_ID=...`. Ejecuta `.\iniciar-demo.bat`, abre `http://127.0.0.1:8000/`, llena el formulario con un celular distinto al tuyo y marca la autorización. Debe llegarte el aviso a Telegram y el botón verde de WhatsApp debe abrir el chat con los datos escritos. Si no llega, la consola dice si faltó el token/chat o si Telegram respondió error (401 = token malo; 400 = chat id malo o no escribiste `/start`).
2. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
3. **GitHub:** descomprime el zip sobre tu carpeta (acepta reemplazar). Borra a mano `app/avisos_whatsapp.py` y `frontend/js/vistas/demos.js` si todavía existen. Luego `git add .`, `git commit -m "v4.8: aviso de demo por Telegram y WhatsApp con datos"` y `git push`.
4. **Render, servicio de la demo:** en *Environment* agrega `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` (y confirma `LANDING_ACTIVA=1`, `DEMO_WHATSAPP`, `DEMO_CONTACTO`). Si ya habías puesto `CALLMEBOT_APIKEY`, bórrala: ya no se usa. Espera a que termine el despliegue.
5. **Render, app real (`ciudadela-digital`):** no necesita variables de Telegram. Confirma que `LANDING_ACTIVA=0`.
6. **Prueba final en la dirección de la demo:** pide una demo con datos de prueba y confirma (a) «Solicitud recibida» y botón de WhatsApp, (b) aviso en tu Telegram, (c) fila en `solicitudes_demo`.

## Cómo volver atrás
`git revert` del commit. No hay migración que deshacer.

## Límites honestos
- Si el cliente no toca «Enviar» en WhatsApp, no te llega por WhatsApp; por eso existe el aviso de Telegram y la copia en la base.
- Con Render gratis, si la demo está dormida el primer visitante espera ~1 minuto.
- Si algún día quieres el aviso por el propio WhatsApp de forma automática, el camino oficial es la API de WhatsApp Business de Meta (cuenta de empresa y plantilla aprobada).
