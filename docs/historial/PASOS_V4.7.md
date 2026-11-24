> **Reemplazado por la v4.8:** CallMeBot tiene el cupo lleno, así que el aviso al vendedor ahora es por Telegram. Todo lo demás de esta versión sigue vigente. Lee `PASOS_V4.8.md`.

# Versión 4.7 · Las solicitudes de demo llegan a TU WhatsApp y la landing vive solo en la demo

**No hay migración nueva** (la tabla `solicitudes_demo` se conserva como respaldo) y **no hay dependencias nuevas** (`httpx` ya estaba en `requirements.txt`). Pruebas: 576 en Python (antes 573; se quitaron las del administrador y se agregaron las del aviso) y 9 en JavaScript, todas en verde.

## Qué pediste y qué se hizo

| Pedido | Qué se cambió | Dónde | Por qué |
|---|---|---|---|
| Que las solicitudes de demo **no las vea un administrador** | Se quitó la pantalla «Solicitudes de demo», la campana y el aviso push al administrador, y las rutas `GET/PATCH /demo/solicitudes`. | `frontend/js/app.js`, `frontend/js/vistas/mas.js`, `frontend/js/vistas/demos.js` (borrado), `app/routers/demo.py` | Los prospectos son del negocio de quien **vende** la app, no del administrador de un conjunto. Además son datos personales de terceros (Ley 1581): no tienen por qué verlos los administradores de tus clientes. |
| Que **todo llegue directo a tu WhatsApp** | Al enviar el formulario, el servidor guarda el contacto y manda un mensaje a tu WhatsApp con nombre, conjunto, celular, correo, ciudad, apartamentos, mensaje y un enlace `wa.me` para escribirle al cliente con un toque. | `app/avisos_whatsapp.py` (nuevo), `app/routers/demo.py`, `app/config.py` | Un servidor no puede escribirle a un WhatsApp personal sin un servicio intermedio. Se usó **CallMeBot** (gratis, uso personal). Ver «Cómo activarlo». |
| Que la **landing no salga en la dirección de la app** | La landing y «Solicitar demo» ahora dependen de `LANDING_ACTIVA`. En `render.yaml` el servicio de la app real quedó con `LANDING_ACTIVA=0`. Con `0`, `/` abre directo la app y `POST /demo/solicitar` responde 404. | `render.yaml`, `app/routers/demo.py`, `app/main.py`, `.env.example` | El interruptor ya existía (por eso en tu computador `iniciar.bat` abría la app y `iniciar-demo.bat` la landing), pero `render.yaml` tenía `LANDING_ACTIVA=1` en el servicio de la app. Por eso `ciudadela-digital.onrender.com` mostraba la landing. |

Detalles que conviene saber:
- **El contacto se guarda primero y el aviso sale después.** Si WhatsApp o CallMeBot fallan, el cliente igual ve «Solicitud recibida» y el contacto queda guardado. El fallo se anota en el registro de Render (sin escribir tu clave).
- **Un mismo celular no te llega dos veces en 24 horas**, y los topes anti-robots (por IP y global) siguen igual.
- **Dónde ver los contactos guardados:** Supabase de la **demo** → *Table Editor* → tabla `solicitudes_demo`. Ya no se ven dentro de la app.
- Los avisos viejos de la campana con enlace `#/demos` (si los hubiera en la base de la demo) no rompen nada: la app te lleva al Inicio.

## Cómo activar el aviso a tu WhatsApp (una sola vez, ~5 minutos)
CallMeBot es un servicio gratuito de terceros para uso **personal**. No es de Meta; si algún día pasa a ser una operación grande, el camino oficial es la **WhatsApp Business Cloud API** (requiere cuenta de empresa y plantillas aprobadas).

1. En tu celular, entra a https://www.callmebot.com/blog/free-api-whatsapp-messages/ y mira **el número del bot que aparece ahí** (puede cambiar con el tiempo). Guárdalo como contacto.
2. Desde **tu WhatsApp (3224101828)** escríbele exactamente: `I allow callmebot to send me messages`.
3. El bot te responde con un mensaje que dice «API Activated … Your APIKEY is XXXXXX». Si no llega en 2 minutos, la página dice que lo intentes de nuevo pasadas 24 horas.
4. Guarda esa clave: es secreta (quien la tenga puede mandarte mensajes). **No la subas a GitHub.**

## Qué hacer después (en este orden)
1. **Probar en tu computador (opcional pero recomendado).** En tu archivo `.env` agrega `LANDING_ACTIVA=1`, `DEMO_WHATSAPP=3224101828` y `CALLMEBOT_APIKEY=tu_clave`. Ejecuta `.\iniciar-demo.bat`, entra a `http://127.0.0.1:8000/`, llena el formulario con un celular distinto al tuyo y marca la autorización. Debe llegarte el mensaje en menos de un minuto. Si no llega, mira la consola: dice si faltó la clave o si CallMeBot respondió con error.
2. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
3. **GitHub:** descomprime este zip **sobre** tu carpeta del proyecto (acepta reemplazar). Ojo: se **borra** `frontend/js/vistas/demos.js`; si tu carpeta lo conserva, bórralo a mano. Luego `git add .` · `git commit -m "v4.7: solicitudes de demo al WhatsApp del vendedor; landing solo en la demo"` · `git push`.
4. **Render, app real (`ciudadela-digital`):**
   - Entra a *Dashboard → ciudadela-digital → Environment*. Revisa que `LANDING_ACTIVA` sea **`0`** (si el servicio se creó con el Blueprint, el push ya lo pone; si lo creaste a mano, cámbialo tú y guarda).
   - Espera a que termine el despliegue (*Events → Deploy live*).
   - Prueba: abrir `https://ciudadela-digital.onrender.com` debe llevarte **directo al login de la app** (`/app/`). Entra como administrador: ya no existe «Solicitudes de demo» en el menú.
5. **Render, servicio de la demo (donde debe vivir la landing):**
   - Si **ya tienes** un servicio de demo aparte: en *Environment* confirma `LANDING_ACTIVA=1`, `DEMO_WHATSAPP=3224101828`, `DEMO_CONTACTO=Cristhian` y agrega `CALLMEBOT_APIKEY=tu_clave` (y `AVISO_DEMO_NUMERO` solo si el número que activó el bot es distinto de `DEMO_WHATSAPP`). Ese servicio se vuelve a desplegar con el mismo repositorio.
   - Si **todavía no existe**: *New + → Web Service* con el mismo repositorio de GitHub, mismos comandos de build y start que `render.yaml`, y en *Environment* las variables de la plantilla comentada al final de `render.yaml` (con **otra** `DATABASE_URL`/Supabase, para no mezclar la demo con los datos reales). La primera vez corre `python -m app.seed_demo` si quieres el conjunto de ejemplo de 30 apartamentos.
6. **Prueba final en la dirección de la demo:** abre la landing, pide una demo con datos de prueba y confirma que (a) ves «Solicitud recibida», (b) te llega el WhatsApp y (c) la fila aparece en `solicitudes_demo` de Supabase.
7. **Celular:** cierra la PWA por completo y ábrela dos veces para que cargue la versión nueva (el menú ya no trae «Solicitudes de demo»).

## Cómo volver atrás
`git revert` del commit de la v4.7. No hay migración que deshacer.

## Límites honestos
- CallMeBot es gratuito y de terceros: puede tardar, tener límites de mensajes o cambiar su número de bot. Por eso el contacto **siempre** queda también en la base.
- Si en Render gratis el servicio de la demo está dormido, el primer visitante espera ~1 minuto a que despierte; la solicitud se procesa igual.
