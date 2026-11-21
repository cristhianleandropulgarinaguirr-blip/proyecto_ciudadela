# Versión 5.1 · «Cerrar sesión» a prueba de fallos

**No hay migración nueva, ni dependencias nuevas, ni variables nuevas.** Pruebas: 591 de Python y 9 de Node en verde.

## 1. ¿Se rompieron los JWT en la v5.0?
No. Lo comprobé contra el servidor: login 200 → `/usuarios/me` 200 → logout 200 → el MISMO token de acceso da 401 → refresh con la cookie vieja da 401.
Lo único que la v5.0 tocó de seguridad fue, solo con `MODO_DEMO=1`, el nombre de la cookie (`ciudadela_rt_demo`) y la clave de firma. Sin `MODO_DEMO` todo es idéntico a la v4.9.

## 2. Qué se cambió, dónde y por qué
Al revisar el navegador encontré tres puntos donde «Cerrar sesión» podía quedarse a medias, sin culpa del JWT:

| Archivo | Problema | Cambio |
|---|---|---|
| `frontend/js/push.js` | `liberarPushAlSalir()` espera a `navigator.serviceWorker.ready`, que **nunca termina** si el service worker no se instaló. El botón se quedaba esperando y `/auth/logout` no se enviaba. | Tope de 3 s: si no terminó, se sigue. |
| `frontend/js/api.js` | `cerrarEnServidor()` esperaba la respuesta sin límite (un servidor de Render dormido tarda mucho). | Espera máxima de 6 s; `keepalive` deja que la petición siga sola. |
| `frontend/js/app.js` | En `cerrarSesion()`, si algo local fallaba (IndexedDB, chat, borrado del perfil), se saltaba `sesion.cerrar()` y nunca volvía al login. | Todo dentro de `try/finally`: el cierre local y la pantalla de login ocurren **siempre**. |

El servicio worker toma una versión nueva solo (se calcula de los archivos), así que no hay que limpiar caché a mano.

## 3. Qué hacer después (en este orden)
1. Descomprime el zip sobre tu carpeta (acepta reemplazar).
2. Pruebas: `python -m pytest -q` y `node --test tests/js/atras.test.mjs`.
3. Local: `.\iniciar.bat` → entra, pulsa **Cerrar sesión** → debe volver al login; recarga la página: debe seguir en el login. En las herramientas del navegador (Application → Cookies) `ciudadela_rt` debe desaparecer.
4. GitHub, un commit por versión y en orden (el repo sigue en una versión vieja): v4.8, v4.9, v5.0 y al final esta v5.1 (`git add .`, `git commit -m "v5.1 cierre de sesión a prueba de fallos"`, `git push`).
5. Render: auto-deploy o *Manual Deploy → Deploy latest commit*. Sin variables nuevas.
6. Prueba ya desplegado, en el celular: cerrar sesión, volver a abrir la app y comprobar que pide la clave.

## 4. Cómo volver atrás
`git revert` del commit de la v5.1. No hay nada más que deshacer.

## 5. Límites honestos
- No pude reproducir «la sesión no se cierra» en el servidor: ahí todo funciona. Estos arreglos cubren las causas que encontré en el navegador, pero **no probé en un celular real**.
- Si después de esto sigue pasando, dime cuál de estos casos es: (a) el botón no hace nada, (b) vuelve al login pero al recargar entras solo, (c) la sesión no vence nunca. Cada uno apunta a un sitio distinto.
