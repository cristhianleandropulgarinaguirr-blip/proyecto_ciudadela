# Versión 4.0 — Fase 4: presentación comercial

**Hay una migración nueva (0020):** crea la tabla `solicitudes_demo`. No hay dependencias nuevas (`requirements.txt` no cambia).

Esta fase tiene cuatro piezas:

1. **White-label:** el nombre, el color, los logos y el nombre del asistente se cambian con variables de entorno, sin tocar el código.
2. **Landing en `/`** y la aplicación en `/app/`.
3. **«Solicitar demo»:** guarda el contacto (el administrador lo ve en la app y recibe un aviso) o abre WhatsApp.
4. **`app/seed_demo.py`:** un conjunto de ejemplo de 30 apartamentos con datos realistas, que se crea y se borra con un comando.

---

## 1. Qué se cambió, dónde y por qué

### 1.1 White-label

| Archivo | Qué cambia | Por qué |
|---|---|---|
| `app/config.py` | Variables nuevas: `MARCA_NOMBRE`, `MARCA_NOMBRE_CORTO`, `MARCA_ESLOGAN`, `MARCA_DESCRIPCION`, `MARCA_COLOR`, `MARCA_ASISTENTE`, `MARCA_DIR`, `LANDING_ACTIVA`, `DEMO_WHATSAPP`, `DEMO_CORREO` | Un solo lugar donde se lee la configuración. Sin ninguna de ellas, la app es idéntica a la de antes (Ciudadela Digital, azul marino). |
| `app/marca.py` (**nuevo**) | Convierte esas variables en lo que ve el navegador: calcula la paleta a partir de **un** color, rellena el HTML, genera el manifest y la «huella» de la marca | Es el único sitio donde vive «cómo se personaliza»; el resto del código solo pide `marca.nombre()`. |
| `app/main.py` | Rutas nuevas `/app/` y `/app/manifest.webmanifest` (se arman al vuelo con la marca); `/app/img/…` sirve el logo del cliente si existe en `marca/`; la marca entra en la versión del service worker | Para que el nombre y el color lleguen a la pestaña, al manifest (nombre bajo el icono del celular) y al service worker. Si cambia la marca, todos los celulares descargan la versión nueva en vez de seguir viendo la vieja. |
| `frontend/index.html` | Los textos fijos pasaron a marcadores (`__MARCA_NOMBRE__`, etc.) y se añadió `<meta name="marca">` | El servidor los rellena (escapados: un nombre con comillas o `<` no puede romper la página). |
| `frontend/js/marca.js` (**nuevo**) | Lee la marca del `<meta>` y la expone a los demás archivos; si falta, usa los valores de siempre | La app nunca se queda sin nombre. |
| `frontend/js/ui.js`, `vistas/login.js`, `chat.js`, `vistas/configuracion.js`, `tema.js`, `sw.js` | Leen el nombre/eslogan/asistente/color de la marca en vez de tenerlos escritos | Eran los sitios donde estaba escrito «Ciudadela Digital» / «Ciudabot». |
| `app/routers/reportes.py`, `paz_y_salvo.py`, `comercio.py`, `asistente.py`, `app/notificaciones.py`, `publico.py` y `frontend/pase`, `frontend/verificar` | Los PDF, correos, el chat de IA y las páginas públicas usan el nombre de la marca | Un PDF o un correo con otro nombre delataría que la app es de otro. En los PDF el encabezado ahora es el **nombre del conjunto** (`CONJUNTO_NOMBRE`), que por defecto es el mismo «Ciudadela Digital». |
| `marca/LEEME.md` (**nuevo**) | Explica qué logos se pueden reemplazar y con qué nombres | Solo se sirven los nombres de la lista (nunca un archivo arbitrario de esa carpeta). |

**Cómo funciona el color:** pones `MARCA_COLOR=#8A1C2B` y el sistema calcula las variantes (fondo del menú, tarjetas, versión para modo oscuro). Si el color es demasiado claro para llevar texto blanco encima (por ejemplo, un amarillo), **se oscurece solo** hasta que el texto de los botones se lea bien. Un color mal escrito se ignora (la app nunca se rompe por una variable).

> **Decisión que conviene que conozcas:** el color de la marca cambia el login, el administrador y la landing. Los colores **por rol** (residente teal, guardia ámbar, inquilino violeta) **no cambian**, porque sirven para distinguir quién está usando la app. Si algún cliente quiere que también los residentes vean su color, es un cambio pequeño; dímelo.

### 1.2 Landing en `/` y app en `/app/`

| Archivo | Qué cambia | Por qué |
|---|---|---|
| `landing/index.html`, `landing/recursos/landing.css`, `landing/recursos/landing.js` (**nuevos**) | La página comercial, con HTML, CSS y JS en archivos separados | Como lo pide tu instructor. El JS no usa librerías. |
| `app/main.py` | `/` sirve la landing con su propia política de seguridad (sin JavaScript dentro de la página); `/landing/…` sirve el css y el js | La plantilla cruda (`/landing/index.html`) **no** se sirve, para que nadie vea los marcadores sin rellenar. |
| `LANDING_ACTIVA` | En `0`, `/` lleva directo a `/app/` como antes | Para la app de un cliente ya contratado no tiene sentido una página comercial. |

La app **ya vivía** en `/app/`; lo nuevo es que `/` ya no la redirige, sino que muestra la landing. La app instalada en un celular **no se afecta** (abre `/app/`).

### 1.3 «Solicitar demo»

| Archivo | Qué cambia | Por qué |
|---|---|---|
| `app/models.py` | Modelo `SolicitudDemo` | Donde se guarda el contacto. |
| `alembic/versions/0020_solicitudes_demo.py` (**nuevo**) | Crea la tabla `solicitudes_demo` y, en PostgreSQL, activa RLS | Ver el aviso de seguridad más abajo. |
| `app/routers/demo.py` (**nuevo**) | `POST /demo/solicitar` (sin sesión), `GET /demo/solicitudes` y `PATCH /demo/solicitudes/{id}` (solo Administrador) | Guardar, listar y dar seguimiento. |
| `app/schemas/demo.py`, `app/constantes.py` (`EstadoDemo`), `app/limitador.py` | Validaciones, estados (Nueva / Contactada / Agendada / Descartada) y el tope de envíos | — |
| `frontend/js/vistas/demos.js` (**nuevo**) y `frontend/js/app.js` | Pantalla «Solicitudes de demo» del administrador, con botones de WhatsApp y llamar | Solo aparece si `LANDING_ACTIVA=1`. |

Es la **única ruta pública que escribe en tu base de datos**, así que va muy limitada:

- máximo **5 envíos por conexión cada 10 minutos** (sobrepasarlo da 429);
- un **campo trampa** invisible: si un robot lo llena, se le responde «ok» pero no se guarda nada ni se avisa;
- el mismo celular **no se duplica en 24 horas** (ni se avisa dos veces al administrador);
- el **consentimiento es obligatorio** (casilla de la Ley 1581 de 2012) y se guarda la fecha en que lo dio;
- **no se guarda la IP** ni nada del dispositivo, solo lo que la persona escribió;
- el celular debe ser colombiano de 10 dígitos (acepta espacios, guiones y +57).

**Botón de WhatsApp:** abre `wa.me` con un mensaje ya escrito (nombre, conjunto, número de apartamentos y ciudad si los llenó). Si además llenó sus datos **y marcó la autorización**, también guarda el contacto. Si no marcó la autorización, abre WhatsApp pero **no guarda nada**. Solo aparece si configuras `DEMO_WHATSAPP`.

### 1.4 `app/seed_demo.py`

Se ejecuta como `python -m app.seed_demo` (igual que `app.seed` y `app.demo_reservas`). Crea:

- **30 apartamentos** (2 torres × 5 pisos × 3), cada uno con propietario, **coeficiente de copropiedad** (los 30 suman **exactamente 100 %**) y cuota proporcional al coeficiente;
- **24 al día y 6 en mora**, con historial de pagos y 3 paz y salvos vigentes;
- 4 inquilinos con contrato activo (más 1 pendiente de aprobación) y 2 guardias;
- ~120 reservas (60 días atrás y 14 adelante, sin choques; las futuras solo de quienes están al día), 12 paquetes, 10 PQRS con respuesta, 8 daños, 5 anuncios, **una votación abierta por coeficiente y otra cerrada**, visitantes y vehículos, 3 trasteos, directorio de emergencias (con los números nacionales reales: 123, 119, 132, 144, 165), negocios de vecinos y bitácora de auditoría.

**Cómo se mantiene seguro:**

- **No crea ningún administrador con clave conocida.** Entras con **tu administrador real** (el de `python -m app.seed`). Lo que aparece «firmado por la administración» (anuncios, respuestas) lo firma un usuario **inactivo** («Administración del conjunto (demo)») que no puede iniciar sesión.
- Todas las cuentas de ejemplo terminan en `@demo.example.com` (un dominio reservado que no existe), así se reconocen y se borran sin tocar nada real.
- **Se niega a correr si la base ya tiene residentes reales** (mezclarlos dañaría los coeficientes y los indicadores). Solo se salta con `--forzar`.
- La clave de las cuentas de ejemplo se **genera al azar** y se muestra al final (o la pones tú con `--clave`).

Comandos:

```
python -m app.seed_demo --crear        # crea el conjunto (pide confirmación y muestra a qué base apunta)
python -m app.seed_demo --borrar       # lo elimina todo, incluida la actividad que se generó durante la demo
python -m app.seed_demo --reiniciar    # borra y vuelve a crear: la demo queda como nueva
python -m app.seed_demo --crear --clave Demo2026x    # eliges la clave (mínimo 8 caracteres)
```

`--borrar` elimina las filas que cuelgan de las cuentas de ejemplo (sesiones, notificaciones, pases QR, votos…). Está comprobado en las pruebas que, después de `--crear` y `--borrar`, **todas las tablas quedan exactamente como estaban**.

---

## 2. ⚠️ Aviso de seguridad que encontré (y arreglé en la migración 0020)

Las migraciones **0018** (paz y salvo) y **0019** (trasteos) crearon sus tablas **sin activar Row Level Security (RLS)** en Supabase, contra la regla que dejó escrita la migración 0008 («toda tabla nueva en PostgreSQL debe activar RLS»). Si tu proyecto de Supabase tiene la API de datos activa, esas dos tablas quedaban expuestas a la clave pública.

La migración **0020 vuelve a ejecutar el bloque idempotente de la 0008**: protege la tabla nueva (`solicitudes_demo`, que guarda nombres y celulares) y repara `paz_y_salvos` y `trasteos`. Es seguro correrla varias veces y no toca datos. En SQLite (tu equipo) no hace nada.

Para comprobarlo en Supabase después de desplegar: *Table Editor → paz_y_salvos / trasteos / solicitudes_demo*: debe decir **RLS enabled**.

---

## 3. Cómo dejarlo funcionando (en este orden)

1. **Copia el proyecto completo** sobre tu carpeta local (no archivos sueltos). Incluye carpetas nuevas: `landing/` y `marca/`.
2. **Migración local:** con el entorno virtual activo, en la carpeta del proyecto:
   ```
   alembic upgrade head
   ```
   Debe decir `Running upgrade 0019 -> 0020`. (`iniciar.bat` ya la corre solo.)
3. **Pruebas:** `pytest -q`. Deben pasar **466** (385 anteriores + 81 nuevas).
4. **Reinicia el servidor** (`Ctrl+C` y `uvicorn` de nuevo; el service worker se recalcula al arrancar) y haz `Ctrl+Shift+R` en el navegador.
5. **Revisa en local** (ver la lista de la sección 5).
6. **GitHub:**
   ```
   git add .
   git commit -m "v4.0: white-label, landing, solicitar demo y seed_demo"
   git push
   ```
7. **Render — antes de que termine el despliegue**, en *Environment* decide estas variables (ver tabla de la sección 4):
   - **Si este servicio es tu app real en producción:** pon `LANDING_ACTIVA=0`. Así `/` sigue llevando a la app como hasta ahora y tus usuarios no ven una página comercial.
   - **Si este servicio es tu demo comercial:** deja `LANDING_ACTIVA=1` y pon `DEMO_WHATSAPP`.
8. **Render despliega solo** al hacer push. El comando de inicio (`alembic upgrade head && python -m app.seed && …`) ya aplica la migración 0020. Espera a que diga **Live**.
9. **Comprueba RLS** en Supabase (sección 2).
10. **Celular:** si tenías la PWA instalada, ciérrala por completo y vuelve a abrirla (el service worker instala la versión nueva en la segunda apertura).

### Recomendación para la demo comercial

Usa un **servicio de Render y un proyecto de Supabase aparte** para la demo (no los de un conjunto real):

1. Crea el servicio nuevo con las mismas variables, `LANDING_ACTIVA=1`, y su propia `DATABASE_URL`.
2. En tu computador, en un `.env` **aparte** (o cambiando temporalmente `DATABASE_URL`) que apunte a la base de la demo:
   ```
   python -m app.seed_demo --crear
   ```
   Te mostrará a qué base apunta, y al final las cuentas para entrar. **Guarda la clave que imprime.**
3. Antes de cada presentación: `python -m app.seed_demo --reiniciar` deja todo como nuevo.

⚠️ **Nunca corras `seed_demo` con el `DATABASE_URL` de un conjunto real.** El script se niega si hay residentes reales, pero no confíes solo en eso: lee la línea «base configurada en .env» que imprime antes de pedir confirmación.

**Dónde llegan las solicitudes de demo:** a la base del servicio que muestra la landing. Entra a esa app como administrador → menú **«Solicitudes de demo»** (y te llega un aviso en la campana y, si activaste push, al celular).

---

## 4. Variables de entorno nuevas (todas opcionales)

| Variable | Ejemplo | Qué hace |
|---|---|---|
| `MARCA_NOMBRE` | `Torres del Alba` | Nombre del producto: pestaña, menú, PDF, correos, chat |
| `MARCA_NOMBRE_CORTO` | `Alba` | Nombre bajo el icono en el celular (máx. 14 letras) |
| `MARCA_ESLOGAN` | `Vive tranquilo, vive en Alba.` | Titular del login (lo que va después de la última coma se resalta) |
| `MARCA_DESCRIPCION` | `Tu conjunto en el celular.` | Descripción corta |
| `MARCA_COLOR` | `#8A1C2B` | Color principal (`#RRGGBB`) |
| `MARCA_ASISTENTE` | `Albita` | Nombre del asistente de chat (por defecto Ciudabot) |
| `MARCA_DIR` | *(vacío)* | Carpeta con los logos del cliente (por defecto `marca/`) |
| `LANDING_ACTIVA` | `1` | `1` = `/` muestra la landing; `0` = `/` lleva a la app |
| `DEMO_WHATSAPP` | `3101234567` | WhatsApp de ventas. Vacío o inválido = sin botón (nunca un enlace roto) |
| `DEMO_CORREO` | `ventas@tuempresa.com` | Correo de ventas que se muestra junto al formulario |

Para **otro cliente**: nuevo servicio de Render + variables `MARCA_*` + `LANDING_ACTIVA=0` + (opcional) sus logos en `marca/`. Si cambias una variable o un logo, **hay que reiniciar/volver a desplegar**: la versión de la caché del celular se calcula al arrancar.

Los nombres de los logos y sus tamaños están en `marca/LEEME.md`.

---

## 5. Qué revisar

**En local** (`http://127.0.0.1:8000`):

- `/` muestra la landing y **«Solicitar demo»** lleva al formulario; **«Ingresar»** lleva a `/app/`.
- Envía el formulario con datos de prueba: debe decir «Solicitud recibida». Entra como administrador → **«Solicitudes de demo»**: aparece, con botones **WhatsApp**, **Llamar** y **Gestionar**.
- Envíalo vacío: muestra los errores en cada campo y no envía nada.
- Prueba con `MARCA_NOMBRE`, `MARCA_COLOR` y `LANDING_ACTIVA=0` en tu `.env` (reinicia cada vez): cambia la pestaña, el login, el menú y el manifest; con `LANDING_ACTIVA=0`, `/` redirige a `/app/` y desaparece «Solicitudes de demo» del menú.
- `python -m app.seed_demo --crear` en una base de prueba: entra con la cuenta de residente al día, la de mora (debe tener las reservas bloqueadas) y la de guardia. Mira Indicadores, Cartera, Votaciones (la abierta pesa por coeficiente) y Trasteos.
- `python -m app.seed_demo --borrar`: la base queda como estaba.

**Ya comprobado por mí** (con 466 pruebas automáticas, la migración sobre una base vacía —subir y bajar—, y el JS real de la landing ejecutado en un DOM simulado con 11 escenarios: envío, errores del servidor, tope de envíos, sin red y los tres casos de WhatsApp).

**No pude comprobar:** cómo **se ve** la landing en un navegador real (no tengo uno en mi entorno). La estructura, los textos y el comportamiento están probados, pero el aspecto visual —espaciados, cómo se ve la maqueta del celular, el móvil— hay que mirarlo tú. Pruébala en el celular y en el computador y dime qué ajustar.

---

## 6. Cosas que debes saber

- **Las páginas públicas del pase y de verificación** toman el **nombre** del cliente, pero conservan sus colores de siempre (tienen su propia hoja de estilo).
- **Pagos en línea:** la landing dice que hoy el residente paga por transferencia y la administración registra el pago. Es lo que hace la app con `PAGOS_SIMULADOS=0`. Si algún día integras una pasarela, hay que cambiar esa pregunta frecuente.
- **No puse precios** en la landing: no los conozco. La pregunta «¿Cuánto cuesta?» invita a pedir la demo. Tampoco inventé testimonios ni cifras de clientes.
- **Los datos de ejemplo** no incluyen documentos PDF (la pantalla «Documentos» sale vacía): es un buen momento en la demo para subir el reglamento en vivo. Tampoco hay correo ni push configurados en una instancia nueva.
- **Los correos de ejemplo** (`@demo.example.com`) no existen: si en la demo se dispara un aviso por correo a un residente de ejemplo, no llegará a nadie.
- **Chat de IA:** en una instancia nueva sin `IA_API_KEY`, el chat responde en «modo básico» con los datos del conjunto de ejemplo.
