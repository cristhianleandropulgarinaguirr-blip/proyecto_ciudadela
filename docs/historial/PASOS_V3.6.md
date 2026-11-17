# Versión 3.6 — Fase 2: valor para el administrador (carga masiva, paz y salvo con QR e indicadores)

## 0. Antes de copiar nada (evita errores raros)
- **Reemplaza la carpeta completa**, no archivos sueltos. Esta versión toca archivos que dependen unos de otros (por ejemplo `ui.js`, `cartera.js` y `app.js`); si copias solo algunos, el navegador muestra errores como «does not provide an export named…».
- **Reinicia el servidor** después de copiar (`Ctrl+C` y vuelve a correr `uvicorn`). El «service worker» (la caché de la app instalable) se calcula al arrancar.
- En el navegador: `Ctrl+Shift+R`; si aún ves la versión vieja, F12 → *Application* → *Service Workers* → **Unregister**, y *Storage* → **Clear site data**.

## 1. Qué trae y por qué
### 1.1 Carga masiva desde Excel/CSV (pantalla «Cargar datos», solo administrador)
Ningún administrador digita 200 residentes ni 200 saldos cada mes. El flujo es en **tres pasos** para no dañar datos por accidente: descargar plantilla → **revisar** (vista previa, no guarda nada) → **importar**.
- **Censo de residentes:** crea las cuentas que faltan (con una clave temporal que se muestra **una sola vez** y se descarga en CSV) y actualiza nombre, apartamento, parqueadero y cuota de los que ya existen. Nunca toca la clave ni el rol de una cuenta existente; si el correo es de un guardia, administrador o inquilino, esa fila se rechaza.
- **Cartera mensual:** reemplaza el saldo de cada apartamento (mayor a 0 = en mora, 0 = al día). Reconoce a la persona por correo o por apartamento. Acepta exportes de **Siigo, World Office y Alegra** (títulos sobre la tabla, columnas «Apto/Inmueble», «Saldo/Deuda/Cartera», valores como `$ 1.250.000`, CSV con `;` y tildes de Windows).
- Seguridad y calidad: máximo 1.000 filas y 2 MB; se valida **todo** el archivo antes de guardar; se guarda en **una sola transacción** (o todo o nada); si hay errores, solo se importa lo válido si el administrador lo pide; todo queda en la **Auditoría**; el CSV de claves neutraliza fórmulas (`= + - @`) para que Excel no las ejecute.
- **Rendimiento:** las claves temporales se cifran con 8 rondas de bcrypt en vez de 12 (≈16 veces más rápido: 200 cuentas tardan ~3,5 s y no ~55 s). Es seguro porque son aleatorias de 72 bits y la persona debe cambiarlas al ingresar (ahí se guardan con las 12 rondas).
- Archivos: `app/importacion.py` (lectura/validación), `app/routers/importaciones.py`, `app/schemas/importaciones.py`, `frontend/js/vistas/importar.js`.

### 1.2 Paz y salvo con código QR de verificación
- El residente (o su inquilino, si le delegó pagar) genera el certificado en PDF **solo si el apartamento está al día**. Sirve 30 días (`PAZ_Y_SALVO_DIAS`), máximo 10 por día. El administrador puede emitirlo para cualquier residente y **revocarlo**.
- El PDF lleva un **QR** que abre `/verificar/<código>`: una página pública (sin sesión) donde un banco, una empresa de trasteos o el guardia comprueba que es auténtico. Estados: **Vigente**, **Vencido** o **No vigente** (revocado o el apartamento volvió a tener saldo; no se revela el motivo para no exponer datos financieros).
- El código es aleatorio de 128 bits; la página pública tiene límite por IP, CSP estricta, sin caché y sin indexar. Se verificó que el QR del PDF real se decodifica a la URL correcta.
- Archivos: modelo `PazSalvo` (migración `0018`), `app/routers/paz_y_salvo.py`, `frontend/verificar/` (HTML, CSS y JS separados), tarjeta «Paz y salvo» en *Mis pagos* y botón «Paz y salvo» por apartamento en *Cartera*.

### 1.3 Indicadores (KPIs) del administrador
Pantalla **Indicadores**: % de cartera al día vs. en mora (con dona), saldo total, zonas más reservadas (90 días), tiempo promedio de respuesta de PQRS, flujo de visitantes por hora con la hora pico (hora de Colombia) y pendientes del día.
- Gráficos en **SVG propio** (`frontend/js/graficos.js`, ~3 KB): sin librerías externas, siguen el tema claro/oscuro y son accesibles (descripción para lectores de pantalla).
- `GET /dashboard/kpis`: todo se calcula en la base de datos con consultas agregadas (12 consultas fijas, ~9 ms, 0,6 KB) y se guarda 60 s en memoria.

### 1.4 Rendimiento: la pantalla Cartera ya no hace una petición por residente
Antes pedía el listado de usuarios y luego el estado de cuenta de **cada** residente (201 peticiones con 200 residentes). Ahora usa `GET /administracion/cartera`: **1 petición, 2 consultas SQL, ~7 ms**. Esto importaba mucho porque la carga masiva llena la app de residentes.

## 2. Variables nuevas (todas opcionales)
`PAZ_Y_SALVO_DIAS` (por defecto 30) y `URL_PUBLICA` (solo si el QR saliera con una dirección interna). Ya están en `.env.example` y `render.yaml`.

## 3. Pasos para dejarlo funcionando
1. **Migración: SÍ** (`0018`, tabla `paz_y_salvos`). En tu PC: `alembic upgrade head`. En Render se aplica sola al desplegar (si ya estaba en 0017 verás «0017 -> 0018»).
2. Pruebas: `pytest -q` → deben pasar **333**.
3. Prueba a mano:
   - Admin → *Más* → **Cargar datos** → *Censo de residentes* → descarga la plantilla, llénala con 3 filas (una con un correo mal escrito), súbela y revisa la vista previa. Importa solo las válidas, descarga el CSV de claves y entra con una de ellas (te pedirá cambiarla).
   - *Cartera mensual*: sube una planilla con `email` y `saldo_pendiente`; mira quién entra o sale de mora.
   - Residente al día → *Mis pagos* → **Generar y descargar**. Abre el PDF, escanea su QR con el celular y confirma que dice «Documento válido». Luego el admin registra un saldo a ese apartamento y recarga la verificación: debe decir «No vigente».
   - Admin → **Indicadores**: gráficos y «Actualizar ahora».
4. GitHub: `git add .` · `git commit -m "v3.6: carga masiva Excel/CSV, paz y salvo con QR, indicadores y cartera en una peticion"` · `git push`.
5. Render despliega solo. En los logs: «Running upgrade 0017 -> 0018» y luego uvicorn sin errores. Si el QR del PDF sale con una dirección rara, define `URL_PUBLICA` en Render (Environment).
6. Celular: cierra y abre la app (o *Clear site data*) para instalar la versión nueva.

## 4. Límites conocidos
- El importador no guarda el archivo entre la vista previa y «Importar»: el navegador lo envía dos veces (así no queda ningún dato personal «en espera» en el servidor).
- La cartera importada **reemplaza** el saldo: no genera recibos de pago (los recibos siguen siendo solo de «Registrar pago»).
- Los indicadores se guardan 60 s: usa «Actualizar ahora» si acabas de importar.
- El paz y salvo certifica el estado de cuotas de administración **a la fecha de emisión**; para efectos legales/bancarios formales, valida con tu administrador si requiere firma manuscrita.
