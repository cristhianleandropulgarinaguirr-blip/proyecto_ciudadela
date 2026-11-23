# Versión 5.4 · Asambleas — Fase 4: acta, cierre y congelado (Ley 675 de 2001, Art. 47)

Requiere **una migración nueva (0025)** que solo CREA una tabla (`asamblea_actas`): no modifica ninguna tabla existente. No hay dependencias nuevas (el PDF usa `reportlab`, que ya estaba). Hay **1 variable de entorno nueva y opcional**.
Esta versión está construida **sobre tu v5.3 (seguridad completa)**, tomada de tu repositorio de GitHub (último commit: «v5.3: seguridad completa»).
Pruebas: **700 de Python** (todas las de la v5.3 + 33 nuevas de la Fase 4) y **9 de Node**, todas en verde.

---

## 0. Lee esto primero: sobre qué versión está construida

La primera vez construí la Fase 4 sobre el zip v5.2 que subiste; después me diste el enlace de tu repositorio y vi que tu último commit es la **v5.3**. **Esta entrega ya es la unión de las dos**: tomé tu v5.3 tal cual está en GitHub y le apliqué solo los cambios de la Fase 4. Lo que cambió por eso:

- **Migración renumerada:** la v5.3 ya usa la `0024` (`seguridad_dos_pasos`), así que la del acta es la **`0025`** y depende de ella. En la base nueva se aplican en orden: 0023 → 0024 → 0025.
- **Contraseña de nuevo:** tu v5.3 pide la contraseña otra vez en las acciones sensibles del administrador (`reauth_admin`). **Sellar** y **publicar** el acta son irreversibles o de alto impacto, así que las protegí igual: la pantalla abre sola la ventana de contraseña, como en el resto de la app. Redactar el borrador, descargar PDFs, subir la copia firmada y verificar **no** la piden.
- **Pruebas de seguridad de la v5.3:** pasan todas, incluida la que barre cada ruta para confirmar que exige sesión y la que comprueba que las rutas «Solo **Administrador**» rechazan a un residente. Las 9 rutas nuevas del acta cumplen ambas.
- **Versión de la API:** `5.4.0`.

**Una corrección al plan de la captura.** La tabla de fases que me mostraste decía que la Fase 4 no llevaba migración («—»). Al leer el código vi que sí la necesita: el acta guarda texto que redacta el secretario, una copia congelada del contenido con su huella, la copia firmada y la fecha de publicación. Eso no cabe en las tablas actuales sin alterarlas, así que usé una tabla nueva, igual que en la Fase 3 (solo crea, no toca nada existente).

---

## 1. Qué hace la Fase 4, en cinco pasos

1. **Cerrar la asamblea** (ya existía). Ahora, además, **congela la reunión**: ya no se acreditan asistentes, no se suben ni aprueban poderes y no se crea, abre, anula ni vota ninguna pregunta. Lo comprobé con una prueba que intenta 21 operaciones distintas sobre una asamblea cerrada y verifica que **todas** se rechazan con error 409. La bitácora del cierre ahora dice cuántas votaciones quedaron cerradas, anuladas o sin votar.
2. **Redactar el borrador del acta** (pestaña nueva **Acta**, solo administrador). Tú completas quién presidió, quién fue secretario, la comisión verificadora (si la hubo) y el desarrollo de la reunión. Todo lo demás (clase de asamblea, convocatoria, orden del día, asistentes con coeficiente, votos) lo toma la aplicación de lo ya registrado. Puedes empezar durante la sesión y descargar el **borrador en PDF con marca de agua «BORRADOR»**.
3. **Sellar el acta** (solo con la asamblea cerrada). Guarda una **copia congelada** de todo el contenido con su **huella SHA-256**, que además queda escrita en la bitácora encadenada. Es **irreversible**: después ni el texto ni la evidencia cambian. El **PDF definitivo** se dibuja siempre desde esa copia congelada, así que sale idéntico cada vez aunque alguien toque la base de datos.
4. **Subir la copia firmada.** Imprimes el acta definitiva, la firman el presidente y el secretario, la escaneas y la subes (PDF). Se guarda su huella en la bitácora. Puedes reemplazarla mientras no esté publicada.
5. **Publicar a los propietarios.** Les llega una notificación y desde ese momento ven la tarjeta **«Acta de la asamblea»** con el PDF (y la copia firmada, si la subiste). El plazo legal aparece siempre arriba y avisa si ya venció.

Además, el botón **«Verificar integridad»** vuelve a calcular todo y lo compara con lo congelado (sección 5).

---

## 2. Lo legal: qué exige el Art. 47 y cómo se cubre

Consulté el texto del artículo y conceptos del Ministerio de Vivienda antes de escribir el contenido del acta. Lectura prudente (la valida un abogado de propiedad horizontal):

| El Art. 47 pide | Cómo lo cubre la app |
|---|---|
| Indicar si es ordinaria o extraordinaria | Sección 1 del acta |
| La forma de la convocatoria | Sección 2: fecha de envío, medio de aviso por unidad (app / entrega manual / sin constancia), documentos adjuntos y huella de lo enviado |
| El orden del día | Sección 3 |
| Nombre y calidad de los asistentes (propietario o apoderado) y su coeficiente | Sección 6 (tabla) |
| Los votos emitidos en cada caso | Sección 7: resultado por opción con coeficiente, quórum al abrir y cerrar, votos presenciales nominales |
| Firma del presidente y del secretario | Renglones de firma en el PDF + subida de la copia firmada |
| Verificación de la redacción por una comisión (si el reglamento o la asamblea la prevén) | Campo «comisión verificadora» y renglón de firma |
| Ponerla a disposición de los propietarios en **20 días hábiles desde la fecha de la reunión** | Plazo calculado (festivos de Colombia; sábados no cuentan salvo `ASAMBLEA_SABADO_HABIL=1`), advertencia si vence y constancia en la bitácora si se publica tarde |

**Puntos que debe revisar tu abogado**
- **Voto secreto de la app vs. «votos emitidos en cada caso».** Los votos de la app son secretos por diseño desde la Fase 3: el acta muestra cuántas unidades votaron y el coeficiente por opción, **no quién votó qué**. Los presenciales sí son nominales. Si el reglamento exige votación nominal siempre, hay que ajustarlo.
- **El PDF no reemplaza el libro de actas.** La ley pide que el administrador conserve el original de las actas; este PDF firmado es el soporte, pero el libro sigue siendo tu obligación.
- **Validez.** El acta vale por las firmas y por haber cumplido el proceso (convocatoria, quórum, mayorías). La aplicación deja evidencia, no sustituye al presidente, al secretario ni al abogado.
- **Reuniones con participación a distancia.** El acta deja constancia de que las conexiones y desconexiones constan en la bitácora y recomienda conservar la **grabación** de la sesión. Confirma con tu abogado qué evidencia adicional exige el reglamento para reuniones no presenciales.
- **Datos personales.** El acta publicada **no incluye números de documento** (de apoderados ni de nadie) ni el listado de morosos; la ley no lo pide y la ven todos los propietarios.

---

## 3. Qué se cambió, dónde y por qué

**Archivos nuevos (6)**

| Archivo | Qué es | Por qué |
|---|---|---|
| `alembic/versions/0025_acta_de_asamblea.py` | Crea la tabla `asamblea_actas` (una por asamblea) con Row Level Security en PostgreSQL | Guardar borrador, copia congelada, huella, copia firmada y publicación sin alterar tablas existentes. Se puede correr varias veces, bajar y volver a subir |
| `app/asamblea_acta.py` | Las reglas: arma el contenido del acta, calcula la huella, verifica, calcula el plazo y dibuja el PDF | Mantener la lógica fuera de los endpoints, como en las fases anteriores |
| `app/routers/asamblea_acta.py` | Los 9 endpoints del acta (sellar y publicar con `reauth_admin`) | Solo traducen HTTP a las reglas |
| `app/schemas/asamblea_acta.py` | Entradas y salidas, con limpieza de texto | Validar longitudes y quitar caracteres de control |
| `tests/test_v54_acta_asamblea.py` | 33 pruebas | Cubren permisos, sellado, verificación, firma, publicación, plazo, congelado, contraseña de nuevo y migración |
| `PASOS_V5.4.md` | Esta guía | |

**Archivos existentes que se tocaron (10)**

| Archivo | Cambio | Tipo |
|---|---|---|
| `app/models.py` | Clase `AsambleaActa` | Solo agregada **al final** |
| `app/constantes.py` | `EstadoActa` (Borrador / Sellada) | Solo agregada **al final** |
| `app/config.py` | `ASAMBLEA_ACTA_DIAS_HABILES` (por defecto 20) | Solo agregada **al final** |
| `app/calendario_co.py` | Función `dia_habil_numero`; `tercer_dia_habil` ahora la usa (mismo resultado) | Edición puntual |
| `app/main.py` | Importar y registrar el router, etiqueta de Swagger, versión `5.4.0` | Edición puntual (4 líneas) |
| `app/routers/asambleas.py` | `cerrar` registra el resumen de votaciones; texto del endpoint | Edición puntual |
| `frontend/js/vistas/asambleas.js` | Pestaña **Acta** (admin), tarjeta **Acta** (residente), botón «Preparar el acta», y en una asamblea cerrada ya no se ofrece «Anular» sobre propuestas sin votar | Bloque nuevo + 5 ediciones pequeñas |
| `frontend/estilos.css`, `.env.example`, `README.md` | Estilos de la lista de pasos; variable nueva; sección de la versión | Solo agregados al final |

---

## 4. Los endpoints nuevos (aparecen en Swagger bajo «Acta de la Asamblea»)

| Método y ruta | Quién | Para qué |
|---|---|---|
| `GET /asambleas/{id}/acta` | Admin: todo. Residente: solo si está publicada | Estado del acta, plazo, qué falta y advertencias |
| `PUT /asambleas/{id}/acta` | Admin | Guardar el borrador (solo se cambia lo que envías) |
| `GET /asambleas/{id}/acta/borrador.pdf` | Admin | PDF con marca de agua «BORRADOR» |
| `POST /asambleas/{id}/acta/sellar` | Admin, asamblea cerrada, **contraseña de nuevo** | Congelar con huella (irreversible) |
| `GET /asambleas/{id}/acta.pdf` | Admin desde que se sella; residente al publicarse | Acta definitiva |
| `POST /asambleas/{id}/acta/firmada` | Admin | Subir la copia firmada (PDF) |
| `GET /asambleas/{id}/acta/firmada` | Admin; residente al publicarse | Descargar la copia firmada |
| `POST /asambleas/{id}/acta/publicar` | Admin, **contraseña de nuevo** | Poner a disposición de los propietarios y notificar |
| `GET /asambleas/{id}/acta/verificar` | Admin | Comprobar que nada se alteró |

El guardia y el inquilino no tienen acceso; el residente solo ve lo publicado. **No se agregó ningún rol nuevo.**

---

## 5. Cómo funciona la verificación de integridad (y su límite)

Cuatro revisiones independientes:
1. **Texto del acta:** el contenido congelado sigue coincidiendo con su huella SHA-256.
2. **Asistentes y votos:** lo que hoy hay en la base de datos (asistentes, votaciones, resultados, datos de la asamblea) es idéntico a lo que se congeló.
3. **Bitácora encadenada:** ningún evento fue alterado ni borrado.
4. **Copia firmada:** el PDF guardado es el mismo que se subió.

Las pruebas manipulan la base de datos a propósito (cambian un coeficiente, el texto congelado, un evento de la bitácora, el hash de la copia firmada) y comprueban que **cada** alteración se detecta.

**Límite honesto:** quien tenga control total de la base de datos y recalcule *toda* la cadena y *todas* las huellas de forma coherente podría reescribirla sin que la verificación lo note, porque la huella vive en la misma base. La defensa es que **la huella queda impresa en el acta que firman el presidente y el secretario**: ese papel firmado es el ancla fuera de la base de datos.

---

## 6. Variable de entorno nueva (opcional)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `ASAMBLEA_ACTA_DIAS_HABILES` | `20` | Días hábiles desde la fecha de la reunión para poner el acta a disposición de los propietarios |

No necesitas tocar nada en Render: sin ella usa 20.

---

## 7. Qué verifiqué y qué NO

**Verificado**
- Cloné tu repositorio (commit `e432f1c`, «v5.3: seguridad completa») y le apliqué la Fase 4. Dos puntos chocaron (el final del README y la línea de versión de `main.py`) y los resolví a mano; los demás archivos entraron limpios.
- Batería completa sobre la versión unida: **700 pasan** (las de la v5.3 + 33 nuevas) y las 9 de Node.
- Una prueba comprueba que **sellar y publicar** devuelven 403 con la señal «confirma tu contraseña» si no hay pase, y funcionan con él.
- La migración 0025 **sube, se puede repetir, baja a 0024 (quitando solo la tabla nueva y dejando la de seguridad) y vuelve a subir** en SQLite.
- Generé un borrador y un acta definitiva de ejemplo, los convertí a imagen y los revisé: marca de agua solo en el borrador, tablas ordenadas, renglones de firma y huella al final.
- Sintaxis del JavaScript nuevo (parsea bien).

**NO verificado (hazlo tú)**
- **La pantalla nueva no la probé en un navegador ni en un celular.** Solo comprobé que el JavaScript es válido y que el servidor responde como la pantalla espera. En particular, no vi con mis ojos la ventana de contraseña al sellar; usa el mismo mecanismo que el resto de la app, pero confírmalo (sección 8, paso 5).
- **No probé la migración contra PostgreSQL real** (esta vez no tenía uno disponible; en la Fase 3 sí lo hice). La parte de PostgreSQL es la misma de la 0023, pero confírmalo mirando el log de Render al desplegar.
- **No probé contra tu Supabase ni tu Render.**
- **No hay revisión legal** (sección 2).
- **No probé el PDF con un acta de cientos de unidades**; la tabla de asistentes se parte en páginas, pero conviene que la veas con tus datos.

---

## 8. Qué hacer después (en este orden)

1. **Descomprime el zip** sobre tu carpeta (acepta reemplazar). Tu carpeta debe estar en la v5.3 (la de tu último commit); si tienes cambios locales sin subir, haz primero un commit o una copia.
2. **Pruebas:** `python -m pytest -q` (esperado: **700 passed**) y `node --test tests/js/atras.test.mjs` (esperado: 9 passed).
3. **Migración local:** `alembic upgrade head` (aplica la 0025; es segura aunque la corras dos veces).
4. **Recorrido manual en local** (`.\iniciar-demo.bat`), el paso más importante. **Usa una asamblea de prueba: sellar es irreversible.**
   1. Crea una asamblea **Mixta**, conócala, acércala con `python -m scripts.acercar_asamblea 1` y **instálala** con asistentes (uno virtual, uno presencial).
   2. Abre una votación, vota, registra el voto presencial y ciérrala.
   3. Pestaña **Acta**: aún no puedes sellar (falta cerrar y los nombres). Escribe presidente, secretario y desarrollo → **Guardar borrador** → **Descargar borrador (PDF)** y revisa la marca de agua.
   4. **Cierra la asamblea** y comprueba que ya no puedes acreditar ni votar.
   5. **Sellar el acta**: debe aparecer la ventana que pide tu contraseña (como en las otras acciones sensibles). Confírmala → descarga el **acta definitiva** → **Verificar integridad** (debe salir todo «Correcto»).
   6. **Subir copia firmada** (cualquier PDF de prueba) → **Publicar** (vuelve a pedir la contraseña solo si pasaron más de 5 minutos).
   7. Entra como **residente** (otra ventana privada): debe aparecer la tarjeta «Acta de la asamblea» con el PDF; antes de publicar debe decir que aún no está publicada.
   8. Pruébalo en el **celular** y en **modo oscuro**.
5. **GitHub:** `git add .` · `git commit -m "v5.4: acta, cierre y congelado de la asamblea (Fase 4)"` · `git push`. Es un solo commit encima de tu «v5.3: seguridad completa».
6. **Render:** deja que despliegue (auto-deploy o *Manual Deploy → Deploy latest commit*). Al arrancar ejecuta `alembic upgrade head && python -m app.seed && uvicorn`, así que **aplica la 0025 sola en Supabase**. **Mira los logs:** debe aparecer `Running upgrade 0024 -> 0025`.
7. **Celular:** cierra la PWA por completo y ábrela dos veces; la versión nueva se toma sola.
8. **Producción:** como administrador, abre una asamblea cerrada y confirma que aparece la pestaña **Acta**. **No selles actas de prueba en producción**: una acta sellada no se puede borrar desde la app.
9. **Antes de una asamblea real:** valida la sección 2 con un abogado, graba la sesión virtual con tu herramienta de videollamada, y ten una fecha en el calendario para publicar el acta (el plazo corre desde la reunión).

---

## 9. Qué NO incluye todavía

- **Corregir un acta ya sellada** (adenda o acta de corrección): hoy una acta sellada no se edita ni se deshace, a propósito. Si hubo un error, hay que hacer una adenda por fuera y adjuntarla.
- **Registrar el acta publicada en «Documentos»** del conjunto: hoy se consulta desde la propia asamblea.
- **Firma electrónica** del acta: la firma es física y se sube escaneada.
- Pendientes del plan original: **elecciones con varios cupos**, **control de presencia virtual** y **candidatos en vivo**.

---

## 10. Cómo volver atrás

- **Solo el código:** `git revert` del commit de la v5.4.
- **También la base de datos:** `alembic downgrade 0024` borra **únicamente** la tabla nueva (la migración de seguridad de la v5.3 se queda). **Ojo: borra los borradores, actas selladas y copias firmadas ya registradas** (los archivos PDF subidos quedan en el almacenamiento, pero sin referencia). Hazlo solo si aún no se usó.
- El bloque «V5.4» de `estilos.css` y los cambios marcados «V5.4» en `asambleas.js` se pueden quitar a mano sin afectar nada más.
