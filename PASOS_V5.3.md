# Versión 5.3 · Seguridad completa

Requiere **una migración nueva (0024)** que solo AGREGA 4 columnas a `usuarios` (con valor por defecto: nadie cambia). Una dependencia declarada (`cryptography`, que ya venía instalada por `pywebpush`).
Pruebas: **668 de Python** (las 628 de siempre + 40 nuevas) y **9 de Node**, todas en verde. Además probé el flujo completo en un Chromium real (login con código, activar dos pasos, ventana de contraseña).
Revisión de dependencias con `pip-audit`: sin vulnerabilidades conocidas en `requirements.txt`.

---

## 1. Qué pasaba con las sesiones (la respuesta a tu duda)

Los JWT **no** estaban rotos: el token de acceso dura 15 minutos. Lo que mantiene la sesión abierta es una cookie de renovación que se alarga con el uso (por eso al volver horas después seguías dentro). Eso lo hicimos a propósito en la v5.1 para que la cámara del celular no te sacara de la app, pero para el **administrador** (7 días) era demasiado.

Además había un detalle que tú no podías ver: mientras una pestaña esté abierta, la app renueva el token **sola**, así que "8 horas de inactividad" nunca se cumpliría. Por eso ahora la app le avisa al servidor si la persona realmente tocó la pantalla.

## 2. Qué cambia (y dónde)

| Cambio | Dónde | Por qué |
|---|---|---|
| El administrador se cierra tras **8 h sin actividad real** y con tope de **72 h** | `app/sesiones.py`, `app/config.py`, `frontend/js/api.js` (cabecera `X-Actividad`) | Una pestaña olvidada ya no mantiene la sesión abierta |
| Residentes e inquilinos: tope absoluto de **30 días** (antes 60) | `app/config.py` | Siguen cómodos (14 días con uso) pero hay un límite |
| **Confirmar la contraseña** en acciones sensibles (pase de 5 min) | `app/dependencies.py` (`reauth_admin`), `POST /auth/reautenticar`, `frontend/js/reauth.js` | Una sesión robada o una pantalla abierta no basta para crear administradores ni exportar datos |
| **Verificación en dos pasos (TOTP)** + 8 códigos de recuperación | `app/totp.py`, `app/routers/auth.py` (`/auth/2fa/*`), `frontend/js/vistas/configuracion.js`, `vistas/login.js` | Aunque se filtre la contraseña, hace falta el celular |
| Login **sin fuga de tiempo** (correo inexistente también calcula bcrypt) | `app/security.py` (`HASH_FALSO`), `app/routers/auth.py` | El tiempo de respuesta ya no delata qué correos existen |
| Tope de fallos **por IP** (30 en 10 min) además del bloqueo por correo | `app/limitador.py`, `app/routers/auth.py` | Frena a quien prueba muchos correos desde un mismo sitio |
| **Contraseñas débiles** rechazadas (lista de comunes, solo números, repetitivas, contiene el correo) | `app/schemas/usuarios.py` | `12345678` o `password123` caen en segundos |
| `Cache-Control: no-store` en la API, `COOP`/`CORP` same-origin | `app/main.py` | Listados, PDF y Excel con datos personales no quedan en cachés |
| **Barrido de las 200 rutas** como prueba automática | `tests/test_v53_seguridad.py` | Si alguien agrega una ruta y olvida protegerla, la prueba falla |
| Rescate de 2FA: `python -m app.reset_2fa correo` y `DELETE /usuarios/{id}/2fa` | `app/reset_2fa.py`, `app/routers/usuarios.py` | Si se pierde el celular y los códigos |

**Acciones que piden la contraseña de nuevo** (solo del administrador): crear usuario, activar/desactivar usuario, restablecer contraseña, asignar coeficiente, aplicar una importación, quitar los dos pasos de otro administrador y las 5 exportaciones a Excel (cartera, PQRS, paquetes, visitantes, auditoría). La app abre una ventana, y tras confirmar **repite la acción sola**.

Ya estaban bien y no los toqué: bcrypt (12 rondas), tokens de renovación con hash y rotación, detección de robo de token, cookie `HttpOnly` + `SameSite=Strict`, CSP sin scripts inline, HSTS.

## 3. Variables de entorno nuevas (todas opcionales, ya traen valor)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `SESION_INACTIVIDAD_ADMIN_MIN` | 480 | Minutos sin actividad para cerrar al administrador |
| `SESION_MAXIMA_ADMIN_HORAS` | 72 | Tope absoluto de su sesión |
| `SESION_MAXIMA_DIAS` | 30 | Tope de residentes e inquilinos (antes 60) |
| `REAUTH_ACTIVA` / `REAUTH_MINUTOS` | 1 / 5 | Pedir la contraseña en acciones sensibles |
| `EXIGIR_2FA_ADMIN` | 0 | `1` = la verificación en dos pasos es obligatoria y no se puede desactivar |
| `LOGIN_FALLOS_POR_IP` | 30 | Fallos de login por conexión en 10 min |

`SESION_DIAS_ADMIN` **ya no existe**: si la tienes en Render o en tu `.env`, puedes borrarla.

## 4. Qué hacer tras el cambio (en este orden)

1. **Descomprime** `proyecto_ciudadela-v5_3.zip` sobre tu carpeta (o reemplaza la carpeta). No toques tu `.env`.
2. **Dependencias:** `pip install -r requirements.txt`.
3. **Migración:** `alembic upgrade head` (crea las 4 columnas; es seguro repetirla). En Render se aplica sola al desplegar, porque el `startCommand` ya la corre.
4. **Pruebas:** `python -m pytest -q` → deben salir **668 passed** (tardan unos 16 min en tu equipo). Y `node --test tests/js/atras.test.mjs` → 9.
5. **GitHub:** `git add -A`, `git commit -m "v5.3: seguridad completa"`, `git push`.
6. **Render (despliegue):** el push despliega solo. Si usas el Blueprint, haz *Sync* para que tome las 3 variables nuevas del `render.yaml`. En la **demo** (otro servicio) no hace falta nada.
7. **Prueba a mano** en la app ya desplegada:
   - Entra como administrador → **Ajustes → Verificación en dos pasos → Activar**. Escanea el QR, escribe el código y **guarda los 8 códigos de recuperación fuera del celular** (se muestran una sola vez).
   - Cierra sesión y vuelve a entrar: debe pedir el código.
   - Intenta crear un usuario o descargar un Excel: debe aparecer *«Confirma tu contraseña»*.
   - Entra como residente y como guardia: todo debe seguir igual que antes.
8. Cuando todos tus administradores tengan los dos pasos activos, pon `EXIGIR_2FA_ADMIN=1` en Render.

## 5. Cosas que debes saber (para no llevarte un susto)

- **Los dos pasos dependen de `SECRET_KEY`.** El secreto de cada administrador se guarda cifrado con una clave derivada de ella. Si algún día cambias `SECRET_KEY`, no se podrán leer: entrarías con un código de recuperación o con `python -m app.reset_2fa correo`. En Render la clave se genera una sola vez y se conserva; no la regeneres.
- **Un código de 6 dígitos sirve una sola vez.** Si acabas de entrar con uno y te piden otro enseguida (por ejemplo para desactivar), espera al siguiente (cambia cada 30 s).
- **Hora del celular:** si los códigos no coinciden, casi siempre es la hora. Debe estar en automático.
- **Si ya tenías una sesión de administrador abierta** antes de desplegar, vence con la regla nueva la próxima vez que se renueve; no hace falta cerrar nada.
- **Migración 0024 ocupada:** el plan de la Fase 4 de asambleas hablaba de una "0024"; esa pasa a ser la **0025**.

## 6. Lo que NO cubre esta versión (siendo honestos)

Esto es una revisión de código y pruebas automáticas, **no** una auditoría externa ni una prueba de penetración. Antes de venderla a un conjunto grande, te recomiendo:

1. **Prueba de penetración independiente** (aunque sea una básica con OWASP ZAP contra la demo).
2. **IP detrás del proxy de Render:** `--forwarded-allow-ips='*'` hace que quien envía una petición pueda escribir su propia IP. Por eso el bloqueo por **correo** sigue siendo la defensa principal y el tope por IP es una segunda barrera.
3. **Contadores en memoria** (`limitador.py`): si algún día corres varias instancias, hay que pasarlos a Redis.
4. **Hashes SHA-256 antiguos:** se migran a bcrypt cuando la persona entra; mientras alguien no entre, su hash sigue siendo el viejo.
5. **Recuperación de contraseña por correo:** hoy la restablece el administrador. Si algún día se automatiza, debe hacerse con enlace de un solo uso y vencimiento corto.
6. **Estilos en línea:** la política de contenido aún permite `style-src 'unsafe-inline'` (no scripts). Es un riesgo bajo, pero se puede cerrar con más trabajo en el frontend.
7. **Copias de seguridad probadas y política de datos** (Ley 1581 de 2012) revisada con un abogado, antes de operar con datos reales.
8. **El acceso al servidor y a Supabase** es tan crítico como la app: activa dos pasos en tu cuenta de GitHub, Render y Supabase.
