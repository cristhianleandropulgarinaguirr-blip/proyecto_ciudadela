@echo off
rem Inicia Ciudadela Digital para probarla desde un celular conectado al MISMO Wi-Fi que este computador.
rem Es igual a iniciar.bat, pero deja la app visible en tu red local. Usala solo en un Wi-Fi de confianza (tu casa).
cd /d %~dp0
call venv\Scripts\activate
if exist propiedad_horizontal.db (
  powershell -NoProfile -Command "New-Item -ItemType Directory -Force respaldos | Out-Null; Copy-Item propiedad_horizontal.db ('respaldos\propiedad_horizontal_' + (Get-Date -Format 'yyyyMMdd_HHmm') + '.db')"
  echo Respaldo de la base de datos guardado en la carpeta respaldos.
)
alembic upgrade head
echo.
echo ================================================================
powershell -NoProfile -Command "$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notlike 'vEthernet*' -and $_.InterfaceAlias -notlike '*Loopback*' } | Select-Object -First 1 -ExpandProperty IPAddress); Write-Host ('  En el celular abre:  http://' + $ip + ':8000')"
echo   (el celular debe estar en el mismo Wi-Fi que este computador)
echo   Si Windows pregunta por el Firewall, elige "Redes privadas" y Permitir.
echo ================================================================
echo.
start http://127.0.0.1:8000
uvicorn app.main:app --reload --host 0.0.0.0
