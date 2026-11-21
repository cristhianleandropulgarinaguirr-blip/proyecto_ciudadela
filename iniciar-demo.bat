@echo off
rem Inicia la DEMOSTRACION en tu computador, completamente separada de tu app real:
rem   - base de datos propia (demo.db) y carpeta de archivos propia (uploads_demo)
rem   - puerto 8001 (tu app real usa el 8000, y pueden estar abiertas a la vez)
rem   - sesion propia: entrar a la demo NO cierra tu sesion de la app real
rem   - cinta "DEMO" arriba para no confundirlas
rem La primera vez crea el conjunto de ejemplo (30 apartamentos) con un administrador de demostracion.
cd /d %~dp0
call venv\Scripts\activate
set MODO_DEMO=1
set LANDING_ACTIVA=1
set PAGOS_SIMULADOS=1
alembic upgrade head
python -m app.seed_demo --local
echo.
echo Demo en http://127.0.0.1:8001/   (la app real sigue en http://127.0.0.1:8000/app/ con iniciar.bat)
start http://127.0.0.1:8001/
uvicorn app.main:app --reload --port 8001
