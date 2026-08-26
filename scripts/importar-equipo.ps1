<#
.SYNOPSIS
    Reconstruye el entorno de trabajo en el equipo destino a partir del paquete
    generado por exportar-equipo.ps1.

.DESCRIPTION
    Instala las herramientas base, VSCode en la MISMA version de origen, todas
    las extensiones con su version exacta, y clona el proyecto desde el bundle.

    No instala a ciegas todo lo que hubiera en el equipo de origen: el
    winget-paquetes.json queda como referencia, pero aqui se instala una lista
    curada (sin drivers NVIDIA, software de periféricos, etc.).

.EXAMPLE
    .\importar-equipo.ps1 -Origen "E:\traspaso-jarvis" -Proyecto "C:\Users\migue\jarvis-local"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Origen,
    [string] $Proyecto = "$env:USERPROFILE\jarvis-local",
    [switch] $SoloJarvis,          # instala solo las extensiones de Python/Markdown
    [switch] $SaltarHerramientas   # no toca winget, solo VSCode + proyecto
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Origen)) { throw "No existe la carpeta de origen: $Origen" }

# --- 0. Comprobacion previa -------------------------------------------------
Write-Host "=== Equipo destino ===" -ForegroundColor Cyan
$gpu = (Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "  Windows : $((Get-CimInstance Win32_OperatingSystem).Caption)"
Write-Host "  CPU     : $((Get-CimInstance Win32_Processor).Name)"
Write-Host "  RAM     : $ramGB GB"
Write-Host "  GPU     : $gpu"
Write-Host ""

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "winget no esta disponible. Instala 'App Installer' desde Microsoft Store" -ForegroundColor Red
    Write-Host "o usa las descargas directas listadas en docs/migracion.md" -ForegroundColor Red
    if (-not $SaltarHerramientas) { throw "winget requerido" }
}

# --- 1. Herramientas base ---------------------------------------------------
if (-not $SaltarHerramientas) {
    Write-Host "[1/4] Herramientas base..." -ForegroundColor Yellow
    $paquetes = @(
        'Git.Git',                          # control de versiones
        'Python.PythonInstallManager',      # gestor 'py', permite instalar 3.12
        'Ollama.Ollama',                    # motor LLM local
        'BurntSushi.ripgrep.MSVC',          # lo usa la extension todo-tree
        '7zip.7zip'
    )
    foreach ($p in $paquetes) {
        Write-Host "  -> $p"
        winget install --id $p --exact --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
    }

    # Python 3.12 explicito (decision D-001: el stack de audio/IA no tiene
    # wheels para 3.14 y compilar en Windows falla con frecuencia).
    Write-Host "  -> Python 3.12 (via py manager)"
    py install 3.12 2>&1 | Out-Null
}

# --- 2. VSCode en la misma version ------------------------------------------
Write-Host "[2/4] VSCode..." -ForegroundColor Yellow
$version = (Get-Content "$Origen\vscode-version.txt" | Select-Object -First 1).Trim()
if (-not (Get-Command code -ErrorAction SilentlyContinue)) {
    $url = "https://update.code.visualstudio.com/$version/win32-x64-user/stable"
    $exe = "$env:TEMP\VSCodeUserSetup-$version.exe"
    Write-Host "  Descargando VSCode $version ..."
    Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    Write-Host "  Instalando (silencioso)..."
    Start-Process $exe -ArgumentList '/VERYSILENT','/MERGETASKS=!runcode,addtopath' -Wait
    $env:Path += ";$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin"
} else {
    Write-Host "  Ya instalado: $((code --version | Select-Object -First 1)) (origen: $version)"
}

# --- 3. Extensiones ---------------------------------------------------------
Write-Host "[3/4] Extensiones..." -ForegroundColor Yellow
$lista = Get-Content "$Origen\vscode-extensiones.txt" | Where-Object { $_.Trim() }
if ($SoloJarvis) {
    $nucleo = 'ms-python.python','ms-python.vscode-pylance','ms-python.debugpy',
              'ms-python.vscode-python-envs','charliermarsh.ruff','usernamehw.errorlens',
              'yzhang.markdown-all-in-one','davidanson.vscode-markdownlint',
              'eamodio.gitlens','mhutchie.git-graph','pkief.material-icon-theme',
              'mikestead.dotenv','gruntfuggly.todo-tree'
    $lista = $lista | Where-Object { $nucleo -contains ($_ -split '@')[0] }
}
$fallos = @()
foreach ($ext in $lista) {
    Write-Host "  -> $ext"
    code --install-extension $ext --force 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $fallos += $ext }
}
if ($fallos) {
    Write-Host "  No se pudieron instalar con esa version exacta:" -ForegroundColor Red
    $fallos | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Write-Host "  Reintenta sin version: code --install-extension <id-sin-@version>" -ForegroundColor Red
}

# --- 4. Configuracion de VSCode y proyecto ----------------------------------
Write-Host "[4/4] Configuracion y proyecto..." -ForegroundColor Yellow
$userDir = "$env:APPDATA\Code\User"
New-Item -ItemType Directory -Force -Path $userDir | Out-Null
foreach ($f in @('settings.json','keybindings.json')) {
    if (Test-Path "$Origen\vscode-config\$f") {
        if (Test-Path "$userDir\$f") { Copy-Item "$userDir\$f" "$userDir\$f.bak" -Force }
        Copy-Item "$Origen\vscode-config\$f" "$userDir\$f" -Force
    }
}
if (Test-Path "$Origen\vscode-config\snippets") {
    Copy-Item "$Origen\vscode-config\snippets" $userDir -Recurse -Force
}

if (Test-Path $Proyecto) {
    Write-Host "  Ya existe $Proyecto, no se clona." -ForegroundColor Yellow
} else {
    git clone "$Origen\jarvis-local.bundle" $Proyecto
    Push-Location $Proyecto
    git remote remove origin   # el bundle no es un remoto util a largo plazo
    Pop-Location
}

# Modelos de Ollama copiados en frio, si venian en el paquete
if (Test-Path "$Origen\ollama-models") {
    Write-Host "  Copiando modelos de Ollama..." -ForegroundColor Yellow
    Copy-Item "$Origen\ollama-models\*" "$env:USERPROFILE\.ollama\models\" -Recurse -Force
}

Write-Host ""
Write-Host "Hecho." -ForegroundColor Green
Write-Host "Pendiente manualmente:" -ForegroundColor Green
Write-Host "  1. Crear el venv:  cd $Proyecto ; py -3.12 -m venv .venv"
Write-Host "  2. Revisar que modelo de Ollama cabe en ESTE equipo (ver docs/migracion.md)"
Write-Host "  3. Iniciar sesion en VSCode (Settings Sync / GitHub) si lo usas"
