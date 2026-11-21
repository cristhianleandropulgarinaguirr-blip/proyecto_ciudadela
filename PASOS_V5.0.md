# Versión 5.0 · Demo aparte de tu app, «Solicitar demo» directo a WhatsApp y pantallas que no se aplastan

**No hay migración nueva, ni dependencias nuevas.** Pruebas: ver el resultado al final de este archivo (se corrieron las de Python y las 9 de Node).

## 1. Qué se cambió, dónde y por qué

### A. Letras verticales en «Usuarios» (y en otras secciones)
**Qué pasaba:** entre ~700 y ~1400 px de pantalla, el nombre y el correo se veían una letra por línea. Yo lo reproduje en un navegador de pruebas: pasaba también en **Inicio, Reservas y Portería** (filas de lista) y en **Cartera** (se desbordaba hacia el lado).
**Por qué:** el diseño se elegía por el ancho de la *ventana*, pero el menú lateral y las dos columnas dejan a cada tarjeta mucho menos sitio. Los botones se quedaban con todo el ancho y el texto con casi nada; y `overflow-wrap: anywhere` deja que el navegador aplaste el texto hasta una letra.

| Archivo | Cambio |
|---|---|
| `frontend/estilos.css` | **Filas** `.item` y `.vehiculo`: ahora el texto siempre tiene un ancho mínimo (14 rem) y, si los botones no caben al lado, pasan a la línea de abajo. **Tablas**: cada tabla mide el ancho de *su tarjeta* (container query): angosta → tarjetas; media → tarjetas en 2 columnas; ancha → tabla de verdad (720 px de tarjeta; las tablas con muchas columnas, 1080 px). La columna del nombre tiene un mínimo de 19 rem y la tarjeta se desplaza de lado antes que aplastar el texto. `.main { width: 100% }` (sin esto la zona de contenido se encogía). Cinta «DEMO». |
| `frontend/js/vistas/residentes.js`, `cartera.js` | Una clase más: `tabla-ancha` en su tabla. |

**Qué verás:** en una pantalla de portátil (~1366 px) Usuarios se muestra como tarjetas en 2 columnas (se lee bien); desde ~1480 px, como tabla. Es a propósito: esa tabla necesita ~1070 px y antes no los tenía.

### B. «Solicitar demo» directo a WhatsApp
| Archivo | Cambio |
|---|---|
| `landing/recursos/landing.js` | Al tocar **Solicitar demo** se validan los datos y **WhatsApp se abre en ese mismo toque** con el mensaje ya escrito (nombre, conjunto, celular…). Desaparece la pantalla que preguntaba si quería ir. El guardado del contacto y el aviso a tu Telegram van en segundo plano. Se arregló un error del botón anterior: `window.open(..., "noopener")` devuelve `null`, así que el código creía que lo habían bloqueado y abría WhatsApp **dos veces**. |
| `landing/index.html` | Se quita el segundo botón «Escribir por WhatsApp» (ya sobra) y la casilla de autorización deja de ser obligatoria. |
| `app/avisos_demo.py` | El aviso de Telegram dice de dónde vino la solicitud. |

**Sobre la autorización de datos (Ley 1581):** con la casilla marcada se guarda el contacto y te llega el aviso a Telegram. Sin marcarla, WhatsApp igual se abre (el cliente envía el mensaje él mismo) y **no se guarda nada** en el servidor. Si no hay `DEMO_WHATSAPP` configurado, vuelve al comportamiento anterior (se guarda y se muestra «Solicitud recibida»; ahí la casilla sí es obligatoria). No soy abogado: confirma con tu instructor/asesor que este texto de autorización te sirve.

### C. La demo ya no se mezcla con tu app (ni en local)
**Qué pasaba:** `iniciar-demo.bat` usaba **la misma base de datos** que tu app real (y la misma cookie de sesión).
**Ahora**, con `MODO_DEMO=1` (lo activa `iniciar-demo.bat`):
- Usa **su propia base**: `demo.db` (o `DEMO_DATABASE_URL`). **Ignora** `DATABASE_URL`. Si alguien la apunta a `propiedad_horizontal.db`, la app se niega a arrancar.
- Guarda archivos en `uploads_demo/` y **nunca** en Supabase Storage.
- Cookie de sesión propia (`ciudadela_rt_demo`) y otra clave de firma de tokens: las cookies se comparten entre puertos del mismo equipo (8000 y 8001); sin esto, entrar a la demo te cerraba la sesión real. Un token de la demo es rechazado (401) por la app real.
- Cinta naranja «DEMO» arriba.
- Corre en el **puerto 8001**; la app real sigue en el 8000. Pueden estar abiertas a la vez.
- Administrador propio de la demo: `administrador@demo.example.com`, clave **`Demo2026`** (misma de las demás cuentas de ejemplo). Solo se crea en la base de la demo; si la base tiene usuarios reales, se niega.

| Archivo | Cambio |
|---|---|
| `app/config.py` | `MODO_DEMO`, base/archivos/almacén aislados. |
| `app/sesiones.py`, `app/routers/auth.py`, `app/security.py` | Nombre de cookie y clave de firma distintos en modo demo. |
| `app/main.py` | Cinta «DEMO» en la página de la app; aviso al arrancar; versión 5.0.0. |
| `app/seed_demo.py` | `--local` (prepara la demo local; solo corre con `MODO_DEMO=1`), `--con-admin`. |
| `iniciar-demo.bat` | Reescrito: `MODO_DEMO=1`, migraciones, `seed_demo --local`, puerto 8001. |
| `iniciar.bat` | Solo fija el puerto 8000 de forma explícita. |
| `.gitignore` | `uploads_demo/`. |

**Tu app real y el servicio de demo de Render NO cambian:** sin `MODO_DEMO` todo funciona exactamente como antes.

## 2. Qué hacer después (en este orden)
1. **Descomprime** el zip sobre tu carpeta del proyecto (acepta reemplazar).
2. **Pruebas:** `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
3. **App real:** `.\iniciar.bat` → http://127.0.0.1:8000/app/ . Entra a **Usuarios** y cambia el ancho de la ventana: no debe verse ninguna letra vertical.
4. **Demo:** `.\iniciar-demo.bat` (la primera vez tarda un poco: crea la base `demo.db` y los 30 apartamentos). Se abre http://127.0.0.1:8001/ . Entra a la app con `administrador@demo.example.com` / `Demo2026`. **No deben aparecer tus usuarios reales** y debe verse la cinta «DEMO».
5. Con las dos abiertas a la vez, entra a ambas: la una **no** debe cerrar la sesión de la otra.
6. **Landing** (http://127.0.0.1:8001/): llena nombre, conjunto y celular y toca **Solicitar demo**. Debe abrirse WhatsApp de inmediato con el mensaje escrito. Para que haya número, pon `DEMO_WHATSAPP=3XXXXXXXXX` en tu `.env` (o en el servicio de la demo en Render).
7. **GitHub (importante):** el repositorio tiene una versión más vieja que la v4.8. Sube **en este orden**, un commit cada una: primero v4.8, luego v4.9 y al final esta v5.0 (`git add .`, `git commit -m "v5.0 demo aislada, WhatsApp directo y tablas responsive"`, `git push`).
8. **Render:** si tienes auto-deploy se despliega solo; si no, *Manual Deploy → Deploy latest commit*. No hay variables nuevas obligatorias. Verifica que el servicio de la demo tenga `DEMO_WHATSAPP` y `LANDING_ACTIVA=1`, y que el de la app real tenga `LANDING_ACTIVA=0`.
9. **Celular, ya desplegado:** prueba la landing (el botón debe abrir la app de WhatsApp) y Usuarios en la tableta/celular.

## 3. Cómo dejar la demo como nueva
`python -m app.seed_demo --reiniciar --con-admin --si` (con `MODO_DEMO=1` activo, p. ej. desde el `.bat`), o simplemente borra el archivo `demo.db` y `uploads_demo/` y vuelve a abrir `iniciar-demo.bat`.

## 4. Cómo volver atrás
`git revert` del commit de la v5.0. No hay migración que deshacer. El `demo.db` es un archivo aparte: puedes borrarlo sin afectar nada real.

## 5. Límites honestos
- Lo probé con un navegador de pruebas (Chromium sin pantalla), **no en un celular real**. Revisa la landing y Usuarios en el tuyo.
- WhatsApp: el navegador solo permite abrirlo dentro del toque del botón; por eso se abre antes de guardar. Si por alguna razón no se abre, queda un enlace «¿No se abrió? Toca aquí».
- La demo local de Render (servicio aparte con su Supabase) ya estaba separada; esta versión resuelve la mezcla **en tu computador**.
- Las tablas de «Cargar datos» usan las mismas reglas nuevas, pero no las rendericé con un archivo cargado; las de Usuarios, Cartera e Historial sí se midieron en un barrido de 700 a 1620 px (sin desplazamiento lateral).
- Si abres la demo y tu app real en el **mismo navegador** verás dos cookies distintas; es lo esperado.
