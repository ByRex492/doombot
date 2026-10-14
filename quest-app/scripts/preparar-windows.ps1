# Prepara el sobremesa Windows para compilar e instalar D.O.O.M en las gafas. Se ejecuta una vez.
# Uso (PowerShell, desde la carpeta del repo):
#   powershell -ExecutionPolicy Bypass -File .\quest-app\scripts\preparar-windows.ps1
#
# Instala lo mismo que se instalo a mano en el portatil el 14/10/2026:
#   1. JDK 17 completo (Eclipse Temurin), con winget.
#   2. Android SDK de linea de comandos: cmdline-tools, platform-tools (adb), android-34, build-tools.
#   3. ANDROID_HOME y adb en el PATH del usuario.
# Las licencias (la de Temurin en winget y las del SDK) se aceptan a mano: las lees tu.
$ErrorActionPreference = "Stop"

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }

# -- 1. JDK 17 ------------------------------------------------------------------------------
Paso "JDK 17"
function Buscar-Jdk {
  Get-ChildItem "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java", "$env:USERPROFILE\.jdks" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "jdk-17*" -and (Test-Path (Join-Path $_.FullName "bin\javac.exe")) } |
    Select-Object -First 1
}
$jdk = Buscar-Jdk
if (-not $jdk) {
  Write-Host "Instalando Eclipse Temurin 17 con winget (te pedira aceptar sus condiciones)..."
  winget install --id EclipseAdoptium.Temurin.17.JDK -e
  $jdk = Buscar-Jdk
}
if (-not $jdk) { Write-Host "No encuentro el JDK 17 tras instalarlo. Instalalo desde https://adoptium.net y vuelve a ejecutar."; exit 1 }
$env:JAVA_HOME = $jdk.FullName
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk.FullName, "User")
Write-Host "JDK: $($jdk.FullName)"

# -- 2. Android SDK -------------------------------------------------------------------------
Paso "Android SDK"
$sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$herramientas = Join-Path $sdk "cmdline-tools\latest"
$sdkmanager = Join-Path $herramientas "bin\sdkmanager.bat"
if (-not (Test-Path $sdkmanager)) {
  # El indice oficial de Google dice cual es la ultima version y su SHA-1.
  $indice = (Invoke-WebRequest -UseBasicParsing "https://dl.google.com/android/repository/repository2-3.xml").Content
  $trozo = $indice.Substring($indice.IndexOf('path="cmdline-tools;latest"'))
  $m = [regex]::Match($trozo, '<checksum[^>]*>(\w+)</checksum>\s*<url>(commandlinetools-win[^<]+)</url>')
  if (-not $m.Success) { Write-Host "No encuentro las herramientas de Windows en el indice de Google."; exit 1 }
  $sha1 = $m.Groups[1].Value; $zip = $m.Groups[2].Value
  $temporal = Join-Path $env:TEMP $zip
  Write-Host "Descargando $zip (unos 150 MB) de dl.google.com..."
  Invoke-WebRequest -UseBasicParsing "https://dl.google.com/android/repository/$zip" -OutFile $temporal
  if ((Get-FileHash $temporal -Algorithm SHA1).Hash.ToLower() -ne $sha1.ToLower()) {
    Remove-Item $temporal; Write-Host "La descarga no coincide con su suma de verificacion. Vuelve a intentarlo."; exit 1
  }
  $destino = Join-Path $sdk "cmdline-tools"
  New-Item -ItemType Directory -Force $destino | Out-Null
  Expand-Archive $temporal -DestinationPath $destino -Force
  if (Test-Path $herramientas) { Remove-Item -Recurse -Force $herramientas }
  Rename-Item (Join-Path $destino "cmdline-tools") "latest"
  Remove-Item $temporal
}
Write-Host "Acepta las licencias del Android SDK (lee y responde 'y'):"
& $sdkmanager --sdk_root=$sdk --licenses
& $sdkmanager --sdk_root=$sdk "platform-tools" "platforms;android-34" "build-tools;34.0.0"

# -- 3. Variables de entorno ----------------------------------------------------------------
Paso "Variables de entorno"
$env:ANDROID_HOME = $sdk
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
$pt = Join-Path $sdk "platform-tools"
$ruta = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not ($ruta -split ";" -contains $pt)) {
  [Environment]::SetEnvironmentVariable("Path", "$ruta;$pt", "User")
}
Write-Host "ANDROID_HOME=$sdk (abre un PowerShell nuevo para que lo vean otros programas)"

# -- 4. Las gafas ---------------------------------------------------------------------------
Paso "Las gafas"
$adb = Join-Path $pt "adb.exe"
& $adb devices
Write-Host @"
Si arriba no sale ningun dispositivo con 'device' al lado:
  - Modo desarrollador activado (app Meta Horizon del movil) y gafas reiniciadas.
  - Cable USB-C de datos, y aceptar 'Permitir depuracion USB' dentro de las gafas.
  - En Windows puede hacer falta el driver ADB de Meta:
    https://developers.meta.com/horizon/downloads/package/oculus-adb-drivers/

Cuando 'adb devices' las vea:  .\quest-app\scripts\deploy.ps1
"@
