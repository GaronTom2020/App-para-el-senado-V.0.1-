@echo off
setlocal
REM Abre el programa desde el codigo fuente (la primera vez instala lo necesario).
cd /d "%~dp0"
if exist .venv\Scripts\pythonw.exe goto :abrir
call :buscar_python || goto :sin_python
echo Preparando el entorno por unica vez...
%PY% -m venv .venv || goto :error
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
:abrir
start "" .venv\Scripts\pythonw.exe app.py
exit /b 0

:error
echo.
echo No se pudo preparar el entorno. Revisa los mensajes de arriba.
pause
exit /b 1

:buscar_python
REM 1) lanzador py  2) python en el PATH  3) carpetas donde instala python.org
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3" && exit /b 0
python --version >nul 2>nul && set "PY=python" && exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*") do (
  if exist "%%~D\python.exe" set "PY="%%~D\python.exe""
)
if not defined PY exit /b 1
%PY% --version >nul 2>nul && exit /b 0
set "PY="
exit /b 1

:sin_python
echo.
echo No se encontro Python en esta PC (el "python" de la Microsoft Store es solo un atajo).
echo.
echo   1. Descargalo de https://www.python.org/downloads/ (version 3.10 o posterior).
echo   2. En la primera pantalla del instalador marca "Add python.exe to PATH".
echo      Sin permisos de administrador: desmarca "Use admin privileges when installing py.exe".
echo   3. Toca "Install Now", cerra esta ventana y volve a ejecutar este archivo.
echo.
echo Para que no aparezca mas la Microsoft Store al escribir "python": Configuracion ^> Aplicaciones
echo ^> Configuracion avanzada de aplicaciones ^> Alias de ejecucion de aplicaciones ^> desactivar los de Python.
echo.
pause
exit /b 1
