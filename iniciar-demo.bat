@echo off
rem Inicia la landing comercial/demo. La app real queda disponible en /app/.
cd /d %~dp0
call venv\Scripts\activate
set LANDING_ACTIVA=1
start http://127.0.0.1:8000/
uvicorn app.main:app --reload
