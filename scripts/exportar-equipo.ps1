<#
.SYNOPSIS
    Genera un paquete de traspaso con todo lo necesario para reproducir este
    entorno de trabajo en otro equipo Windows.

.DESCRIPTION
    No copia programas: copia la *receta* (versiones exactas, listas de paquetes,
    configuracion) mas el repositorio completo con su historial. Lo unico pesado
    y opcional son los modelos de Ollama.

.EXAMPLE
    .\scripts\exportar-equipo.ps1
    .\scripts\exportar-equipo.ps1 -Destino "E:\traspaso" -IncluirModelosOllama
#>
[CmdletBinding()]
param(
    [string] $Destino = "$env:USERPROFILE\Desktop\traspaso-jarvis",
    [switch] $IncluirModelosOllama
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "Exportando a: $Destino" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $Destino | Out-Null

# --- 1. VSCode: version exacta + extensiones con su version -----------------
Write-Host "[1/5] VSCode..." -ForegroundColor Yellow
$vscodeVersion = (code --version | Select-Object -First 1)
$vscodeVersion | Out-File "$Destino\vscode-version.txt" -Encoding utf8
code --list-extensions --show-versions | Out-File "$Destino\vscode-extensiones.txt" -Encoding utf8

$userDir = "$env:APPDATA\Code\User"
New-Item -ItemType Directory -Force -Path "$Destino\vscode-config" | Out-Null
foreach ($f in @('settings.json','keybindings.json')) {
    if (Test-Path "$userDir\$f") { Copy-Item "$userDir\$f" "$Destino\vscode-config\" -Force }
}
if (Test-Path "$userDir\snippets") {
    Copy-Item "$userDir\snippets" "$Destino\vscode-config\" -Recurse -Force
}

# --- 2. Paquetes instalados via winget --------------------------------------
Write-Host "[2/5] Paquetes winget..." -ForegroundColor Yellow
winget export --output "$Destino\winget-paquetes.json" --include-versions --accept-source-agreements | Out-Null

# --- 3. El proyecto, con historial completo ---------------------------------
# Un bundle es un unico fichero que contiene todo el repositorio (commits,
# ramas, historial). Se clona en destino como si fuera un remoto normal.
Write-Host "[3/5] Repositorio..." -ForegroundColor Yellow
Push-Location $repo
$sucio = git status --porcelain
if ($sucio) {
    Write-Host "  AVISO: hay cambios sin commitear. El bundle NO los incluye:" -ForegroundColor Red
    $sucio | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
}
git bundle create "$Destino\jarvis-local.bundle" --all
Pop-Location

# --- 4. Modelos de Ollama: manifiesto (y blobs si se pide) ------------------
Write-Host "[4/5] Ollama..." -ForegroundColor Yellow
$ollamaModels = "$env:USERPROFILE\.ollama\models"
if (Test-Path "$ollamaModels\manifests") {
    Get-ChildItem "$ollamaModels\manifests" -Recurse -File |
        ForEach-Object { $_.FullName.Replace("$ollamaModels\manifests\", '').Replace('\', ':') -replace '^registry.ollama.ai:library:', '' } |
        Out-File "$Destino\ollama-modelos.txt" -Encoding utf8
    if ($IncluirModelosOllama) {
        $gb = "{0:N1}" -f ((Get-ChildItem "$ollamaModels\blobs" -File | Measure-Object Length -Sum).Sum / 1GB)
        Write-Host "  Copiando $gb GB de modelos (puede tardar)..." -ForegroundColor Yellow
        Copy-Item $ollamaModels "$Destino\ollama-models" -Recurse -Force
    }
}

# --- 5. Manifiesto del equipo de origen -------------------------------------
Write-Host "[5/5] Manifiesto..." -ForegroundColor Yellow
$gpu = (Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join ', '
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$pythons = ((py -0p 2>&1) -join ' | ').Trim()
@"
Equipo de origen  : $env:COMPUTERNAME
Fecha             : $(Get-Date -Format 'yyyy-MM-dd HH:mm')
Windows           : $((Get-CimInstance Win32_OperatingSystem).Caption)
CPU               : $((Get-CimInstance Win32_Processor).Name)
RAM               : $ramGB GB
GPU               : $gpu
VSCode            : $vscodeVersion
Extensiones       : $((Get-Content "$Destino\vscode-extensiones.txt").Count)
Git               : $(git --version)
Node              : $(node --version)
Python (py -0p)   : $pythons
"@ | Out-File "$Destino\MANIFIESTO.txt" -Encoding utf8

Write-Host ""
Write-Host "Listo. Contenido de $Destino :" -ForegroundColor Green
Get-ChildItem $Destino | Select-Object Name, @{n='MB';e={"{0:N1}" -f ($_.Length/1MB)}} | Format-Table -AutoSize
Write-Host "Copia esta carpeta al portatil y ejecuta alli scripts\importar-equipo.ps1" -ForegroundColor Green
