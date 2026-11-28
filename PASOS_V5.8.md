# Versión 5.8 · Cambios que pidió el instructor (entrega 2 de 2)

Esta entrega completa la lista: el **botón de inglés/español** (cambio 4) y el **micrófono de voz a texto** (cambio 5).
**Incluye todo lo de la v5.7** (daños con aprobación, notificaciones «por gestionar» y chat con datos), así que es el zip completo y definitivo.

> **No hay migración nueva en la v5.8.** Si no aplicaste la v5.7, corre `alembic upgrade head`: aplicará la `0027`.

---

## 1. Cambio 4 · Botón de inglés / español

### Cómo se usa
- Hay un botón **EN / ES** en la barra superior (junto al tema claro/oscuro) y en la pantalla de ingreso. Muestra el idioma **al que se cambia**: estando en español dice «English»; estando en inglés dice «Español».
- La preferencia **se recuerda** en el dispositivo. Al cambiar, la pantalla se recarga (la sesión no se pierde).
- Fechas, horas y dinero cambian de formato (`1.250.000` ↔ `1,250,000`, «hace 5 min» ↔ «5 min ago»).
- El **chat responde en inglés** cuando la interfaz está en inglés.

### Cómo funciona (y por qué así)
En vez de tocar las ~40 pantallas una por una, hay un **traductor** (`i18n.js`) y un **diccionario** (`i18n-en.js`):
1. El código sigue escrito en español; el español es la «llave» del diccionario.
2. En inglés, el traductor reemplaza los textos que coinciden **exactamente** con el diccionario (y los que tienen partes variables, con patrones como «Tienes 3 paquetes en portería»). También traduce `placeholder`, `title`, `aria-label` y `alt`.
3. Un `MutationObserver` traduce lo que aparece después (pantallas nuevas, avisos, ventanas, el chat), **antes de pintar**: no se ve un destello en español.
4. **Si a un texto le falta traducción, se ve en español.** Nada se rompe.

**Ventaja:** agregar o corregir una traducción es editar **una línea** en `i18n-en.js`, sin tocar las pantallas.

### Qué cubre y qué no (con honestidad)
| | Cobertura |
|---|---|
| Ingreso, menú, Inicio, Daños, Cartera, Paquetes, Reservas, PQRS, Cartelera, Visitas, Visitantes, Portería, Ajustes, Votaciones, Trasteos, Arrendamientos, Usuarios, Documentos, Emergencias, Indicadores, Auditoría, QR, Escáner, Importar, notificaciones y chat | **≈ 95 %** de los textos |
| **Asambleas** (actas, poderes, quórum: textos legales largos) | **≈ 13 %** — sigue mayormente en español |
| Total de la app | **≈ 81 %** de los textos fijos (1.473 de 1.797) |

**Lo que NO se traduce a propósito:**
- Lo que escribe la gente: nombres, anuncios, descripciones de daños, respuestas a PQRS. (Solo coinciden textos **exactos** del diccionario.)
- Los **borradores con IA** (PQRS, daños, anuncios) se redactan en español, porque la administración los lee en español.
- Los textos que arma el servidor con datos variables (por ejemplo el detalle de un aviso) y la política de privacidad.
- Las páginas **públicas** del pase de visitante y del técnico (otra aplicación aparte, sin sesión).
- El **chat sin IA** (modo básico): responde con la guía en español; en inglés solo habla bien con la IA activa.

**Para completar lo que falta:** abre la app en inglés, escribe `i18nFaltantes()` en la consola del navegador (F12) y verás la lista de textos sin traducir; agrégalos al diccionario.

### Dónde se cambió
| Archivo | Qué se hizo |
|---|---|
| `frontend/js/i18n.js` *(nuevo)* | Idioma, traductor, observador y el botón EN/ES. |
| `frontend/js/i18n-en.js` *(nuevo)* | El diccionario (≈ 1.400 textos) y los patrones. |
| `frontend/js/app.js`, `vistas/login.js` | Arranque (idioma primero, luego se pinta) y el botón en la barra y en el ingreso. |
| `frontend/js/ui.js` y 8 vistas | Fechas, horas y dinero según el idioma (antes decían `"es-CO"` fijo). |
| `frontend/js/chat.js`, `app/routers/asistente.py`, `app/schemas/asistente.py` | El chat envía `idioma` y la IA responde en ese idioma (también el segundo paso del análisis de datos). |

---

## 2. Cambio 5 · Micrófono de voz a texto

### Cómo se usa
- En cada campo donde se redacta (descripción de un daño, PQRS, anuncios, respuestas, **el chat**…) aparece un botón de **micrófono**.
- Púlsalo y habla; el texto aparece mientras hablas. Púlsalo otra vez para detener. Escribe donde está el cursor y respeta lo que ya habías escrito.
- La **primera vez** se explica que el navegador manda el audio a su servicio de voz (en Chrome, al de Google) y se pide aceptar. Luego el navegador pide permiso del micrófono.
- Entiende **español o inglés** según el idioma elegido.

### Protecciones
- **Nunca** aparece en campos sensibles: contraseñas, códigos, cédulas y documentos, teléfonos, correos, tarjetas, placas, referencias… Cualquier campo se puede excluir a mano con `data-sin-voz`.
- Solo escucha mientras el botón está activo: se detiene al pulsarlo, al **enviar**, al **cambiar de pantalla** o si **escondes la app**.
- Respeta el límite de caracteres del campo y avisa.

### Límites reales (importante para tu demostración)
- **Funciona en:** Chrome, Edge, Safari y los navegadores de Android. **No funciona en Firefox** (ahí simplemente no aparece el botón).
- **Necesita internet** (el reconocimiento lo hace el servicio del navegador).
- **iPhone con la app instalada en la pantalla de inicio:** el dictado del navegador no es fiable, así que el botón no se muestra; el iPhone tiene el micrófono del teclado.
- Requiere **HTTPS** (Render ya lo tiene; en local funciona en `localhost`).
- El audio lo procesa el navegador, **no este sistema**. Por eso el aviso de la primera vez.

### Dónde se cambió
| Archivo | Qué se hizo |
|---|---|
| `app/main.py` | El encabezado `Permissions-Policy` decía `microphone=()` (**prohibía** el micrófono a toda la app). Ahora `microphone=(self)`. Las páginas públicas del pase y del técnico **siguen sin micrófono**. |
| `frontend/js/voz.js` *(nuevo)* | El botón, el dictado, los campos permitidos y el aviso de privacidad. |
| `frontend/js/ui.js`, `estilos.css` | Ícono del micrófono y estilos (con animación que respeta «reducir movimiento»). |
| `frontend/js/app.js` | Arranque del módulo. |

---

## 3. Cómo dejarlo funcionando (en orden)

1. **Descomprime** el zip y copia su contenido **sobre tu carpeta del proyecto**. No borres tu `.env`.
2. **Migración (local):** `alembic upgrade head`. Si ya tenías la v5.7 dirá que no hay nada nuevo; está bien.
3. **Pruebas (local):**
   ```
   python -m pytest -q
   node --test tests/js/*.mjs
   ```
   Esperado: **759 del backend** y **19 de JS** en verde.
4. **Prueba a mano** antes de subir (lista abajo). El micrófono y el idioma **solo se pueden probar en un navegador real**; las pruebas automáticas cubren la lógica, no el navegador.
5. **GitHub:**
   ```
   git add .
   git commit -m "v5.8: idioma ingles/espanol y dictado por voz"
   git push
   ```
6. **Despliegue (Render):** se despliega solo al subir. Espera «Live».
7. **Prueba en producción con un celular real.** Después de desplegar, **recarga la app dos veces** (la primera descarga la versión nueva y la segunda la activa).

### Lista de prueba manual
**Idioma**
- [ ] En el ingreso aparece el botón «English». Púlsalo: todo pasa a inglés. Ingresa.
- [ ] El menú, Inicio, Daños, Cartera y Reservas están en inglés; las fechas muestran «Nov 28» y el dinero «$1,250,000».
- [ ] Recarga la página: sigue en inglés (se recuerda). Pulsa «Español»: vuelve todo.
- [ ] En el chat (con IA) pregunta «Which residents are overdue?»: responde en inglés y llega la tabla.
- [ ] Abre Asambleas en inglés: está **mayormente en español** (es lo esperado, ver la tabla de cobertura).

**Micrófono (Chrome en Android o escritorio)**
- [ ] Entra a «Reportar un daño»: el campo «Cuéntanos los detalles» tiene un micrófono. Púlsalo, acepta el aviso y el permiso, y dicta una frase.
- [ ] El texto aparece mientras hablas; pulsa el micrófono para detener.
- [ ] Dicta **en medio** de un texto que ya escribiste: se inserta donde estaba el cursor.
- [ ] En el ingreso (correo y contraseña) y en cédulas/teléfonos **no** hay micrófono.
- [ ] En el chat, el micrófono está junto al botón de enviar; al enviar, se apaga solo.
- [ ] Abre la app en Firefox: no aparece ningún micrófono (y nada se ve roto).

### Si algo sale mal
- **El micrófono no aparece:** revisa que sea Chrome/Edge/Safari y que el sitio esté en HTTPS. Si acabas de desplegar, recarga dos veces.
- **Dice «Permiso del micrófono denegado»:** toca el candado junto a la dirección y permite el micrófono.
- **Algo quedó en español en inglés:** es una traducción que falta; ver `i18nFaltantes()` arriba.

> **Con esto quedan los cinco cambios del instructor.** Lo que sigue es congelar: pruebas, y actualizar el informe técnico y el manual de usuario (estados de daños, notificaciones, chat con datos, idioma y voz) y el póster.
