# Versión 5.6 · Rol Mantenimiento (enlace de técnico, sin cuenta)

Esta versión agrega **una sola función**: el administrador le comparte a un técnico un enlace temporal para que atienda **un** reporte de daño. El técnico no tiene cuenta, no inicia sesión y casi no ve nada. Hay **una migración nueva (0026)** que solo **crea dos tablas**; no modifica ninguna tabla que ya tienes.

> **Regla del proyecto desde ahora:** esta es la **última función nueva**. Lo que sigue es probar, corregir, el informe y el póster.

---

## 1. Cómo funciona (el recorrido completo)

1. Una residente reporta un daño (como siempre).
2. El administrador abre **Daños** y, en esa tarjeta, toca **«Enlace para técnico»**. Elige cuánto dura (1, 3 o 7 días; recomendado 3), opcionalmente para quién es («Plomero · Don Jaime») y toca **Generar enlace**.
3. Lo copia o lo manda por WhatsApp con el botón de la ventana.
4. El técnico abre el enlace en su celular (**sin contraseña**). Ve el apartamento, el título, la descripción y la foto del daño. Elige **«Estoy reparando»** o **«Ya quedó solucionado»**, escribe una nota y sube una foto de evidencia (con la cámara o desde la galería).
5. En cada cambio, la app: actualiza el estado del reporte, guarda la nota y la foto, **registra en la auditoría** y **avisa** a la residente (y a su propietario si ella es inquilina) y al administrador que creó el enlace.
6. Al marcar **Solucionado** el enlace **se cierra solo**: ya no abre nada.

## 2. Lo que se diseñó para que sea seguro

| Decisión | Por qué |
|---|---|
| El enlace es de **un solo reporte** | Si alguien lo reenvía, solo puede ver/tocar ese reporte, nunca otro. |
| **Vence pronto** (72 h por defecto, tope 7 días) | Un enlace viejo perdido por ahí deja de servir solo. |
| El administrador puede **anularlo** al instante, y **crear uno nuevo anula el anterior** | Solo un enlace vigente por reporte: si reenviaron el viejo, ya no funciona. |
| El técnico ve **solo** apartamento, título, descripción y foto | El nombre, el correo y el teléfono de la residente **ni siquiera viajan** en la respuesta (hay una prueba que lo verifica). |
| El técnico solo puede ir **hacia adelante**: a *En reparación* o *Solucionado* | No puede reabrir, volver atrás ni tocar nada más. «Solucionado» exige nota y foto. |
| El token tiene **192 bits** de azar y la foto se guarda **sin GPS** | Imposible de adivinar; la ubicación del celular no queda en el archivo. |
| Todo se valida **antes** de leer la foto subida | Quien no tiene un enlace vigente ni consigue que el servidor procese una imagen. |
| Límites de uso: **10 intentos/10 min por IP** y **12/hora por enlace** | Frena el abuso; el límite por enlace no depende de la IP, que detrás de un proxy puede falsearse. |
| La página tiene **CSP estricta**, no se guarda en caché y no se indexa | Mismo nivel de protección que la página pública del pase de visitante. |

### Riesgos que quedan (hay que conocerlos)

- **Quien reciba el enlace puede reenviarlo.** Está mitigado (un reporte, vence pronto, se anula), no eliminado: mientras esté vigente, cualquiera que lo tenga puede actuar. Si sospechas, **anúlalo** desde la misma ventana.
- **El texto del reporte se muestra tal cual.** Si la residente escribió «llamar a Juan al 300…» en la descripción, el técnico lo verá. Por eso la ventana del administrador **le muestra exactamente lo que verá el técnico** antes de generar el enlace.
- El token se guarda en la base **tal cual** (igual que el del pase de visitante), para que el administrador pueda volver a copiar un enlace vigente. Si alguien leyera la base de datos, vería los enlaces vigentes (que duran pocos días y solo abren un reporte).

## 3. Color del rol

**Mantenimiento = naranja de obra** (casco y chaleco de seguridad). Los demás: Administrador azul marino · Residente verde azulado · Guardia ámbar · Inquilino violeta. Se eligió el naranja porque apunta al rojo-teja y **no se confunde con el ámbar del Guardia**. Se ve en: el encabezado y los botones de la página del técnico (con una franja de «obra» bajo el título), la insignia **«Técnico»**, el botón «Enlace para técnico» y la evidencia dentro de cada tarjeta de daño. Tiene versión clara y oscura.

## 4. Qué archivos se tocaron y por qué

### Nuevos
| Archivo | Para qué |
|---|---|
| `alembic/versions/0026_enlace_tecnico_mantenimiento.py` | Crea las tablas `enlaces_tecnico` y `evidencias_danio` (con seguridad RLS en Supabase, como las migraciones anteriores). **No toca `reportes_danios`.** Se puede correr varias veces y se puede devolver. |
| `app/routers/tecnico.py` | Toda la lógica: crear/listar/anular enlaces (administrador) y las 3 rutas públicas del técnico (ver datos, ver foto, cambiar estado). |
| `app/schemas/tecnico.py` | Los formatos de entrada y salida del administrador. |
| `frontend/tecnico/tecnico.html`, `tecnico.css`, `tecnico.js` | La página del técnico (HTML, CSS y JS **separados**). Reduce la foto en el celular antes de subirla. |
| `tests/test_v56_enlace_tecnico.py` | 24 pruebas automáticas de todo lo anterior. |

### Modificados (cambios pequeños)
| Archivo | Qué cambió | Por qué |
|---|---|---|
| `app/models.py` | Modelos `EnlaceTecnico` y `EvidenciaDanio` + la relación `evidencias` en `ReporteDanio` | Guardar enlaces y evidencias. La relación no crea columnas. |
| `app/constantes.py` | `EstadoTecnico`, `EstadoEnlaceTecnico`, vigencias | Un solo lugar para los estados permitidos al técnico. |
| `app/limitador.py` | Dos límites nuevos | Freno contra abuso. |
| `app/schemas/negocio.py` | `ReporteResponse` ahora trae `evidencias` (vacío si no hay) | Para que la residente y el administrador vean lo que dejó el técnico. |
| `app/routers/modulos.py` | `listar_danios` carga las evidencias en una sola consulta extra | Evita una consulta por cada reporte. |
| `app/main.py` | Registra el router, la etiqueta en Swagger, el rol en la documentación, versión 5.6.0, y **excluye `frontend/tecnico/` de la caché del celular** | La página del técnico no debe descargarse en los celulares de los residentes (igual que `pase/`). |
| `frontend/js/vistas/mantenimiento.js` | Botón «Enlace para técnico», su ventana y el bloque de evidencias | La parte visible para administrador y residente. |
| `frontend/estilos.css` | Colores del rol y estilos nuevos (solo se **agregó** al final) | El naranja. |
| `tests/test_v53_seguridad.py` y `tests/test_v41_fase5.py` | Se declararon las 3 rutas públicas nuevas y la carpeta `tecnico` | Son pruebas «guardianas»: obligan a declarar a propósito toda ruta pública nueva. Es lo mismo que ya se hizo con el pase. |
| `README.md` y esta guía | Documentación; la guía 5.5 pasó a `docs/historial/` | Orden. |

## 5. Qué se verificó

- **Antes de empezar**, tu v5.5 pasaba **700 pruebas**.
- **Ahora:** **724 pruebas pasan** (las 700 de antes + 24 nuevas), sin ninguna rota.
- **Pruebas JS del CI** (`atras` e `imports`): pasan.
- **En un navegador real** (Chromium con tamaño de celular) se recorrió todo: abrir el enlace, error al intentar «Solucionado» sin nota, pasar a «En reparación» con una foto de 12,3 MB (se redujo a ~1 MB antes de subir), pasar a «Solucionado», y volver a abrir el enlace ya cerrado. Sin errores de consola ni de seguridad. También se probó el lado del administrador (generar el enlace, ver la lista, botones Copiar/WhatsApp) y los modos claro y oscuro.
- **No se pudo probar aquí:** Render, Supabase real, WhatsApp real ni la cámara física de un celular. Eso lo debes probar tú (sección 6, paso 7).

---

## 6. Cómo dejar todo funcionando (en orden)

1. **Descomprime** el zip sobre tu carpeta del proyecto (reemplaza archivos). En tu carpeta **borra a mano** `PASOS_V5.5.md` de la raíz (ahora vive en `docs/historial/`).
2. **Instala dependencias** (no hay nuevas, pero por costumbre): `pip install -r requirements.txt`.
3. **Migración (obligatoria):** con el entorno virtual activo, `alembic upgrade head`. Debe terminar con `Running upgrade 0025 -> 0026`. *Si no la corres, la app arranca pero fallará al abrir Daños.*
4. **Pruebas en tu PC:**
   ```
   python -m pytest -q
   node --test tests/js/atras.test.mjs
   node --test tests/js/imports.test.mjs
   ```
   Todo debe quedar en verde. Si algo falla, **no subas nada**: mándame el mensaje.
5. **Pruébalo a mano en local** (`iniciar.bat`): entra como residente y reporta un daño con foto → entra como administrador → Daños → «Enlace para técnico» → Generar → copia el enlace → ábrelo en **otra ventana privada** (sin sesión) → pásalo a «En reparación» con nota → vuelve al administrador y recarga: debes ver la nota y la insignia naranja «Técnico» → como residente también debes verla y recibir el aviso en la campana.
6. **Sube a GitHub:**
   ```
   git add -A
   git commit -m "v5.6: enlace de técnico de mantenimiento (rol Mantenimiento)"
   git push
   ```
   Como borraste `PASOS_V5.5.md` de la raíz y apareció en `docs/historial/`, `git add -A` lo registra como movido.
7. **Despliegue en Render:** al detectar el push se vuelve a desplegar solo. El comando de arranque ya incluye `alembic upgrade head`, así que **la migración 0026 se aplica sola**, tanto en tu app real como en la demo (cada una con su base). **Revisa en los logs de Render** que aparezca `Running upgrade 0025 -> 0026` y que no haya errores. Luego repite el recorrido del paso 5 **en producción**, esta vez con un **celular de verdad** (cámara incluida) y compartiendo el enlace por WhatsApp.
8. **Congela:** a partir de aquí, nada de funciones nuevas.

## 7. Resultado final de pruebas

`python -m pytest -q` → **724 passed** (700 de la v5.5 + 24 nuevas de `test_v56_enlace_tecnico.py`). `node --test tests/js/atras.test.mjs` → 9 pasan. `node --test tests/js/imports.test.mjs` → 1 pasa.

## 8. Mejoras futuras (anotadas, NO se hacen ahora)

- Enviar el enlace al técnico directamente desde la app (hoy se copia o se manda por WhatsApp).
- Descargar el historial de evidencias de un reporte en PDF para el informe de mantenimiento.
- Que el enlace guarde un hash del token en vez del token (más seguro, pero habría que mostrarlo una sola vez).
- Un aviso al administrador cuando un enlace está por vencer sin que el técnico haya actuado.
