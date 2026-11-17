# Versión 3.1 — pasos para dejar todo funcionando

1. **Descomprime** este zip encima de tu proyecto (reemplaza archivos).
2. **Dependencias** (local): `pip install -r requirements.txt`  → agrega `pywebpush`.
3. **Migración** (local): `alembic upgrade head`  → crea 6 tablas (migración 0013). En Render se aplica sola al desplegar.
4. **Claves de avisos push** (una sola vez): `python -m app.generar_vapid`
   Pega `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` y `VAPID_SUBJECT` en tu `.env` y en Render → Environment. La privada NO va a GitHub.
5. **Pruebas**: `pytest -q`  → deben pasar 197.
6. **GitHub**: `git add . && git commit -m "v3.1: sesión segura, push, votaciones, portería sin internet" && git push`
7. **Render**: espera el despliegue (arranca con `alembic upgrade head`). Revisa los logs: sin errores de migración.
8. **Opcional, evita que Render gratis se duerma**: GitHub → Settings → Secrets and variables → Actions → Variables → `APP_URL = https://TU-APP.onrender.com`.
9. **Prueba en el celular** (con la app instalada):
   - Entra una vez con cada rol (todos quedan con sesión cerrada tras el despliegue: es normal, la sesión cambió de formato).
   - Guardia: toma la foto de un paquete → debe seguir con la sesión abierta.
   - Guardia: apaga datos/wifi → registra un ingreso de vehículo → aparece «Pendiente» → prende internet → se envía solo.
   - Configuración → «Activar avisos» → «Probar».
   - Administrador: crea una votación → los residentes reciben el aviso.
