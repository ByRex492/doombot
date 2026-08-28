@echo off
REM Lanzador de D.O.O.M.
REM
REM Existe porque "python -m doombot" con el entorno virtual sin activar usa el
REM Python del sistema, que no tiene el paquete instalado, y el error que sale
REM -"No module named doombot"- no delata la causa. Ha pasado ya varias veces
REM en las dos maquinas.
REM
REM   doom                      diagnostico
REM   doom escuchar tecla       bucle de voz con pulsacion
REM   doom "que hora es"        pregunta al modelo
setlocal
set "VENV=%~dp0.venv\Scripts\python.exe"
if not exist "%VENV%" (
    echo No hay entorno virtual en %~dp0.venv
    echo Crealo con:  py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -e ".[dev,voice]"
    exit /b 1
)
"%VENV%" -m doombot %*
