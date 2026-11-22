# Versión 5.2 · Asambleas — Fase 3: votaciones dentro de la asamblea (Ley 675 de 2001)

Requiere **una migración nueva (0023)** que solo CREA tres tablas: no modifica ninguna tabla existente. No hay dependencias nuevas. Hay 3 variables de entorno opcionales (ya traen valor).
Pruebas: **628 de Python** (las 591 de siempre + 37 nuevas) y **9 de Node**, todas en verde.

---

## 1. Antes de empezar: revisé que todo estuviera sincronizado

Abrí el zip `proyecto_ciudadela-v5_1.zip` y corrí las 591 pruebas **antes de tocar nada**: todas pasaron. Esa es la base contra la que comparo.

**Una corrección al plan de trabajo.** La tabla de fases que me pasaste decía que la Fase 2 iba en la migración 0023. No es así: la Fase 2 (acreditación, poderes, quórum en vivo, pantalla grande) ya salió **dentro de la 0022**, junto con la Fase 1. Por eso la tabla correcta queda así:

| Fase | Contenido | Migración | Estado |
|---|---|---|---|
| 1 | Unidades + asamblea + convocatoria (orden del día, 2.ª convocatoria, morosos, bitácora con huella) | 0022 | Hecha |
| 2 | Acreditación presencial y virtual, poderes con aprobación, quórum en vivo, pantalla grande | 0022 | Hecha |
| **3** | **Votaciones ligadas a la asamblea, bloqueo del 70 % en virtual y 2.ª convocatoria, resultados** | **0023** | **Esta versión** |
| 4 | Acta PDF borrador, cierre y congelado | probablemente 0024 | Pendiente |

Otro detalle: `main.py` decía versión `5.0.0` aunque la guía anterior era la 5.1. Lo dejé en `5.2.0`.

---

## 2. Una decisión de diseño que cambié (y por qué)

En mi primer mensaje dije que ligaría las votaciones a la asamblea agregando una columna `asamblea_id` a la tabla `votaciones` de tu app. Al leer el código vi que era riesgoso:

- El motor de **«Votaciones»** del conjunto calcula todo a partir de los **usuarios con cuenta** (un voto por apartamento con residentes).
- La **asamblea** cuenta también a propietarios **sin cuenta**, a **apoderados**, y usa el coeficiente que se «fotografió» al acreditar.

Mezclarlos podía dañar lo que ya funciona y habría hecho aparecer las votaciones de asamblea en la lista general de residentes. Por eso construí un **motor aparte** (3 tablas nuevas) que copia lo bueno del actual (voto secreto, nadie vota dos veces) y **no toca ninguna tabla ni ruta de `/votaciones`**. Hay una prueba que lo verifica (`test_las_votaciones_del_conjunto_siguen_independientes`).

---

## 3. Qué se agregó, dónde y por qué

### Cómo funciona una pregunta (de principio a fin)

1. **Crear** (administrador, con la asamblea *Convocada* o *En sesión*). Queda en *Borrador*. Puede ser una **Decisión** (opciones fijas: A favor / En contra / Abstención) o una **Elección** (de 2 a 12 opciones que escribes, p. ej. candidatos).
2. **Abrir** (administrador, con la asamblea *En sesión*). El sistema valida el quórum, el bloqueo del 70 % y que no haya otra votación abierta, y **congela el padrón**: pueden votar las unidades que en ese instante están presentes y con derecho a voto, cada una con su coeficiente acreditado. Avisa a quienes votan desde la app.
3. **Votar**:
   - **Asistente virtual**: vota él mismo desde la app. El voto es **secreto** y no se puede cambiar.
   - **Asistente presencial**: el administrador registra su voto. Queda **a nombre de la unidad** (no es secreto), porque la persona está en el salón y alguien tiene que anotarlo.
   - **Apoderado**: si representa a más de una unidad, vota por cada una por separado.
4. **Cerrar** (administrador). Se valida el quórum **de ese momento**, se calcula el resultado, se **congela con una huella SHA-256** y se escribe en la bitácora encadenada.
5. **Anular** (administrador, con un motivo obligatorio) una pregunta en borrador o abierta. Una pregunta ya cerrada **no** se puede anular.

### Tablas nuevas (migración `alembic/versions/0023_votaciones_de_asamblea.py`)

| Tabla | Qué guarda | Por qué así |
|---|---|---|
| `asamblea_votaciones` | La pregunta, su tipo y mayoría, el padrón congelado, los quórums y el resultado congelado con su huella | Que el resultado no cambie después y se pueda demostrar |
| `asamblea_votacion_opciones` | Cada opción y su contador (votos y coeficiente) | Es el «conteo» del voto secreto: no está unido a ninguna persona |
| `asamblea_votos` | Que una unidad **ya votó** (una sola vez) y por qué vía | Una restricción de la base de datos impide votar dos veces, aunque lleguen dos peticiones a la vez |

Además, un **índice único parcial** hace que la base de datos garantice que haya **una sola votación abierta por asamblea** (no depende solo del código).

### Archivos nuevos
- `alembic/versions/0023_votaciones_de_asamblea.py` — la migración (segura de repetir; en PostgreSQL deja las tablas con Row Level Security, igual que las migraciones anteriores).
- `app/asamblea_votos.py` — **las reglas** (padrón, mayorías, quórum, resultado). Es el archivo más importante: léelo con el abogado.
- `app/routers/asamblea_votos.py` — los 8 endpoints (`/asambleas/{id}/votaciones/...`).
- `app/schemas/asamblea_votos.py` — lo que entra y sale de la API.
- `tests/test_v52_votaciones_asamblea.py` — 37 pruebas.
- `scripts/acercar_asamblea.py` — **solo para probar en tu computador** (ver sección 7).

### Archivos existentes que se modificaron (solo se AGREGÓ, salvo lo indicado)
| Archivo | Cambio |
|---|---|
| `app/constantes.py` | Al final: 3 enums (`TipoVotacionAsamblea`, `MayoriaAsamblea`, `EstadoVotacionAsamblea`) |
| `app/config.py` | Al final: 3 variables de bloqueo del 70 % |
| `app/models.py` | Al final: 3 clases; y en el `import` de SQLAlchemy se agregó `text` |
| `app/main.py` | Se importa y registra el router nuevo, una etiqueta en la documentación y la versión `5.2.0` |
| `app/routers/asambleas.py` | **Un cambio de comportamiento, a propósito:** no se puede **cerrar la asamblea** si hay una votación abierta (devuelve 409 con un mensaje claro) |
| `frontend/js/vistas/asambleas.js` | Pestaña **«Votaciones»** del administrador y tarjeta **«Votaciones»** del residente (marcado «V5.2») |
| `frontend/estilos.css` | Un bloque al final «v5.2» (barras de resultado y botones grandes de votar) |
| `.env.example` | Las 3 variables nuevas, comentadas |
| `README.md` | Una línea al final con la versión 5.2 y el recordatorio de la migración |

---

## 4. Las reglas, explicadas sin tecnicismos

**Padrón congelado.** Cuando el administrador abre una pregunta, el sistema anota quiénes están presentes con derecho a voto. Quien llega **después** no vota esa pregunta; quien se va **antes de votar** ya no puede hacerlo. Así el quórum no «se mueve» mientras se vota.

**Mayoría simple.** Se aprueba con **más del 50 %** del coeficiente **presente con derecho a voto** cuando se abrió la pregunta. Exactamente 50 % **no** alcanza. La **abstención no suma a favor**. Si alguien se retira después de abrir, su coeficiente sigue en la base (la lectura más exigente).

**Mayoría calificada (70 %).** Se aprueba con **70 % o más del coeficiente de TODO el conjunto**, no solo de los presentes. Ejemplo que está probado: si solo están presentes el 65 % y todos votan a favor, **no se aprueba** (65 % del conjunto < 70 %).

**Bloqueo del 70 %.** El sistema **no deja crear** una pregunta de 70 % si la asamblea es **virtual o mixta**, y **no deja abrirla** si la asamblea se instaló en **segunda convocatoria**. Cada bloqueo se puede apagar con una variable (sección 6), pero solo si tu abogado lo indica.

**Elección.** Gana la opción con más coeficiente. Si hay **empate** en el primer lugar, el sistema **no declara ganador** y lo dice: la asamblea decide cómo desempatar según su reglamento.

**Quórum al cerrar.** Si cuando se cierra la pregunta ya no hay quórum (por ejemplo, se fue gente), el resultado queda marcado **«SIN VALIDEZ»** y nunca como aprobado.

**Sin resultados parciales.** Mientras la pregunta está abierta **nadie** ve cuántos van a favor o en contra, ni siquiera el administrador; solo se ve **cuántas unidades han votado** (participación). Así no se influye en quien aún no vota.

**Resultado congelado.** Al cerrar se calcula **una sola vez** y se guarda con una huella SHA-256 que también queda en la bitácora encadenada. Antes de congelar, el sistema comprueba que lo contado en las opciones coincida con las unidades que votaron; si no coincide, marca el resultado sin validez (protege contra alteraciones directas en la base de datos).

---

## 5. Seguridad: qué se hizo y sus límites honestos

**Qué se hizo**
- **Voto secreto real en la app:** la tabla de votos no guarda qué se votó; la bitácora dice «votó por la app (voto secreto)»; la auditoría dice «Votó en una asamblea» **sin la opción**. Hay una prueba que revisa las tres.
- **Un voto por unidad**, garantizado por la base de datos (no solo por el código).
- **Nadie vota por otro:** a un asistente **virtual** no se le puede registrar el voto a mano; solo él, desde su sesión. El administrador solo registra votos de asistentes **presenciales**.
- **Permisos:** solo el administrador crea, abre, cierra, anula y registra votos presenciales. El residente solo vota por la unidad con la que está acreditado. El guardia solo mira. El inquilino no tiene acceso (como en el resto de Asambleas).
- **Concurrencia:** las operaciones bloquean la asamblea mientras se ejecutan, así dos votos simultáneos o «votar a la vez que se cierra» no dejan datos inconsistentes. **Probado con PostgreSQL real** (sección 8).

**Límites honestos**
- El **secreto** protege frente a la app y sus administradores. Quien tuviera acceso directo a la base de datos y la observara **voto por voto en tiempo real** podría, en teoría, deducir un voto por la variación de los contadores. Es un riesgo bajo, pero no es un sistema de voto electrónico certificado.
- El voto **presencial no es secreto** (queda a nombre de la unidad). Es una decisión consciente; si el reglamento exige voto secreto presencial, se haría con papeletas fuera del sistema.
- Una unidad **virtual sin cuenta en la app** no puede votar (cuenta para el quórum, pero no vota). Al abrir la pregunta el administrador recibe una advertencia con la lista de esas unidades.

---

## 6. Variables de entorno (todas opcionales; ya traen valor)
```
ASAMBLEA_BLOQUEA_70_VIRTUAL=1    # 1 = no se abren votaciones del 70 % en asambleas virtuales
ASAMBLEA_BLOQUEA_70_MIXTA=1      # 1 = ídem en asambleas mixtas
ASAMBLEA_BLOQUEA_70_SEGUNDA=1    # 1 = ídem si la asamblea se instaló en segunda convocatoria
```
**No las cambies sin consultar a un abogado.** Dejarlas en 1 es lo prudente.

---

## 7. Supuestos que debe validar un abogado de propiedad horizontal

Son lecturas **prudentes**, no verdades legales. Si tu reglamento dice otra cosa, **el reglamento manda**. Los números de artículo son los que el proyecto ya venía usando desde la v4.6; que el abogado los confirme.

1. **Mayoría simple medida sobre el coeficiente presente con derecho a voto al abrir**, no sobre los que alcanzan a votar. Si el reglamento la mide sobre los votos emitidos, cambia el resultado.
2. **Mayoría calificada del 70 % medida sobre el 100 % del conjunto.**
3. **La abstención no suma a favor** (cuenta en la base, no en el «a favor»).
4. **Bloqueo del 70 %** en reuniones virtuales, **mixtas** y de segunda convocatoria. El bloqueo de las mixtas es una decisión mía por prudencia (hay votantes a distancia); la ley habla de reuniones «no presenciales» y de segunda convocatoria.
5. **Padrón congelado al abrir** (quien llega tarde no vota esa pregunta).
6. **Pérdida de quórum al cerrar = resultado sin validez.**
7. **Elección:** gana la de más coeficiente, sin exigir una mayoría mínima. Si tu reglamento la exige, el presidente y el secretario deben verificarla.
8. **Empate:** no se desempata solo.
9. **Voto presencial nominal** (a nombre de la unidad).
10. **Mora:** respeta lo ya existente (por defecto no quita el voto; solo si la asamblea se creó con «restringe mora»; esas unidades cuentan para el quórum pero no entran al padrón).
11. **Inquilinos:** no votan en la asamblea. Vota el propietario o un apoderado con poder aprobado.

---

## 8. Qué verifiqué (y qué NO)

**Verificado**
- Las 591 pruebas anteriores pasaban en el zip recibido; **siguen pasando**, más las 37 nuevas (**628 en total**). Las 9 de Node también.
- La migración 0023 **sube, se puede repetir, baja y vuelve a subir** tanto en SQLite como en **PostgreSQL 16 real**. Comprobé en PostgreSQL que el índice único parcial existe y que las 3 tablas quedan con Row Level Security.
- Corrí las pruebas de votaciones **contra PostgreSQL real** y pasan (36 de 36 que no dependen de SQLite).
- **Concurrencia en PostgreSQL real:** 10 votos simultáneos de la misma unidad → exactamente **un** 200 y nueve 409, un solo voto guardado, contador correcto y bitácora íntegra. Dos unidades votando a la vez → ambas se cuentan y la cadena sigue íntegra. «Votar» y «cerrar» a la vez → el resultado queda consistente.
- Sintaxis del JavaScript nuevo (parsea bien).

**NO verificado (hazlo tú)**
- **La pantalla nueva no la probé en un navegador ni en un celular.** Solo comprobé que el código JavaScript es válido y que el servidor responde como la pantalla espera. Es lo primero que debes recorrer (sección 9, paso 4).
- **No probé contra tu Supabase ni tu Render reales.**
- **No hay revisión legal:** las reglas son lecturas prudentes (sección 7).

---

## 9. Qué hacer después (en este orden)

1. **Descomprime el zip** sobre tu carpeta (acepta reemplazar).
2. **Pruebas:** `python -m pytest -q` (esperado: **628 passed**) y `node --test tests/js/atras.test.mjs` (esperado: 9 passed).
3. **Migración local:** `alembic upgrade head` (aplica la 0023; es segura aunque la corras dos veces).
4. **Recorrido manual en local** (`.\iniciar-demo.bat`), el paso más importante:
   1. Como administrador: *Más → Asambleas → Unidades y coeficientes* (deben sumar 100 %).
   2. Crea una asamblea **Mixta** y **convócala**.
   3. En la terminal: `python -m scripts.acercar_asamblea 1` (mueve la hora de la reunión a «ahora» **solo en tu base local**; se niega a funcionar con Supabase/producción).
   4. Como residente (otro navegador o ventana privada): entra a la asamblea y pulsa **conectarte** (queda como virtual).
   5. Como administrador: *Asistencia* → acredita a otra unidad como **presencial** → **Instalar**.
   6. Pestaña **Votaciones** → *Nueva votación* → **Abrir**.
   7. Como residente: debe aparecer la tarjeta **Votaciones** con botones grandes; vota. Intenta votar otra vez (no debe dejar).
   8. Como administrador: registra el voto del presencial, mira que **no** haya resultados parciales, **cierra** y revisa el resultado y la pestaña **Bitácora** («Cadena íntegra»).
   9. Prueba también en el celular y en modo oscuro.
5. **GitHub:** tu repo sigue en una versión vieja. Sube **un commit por versión y en orden**: v4.8, v4.9, v5.0, v5.1 y al final esta: `git add .` · `git commit -m "v5.2: votaciones dentro de la asamblea (Fase 3)"` · `git push`.
6. **Render:** deja que despliegue (auto-deploy o *Manual Deploy → Deploy latest commit*). Al arrancar ejecuta `alembic upgrade head && python -m app.seed && uvicorn`, así que **aplica la 0023 sola en Supabase**. **Mira los logs de arranque**: si la migración falla, la app no arranca.
7. **Celular:** cierra la PWA por completo y ábrela dos veces; la versión nueva se toma sola.
8. **Producción:** como administrador, abre una asamblea y confirma que aparece la pestaña **Votaciones**. **No abras votaciones de prueba en una asamblea real.**
9. **Antes de una asamblea real:** valida la sección 7 con un abogado, usa un plan de Render que no se duerma ese día (el gratis se duerme a los 15 minutos), y graba la sesión virtual con la herramienta de videollamada (es la prueba principal).

---

## 10. Qué NO incluye todavía

- **Pantalla grande con la votación en vivo** (la pantalla grande actual sigue mostrando solo el quórum).
- **Elección con varios cupos** (p. ej. elegir 5 consejeros a la vez): hoy una elección escoge **una** opción ganadora.
- **Acta PDF, cierre y congelado de la asamblea** (Fase 4). Todo lo necesario para el acta ya queda guardado (padrón, resultados, huellas).
- No hay «deshacer» de un voto: es a propósito.

---

## 11. Cómo volver atrás

- **Solo el código:** `git revert` del commit de la v5.2.
- **También la base de datos:** `alembic downgrade 0022` borra **únicamente** las 3 tablas nuevas (las demás no se tocan). **Ojo: borra los votos y resultados de asamblea que ya existan**, así que hazlo solo si aún no se usó de verdad.
- El bloque «v5.2» de `estilos.css` y los cambios marcados «V5.2» en `asambleas.js` se pueden quitar a mano sin afectar nada más.
