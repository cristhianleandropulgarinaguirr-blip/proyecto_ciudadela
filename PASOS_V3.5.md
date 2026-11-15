# Versión 3.5 — Fase 0 (rendimiento) y Fase 1 (portería sin fricción)

## 1. Qué trae y por qué
### Fase 0 · Rendimiento
Se midió la app con un conjunto «grande» (200 residentes, 3.000 reservas, ~2 años de historial) con `python -m scripts.medir_rendimiento`.
**Hallazgo:** no había consultas repetidas (N+1) en ninguna pantalla; el problema real era el *peso*: la pantalla de inicio del administrador y del guardia descargaba TODO el historial de reservas (~670 KB) solo para contar las pendientes o las de hoy.

| Pantalla | Antes | Después |
|---|---|---|
| Inicio del guardia (`/reservas/listar`) | 671 KB | 1 KB (solo las aprobadas de hoy) |
| Inicio del administrador | 671 KB | 11 KB (solo las pendientes) |
| Pantalla «Reservas» (admin/guardia) | 671 KB | 121 KB (últimos 90 días + todo lo futuro) |

- `app/routers/modulos.py`: `GET /reservas/listar` acepta filtros opcionales `estado`, `desde`, `hasta` y `limite`. **Sin filtros responde igual que antes** (no se rompe nada).
- `frontend/js/vistas/resumen.js` y `reservas.js`: piden solo lo que necesitan. `ui.js`: nueva función `diaLocal()` (fecha local AAAA-MM-DD).
- Migración `0016`: 3 índices que faltaban (`usuarios.rol_id`, `vehiculos_visitantes.estado` y `.fecha_ingreso`). PostgreSQL no indexa solo las llaves foráneas.
- `scripts/medir_rendimiento.py`: para repetir la medición cuando quieras (usa una base temporal, no toca la tuya).
- El seed ya era idempotente (v3.4); no hizo falta cambiarlo.

### Fase 1 · Portería sin fricción
1. **Enlace público del pase** `/pase/<token>`: el residente lo comparte por WhatsApp. El visitante ve su QR grande (negro sobre blanco), su PIN, «Cómo llegar» (Google Maps / Waze) y mantiene la pantalla encendida. *Nota técnica:* una web no puede subir el brillo del celular; se usa Screen Wake Lock para que la pantalla no se apague.
   - Archivos: `app/routers/publico.py`, `frontend/pase/pase.html`, `pase.css`, `pase.js` (HTML y CSS separados).
   - Seguridad: solo el token (192 bits) da acceso; token falso o de carnet → 404; muestra solo nombre del visitante, placa y apartamento destino (nunca el nombre del residente ni su cartera); límite por IP; sin caché, sin indexar y sin enviar «referer»; CSP estricta (sin scripts ni estilos inline).
2. **PIN de 6 dígitos** en cada pase de visitante: `POST /qr/escanear-pin`. El guardia lo escribe en el mismo campo del escáner (6 dígitos = PIN). Funciona igual que el QR (1.ª vez ingreso, 2.ª salida). 8 PIN incorrectos en 10 min bloquean al guardia unos minutos (429). Es único entre pases vigentes; los intentos fallidos no guardan el número probado.
3. **«Estoy en camino» / «Ya llegué»** (en la página del pase): «en camino» avisa al residente; «llegué» avisa a la portería y al residente (campana + push). Espera de 5 minutos entre avisos iguales.
4. `app/limitador.py`: freno en memoria (sin consultas extra a la base de datos).
5. Migración `0017`: columnas `pin`, `aviso_camino`, `aviso_llegada` en `codigos_qr` + índice del PIN.
6. En «Mi QR» el residente ve el PIN y los botones **Compartir enlace**, Copiar enlace, Enviar imagen y Descargar.

## 2. Variables nuevas (todas opcionales)
`CONJUNTO_NOMBRE`, `CONJUNTO_DIRECCION`, `CONJUNTO_LATITUD`, `CONJUNTO_LONGITUD` (ver `.env.example`). Con coordenadas, «Cómo llegar» apunta al punto exacto de la portería. En Render: Environment → agregarlas (ya están declaradas en `render.yaml`).

## 3. Pasos para dejarlo funcionando
1. **Migración: SÍ** (0016 y 0017). En tu PC: `alembic upgrade head`. En Render se aplica sola al desplegar.
2. Pruebas: `pytest -q` → deben pasar **274**.
3. Prueba a mano (con el servidor corriendo):
   - Residente: Mi QR → Pases con vehículo → crear pase → ver el PIN → «Compartir enlace».
   - Abre el enlace en otra pestaña/celular (sin sesión): debe verse el QR, el PIN y los botones. Pulsa «Estoy en camino» y revisa la campana del residente; pulsa «Ya llegué» y revisa la del guardia.
   - Guardia: Portería → Escanear QR → escribe el PIN de 6 dígitos → «Ingreso registrado»; repítelo → «Salida registrada».
   - Admin y guardia: el inicio debe cargar igual que siempre; la pantalla Reservas muestra los últimos 90 días y lo futuro.
4. GitHub: `git add .` · `git commit -m "v3.5: rendimiento de reservas, enlace público del pase, PIN y avisos"` · `git push`.
5. Render despliega solo. En los logs deben aparecer «Running upgrade 0015 -> 0016» y «0016 -> 0017», y luego uvicorn sin errores.
6. Celular: cerrar y abrir la app para instalar la versión nueva. Los pases creados ANTES de esta versión no tienen PIN (se creará en los nuevos).
7. Opcional: define `CONJUNTO_NOMBRE` y las coordenadas en Render para que el visitante vea el nombre del conjunto y el mapa.

## 4. Límites conocidos
- El limitador vive en la memoria de cada proceso (suficiente para un servicio). Con varias instancias habría que pasarlo a Redis (solo cambia `app/limitador.py`).
- El plan gratuito de Render duerme el servicio tras 15 min: el primer visitante que abra el enlace puede esperar ~1 min. Para operar de verdad, plan de pago.
