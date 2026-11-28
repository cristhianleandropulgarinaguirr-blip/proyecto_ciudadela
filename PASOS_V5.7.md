# Versión 5.7 · Cambios que pidió el instructor (entrega 1 de 2)

Esta entrega trae **tres** de los cinco cambios: el flujo de daños (2), las notificaciones «por gestionar» (3) y el chatbot que trae datos reales (1).
Quedan para la **v5.8**: el botón de inglés/español (4) y el micrófono de voz a texto (5).

> **Hay una migración nueva: la `0027`.** Solo agrega 4 columnas a la tabla `notificaciones`. No borra ni cambia nada existente.

---

## 1. Qué cambia (resumen de una mirada)

| # | Cambio | Dónde se ve | Migración |
|---|---|---|---|
| 2 | El administrador **ya no** pone «En revisión» ni «En reparación»: eso lo hace el técnico. Al final el administrador revisa y pone **«Aprobado»**. | Daños | No |
| 3 | Las notificaciones muestran cuáles están **gestionadas** y cuáles **por gestionar**. Abrir un aviso ya no lo hace «desaparecer» si faltaba hacer algo. | Campana, Inicio | **Sí (0027)** |
| 1 | El chat **trae datos reales**: «¿Qué residentes están en mora?» responde con una tabla dentro del chat. | Chat (solo Administrador) | No |

---

## 2. Cambio 2 · Flujo de daños

**El ciclo nuevo:** `Abierto → En reparación (técnico) → Solucionado (técnico) → Aprobado (administrador)`

### Qué hace ahora cada quien
- **Residente:** reporta el daño (igual que antes) y ve el avance.
- **Administrador:** toca **«Enlace para técnico»** y se lo manda al técnico. Cuando el técnico termina, en la tarjeta aparece **«Por aprobar»** con dos botones:
  - **Aprobar:** cierra el reporte y le avisa al residente.
  - **Devolver:** el reporte vuelve a «Abierto» (con un motivo opcional que lee el residente) y puedes crear un enlace nuevo.
- **Técnico:** desde su enlace pasa el reporte a «En reparación» y luego a «Solucionado» (con nota y foto). Eso no cambió.

### Dónde se cambió y por qué
| Archivo | Qué se hizo | Por qué |
|---|---|---|
| `app/constantes.py` | Estado nuevo `Aprobado`. `En Revision` se conserva solo como «heredado». | Los reportes viejos que ya estaban «En Revision» deben seguir funcionando. |
| `app/routers/modulos.py` (`cambiar_estado_danio`) | El administrador **solo** puede mandar `Aprobado` o `Abierto` (devolver), y **solo** si el reporte está en `Solucionado`. Todo lo demás responde 400. | La regla está en el **servidor**, no solo en los botones: aunque alguien llame la API a mano, no se salta al técnico. |
| `app/routers/tecnico.py` | El enlace se cierra también en `Aprobado`; después de «Devolver» se puede crear otro. | Que un reporte aprobado no se pueda volver a mover desde un enlace viejo. |
| `frontend/js/vistas/mantenimiento.js` | Los pasos del avance son de solo lectura; aparecen **Aprobar** y **Devolver** cuando toca la revisión final. | El administrador ya no «salta» estados con un clic. |
| `app/routers/dashboard.py`, `indicadores.js`, `resumen.js` | «Daños sin resolver» ahora cuenta todo lo no aprobado; hay un indicador nuevo **«Daños por aprobar»**. | Lo «Solucionado» aún es trabajo pendiente del administrador. |

> **Algo que debes saber:** un daño ya **no se puede cerrar «a mano»** sin técnico. Siempre pasa por el enlace del técnico. Es lo que pidió el instructor (separación de funciones).

---

## 3. Cambio 3 · Notificaciones «por gestionar»

**La idea:** «leída» y «gestionada» son cosas distintas. Si abres un aviso de «Reserva por aprobar» y te olvidas de aprobarla, el aviso **sigue marcado «Por gestionar»** hasta que lo hagas.

### Cómo se ve
- **Campana:** burbuja **roja** = sin leer; burbuja **ámbar** = por gestionar (se queda aunque ya hayas abierto el aviso).
- **Lista:** filtros **Todas / Por gestionar / Gestionadas**. Cada aviso que pide una acción lleva una etiqueta con **ícono y texto** («Por gestionar» / «Gestionada»), no solo color. Los pendientes salen primero y nunca se ven «apagados».
- **Inicio:** una tarjeta «Tienes avisos por gestionar» con los 5 primeros.
- **Se gestionan solos** cuando haces lo que pedían (apruebas la reserva, respondes la PQRS, recoges el paquete…). También hay un botón **«Marcar como gestionada»** y **«Volver a pendiente»** por si te equivocas.

### Qué avisos quedan «por gestionar»
| Aviso | Para quién | Se cierra cuando… |
|---|---|---|
| Reserva por aprobar *(aviso nuevo)* | Administrador | se aprueba o cancela la reserva |
| Nuevo daño por atender *(aviso nuevo)* | Administrador | crea el enlace para el técnico |
| Daño por aprobar: el técnico terminó | Administrador | aprueba o devuelve el reporte |
| Nueva queja o sugerencia (PQRS) | Administrador | responde o cambia el estado |
| Arrendamiento por aprobar | Administrador | aprueba o rechaza |
| Solicitud de trasteo | Administrador | aprueba, rechaza o se cancela |
| Poder de asamblea por revisar | Administrador | lo aprueba o rechaza |
| Tienes un paquete en portería | Residente | lo recoge (o se anula) |

Los demás avisos (anuncios, cambios de estado, etc.) siguen siendo **informativos**.

### Dónde se cambió y por qué
| Archivo | Qué se hizo |
|---|---|
| `alembic/versions/0027_notificaciones_por_gestionar.py` | Agrega a `notificaciones`: `requiere_gestion`, `gestionada_en`, `ref_tipo`, `ref_id` + un índice. Es segura de correr varias veces y reversible. Los avisos viejos quedan como informativos (nada aparece «pendiente» de golpe). |
| `app/models.py` | Las 4 columnas nuevas y la propiedad `estado_gestion`. |
| `app/notificaciones.py` | `notificar(..., requiere_gestion, ref_tipo, ref_id)` y la función nueva `marcar_gestionadas()`. **Importante:** cerrar un aviso automáticamente **no** lo marca como leído (si nadie lo vio, conserva su burbuja roja). |
| `app/routers/notificaciones.py` | Filtro `?gestion=por_gestionar`, conteo con `por_gestionar`, y endpoints `POST /{id}/gestionar` y `POST /{id}/pendiente`. |
| `app/routers/{pqrs,arrendamientos,trasteos,asambleas,modulos,paquetes,tecnico}.py` | Crean el aviso «por gestionar» y lo cierran al resolverse. |
| `frontend/js/campana.js`, `estilos.css`, `vistas/resumen.js` | La campana con dos burbujas, los filtros, las etiquetas y la tarjeta de Inicio. |

---

## 4. Cambio 1 · El chat que trae datos reales (solo Administrador)

**Ejemplos que ahora funcionan:** «¿Qué residentes están en mora?», «¿Quién me debe plata?», «¿Quiénes deben más de 500 mil?», «¿Hay reservas pendientes?», «¿Qué PQRS siguen abiertas?», «¿Qué daños faltan por aprobar?», «¿Qué tengo pendiente por gestionar?», trasteos, arrendamientos y paquetes sin recoger.

### Cómo funciona (en 4 pasos)
1. **La IA entiende la pregunta** (aunque esté escrita de una forma rara) y **elige una consulta** de un catálogo cerrado. Nunca escribe SQL ni toca la base de datos.
2. **El servidor la ejecuta**, solo si el **rol de la sesión** puede (un residente, un inquilino o la guardia no obtienen nada, aunque la IA lo pidiera).
3. **La tabla con nombres la arma el servidor** y se muestra en el chat.
4. **La IA redacta el análisis** («hay 12 residentes en mora, el saldo total es…») usando **solo cifras y apartamentos: nunca nombres ni correos**.

### Protecciones (por qué es seguro)
- Catálogo **cerrado** de 8 consultas de **solo lectura**. Los parámetros se validan contra listas y rangos fijos; lo raro se descarta.
- Si la IA **inventa una cifra grande** que no está en los datos, se descarta su texto y se usa el que armó el servidor.
- Si la IA **falla o no hay cupo**, el administrador igual recibe su tabla (el servidor reconoce las preguntas más comunes sin IA).
- Las preguntas de «cómo se hace» («¿Cómo registro a un residente en mora?») **no** disparan la tabla: las responde la guía de siempre.
- El texto de la respuesta **no lleva nombres**, porque el chat lo reenvía a la IA como historial.
- La mora es **la misma definición que Cartera** (residentes activos con saldo > 0 o sin estar al día).
- Cuenta para el tope diario de mensajes: elegir la consulta + redactar = **2 mensajes** en las preguntas de datos.

### Dónde se cambió
| Archivo | Qué se hizo |
|---|---|
| `app/chat_consultas.py` *(nuevo)* | El catálogo de consultas, la validación de parámetros y el reconocimiento sin IA. |
| `app/routers/asistente.py` | El chat acepta que la IA elija una consulta, la ejecuta, y hace el segundo paso de redacción. |
| `app/schemas/asistente.py` | `TablaChat` en la respuesta del chat. |
| `app/chat_datos.py` | Las preguntas de arranque del administrador incluyen «¿Qué residentes están en mora?» y «¿Qué tengo pendiente por gestionar?». También se actualizó la guía de Daños. |
| `frontend/js/chat.js`, `estilos.css` | Dibuja la tabla dentro del chat. |

---

## 5. Cómo dejarlo funcionando (en orden)

1. **Descomprime** el zip y copia su contenido **sobre tu carpeta del proyecto** (reemplaza archivos). No borres tu archivo `.env`.
2. **Migración (local):** en la carpeta del proyecto, con tu entorno activado:
   ```
   alembic upgrade head
   ```
   Debe terminar diciendo `Running upgrade 0026 -> 0027`.
3. **Pruebas (local):**
   ```
   python -m pytest -q
   node --test tests/js/*.mjs
   ```
   Esperado: **754 pruebas del backend** y **10 de JS** en verde.
4. **Pruébalo a mano** antes de subirlo (ver lista abajo).
5. **GitHub:**
   ```
   git add .
   git commit -m "v5.7: flujo de daños con aprobación, notificaciones por gestionar y chat con datos"
   git push
   ```
6. **Despliegue (Render):** al subir a GitHub se despliega solo. El arranque corre `alembic upgrade head`, así que la migración **0027** se aplica sola en producción. Espera a que el despliegue quede en «Live».
7. **Prueba en producción con un celular real** (ver lista).

### Lista de prueba manual
- [ ] Como residente, reporta un daño → el administrador recibe «Nuevo daño por atender» (ámbar).
- [ ] Como administrador, crea el enlace para el técnico → ese aviso pasa a «Gestionada».
- [ ] Abre el enlace del técnico → «En reparación» → «Solucionado» (nota + foto).
- [ ] Como administrador, la tarjeta dice **Por aprobar** y NO hay botones de «En revisión» ni «En reparación». Prueba **Devolver** y **Aprobar**.
- [ ] Abre un aviso «por gestionar» y ciérralo sin hacer nada → la burbuja **ámbar** de la campana sigue ahí. Aprueba la reserva → el aviso pasa a «Gestionada».
- [ ] En Inicio aparece «Tienes avisos por gestionar».
- [ ] En el chat como administrador: «¿Qué residentes están en mora?» → llega la tabla.
- [ ] En el chat como residente: la misma pregunta → **no** llega tabla.

### Si algo sale mal
- **La migración falla:** cópiame el error completo; la 0027 es reversible (`alembic downgrade 0026`).
- **El chat no muestra tabla:** revisa que estés con el rol Administrador. Sin IA configurada también debe funcionar para las preguntas comunes.

> **Pendiente para la v5.8:** botón de inglés/español y micrófono de voz a texto. Después, congelar: pruebas, informe y póster (el informe y el manual deberán actualizarse con los cambios de daños, notificaciones y chat).
