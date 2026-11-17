# Versión 4.1 — Fase 5: puerta de decisión (multi-copropiedad) y rendimiento transversal

**No hay migración nueva** y **no hay dependencias nuevas** (`requirements.txt` no cambia). Es una versión pequeña a propósito: esta fase es sobre todo *revisar y decidir*, y solo se cambia código donde la revisión encontró algo que de verdad lo merecía.

Esta fase tiene dos partes:

1. **La puerta de decisión:** ¿hace falta que una sola instalación atienda a varios conjuntos (multi-tenant)? Respuesta: **no, mientras no haya un segundo cliente.** Se explica el porqué y cómo operar un conjunto por despliegue.
2. **La lista de rendimiento «en todas las fases»:** se revisó punto por punto contra el código real y se midió antes y después.

---

## 1. Resultado de la revisión de rendimiento (punto por punto)

| Punto de la lista | Estado | Qué se encontró |
|---|---|---|
| Agregaciones en SQL, no en Python | **Corregido (3 sitios)** | Los indicadores y las votaciones sumaban/contaban en Python. Ver sección 2. |
| Chart.js solo en el dashboard | **Ya cumplido (mejor aún)** | La app **no usa Chart.js**: los gráficos son SVG propio (`frontend/js/graficos.js`), unos pocos KB en vez de ~200 KB. Solo los usa `indicadores.js`, que se carga bajo demanda. Se agregó una prueba para que nadie lo meta por accidente. |
| Imágenes redimensionadas en el celular antes de subirlas | **Ya cumplido** | `frontend/js/foto.js` reduce a 1600 px y comprime a JPEG. Lo usan los tres formularios que suben fotos (`mantenimiento.js`, `paquetes.js`, `comercio.js`). Los otros dos campos de archivo (`documentos.js` = PDF, `importar.js` = Excel/CSV) no son imágenes. |
| Importaciones en segundo plano | **Decisión: todavía no** | Se midió. Ver sección 3. |
| Caché del service worker para los estáticos nuevos | **Ya cumplido + prueba nueva** | El servidor arma la lista de archivos solo (`app/main.py`, `_archivos_de_la_app`): todo `.js`, `.css`, `.html` o `.webmanifest` nuevo entra a la caché del celular **sin tocar ninguna lista**, y la versión de la caché cambia sola cuando cambia cualquier archivo. Se agregó una prueba que lo verifica. Las imágenes nuevas se guardan la primera vez que se usan (diseño intencional: no se descargan todas al instalar). |
| Comparar con la medición de la Fase 0 al cerrar cada fase | **Hecho** | Ver sección 4. |

---

## 2. Qué se cambió, dónde y por qué

| Archivo | Qué cambia | Por qué |
|---|---|---|
| `app/routers/dashboard.py` | (a) **Promedio de respuesta de PQRS:** antes se traían hasta 5.000 filas con dos fechas y se restaban en Python; ahora la base calcula `COUNT` y `AVG` en una sola consulta. (b) **Visitantes por hora:** antes se traían hasta 50.000 fechas y se repartían en 24 casillas en Python; ahora la base agrupa por hora (`GROUP BY`) y devuelve **máximo 24 filas por tabla**. | A medida que el conjunto acumula historial, la versión en Python trae más y más filas para producir 24 números. En SQL el costo de transferencia es fijo. También se quitaron los topes artificiales (5.000 y 50.000 filas) que podían falsear el resultado en un conjunto muy activo. |
| `app/routers/votaciones.py` | La suma del coeficiente de quienes ya votaron (`peso_ya`) la hace la base con `SUM` en vez de traer cada fila. Se agregó `func` a los imports. | Es la misma regla (agregar en SQL). Con pocos cientos de residentes la ganancia es mínima; se cambió por consistencia y porque no cuesta nada. |
| `scripts/medir_rendimiento.py` | El conjunto de datos de prueba ahora incluye 2.000 PQRS respondidas y 20.000 accesos a pie (cada uno con su salida, como en la vida real). | Sin esos datos, la medición del dashboard salía artificialmente barata y no habría mostrado ninguna diferencia. |
| `tests/test_v41_fase5.py` (**nuevo**) | 3 pruebas: (1) todo archivo estático nuevo queda en la caché del service worker; (2) la app no carga librerías de gráficos; (3) una PQRS con «respuesta anterior a la radicación» (dato corrupto) sigue sin contarse en el promedio. | Para que lo ya optimizado no se pierda en una versión futura. La prueba (3) protege un comportamiento que el código viejo tenía y que se conservó al pasar a SQL. |

**Un detalle técnico que conviene que conozcas:** restar dos fechas directamente en SQL **no funciona igual** en SQLite (tu PC) y PostgreSQL (Supabase). Por eso la resta se hace con `extract('epoch', …)` (segundos desde 1970), que sí funciona en ambos. Se comprobó que el resultado nuevo es **idéntico** al viejo con los mismos datos (mismo promedio de PQRS, mismas 24 cifras por hora, mismo total y hora pico). Lo probé en SQLite; **no pude probarlo contra PostgreSQL real** desde aquí, así que la verificación final está en el paso 4 de la sección 6.

---

## 3. Importaciones en segundo plano: por qué se decidió esperar

Se midió importar el máximo permitido (1.000 filas) con el cifrado de producción (`BCRYPT_ROUNDS=12`, o sea 8 rondas en las claves temporales):

| Filas | Tiempo en esta máquina de pruebas |
|---|---|
| 200 | 3,1 s |
| 1.000 | 14,9 s |

- Un conjunto típico tiene entre 30 y 300 apartamentos: **menos de unos 5 segundos**.
- La pantalla ya bloquea el botón mientras trabaja (`conCarga`) y espera hasta 90 s, así que no hay doble clic ni pantalla congelada sin aviso.
- **Mover esto a segundo plano tiene un costo de seguridad real:** el resultado de la importación incluye las **claves temporales en texto claro**, que hoy se muestran una sola vez y no se guardan en ninguna parte. Un trabajo en segundo plano obligaría a guardarlas en algún sitio hasta que el administrador las descargue. Es un riesgo que no vale la pena asumir sin necesidad.
- **Advertencia honesta:** el plan gratuito de Render tiene mucho menos CPU que mi equipo, así que las cifras allá serán mayores y **no las pude medir**. Si en tu demo o con un cliente real una importación de más de ~500 filas se acerca a los 90 s, ese es el momento de hacerlo (y la salida sería dividir el archivo o pasar a un plan de pago antes que construir el segundo plano).

---

## 4. Comparación con la medición de la Fase 0

Mismos datos, mismo script (`python -m scripts.medir_rendimiento`):

| Pantalla / endpoint | Fase 0 (después de optimizar) | Ahora (v4.1) |
|---|---|---|
| Inicio del guardia (`/reservas/listar` filtrado) | 1 KB | 1,1 KB |
| Inicio del administrador (pendientes) | 11 KB | 11,0 KB |
| Pantalla «Reservas» (últimos 90 días + futuro) | 121 KB | 120,7 KB |
| Consultas N+1 (más de 15 consultas por pantalla) | ninguna | **ninguna** |
| **Cálculo de los indicadores** (`/dashboard/kpis`, con 20.000 accesos a pie y 2.000 PQRS) | 20,8 ms (versión en Python) | **10,0 ms** (≈52 % menos; mismo número de consultas y **resultado idéntico**) |

**Cómo se midió lo de indicadores (y una advertencia sobre el script):** comparé la versión vieja y la nueva **en el mismo proceso, sobre la misma base, alternándolas** 60 veces cada una y tomando la mediana (la versión vieja además tuvo picos de hasta 88 ms; la nueva, máximo 15 ms). Lo hice así porque `python -m scripts.medir_rendimiento` **tiene mucho ruido en los milisegundos**: dos corridas seguidas pueden diferir hasta el doble en una misma ruta, porque mide el endpoint completo (login simulado, JSON, etc.) y una sola corrida de 3 intentos. Por eso, cuando compares versiones con ese script, **fíate de las columnas `SQL` (número de consultas) y `KB` (tamaño de la respuesta), que son exactas**, y toma los `ms` solo como orientación.

Lo logrado en la Fase 0 **se mantiene**. La mejora nueva está en indicadores, y crece con el historial: la versión vieja traía más filas cuanto más datos hubiera.

**Peso de la app en el celular:** 65 archivos, 863 KB sin comprimir (~554 KB comprimidos, el servidor ya comprime con gzip), guardados una sola vez al instalar.

**Una sugerencia para más adelante (no se hizo, no estaba en el plan):** `/anuncios/` devuelve unos 49 KB (120 avisos en la prueba) y lo piden las pantallas de Inicio de los cuatro roles; en el Inicio del administrador `/usuarios/` (55 KB) pesa algo más. Se pueden limitar a lo que el Inicio muestra de verdad (los últimos N avisos, por ejemplo); cambia el contrato de la API, por eso prefiero que lo decidas tú.

---

## 5. La puerta de decisión: multi-tenant

**Decisión: un despliegue por conjunto, hasta que exista un segundo cliente.**

Por qué no conviene construirlo ahora:

- **Hoy no hay ningún cliente que lo necesite.** Es una inversión grande para un problema que todavía no existe.
- **Toca absolutamente todo:** una columna de conjunto en cada tabla, un filtro de conjunto en cada consulta de cada router (un solo olvido sería una filtración de datos entre conjuntos), reglas de seguridad por conjunto en la base, y pruebas para cada una de esas rutas.
- **La separación física ya es una ventaja de venta:** cada conjunto con su propia base de datos significa que los datos de un cliente **no pueden** mezclarse con los de otro. Para propiedad horizontal (datos personales, cartera de vecinos, Ley 1581) eso tranquiliza.
- **La app ya está preparada para esto:** el white-label de la v4.0 (nombre, color, logos, asistente) se cambia solo con variables de entorno, sin tocar código.

**Cuándo sí reabrir la decisión** (cualquiera de estas):
1. Hay un **segundo cliente real** y operar dos despliegues ya cuesta tiempo.
2. Un cliente quiere administrar **varios conjuntos** (una administradora con varias copropiedades) y ver todo junto.
3. Los costos o el mantenimiento de N despliegues superan lo que costaría el multi-tenant.

**Cómo operar un conjunto nuevo (un despliegue por conjunto):**
1. Crear un **proyecto nuevo en Supabase** (su propia base de datos y su propio bucket de archivos).
2. En Render, crear un **servicio nuevo** a partir del mismo repositorio de GitHub (el mismo `render.yaml`, con otro `name`).
3. En las variables de entorno de ese servicio: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_BUCKET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, un `SECRET_KEY` propio y un par `VAPID_*` propio (`python -m app.generar_vapid`).
4. Para que sea **la app del cliente y no la demo comercial:** `LANDING_ACTIVA=0`, más `CONJUNTO_NOMBRE`, `CONJUNTO_DIRECCION` y las variables `MARCA_*` del cliente.
5. Al arrancar, la migración y el seed corren solos (el comando de inicio ya lo hace). Después, el administrador entra y usa la **carga masiva** (Excel/CSV) para crear a los residentes.

Un solo código, N despliegues: cada mejora que subas a GitHub la puedes llevar a todos.

---

## 6. Pasos para dejarlo funcionando

1. **Migración: NO.** No hay tablas ni columnas nuevas.
2. **Copiar los archivos.** Si descomprimes el zip completo sobre tu carpeta, no se pierde nada de lo tuyo (el `.env` y las fotos subidas no van en el zip). Los únicos archivos que cambiaron respecto a la v4.0 son:
   `app/routers/dashboard.py`, `app/routers/votaciones.py`, `scripts/medir_rendimiento.py`, `tests/test_v41_fase5.py` y este `PASOS_V4.1.md`.
3. **Pruebas en tu PC:** `pytest -q` → deben pasar **470** (467 que ya existían + 3 nuevas). Para repetir la medición: `python -m scripts.medir_rendimiento`.
4. **Subir a GitHub:**
   ```
   git add .
   git commit -m "v4.1: Fase 5 - agregaciones en SQL, pruebas de rendimiento y decision multi-tenant"
   git push origin main
   ```
   Render detecta el push y vuelve a desplegar solo.
5. **Prueba a mano después del despliegue en Render** (esto es lo que **no pude comprobar yo**, porque tu base real es PostgreSQL):
   - Entra como **administrador** → **Indicadores**. Deben cargar sin error y mostrar el tiempo promedio de respuesta de PQRS y la gráfica de visitantes por hora. Si ves el mensaje «No pudimos cargar esta sección», abre los registros (*Logs*) de Render y pásamelos: el único punto sensible es el `extract('epoch', …)` en PostgreSQL.
   - Entra como administrador → **Votaciones** → abre «Quién ya votó» de una votación ponderada. Debe mostrar el coeficiente de los que participaron y de los que faltan.
   - En el celular **no hay que hacer nada**: esta versión no toca la interfaz (ningún archivo de `frontend/`), así que la caché del service worker conserva su misma versión y no se descarga nada nuevo.
6. **Antes de presentar el proyecto final:** repite el paso 5 en tu app real **y** en la demo comercial (es otro servicio, con su propio Supabase), porque cada una tiene su propia base de datos.
