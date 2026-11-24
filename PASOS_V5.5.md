# Versión 5.5 · Limpieza, optimización y correcciones

Esta versión **no cambia ninguna función visible** ni la base de datos: no hay migración nueva. Ordena el proyecto, quita lo que sobraba y corrige tres fugas de memoria del frontend. Todo quedó verificado con las pruebas automáticas (ver el final).

---

## 1. Qué se eliminó (basura confirmada)

Antes de borrar cada archivo se buscó si algo lo usaba (código, HTML, README, tests). Estos no los usaba nada:

| Archivo | Por qué sobraba |
|---|---|
| `docs/Captura de pantalla (137).png` (1,2 MB) | Captura suelta; ningún documento la mencionaba. Era el archivo más pesado del repositorio. |
| `frontend/img/ciudadela.svg` (12 KB) | Ninguna página, CSS ni script la cargaba. |
| `frontend/js/vistas/demos.js` | Pantalla del administrador que pedía `/demo/solicitudes`. Ese endpoint **ya no existe** (en la v4.7 las solicitudes de demo pasaron a WhatsApp/Telegram), así que el archivo nunca podía funcionar. Además el Service Worker lo descargaba en cada celular sin necesidad. |
| 10 archivos `PASOS_V3.1 … PASOS_V4.1.md` de la raíz | Eran copias **idénticas** (comparadas byte a byte) de las que ya están en `docs/historial/`. |

## 2. Qué se reorganizó

Las guías `PASOS_V4.3 … PASOS_V5.4.md` pasaron a `docs/historial/`. En la raíz queda **solo la guía de la versión actual** (`PASOS_V5.5.md`). Se actualizaron los enlaces que las mencionaban: `README.md`, `render.yaml` (comentario) y los comentarios de `app/config.py` y `app/asamblea_votos.py`.

## 3. Código muerto quitado (Python y JavaScript)

- **26 imports sin usar** en `app/`, `scripts/` y `tests/` (por ejemplo `datetime` en cinco routers, `get_current_user` en `asambleas.py` y `paz_y_salvo.py`). Menos código que cargar al arrancar el servidor.
- `app/asamblea_acta.py`: un estilo de PDF (`mono`) que se definía y nunca se aplicaba.
- `app/routers/auth.py`: en el login se calculaba `ahora` y no se usaba.
- `app/importacion.py`: el diccionario `TITULOS` (nadie lo leía).
- `frontend/js/offline.js`: la función exportada `resultadoDe` (nadie la llamaba).

## 4. Errores corregidos (frontend)

Tres lugares añadían un oyente de eventos cada vez que se abría una pantalla o se iniciaba sesión, **y nunca lo quitaban**. Con el uso se acumulaban y gastaban batería y datos:

1. **`frontend/js/campana.js` (el más importante).** Cada vez que se construía la barra superior (al cerrar e iniciar sesión) se agregaba otro oyente de «volví a la app». Al regresar a la app, **todos** disparaban a la vez una petición a `/notificaciones/conteo`. Ahora hay un único oyente y `detenerCampana()` lo quita.
2. **`frontend/js/foto.js`.** Cada formulario con foto agregaba un oyente que apaga la cámara al ocultar la pestaña y no se retiraba. Ahora se retira solo cuando el formulario ya no está en pantalla.
3. **`frontend/js/vistas/login.js`.** El oyente `pageshow` (autocompletado del navegador) se acumulaba en cada cierre de sesión. Ahora se retira cuando el formulario de login desaparece.

## 5. Prueba automática nueva

`tests/js/imports.test.mjs` revisa que **todo `import { algo }` del frontend exista de verdad**. Es el error que viste con *«'./ui.js' does not provide an export named 'diaLocal'»*: solo se notaba al abrir esa pantalla. Ahora GitHub lo detecta antes de publicar (se añadió al workflow `.github/workflows/ci.yml`). Se comprobó que la prueba falla si se provoca un import roto y pasa cuando todo está bien.

## 6. Lo que se revisó y NO hacía falta tocar

- **Los archivos `pasos.md` no ralentizan la app** (ver respuesta anterior); aun así quedaron ordenados.
- **Consultas a la base de datos:** no hay consultas dentro de bucles en las pantallas de uso diario. KPIs, importación y cartera ya usan agregados SQL y lotes.
- **Autenticación por petición:** el rol ya viaja en la misma consulta del usuario (`lazy="joined"`) y la sesión tiene caché de 15 s.
- **Índices:** las claves foráneas sin índice son, casi todas, columnas de auditoría («quién registró») que nunca se filtran. Las pocas que sí se consultan lo hacen junto a un filtro ya indexado en tablas pequeñas. **No se creó migración**: el riesgo de tocar la base no compensa una ganancia que no se notaría.
- **Imágenes:** se recomprimieron sin pérdida y ya estaban óptimas (ahorro 0 KB); no se modificó ninguna.
- **CSS (122 KB):** las únicas 4 clases «sin uso» son dinámicas (`t-Evento`, `t-Urgente`…); borrarlas habría roto las etiquetas de la Cartelera.
- **Dependencias** (`requirements.txt`): sin cambios.

---

## Cómo dejar todo funcionando (en orden)

1. **Descomprime** este proyecto sobre tu carpeta (reemplaza archivos). Como se **eliminaron** archivos, en tu carpeta de siempre bórralos a mano si siguen ahí: `frontend/js/vistas/demos.js`, `frontend/img/ciudadela.svg`, `docs/Captura de pantalla (137).png` y los `PASOS_V*.md` viejos de la raíz. (Git los quita solo al hacer commit si los borras.)
2. **Migración:** *no hay ninguna nueva.* No hace falta `alembic upgrade head` (aunque no pasa nada si lo corres).
3. **Pruebas en tu PC** (con el entorno virtual activo):
   ```
   python -m pytest -q
   node --test tests/js/atras.test.mjs
   node --test tests/js/imports.test.mjs
   ```
   Deben pasar todas.
4. **Prueba a mano** (2 minutos): `iniciar.bat`, inicia sesión con cada rol, abre Inicio, Cartelera, un formulario con foto (Daños o Paquetes) y cierra e inicia sesión dos veces.
5. **GitHub:**
   ```
   git add -A
   git commit -m "v5.5: limpieza, optimización y corrección de fugas del frontend"
   git push
   ```
   Si habías subido `v5.4` sin hacer commit antes, súbela primero.
6. **Render:** el despliegue arranca solo al hacer push (si tienes autodeploy). Espera a que diga **Live**, abre `/salud` y luego la app. Haz lo mismo con el servicio de la **demo**.
7. **En el celular:** la app instalada descarga la versión nueva sola (el Service Worker cambia de versión). Si algo se ve viejo, ciérrala por completo y ábrela otra vez.
8. **Revisa** en GitHub → pestaña *Actions* que el workflow «Pruebas» salga en verde.
