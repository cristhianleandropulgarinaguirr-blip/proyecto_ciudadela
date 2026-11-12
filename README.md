# Mi Proyecto SENA – API de Propiedad Horizontal

Backend en **FastAPI + SQLAlchemy + Alembic** para administrar un conjunto residencial:
reservas de zonas comunes, reportes de daños con foto, cartera de administración, control de vehículos y visitantes en portería, cartelera, **códigos QR** (carnet y pases de visitantes), un **directorio comercial** con anuncios de pago, **paquetes y correspondencia** y **contactos de emergencia**.
La seguridad usa **JWT + bcrypt + roles (RBAC)**.

## Tecnologías
Python 3.12+ · FastAPI · SQLAlchemy 2 · Alembic · PyJWT · bcrypt · Pillow · segno (códigos QR) · SQLite (desarrollo) / PostgreSQL en Supabase (producción)

## Estructura
```
app/
  main.py            # aplicación y routers
  config.py          # lee variables de entorno (.env)
  database.py        # motor y sesión de SQLAlchemy
  models.py          # tablas: roles, usuarios, reservas, reportes_danios, vehiculos_visitantes, anuncios,
                     #         codigos_qr, escaneos_qr, publicidad, auditoria, intentos_login,
                     #         visitantes_autorizados, accesos_visitantes, paquetes, contactos_emergencia, notificaciones, pqrs, documentos
  security.py        # bcrypt + creación/validación de JWT
  dependencies.py    # get_current_user (401) y requiere_roles (403)
  archivos.py        # validación de imágenes y PDF
  almacen.py         # dónde se guardan: disco local o Supabase Storage
  seed.py            # crea roles y el primer administrador
  routers/           # auth.py, usuarios.py, modulos.py, anuncios.py, qr.py, comercio.py, auditoria.py,
                     #          visitantes.py, paquetes.py, emergencias.py, pqrs.py, documentos.py, notificaciones.py, reportes.py
  schemas/           # validaciones Pydantic (con ejemplos para Swagger)
alembic/             # migraciones de la base de datos
docs/DER.png         # diagrama entidad-relación (también en docs/DER.md)
tests/               # pruebas automáticas
uploads/             # fotos subidas (no se suben a Git)
```

## Instalación local

```bash
# 1. Crear y activar el entorno virtual
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # Linux / Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env           # Windows   (Linux/Mac: cp .env.example .env)
#    Abre .env y completa SECRET_KEY y ADMIN_PASSWORD.
#    Para generar una SECRET_KEY segura:
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. Crear/actualizar las tablas con Alembic
alembic upgrade head

# 5. Crear los roles y el primer administrador (usa ADMIN_EMAIL / ADMIN_PASSWORD del .env)
python -m app.seed

# 6. Arrancar el servidor
uvicorn app.main:app --reload
```
Abre **http://127.0.0.1:8000/docs** (Swagger UI).

> El archivo `.env` contiene secretos: está en `.gitignore` y **nunca** se sube al repositorio. Solo se sube `.env.example`.

## Interfaz web (Ciudadela Digital)

El frontend vive en `frontend/` (HTML + CSS + JavaScript puro, sin build) y lo sirve la misma API:

```bash
uvicorn app.main:app --reload
# Abre http://localhost:8000  ->  redirige a /app/
```

- `index.html` / `estilos.css`: estructura y estilos (mobile-first, responsivo desde 320 px hasta pantallas grandes).
- `js/api.js`: cliente HTTP, token JWT en `sessionStorage` y manejo de errores de la API.
- `js/ui.js`: componentes y utilidades (toasts, modales, formatos, iconos). Todo el DOM se crea sin `innerHTML` con datos del usuario (evita XSS).
- `js/vistas/`: una pantalla por módulo (resumen, reservas, cartelera, mantenimiento, cartera, portería con historial, usuarios). El menú muestra solo lo que el rol puede usar.
- `js/tema.js`: tema claro / oscuro / automático y preferencias (fondo, animaciones, tamaño de texto), guardadas en el navegador. `img/` trae el logo (versión clara y crema para fondos oscuros) y los dos fondos ilustrados.
- `js/vistas/configuracion.js`: perfil y apariencia (se abre tocando el avatar).
- `iniciar.bat` (Windows): respalda la base de datos en `respaldos/`, aplica migraciones y arranca la app con un doble clic.

**Novedades de la versión 2.1** (recuerda correr `alembic upgrade head`):
- **Historial de portería:** cada entrada y salida queda guardada con hora, duración y quién la registró; se puede filtrar y el administrador lo exporta a Excel (CSV).
- **Cartelera:** el administrador publica reuniones, eventos y avisos; los usuarios confirman asistencia y el administrador ve quién va.
- La documentación de la API sigue en `/docs` y el estado del servidor en `/salud`.

## Fase 2: códigos QR y comercio (versión 2.2) — recuerda correr `alembic upgrade head` e `pip install -r requirements.txt`

### Códigos QR (`/qr`)
- **Carnet:** cada usuario tiene un QR permanente (pantalla *Mi QR*). El guardia lo escanea y ve nombre, rol, apartamento y parqueadero. Por privacidad **no** muestra datos de cartera. Se puede renovar si se pierde el celular.
- **Pase de visitante:** el residente crea un pase con nombre y placa del invitado (válido de 2 h a 3 días) y lo comparte por WhatsApp como imagen. **Primer escaneo = ingreso** (queda en el historial de portería), **segundo escaneo = salida**. Un pase usado, vencido o revocado se rechaza.
- **Seguridad:** el QR solo contiene un token aleatorio de 192 bits (`CD1:…`); no lleva datos personales y se valida siempre en el servidor, por eso se puede revocar al instante. Cada escaneo —también los rechazados— queda en la tabla `escaneos_qr` con quién lo hizo.
- **Escáner:** pestaña *Escanear QR* en Portería. Usa la cámara (`BarcodeDetector`, o `jsQR` en iPhone), un lector USB o el código escrito a mano. **La cámara del navegador exige HTTPS** (o `localhost`): en producción sirve la app con HTTPS; en una red local por HTTP usa el campo de texto.

### Comercio (`/comercio`)
Flujo de un anuncio: `Pendiente de pago → En revisión → Activa → Vencida` (o `Rechazada`).
1. El vecino crea el anuncio (foto opcional, categoría, WhatsApp, plan Semanal / Mensual / Trimestral).
2. Paga por transferencia y pulsa **Ya pagué** con el número del comprobante.
3. El administrador **confirma el pago** (el plazo empieza a correr) o lo **rechaza con un motivo**.
4. Mientras esté activo aparece en el directorio; cada toque en *Escribir por WhatsApp* suma a su contador de contactos. Al vencer desaparece solo y se puede renovar.
- Los precios están en `app/constantes.py` (`PLANES_PUBLICIDAD`, valores de ejemplo) y las instrucciones de pago en la variable `COMERCIO_INSTRUCCIONES_PAGO` del `.env`.
- El cobro es manual a propósito (simple y verificable en la sustentación). Más adelante se puede cambiar por una pasarela como Wompi sin tocar el resto del flujo.

## Bloque 1: seguridad y auditoría (versión 2.3) — recuerda correr `alembic upgrade head`
- **Contraseñas:** cualquier usuario cambia la suya en *Configuración → Cambiar contraseña* (`POST /auth/cambiar-password`, pide la actual). Si alguien la olvida, el administrador pulsa **Restablecer clave** en *Usuarios*: se genera una clave temporal (se muestra una sola vez) y la persona **debe crear una propia** al entrar. Aún no hay recuperación por correo (ver nota en el bloque 3).
- **Límite de intentos:** 5 fallos seguidos con un correo lo bloquean 15 minutos (`429`). Se cuenta por el correo escrito, exista o no, para no revelar qué cuentas hay. Un acierto reinicia el contador y el bloqueo queda en la auditoría.
- **Auditoría:** pantalla *Auditoría* (solo administrador) y `GET /auditoria/`. Registra quién hizo qué y cuándo en reservas, usuarios, cartera, daños, cartelera y comercio, más los bloqueos y cambios de clave. El registro se guarda en la misma transacción que el cambio.
- **Reservas en portería:** el guardia ve nombre y apartamento de quien reservó (no su correo) y la pantalla abre filtrada en las aprobadas.

## Bloque 2: operación diaria (versión 2.4) — recuerda correr `alembic upgrade head`

### Visitantes autorizados (`/visitantes-autorizados`)
- **Para quién:** personas que entran seguido (familia, empleada, cuidador, contratista). El pase QR de la fase 2 sigue siendo para una visita puntual **con vehículo**.
- **Residente** (pantalla *Visitantes*): autoriza con nombre, documento (cédula o pasaporte), relación, fecha límite opcional y una nota para portería. Máximo 20 personas. Al «retirar» una autorización la persona deja de poder entrar pero **su historial se conserva**; si la vuelve a autorizar se reactiva el mismo registro.
- **Guardia** (Portería → *Visitantes a pie*): busca por nombre o documento (mínimo 3 caracteres) y ve **quién la autorizó**, su apartamento y la nota. Si no aparece, nadie la autorizó. Registra el ingreso y la salida; queda guardado qué guardia lo hizo.
- **Reglas:** se rechaza el ingreso si la autorización venció (la fecha incluye todo el día, hora de Colombia), si quien la dio está desactivado o si la persona ya figura dentro.

### Paquetes y correspondencia (`/paquetes`)
Flujo: `En portería → Entregado` (o `Anulado` si se registró por error).
1. El guardia elige al residente (busca por nombre o apartamento), indica tipo (paquete, correspondencia, domicilio), empresa y descripción.
2. El residente ve en su Inicio y en *Paquetes* que tiene algo esperándolo. Solo ve **los suyos**.
3. Al entregar, el guardia escribe quién lo recoge (si es otra persona) y queda fecha, hora y responsable. Todo —registro, entrega y anulación— queda en la **auditoría**, útil si luego hay reclamos por un paquete perdido.
- `GET /paquetes/destinatarios` solo devuelve nombre y apartamento de los residentes activos (nada de correo ni cartera).
- Aviso al residente: llega a su campana y, si hay correo configurado, también por correo (bloque 3).

### Contactos de emergencia (`/emergencias`)
- Todos los roles ven el directorio y llaman con un toque (`tel:`). Solo el administrador agrega, edita o elimina (máx. 60); cada cambio queda en la auditoría.
- La migración `0006` carga las líneas nacionales de Colombia: **123** (línea única), **112** (Policía), **119** (Bomberos), **132** (Cruz Roja) y **144** (Defensa Civil). Se cargan una sola vez: si el administrador borra alguna, no reaparece. Verifica y agrega los números **locales** de tu conjunto (clínica, CAI del cuadrante, gas, ascensores).

## Bloque 3: comunicación y reportes (versión 2.5) — recuerda `pip install -r requirements.txt` y `alembic upgrade head`

Se agregaron dos librerías (`openpyxl` para Excel y `reportlab` para PDF) y la migración `0007`.

### Notificaciones (la campana)
- Cada usuario ve **solo las suyas** (campana de la barra superior, con contador; se actualiza cada minuto).
- Se generan solos cuando: llega un **paquete**, el administrador **aprueba o cancela una reserva**, se publica un **anuncio**, se sube un **documento** o la administración **responde una PQRS**. Cuando un residente radica una PQRS, se avisa a los administradores.
- **Correo (opcional):** si completas `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y `SMTP_FROM` en `.env`, también se envía correo en tres casos: paquete en portería, respuesta a una PQRS y anuncios de tipo **Urgente**. Sin SMTP la app funciona igual, solo con la campana. Los correos salen **después** de guardar el cambio y en segundo plano, y si el servidor de correo falla no se rompe nada. Con Gmail necesitas una *contraseña de aplicación*.
- **WhatsApp no está incluido:** requiere una cuenta de WhatsApp Business con costo; se puede enchufar después en `app/notificaciones.py`.

### PQRS (`/pqrs`)
Peticiones, quejas, reclamos y sugerencias. Flujo: `Radicada → En trámite → Resuelta → Cerrada`.
- El residente radica (asunto + descripción) y recibe un número tipo `PQRS-2026-0003`. Ve solo las suyas y máximo 5 abiertas a la vez.
- El administrador las ve todas, cambia el estado y responde. Una respuesta sin estado la deja *Resuelta*. Para resolver debe haber respuesta.
- Queda todo en la auditoría y se puede exportar a Excel.

### Documentos del conjunto (`/documentos`)
- El administrador sube **PDF** (reglamento, actas, circulares, financieros) de máximo 10 MB. Se revisa que el archivo sea un PDF real (no solo la extensión) y se guarda con nombre aleatorio.
- Todos los usuarios con sesión iniciada los descargan; **no hay enlaces públicos**. Al eliminar uno se borra también el archivo.

### Reportes (`/reportes`)
| Reporte | Quién | Formato |
|---|---|---|
| Cartera (cuota, saldo y estado por residente, con totales) | Administrador | Excel |
| PQRS, paquetes, ingresos de visitantes a pie, auditoría | Administrador | Excel |
| Estado de cuenta (indica «a paz y salvo» si no hay saldo) | Residente (el suyo) · Administrador (cualquiera) | PDF |
- Las horas salen en hora de Colombia y los textos que empiezan por `=`, `+`, `-` o `@` se neutralizan para que Excel no los tome como fórmulas. Cada exportación del administrador queda en la auditoría. El PDF es informativo: para que valga como certificado debe llevar la firma del administrador.

> **Recuperar contraseña por correo:** queda pendiente. Un enlace de recuperación por correo necesita una tabla de tokens con vencimiento para que nadie pueda bloquear la cuenta de otro; mientras tanto el administrador sigue restableciendo claves desde *Usuarios*.

## Versión 2.9: asistente de IA (solo borradores) — recuerda `alembic upgrade head`
La IA **redacta borradores**; nunca radica, publica ni envía nada por su cuenta. Una persona revisa y confirma con los formularios de siempre.

| Quién | Qué hace | Dónde |
|---|---|---|
| Residente | Cuenta el problema con sus palabras y recibe un borrador de **PQRS** o de **reporte de daño**, o consulta el **estado** de sus solicitudes | Botón «Ayúdame a redactarlo» en *Quejas y sugerencias* y *Reportar un daño* |
| Administrador | Describe un aviso y recibe un borrador de **anuncio** con vista previa de a cuántas personas llegaría | «Redactar con IA» al crear un anuncio |

**Activarlo (gratis):** crea una clave en Google AI Studio (https://aistudio.google.com/apikey) y en `.env` pon `IA_API_KEY=...` (en Render: variable de entorno). Sin clave el asistente queda apagado y la app funciona igual. El modelo por defecto es `gemini-3.5-flash` (los anteriores, como `gemini-2.5-flash`, ya no están disponibles para cuentas nuevas). Para ver qué modelos tiene tu cuenta y probar la clave: `python -m app.diagnostico_ia`. Otras variables: `PROVEEDOR_IA` (`gemini`, `groq` o `compatible`), `IA_MODELO`, `IA_PENSAMIENTO` (`low` por defecto: respuestas rápidas en Gemini 3.x), `IA_TIMEOUT_SEGUNDOS` (45), `IA_LIMITE_DIARIO_USUARIO` (10) e `IA_LIMITE_DIARIO_GLOBAL` (100). Los nombres de modelos cambian: confírmalo en la consola del proveedor.

**Seguridad (por diseño):**
- La IA no tiene herramientas ni acceso a la base de datos; su respuesta se valida con esquemas estrictos y se limpia (sin enlaces ni caracteres de control).
- El mensaje del usuario va delimitado como *datos* (defensa contra inyección de instrucciones) y se ocultan correos y números largos (posibles cédulas) antes de salir del servidor. Nunca se envían nombre, apartamento ni datos de otros usuarios.
- «¿Cómo va mi solicitud?» lo responde el backend leyendo solo las solicitudes de esa persona; la IA no las ve.
- Si el mensaje suena a emergencia (incendio, gas, herido…) no se consulta la IA: se remite a los contactos de emergencia y a la línea 123.
- La clave vive solo en el servidor y viaja en un encabezado (no en la URL). Topes diarios por persona y globales. La auditoría registra *que* se usó el asistente, nunca el texto.
- **Privacidad:** en el plan gratuito de Google, lo que se envía puede usarse para mejorar sus productos. Para demostraciones usa datos ficticios; para operar con residentes reales usa un plan de pago o un proveedor con garantías de privacidad, y ajusta la política de datos.

## Versión 3.0: color por rol, cámara en las fotos y más velocidad — recuerda `alembic upgrade head` (migraciones 0011 y 0012)

**Color por rol.** Cada rol tiene su identidad: Administrador = azul marino, Residente = verde esmeralda, Guardia = cobre/ámbar (modo claro y oscuro).
Todo vive en variables CSS al final de las variables de `frontend/estilos.css` (`:root[data-rol="…"]`); `js/tema.js` pone el atributo `data-rol` según el usuario.
Para cambiar un color basta con editar esas variables.

**Cámara.** `frontend/js/foto.js` es un selector reutilizable («Tomar foto» + «Galería»). En celular abre la cámara nativa; en computador, la webcam (necesita HTTPS o `localhost`).
La foto se reduce y comprime en el navegador antes de subir. Está en Daños y en la imagen de Comercio; para usarlo en otra pantalla: `selectorFoto({...})`, agregar `.el` al formulario y leer `.archivo()`.

**Foto en Paquetes (opcional).** Al registrar la llegada, portería puede tomar o elegir una foto como evidencia. Se sube justo después de crear el paquete (`POST /paquetes/{id}/foto`, solo Guardia/Administrador y solo mientras está en portería); la ven el destinatario, el guardia y el administrador (`GET /paquetes/{id}/foto`, con `?miniatura=true` para la versión liviana). Migración `0012` (`paquetes.foto_url`).

**Rendimiento.**
- Las pantallas se cargan solo cuando se abren (`import()` en `app.js`); las de la barra inferior se precargan en segundo plano.
- `GET /app/sw.js` se genera en el servidor con una versión calculada de los archivos: la caché del celular se renueva sola en cada despliegue con cambios (no hay número que subir a mano).
- Compresión GZip del texto y caché de una semana para `/app/img/`.
- Las fotos subidas se reducen a 1600 px, se enderezan y se les quitan los metadatos EXIF (incluido el GPS). Daños y Comercio guardan además una miniatura (`m_<nombre>`); `?miniatura=true` la pide.
- Migración `0011`: índices en reservas y reportes de daños. Pool de conexiones ajustado para PostgreSQL.
- Caché corta (12 s) de lecturas en el navegador, que se vacía con cualquier escritura.

**Nota sobre Render (plan gratis):** el servicio se duerme tras 15 minutos sin uso y tarda cerca de un minuto en despertar; eso pesa más que cualquier optimización de código.

## Cómo probar la seguridad en Swagger
1. Pulsa **Authorize** 🔒 e ingresa el correo y la contraseña del administrador.
2. Swagger enviará el token en cada petición. Prueba las rutas protegidas.
3. Para probar otro rol: con el administrador crea un guardia o un residente con `POST /usuarios/` y vuelve a autorizar con esa cuenta. **No hay registro público**: solo el administrador crea cuentas.

| Código | Significado |
|---|---|
| **401** | No enviaste token, es falso, o expiró |
| **403** | Tu token es válido pero tu rol no tiene permiso para esa acción |

## Roles y permisos

| Acción | Administrador | Residente | Guardia |
|---|:--:|:--:|:--:|
| Iniciar sesión | ✅ | ✅ | ✅ |
| Crear usuarios con cualquier rol, activar/desactivar, asignar parqueadero | ✅ | ❌ | ❌ |
| Solicitar reserva / ver mis reservas / cancelar la mía | ✅ | ✅ | ❌ |
| Ver todas las reservas | ✅ | ❌ | ✅ |
| Aprobar o cancelar cualquier reserva | ✅ | ❌ | ❌ |
| Reportar daños con foto | ✅ | ✅ | ❌ |
| Ver reportes de daños | todos | solo los míos | solo los míos |
| Cambiar estado de un daño | ✅ | ❌ | ❌ |
| Ver estado de cuenta | cualquiera | solo el mío | solo el mío |
| Registrar deuda de un apartamento | ✅ | ❌ | ❌ |
| Registrar un pago recibido (transferencia/efectivo) | ✅ | ❌ | ❌ |
| Pagar administración (simulado, solo con `PAGOS_SIMULADOS=1`) | ✅ | ✅ | ❌ |
| Ingreso/salida de vehículos y ver vehículos dentro | ✅ | ❌ | ✅ |
| Ver y renovar mi carnet QR | ✅ | ✅ | ✅ |
| Crear / revocar pases QR de visitantes | ✅ | ✅ | ❌ |
| Escanear QR en portería y ver la bitácora de escaneos | ✅ | ❌ | ✅ |
| Ver quién reservó cada zona (nombre y apartamento) | ✅ | ❌ | ✅ |
| Autorizar, editar y retirar visitantes frecuentes | ✅ | ✅ (los míos) | ❌ |
| Buscar visitantes y registrar su ingreso/salida a pie | ✅ | ❌ | ✅ |
| Registrar, entregar y anular paquetes | ✅ | ❌ | ✅ |
| Ver paquetes | todos | solo los míos | todos |
| Ver el directorio de emergencias | ✅ | ✅ | ✅ |
| Radicar una PQRS | ✅ | ✅ | ❌ |
| Ver PQRS · responderlas | todas · ✅ | solo las mías · ❌ | ❌ |
| Ver y descargar documentos | ✅ | ✅ | ✅ |
| Subir y eliminar documentos | ✅ | ❌ | ❌ |
| Exportar reportes a Excel | ✅ | ❌ | ❌ |
| Descargar estado de cuenta en PDF | cualquiera | el mío | ❌ |
| Ver mis notificaciones | las mías | las mías | las mías |
| Agregar, editar y eliminar contactos de emergencia | ✅ | ❌ | ❌ |
| Cambiar mi propia contraseña | ✅ | ✅ | ✅ |
| Restablecer la contraseña de otro usuario y ver la auditoría | ✅ | ❌ | ❌ |
| Ver el directorio comercial y contactar negocios | ✅ | ✅ | ✅ |
| Publicar un anuncio, informar el pago y renovarlo | ✅ | ✅ | ❌ |
| Confirmar pagos, rechazar o retirar anuncios, ver ingresos | ✅ | ❌ | ❌ |

## Medidas de seguridad implementadas
- Contraseñas con **bcrypt** (sal incluida). Las claves antiguas en SHA-256 se actualizan solas a bcrypt la próxima vez que el usuario inicia sesión.
- **JWT firmado** con expiración; la clave secreta vive en `.env`.
- El rol se verifica en la base de datos en cada petición: si se desactiva un usuario o se le cambia el rol, aplica de inmediato.
- El registro público **siempre** crea Residentes; nadie puede auto-asignarse el rol Administrador.
- Cada usuario solo accede a sus propios datos (reservas, daños, estado de cuenta).
- Fotos: se valida el tipo, el tamaño (máx. 5 MB) y el **contenido real** de la imagen; se guardan con nombre aleatorio y solo las puede ver el dueño o un administrador.
- Estados y placas validados (Enum / expresión regular); el pago no acepta valores negativos ni mayores al saldo.

## Migraciones (Alembic)
```bash
alembic upgrade head            # aplicar todas las migraciones
alembic current                 # ver en qué versión está la base
alembic downgrade -1            # devolver la última migración
alembic revision --autogenerate -m "describe el cambio"   # crear una nueva tras modificar models.py
```
- `0001` – esquema base (crea solo las tablas que falten).
- `0002` – tabla `roles` y `usuarios.rol_id`. **Conserva los datos**: el texto del rol de cada usuario se convierte a su `rol_id` (Celador → Guardia).
- `0003` – trazabilidad de portería (quién registró cada ingreso/salida) y tablas `anuncios` y `anuncio_asistencias`.
- `0005` – bloque 1: `usuarios.debe_cambiar_password` y tablas `auditoria` e `intentos_login`.
- `0004` – fase 2: tablas `codigos_qr`, `escaneos_qr` y `publicidad`. No toca datos existentes.
- `0010` – versión 2.9: tabla `uso_asistente` (topes diarios del asistente de IA; no guarda el texto de los mensajes); en PostgreSQL con RLS activo.
- `0009` – versión 2.7: tabla `pagos` (comprobantes) y columna `usuarios.politica_datos_fecha`; en PostgreSQL deja `pagos` con RLS activo.
- `0008` – seguridad en PostgreSQL/Supabase: activa RLS en todas las tablas (en SQLite no hace nada).
- `0007` – bloque 3: tablas `notificaciones`, `pqrs` y `documentos`. No toca datos existentes.
- `0006` – bloque 2: tablas `visitantes_autorizados`, `accesos_visitantes`, `paquetes` y `contactos_emergencia` (esta última con las líneas nacionales de emergencia). No toca datos existentes.

## Versión 2.7: más simple para todas las edades — recuerda `alembic upgrade head`

**Navegación.** En el celular hay una barra inferior con **máximo 5 botones** (4 + *Más*) y *Más* abre todas las secciones en botones grandes y agrupados. En el computador sigue el menú lateral completo.
| Rol | Barra inferior del celular |
|---|---|
| Residente | Inicio · Reservas · Mis paquetes · Mis pagos · Más |
| Guardia | Inicio · Portería · Paquetes · Emergencias · Más |
| Administrador | Inicio · Reservas · Cartera · PQRS · Más |

**Palabras de todos los días** (el administrador conserva los nombres de oficina): Cartera → *Mis pagos*, PQRS → *Quejas y sugerencias*, Daños → *Reportar un daño*, y *Mi QR* + *Visitantes* se unieron en **Mis visitas**. El guardia ya no ve Comercio. Los enlaces antiguos (`#/qr`, `#/visitantes`) siguen funcionando.

**Mis visitas** tiene 4 pestañas: **Hoy** (autoriza a alguien solo por hoy con nombre y cédula; se vence sola a medianoche y no ocupa cupo de los 20), **Frecuentes**, **Vehículo** (pase QR de un solo uso) y **Mi carnet**.

**Reservas con calendario:** se elige zona → día (libre / ocupado / alguien ya lo pidió) → hora. El calendario usa `GET /reservas/ocupacion`, que devuelve solo el día y el estado, **nunca quién reservó**.

**Mis pagos y comprobantes:** cada pago queda guardado (tabla `pagos`) con un número `REC-AAAA-000123` y un PDF descargable (`GET /reportes/recibo/{id}.pdf`; lo ve quien pagó y el administrador). Es un comprobante informativo de la app: no reemplaza la factura ni el recibo de caja oficial. Los pagos de versiones anteriores no tienen comprobante porque no se guardaban.

**Sesión del guarda:** dura un turno (12 h por defecto, `GUARDIA_TOKEN_HORAS` en `.env`) para no pedirle la clave a cada rato. Las demás cuentas conservan 60 minutos. Ojo: un computador de portería con sesión larga debe estar en un lugar vigilado.

**Política de tratamiento de datos (Ley 1581 de 2012):** al primer ingreso cada persona ve un resumen en lenguaje simple y debe aceptarlo (queda la fecha y en la auditoría). **El texto es una plantilla** (`frontend/js/vistas/politica.js`): antes de operar con residentes reales hay que ajustarlo (responsable, canal de contacto) y validarlo con un asesor jurídico.

**Instalar como app:** hay `manifest.webmanifest` e íconos. En Android (Chrome) menú ⋮ → *Agregar a la pantalla principal*; en iPhone (Safari) *Compartir* → *Agregar a inicio*. Con HTTP en la red local queda como acceso directo con ícono; la instalación completa como app necesita HTTPS (cuando publiques el sistema).

### Ver cómo se ve en el celular
1. **Sin celular (en el computador):** abre la app en Chrome o Brave, pulsa `F12` y luego `Ctrl + Shift + M` (modo dispositivo). Elige un modelo (por ejemplo *iPhone SE*, que es pequeño) y recarga con `Ctrl + R`.
2. **Con tu celular real:** conéctalo al **mismo Wi-Fi** del computador, ejecuta **`.\iniciar-celular.bat`**, y abre en el celular la dirección que aparece en la ventana (`http://192.168.x.x:8000`). Si Windows pregunta por el Firewall, elige *Redes privadas*. Úsalo solo en un Wi-Fi de confianza: mientras está encendido, cualquiera en esa red puede abrir la app.

## Versión 2.8: GitHub + Supabase + instalar como app — recuerda `pip install -r requirements.txt`

Sin migraciones nuevas. Qué cambió:
- **Archivos en la nube:** `app/almacen.py` guarda fotos y PDF en disco (`ALMACEN=local`) o en un bucket **privado** de Supabase Storage (`ALMACEN=supabase`). El navegador nunca habla con Supabase: la API descarga el archivo y lo entrega solo a quien tiene permiso.
- **Pagos reales:** el botón «Pagar ahora» es una **simulación** y solo funciona con `PAGOS_SIMULADOS=1` (demostración). En producción va en `0`: el residente paga por transferencia y el administrador pulsa **Cartera → Registrar pago** (`POST /administracion/registrar-pago/{id}`): descuenta del saldo, genera el comprobante `REC-…`, avisa al residente y queda en la auditoría. `GET /administracion/config-pagos` le dice a la pantalla cuál modo está activo.
- **Instalar como app (PWA):** `frontend/sw.js` (service worker) + botón **Ajustes → Instalar**. La app abre desde la pantalla principal; los archivos de la app se guardan para abrir sin internet, pero **los datos de la API nunca se guardan en el dispositivo**. Necesita HTTPS (queda automático al publicar en Render).
- **Cabeceras de seguridad** en todas las respuestas (`nosniff`, anti-iframe, HSTS bajo HTTPS, cámara solo para la propia app).
- **GitHub:** `.github/workflows/ci.yml` corre las pruebas en cada push; `migrar-supabase.yml` es un botón para crear las tablas en Supabase sin instalar nada. `render.yaml` publica la app desde el repositorio.

### Publicar paso a paso (GitHub → Supabase → Render)
1. **GitHub:** crea un repositorio **privado** y sube el proyecto (`git init`, `git add .`, `git commit -m "v2.8"`, `git remote add origin …`, `git push -u origin main`). Comprueba que `.env` NO aparezca en GitHub (está en `.gitignore`).
2. **Supabase:** *New project*, región **East US (N. Virginia)**. Guarda la clave de la base. Luego:
   - **Connect → Session pooler** → copia la cadena como `DATABASE_URL` (ver sección siguiente para los símbolos de la clave).
   - **Storage → New bucket** → nombre `ciudadela-archivos`, **privado** (no marques *Public*).
   - **Settings → API Keys** → copia la **Secret key** (`sb_secret_…`) y la **Project URL**.
3. **Crear las tablas desde GitHub:** en el repositorio, *Settings → Secrets and variables → Actions* agrega `DATABASE_URL`, `ADMIN_EMAIL` y `ADMIN_PASSWORD`. Ve a *Actions → Aplicar migraciones a Supabase → Run workflow*. Al terminar, revisa en Supabase → *Table Editor* que existan las tablas.
4. **Render:** *New → Blueprint* → elige el repositorio. Render lee `render.yaml` y te pide los valores marcados `sync: false`: `DATABASE_URL`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY` y `PAGOS_INSTRUCCIONES`. Al terminar te da una dirección `https://….onrender.com`.
5. **Probar:** entra con el administrador, crea un residente, sube un PDF en *Documentos* y revisa que aparezca en Supabase → Storage. En el celular abre la dirección → *Ajustes → Instalar*.
6. Desde ahora, cada `git push` a `main` actualiza la app solo.

**Límites del plan gratuito de Render:** el servicio se duerme tras 15 min sin uso y tarda cerca de 1 minuto en despertar (molesto para la portería); para operar con un conjunto real usa un plan de pago. Los archivos ya no se pierden porque viven en Supabase.
**Reglas de oro:** la `SUPABASE_SECRET_KEY` solo en Render/GitHub Secrets, nunca en el código ni en el frontend; deja `PAGOS_SIMULADOS=0` en producción.

## Conexión a Supabase (PostgreSQL)
La app ya está probada contra PostgreSQL 16 real (migraciones, seed y los flujos de los 3 bloques). **No hay que cambiar código**, solo configuración.

1. **Crea el proyecto** en [supabase.com](https://supabase.com) (New project). Elige la región más cercana (para Colombia suele ser *South America – São Paulo*) y **guarda la contraseña de la base de datos**: Supabase no la vuelve a mostrar completa.
2. **Copia la cadena de conexión:** botón **Connect** (arriba) → método **Session pooler** (puerto 5432). Usa *session pooler* y no *Direct connection*: la conexión directa solo funciona por IPv6 y muchas redes domésticas no la soportan.
3. **Pégala en tu `.env`** como `DATABASE_URL`, cambiando `[YOUR-PASSWORD]` por tu clave y agregando `?sslmode=require` al final. Si la clave tiene símbolos (`@ # / : ?`) conviértelos: `@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`, `?` → `%3F`. El usuario tiene el formato `postgres.<id-del-proyecto>` (no solo `postgres`).
4. **Crea las tablas y el administrador:** `alembic upgrade head` y luego `python -m app.seed`. Revisa en Supabase → *Table Editor* que aparezcan las 21 tablas.
5. **Arranca la app** como siempre (`iniciar.bat` o `uvicorn app.main:app`) y entra con el administrador del seed.

**Seguridad (ya incluida):** las tablas creadas por migraciones nacen sin *Row Level Security* y Supabase publica `public` con una clave pública (`anon`). La migración `0008` activa RLS en todas las tablas y le quita permisos a `anon`/`authenticated`; tu backend no se afecta porque entra como `postgres` (dueño de las tablas). Reglas: **nunca** pongas la clave `service_role` ni la `anon` en el frontend, no subas el `.env` a GitHub, y si agregas una tabla nueva en una migración, activa RLS en ella (`ALTER TABLE public.<tabla> ENABLE ROW LEVEL SECURITY;`) o vuelve a correr la lógica de `0008`.

**Archivos (fotos y PDF):** desde la versión 2.8 pueden guardarse también en Supabase Storage (`ALMACEN=supabase`, ver abajo). Con `ALMACEN=local` siguen en la carpeta `uploads/` y hay que respaldarla aparte.

**Si no conecta:** `password authentication failed` → clave mal copiada o sin codificar; `could not translate host name` / `Network is unreachable` → usaste *Direct connection*, cambia a *Session pooler*; `Tenant or user not found` → el usuario debe ser `postgres.<id-del-proyecto>`.

## Pruebas automáticas
```bash
python -m pytest -q
```
Usan una base de datos temporal; no tocan tus datos. Cubren login, 401/403, roles, reservas, mora y pagos, subida de imágenes, portería, cartelera, códigos QR (ingreso/salida, vencimiento, revocación, bitácora), comercio (flujo de pago, vencimiento, permisos), seguridad (contraseñas, bloqueo de login, auditoría), visitantes autorizados, paquetes, contactos de emergencia y las migraciones.

## Flujo de trabajo con Git (trabajo en equipo)
```bash
git checkout -b feature/seguridad-jwt        # cada integrante trabaja en su rama
git add .
git commit -m "feat: login con JWT y bcrypt"
git push origin feature/seguridad-jwt        # luego Pull Request hacia main
```
