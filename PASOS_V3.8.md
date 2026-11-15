# Versión 3.8 — Fase 3: legal y operativo (coeficiente, votación ponderada y trasteos)

## 0. Antes de copiar nada (evita errores raros)
- **Reemplaza la carpeta completa**, no archivos sueltos: esta versión toca archivos que dependen unos de otros (`app.js`, `ui.js`, `votaciones.js`, `residentes.js`, `mas.js`, `estilos.css`, modelos, routers y schemas).
- **Reinicia el servidor** después de copiar (`Ctrl+C` y vuelve a correr `uvicorn`): el «service worker» se calcula al arrancar.
- En el navegador: `Ctrl+Shift+R`; si aún ves la versión vieja, F12 → *Application* → *Service Workers* → **Unregister**, y *Storage* → **Clear site data**.

## 1. Qué trae y por qué

### 1.1 Coeficiente de copropiedad (Ley 675 de 2001)
En propiedad horizontal cada apartamento «pesa» un porcentaje en las decisiones de la asamblea (el coeficiente, que sale del reglamento). Todos los apartamentos suman **100 %**.
- Campo nuevo `usuarios.coeficiente` (porcentaje, 4 decimales, por ejemplo `0,8523`).
- El administrador lo asigna en **Usuarios** (nueva columna «Coeficiente», botón por residente) o lo carga junto con el censo en **Cargar datos** (columna `coeficiente` de la plantilla; acepta `0,8523`, `0.8523` o `0,8523 %`).
- Reglas: solo propietarios (rol Residente) con apartamento; valor mayor que 0 y máximo 100; **la suma de todos los apartamentos no puede pasar de 100** (se valida al asignar y también al importar la planilla); si hay dos copropietarios en el mismo apartamento cuentan **una sola vez** (se toma el mayor valor).
- Resumen: `GET /usuarios/coeficientes/resumen` (cuántos apartamentos faltan y cuánto suman); se ve arriba de la tabla de Usuarios.
- Todo cambio queda en la **Auditoría**.

### 1.2 Votación ponderada con quórum
- Al crear una votación aparece la casilla **«Votar por coeficiente de copropiedad (Ley 675)»**. Obliga a «un voto por apartamento» y **no deja publicarla si algún apartamento no tiene coeficiente** (te dice cuáles faltan).
- Cada voto vale el coeficiente del apartamento (si vota el inquilino con el voto delegado, vale el del propietario). Los resultados muestran, por opción, el **coeficiente** que la eligió y su porcentaje sobre el coeficiente que votó.
- **Quórum:** barra y porcentaje del coeficiente total del conjunto que ya votó. El administrador, en «Quién votó», ve cuánto coeficiente ya participó y cuánto falta.
- El residente ve **cuánto vale su voto** antes de confirmar.
- El **voto sigue siendo secreto**: se guarda quién votó (con su peso, para el quórum) y, por separado, la suma de cada opción; no hay forma de unirlos.
- Las votaciones normales **no cambian**.
- Campos nuevos: `votaciones.ponderada`, `votacion_opciones.peso`, `votacion_participaciones.peso`.

### 1.3 Flujo de trasteos (mudanzas)
Pantalla nueva **Trasteos** (en *Más → Mi día a día*), para residente, inquilino, administrador y guardia:
1. **Solicitud** (residente o inquilino): tipo **Entrada** (llegan muebles) o **Salida** (salen muebles), desde/hasta (máximo 12 h, hasta 60 días de anticipación), empresa, placa y observaciones. Máximo 2 solicitudes abiertas por apartamento.
2. **Validación de paz y salvo** (solo Salida): si el apartamento tiene saldo pendiente, la solicitud se rechaza; si está al día, el sistema enlaza su paz y salvo vigente o **genera uno** (el inquilino no necesita el permiso de «pagar» para mudarse). El estado del paz y salvo se vuelve a comprobar **en cada paso**, porque la cartera puede cambiar.
3. **Aprobación** (administrador): aprueba o rechaza (con motivo). Si la salida ya no tiene paz y salvo vigente, no se aprueba. Si ya hay otro trasteo aprobado en el mismo horario, avisa y pide confirmar.
4. **Alerta al guardia:** al aprobar, los guardias reciben aviso en la campana (y en el celular si activaron los avisos push); también al cancelarse uno aprobado.
5. **Portería:** el guardia ve solo los trasteos aprobados de hoy y de los próximos 7 días, con el estado del paz y salvo. Puede **iniciar** (desde 2 h antes de la hora acordada y hasta que termine la ventana) y **finalizar**. Si en una salida el paz y salvo dejó de ser vigente, el botón se bloquea y el sistema lo impide (el trasteo no debe salir).
- Estados: Pendiente → Aprobado → En curso → Completado; también Rechazado, Cancelado y «Vencido» (se calcula si pasó la fecha sin iniciarse).
- Todo queda en la **Auditoría** y el solicitante recibe avisos de cada paso.
- Archivos: modelo `Trasteo`, `app/routers/trasteos.py`, `app/schemas/trasteos.py`, `frontend/js/vistas/trasteos.js`.

## 2. Qué se cambió y dónde
| Archivo | Cambio |
|---|---|
| `alembic/versions/0019_coeficiente_y_trasteos.py` | **Nuevo.** Agrega las columnas del coeficiente/voto ponderado y la tabla `trasteos`. Se puede correr varias veces sin dañar nada. |
| `app/models.py` | `Usuario.coeficiente`, `Votacion.ponderada`, `peso` en opciones y participaciones, modelo `Trasteo`. |
| `app/constantes.py` | Estados y tipos de trasteo, y los límites (2 abiertas, 12 h, 60 días, 2 h antes). |
| `app/coeficientes.py` | **Nuevo.** Agrupa por apartamento y calcula el resumen/suma. |
| `app/routers/usuarios.py` y `schemas/usuarios.py` | `PATCH /usuarios/{id}/coeficiente` y `GET /usuarios/coeficientes/resumen`. |
| `app/routers/votaciones.py` y `schemas/votaciones.py` | Votación ponderada, quórum y peso por voto. |
| `app/importacion.py` y `routers/importaciones.py` | Columna `coeficiente` en la plantilla y validación de que no pase de 100. |
| `app/routers/trasteos.py`, `schemas/trasteos.py`, `main.py` | Flujo de trasteos; versión 3.8.0. |
| `frontend/js/vistas/trasteos.js` | **Nuevo.** Pantalla de trasteos para los cuatro roles. |
| `frontend/js/vistas/votaciones.js`, `residentes.js`, `importar.js`, `mas.js`, `app.js`, `ui.js`, `estilos.css` | Casilla de coeficiente y quórum, columna de coeficiente, textos, ruta y colores de estados. |
| `tests/test_v38_*.py` | **Nuevos.** 48 pruebas de coeficiente, voto ponderado y trasteos. |

## 3. Pasos para dejarlo funcionando (en este orden)
1. **Descomprime y reemplaza** la carpeta del proyecto con la de este zip (conserva tu `.env`, que no viene en el zip).
2. **Migración: SÍ** (`0019`). En tu PC: `alembic upgrade head`. Debes ver «0018 -> 0019». En Render se aplica sola al desplegar.
3. **Pruebas:** `pytest -q` → deben pasar **todas** (384). Si alguna falla sola y al repetirla pasa, es una prueba sensible a la hora; avísame cuál.
4. **Prueba a mano (10 minutos):**
   - *Admin → Usuarios:* pon coeficientes a dos residentes (por ejemplo 60 y 40). Mira el aviso de arriba: debe decir «completo… suman 100 %». Intenta poner 70 y 40: debe rechazarlo.
   - *Admin → Votaciones → Nueva votación:* marca «Votar por coeficiente»; con un apartamento sin coeficiente debe negarse y decir cuál falta. Con todos cargados, publícala; vota como residente y mira el quórum.
   - *Residente al día → Trasteos → Solicitar trasteo (Salida).* Debe quedar «Pendiente» con su paz y salvo «Vigente». Con saldo pendiente debe negarse.
   - *Admin → Trasteos → Aprobar.* Entra como **guardia**: debe haber un aviso en la campana y el trasteo en su lista. Antes de la hora (más de 2 h) el botón aparece bloqueado; dentro de la ventana, «Autorizar salida» y luego «Registrar fin».
   - Prueba el caso legal: aprueba una salida y, antes de iniciarla, registra un saldo a ese apartamento. Como guardia, el botón debe bloquearse con el aviso del paz y salvo.
5. **Sube a GitHub:** `git add .` → `git commit -m "v3.8: coeficiente, votación ponderada y trasteos"` → `git push`.
6. **Despliegue:** Render redespliega solo al recibir el push y corre la migración. Revisa que el despliegue termine en verde y repite la prueba rápida del paso 4 en la URL pública (en el celular también).

## 4. Pendiente para la Fase 4 (lo que quedó fuera a propósito)
White-label (nombre, logo y colores del conjunto), modo demo (`seed_demo.py`), landing en `/` y multi-copropiedad. Mejoras posibles de esta fase: mayorías calificadas de la Ley 675 (por ejemplo 70 %) y exportar el acta de la votación en PDF.
