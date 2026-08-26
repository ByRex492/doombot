<#
    BOOTSTRAP DEL PORTATIL - proyecto jarvis-local
    =============================================
    Script AUTOSUFICIENTE: no necesita ningun fichero del equipo de origen.
    Reconstruye el entorno completo descargandolo todo de internet.

    USO
      1. Abrir PowerShell COMO ADMINISTRADOR en el portatil.
      2. Set-ExecutionPolicy -Scope Process Bypass -Force
      3. .\bootstrap-portatil.ps1 -RepoUrl "URL_DEL_REPO"

      Sin -RepoUrl instala el entorno pero no clona el proyecto.
      Con -Completo instala las 45 extensiones en vez de las 13 del nucleo.

    Generado desde el equipo BYREX492 el 26/08/2026.
    VSCode 1.134.0 - Git 2.54.0 - Ollama 0.33.0 - Python 3.12.10
#>
[CmdletBinding()]
param(
    [string] $RepoUrl,
    [string] $Proyecto = "$env:USERPROFILE\jarvis-local",
    [switch] $Completo,
    [switch] $SaltarOllama
)

$ErrorActionPreference = 'Stop'
$VSCODE_VERSION = '1.134.0'

# --- PATH -------------------------------------------------------------------
# Un proceso hereda el PATH al arrancar y no ve lo que escriben los
# instaladores despues. Sin esto, git/code/py no serian invocables aqui.
function Update-Path {
    $m = [Environment]::GetEnvironmentVariable('Path','Machine')
    $u = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = (@($m,$u) | Where-Object { $_ }) -join ';'
}
function Resolve-Comando {
    param([Parameter(Mandatory)][string]$Nombre, [string[]]$Rutas = @())
    Update-Path
    if (Get-Command $Nombre -ErrorAction SilentlyContinue) { return $true }
    foreach ($r in $Rutas) {
        if (Test-Path $r) {
            $env:Path = "$env:Path;$r"
            if (Get-Command $Nombre -ErrorAction SilentlyContinue) { return $true }
        }
    }
    return $false
}
function Paso {
    param([string]$T)
    Write-Host ""
    Write-Host ">>> $T" -ForegroundColor Cyan
}

# ============================================================================
# 0. Diagnostico del equipo
# ============================================================================
Paso "Equipo destino"
$so  = Get-CimInstance Win32_OperatingSystem
$gpu = Get-CimInstance Win32_VideoController
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
Write-Host "  Windows : $($so.Caption) build $($so.BuildNumber)"
Write-Host "  RAM     : $ram GB"
foreach ($g in $gpu) {
    $vram = if ($g.AdapterRAM) { "{0:N0} MB" -f ($g.AdapterRAM/1MB) } else { "desconocida" }
    Write-Host "  GPU     : $($g.Name)  (VRAM reportada: $vram)"
}
if ([int]$so.BuildNumber -lt 17763) {
    throw "Windows demasiado antiguo (build $($so.BuildNumber)). VSCode $VSCODE_VERSION necesita Windows 10 1809 (build 17763) o superior."
}
if (-not [Environment]::Is64BitOperatingSystem) { throw "Se requiere Windows de 64 bits." }

# ============================================================================
# 1. Herramientas base
# ============================================================================
Paso "Herramientas base (winget)"
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget no disponible. Instala 'App Installer' desde Microsoft Store y relanza."
}
$paquetes = @(
    'Git.Git',
    'Python.PythonInstallManager',
    'BurntSushi.ripgrep.MSVC',
    '7zip.7zip'
)
if (-not $SaltarOllama) { $paquetes += 'Ollama.Ollama' }
foreach ($p in $paquetes) {
    Write-Host "  -> $p"
    winget install --id $p --exact --silent --accept-package-agreements --accept-source-agreements 2>&1 | Out-Null
}
Update-Path

if (-not (Resolve-Comando -Nombre 'git')) {
    throw "git no es invocable. Cierra y reabre PowerShell y relanza."
}
Write-Host "  git : $(git --version)" -ForegroundColor Green

# --- Python 3.12: el stack de audio/IA no publica wheels para 3.14 ----------
Paso "Python 3.12"
if (Resolve-Comando -Nombre 'py') {
    py install 3.12 --yes 2>&1 | Out-Null
    Update-Path
    Write-Host "  Instalados:" -ForegroundColor Green
    py -0p | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  'py' no disponible. Instala Python 3.12 a mano:" -ForegroundColor Red
    Write-Host "  python.org -> Downloads -> Release 3.12.10 -> Windows installer 64-bit" -ForegroundColor Red
}

# ============================================================================
# 2. VSCode en la version exacta del equipo de origen
# ============================================================================
Paso "VSCode $VSCODE_VERSION"
$rutasCode = @(
    "$env:LOCALAPPDATA\Programs\Microsoft VS Code\bin",
    "$env:ProgramFiles\Microsoft VS Code\bin"
)
if (Resolve-Comando -Nombre 'code' -Rutas $rutasCode) {
    Write-Host "  Ya presente: $((code --version | Select-Object -First 1))"
} else {
    $exe = "$env:TEMP\VSCodeUserSetup-$VSCODE_VERSION.exe"
    # La URL se compone en piezas a proposito: escrita del tiron, las
    # herramientas que auto-enlazan (Notion entre ellas) la envuelven entre
    # < y > al pegar el script, y la descarga falla sin decir por que.
    $esquema  = 'https'
    $servidor = 'update.code.visualstudio.com'
    $urlVSCode = "$esquema" + "://" + "$servidor/$VSCODE_VERSION/win32-x64-user/stable"
    Write-Host "  Descargando..."
    Invoke-WebRequest $urlVSCode -OutFile $exe -UseBasicParsing
    Write-Host "  Instalando..."
    Start-Process $exe -ArgumentList '/VERYSILENT','/MERGETASKS=!runcode,addtopath' -Wait
    if (-not (Resolve-Comando -Nombre 'code' -Rutas $rutasCode)) {
        throw "VSCode instalado pero 'code' no es invocable. Cierra y reabre PowerShell y relanza."
    }
    Write-Host "  Instalado: $((code --version | Select-Object -First 1))" -ForegroundColor Green
}

# ============================================================================
# 3. Extensiones (versiones fijadas a las del equipo de origen)
# ============================================================================
# Las 13 imprescindibles para este proyecto.
$extNucleo = @(
    'charliermarsh.ruff@2026.74.0',
    'davidanson.vscode-markdownlint@0.62.1',
    'eamodio.gitlens@19.0.1',
    'gruntfuggly.todo-tree@0.0.226',
    'mhutchie.git-graph@1.30.0',
    'mikestead.dotenv@1.0.1',
    'ms-python.debugpy@2026.6.0',
    'ms-python.python@2026.4.0',
    'ms-python.vscode-pylance@2026.3.1',
    'ms-python.vscode-python-envs@1.36.0',
    'pkief.material-icon-theme@5.38.1',
    'usernamehw.errorlens@3.28.0',
    'yzhang.markdown-all-in-one@3.6.3'
)

# Las otras 32: Java, Dart/Flutter, bases de datos, contenedores, estetica.
# jarvis-local no las necesita. Se instalan solo con -Completo.
$extResto = @(
    'be5invis.vscode-custom-css@7.5.1',
    'brandonkirbyson.vscode-animations@2.0.8',
    'dart-code.dart-code@3.140.0',
    'dart-code.flutter@3.140.0',
    'dbaeumer.vscode-eslint@3.0.34',
    'enkia.tokyo-night@1.1.2',
    'esbenp.prettier-vscode@12.4.0',
    'geometrislp.gson-toolbox@1.1.0',
    'github.vscode-pull-request-github@0.162.0',
    'mateoryhr.minecraft-theme@1.0.7',
    'ms-azuretools.vscode-containers@2.5.0',
    'ms-azuretools.vscode-docker@2.0.0',
    'ms-vscode-remote.remote-wsl@0.104.3',
    'mtxr.sqltools@0.28.6',
    'mtxr.sqltools-driver-mssql@0.4.11',
    'mtxr.sqltools-driver-mysql@0.6.7',
    'mtxr.sqltools-driver-sqlite@0.5.4',
    'oderwat.indent-rainbow@8.3.1',
    'oracle.oracle-java@26.0.2',
    'randomfractalsinc.duckdb-sql-tools@1.6.0',
    'redhat.java@1.55.0',
    'redhat.vscode-yaml@1.24.0',
    'tomoki1207.pdf@1.2.2',
    'visualstudioexptteam.intellicode-api-usage-examples@0.2.9',
    'visualstudioexptteam.vscodeintellicode@1.3.2',
    'vscjava.migrate-java-to-azure@1.23.0',
    'vscjava.vscode-gradle@3.18.0',
    'vscjava.vscode-java-debug@0.59.0',
    'vscjava.vscode-java-dependency@0.27.6',
    'vscjava.vscode-java-pack@0.31.1',
    'vscjava.vscode-java-upgrade@2.1.2',
    'vscjava.vscode-maven@0.45.3'
)

$extensiones = if ($Completo) { $extNucleo + $extResto } else { $extNucleo }
Paso "Extensiones ($($extensiones.Count))"
$fallos = @()
foreach ($e in $extensiones) {
    Write-Host "  -> $e"
    code --install-extension $e --force 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $fallos += $e }
}
if ($fallos) {
    Write-Host "  Fallaron con version exacta. Reintentando sin fijarla:" -ForegroundColor Yellow
    foreach ($e in $fallos) {
        $id = ($e -split '@')[0]
        Write-Host "    -> $id"
        code --install-extension $id --force 2>&1 | Out-Null
    }
}

# ============================================================================
# 4. settings.json
# ============================================================================
# Copia del equipo de origen con los DOS ajustes rotos ya corregidos:
#  - vscode_custom_css.imports apuntaba a c:/Users/IFC302_2/... (usuario que no
#    existe) y a la version 2.0.7 de una extension que aqui es 2.0.8. Eliminado.
#  - todo-tree.ripgrep.ripgrep era una ruta absoluta con el usuario 'migue'
#    incrustado. Se recalcula para ESTE equipo.
Paso "Configuracion de VSCode"
$userDir = "$env:APPDATA\Code\User"
New-Item -ItemType Directory -Force -Path $userDir | Out-Null
if (Test-Path "$userDir\settings.json") {
    Copy-Item "$userDir\settings.json" "$userDir\settings.json.bak" -Force
    Write-Host "  settings.json anterior guardado como settings.json.bak"
}

$rg = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\rg.exe"
$ajustes = [ordered]@{
    'workbench.colorTheme'                       = 'Minecraft: Nether'
    'workbench.iconTheme'                        = 'material-icon-theme'
    'files.associations'                         = @{ '*.jsonc' = 'json' }
    'jdk.telemetry.enabled'                      = $true
    'redhat.telemetry.enabled'                   = $true
    'gitlens.ai.model'                           = 'vscode'
    'gitlens.ai.vscode.model'                    = 'copilot:gpt-4.1'
    'github.copilot.nextEditSuggestions.enabled' = $true
    'github.copilot.selectedCompletionModel'     = ''
    'github.copilot.enable'                      = [ordered]@{
        '*' = $false; 'plaintext' = $false; 'markdown' = $false; 'scminput' = $false
    }
    'sqltools.connections'                       = @()
}
if (Test-Path $rg) { $ajustes['todo-tree.ripgrep.ripgrep'] = $rg }
$ajustes | ConvertTo-Json -Depth 6 | Set-Content "$userDir\settings.json" -Encoding UTF8
Write-Host "  settings.json escrito" -ForegroundColor Green

# ============================================================================
# 5. El proyecto
# ============================================================================
Paso "Proyecto"
if ($RepoUrl) {
    if (Test-Path $Proyecto) {
        Write-Host "  Ya existe $Proyecto, no se clona."
    } else {
        git clone $RepoUrl $Proyecto
        Write-Host "  Clonado en $Proyecto" -ForegroundColor Green
    }
    if ((Test-Path $Proyecto) -and (Get-Command py -ErrorAction SilentlyContinue)) {
        Push-Location $Proyecto
        if (-not (Test-Path '.venv')) {
            Write-Host "  Creando entorno virtual con Python 3.12..."
            py -3.12 -m venv .venv
            Write-Host "  Activalo con: .venv\Scripts\Activate.ps1" -ForegroundColor Green
        }
        Pop-Location
    }
} else {
    Write-Host "  Sin -RepoUrl: omitido. Clona a mano cuando tengas la URL:" -ForegroundColor Yellow
    Write-Host "    git clone <url> $Proyecto"
}

# ============================================================================
# 6. Ollama: eleccion de modelo segun la GPU DE ESTE equipo
# ============================================================================
if (-not $SaltarOllama) {
    Paso "Ollama"
    $vramMax = 0
    foreach ($g in $gpu) {
        if ($g.AdapterRAM -and $g.AdapterRAM -gt $vramMax) { $vramMax = $g.AdapterRAM }
    }
    $vramGB = [math]::Round($vramMax / 1GB, 1)
    Write-Host "  VRAM detectada: $vramGB GB"
    Write-Host "  (Win32 la reporta mal en algunas GPU; comprueba a mano si dudas)"
    Write-Host ""
    Write-Host "  El equipo de origen usa gemma4:12b (7,6 GB) sobre 14,8 GiB de VRAM."
    Write-Host "  Ese modelo NO cabe aqui salvo que tengas 8 GB o mas."
    Write-Host ""
    if ($vramGB -ge 8) {
        Write-Host "  Recomendado:  ollama pull gemma4:12b" -ForegroundColor Green
    } elseif ($vramGB -ge 4) {
        Write-Host "  Recomendado:  ollama pull qwen3:8b   (5,2 GB)" -ForegroundColor Yellow
    } else {
        Write-Host "  VRAM insuficiente o no detectada." -ForegroundColor Yellow
        Write-Host "  Opciones: un modelo de 3-4B, o apuntar al Ollama del sobremesa"
        Write-Host "  por red (OLLAMA_HOST=0.0.0.0 alli, su IP aqui)."
    }
    Write-Host ""
    Write-Host "  Tras cargarlo, comprueba con 'ollama ps' que PROCESSOR dice 100% GPU."
}

# ============================================================================
# 7. Verificacion
# ============================================================================
Paso "Verificacion"
Update-Path
foreach ($c in @('git','code','py','ollama')) {
    $ok = [bool](Get-Command $c -ErrorAction SilentlyContinue)
    $txt = if ($ok) { 'OK' } else { 'NO ENCONTRADO' }
    $col = if ($ok) { 'Green' } else { 'Red' }
    Write-Host ("  {0,-8} {1}" -f $c, $txt) -ForegroundColor $col
}
Write-Host ""
Write-Host "Pendiente y manual:" -ForegroundColor Cyan
Write-Host "  - Activar Settings Sync en VSCode (Manage > Backup and Sync Settings...)"
Write-Host "  - Elegir y descargar el modelo de Ollama"
Write-Host "  - Si algo no aparece, cierra y reabre PowerShell: el PATH se refresca al arrancar."
