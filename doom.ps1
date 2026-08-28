# Lanzador de D.O.O.M. para PowerShell. Ver doom.cmd para el porque.
$venv = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
    Write-Host "No hay entorno virtual en $PSScriptRoot\.venv"
    Write-Host 'Crealo con:  py -3.12 -m venv .venv; .venv\Scripts\pip install -e ".[dev,voice]"'
    exit 1
}
& $venv -m doombot @args
