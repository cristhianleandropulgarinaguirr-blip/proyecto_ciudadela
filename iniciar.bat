@echo off
rem Inicia Ciudadela Digital: respalda la base de datos, aplica migraciones pendientes y abre la app.
cd /d %~dp0
call venv\Scripts\activate
set LANDING_ACTIVA=0
if exist propiedad_horizontal.db (
  powershell -NoProfile -Command "New-Item -ItemType Directory -Force respaldos | Out-Null; Copy-Item propiedad_horizontal.db ('respaldos\propiedad_horizontal_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.db')"
  echo Respaldo de la base de datos guardado en la carpeta respaldos.
)
alembic upgrade head
start http://127.0.0.1:8000/app/
uvicorn app.main:app --reload --port 8000
