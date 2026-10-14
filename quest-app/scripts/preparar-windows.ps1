# Prepara un Windows para compilar e instalar D.O.O.M en las gafas. Se ejecuta una vez.
# Uso (PowerShell, desde la carpeta del repo):
#   powershell -ExecutionPolicy Bypass -File .\quest-app\scripts\preparar-windows.ps1
#
# Probado en Windows 11 el 15/10/2026. Instala, sin pedir administrador:
#   1. JDK 17 completo (Eclipse Temurin), el zip oficial en %USERPROFILE%\.jdks, con su SHA-256.
#   2. Android SDK: cmdline-tools (con su SHA-1), platform-tools (adb), android-34 y build-tools,
#      con la Android CLI nueva (sdkmanager quedo obsoleto en 2026) y sin enviar metricas.
#   3. JAVA_HOME, ANDROID_HOME y adb en el PATH del usuario.
#   4. Java con el almacen de certificados de Windows: si un antivirus inspecciona HTTPS (Norton,
#      Avast...), Gradle no puede descargar nada con el almacen propio de Java.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }

# -- 1. JDK 17 ------------------------------------------------------------------------------
Paso "JDK 17"
function Buscar-Jdk {
  Get-ChildItem "$env:USERPROFILE\.jdks", "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "jdk-17*" -and (Test-Path (Join-Path $_.FullName "bin\javac.exe")) } |
    Select-Object -First 1
}
$jdk = Buscar-Jdk
if (-not $jdk) {
  $a = (Invoke-RestMethod 'https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse')[0]
  $pkg = $a.binary.package
  Write-Host "Descargando $($a.release_name) ($([int]($pkg.size / 1MB)) MB) de Adoptium..."
  $zip = Join-Path $env:TEMP $pkg.name
  Invoke-WebRequest -UseBasicParsing $pkg.link -OutFile $zip
  if ((Get-FileHash $zip -Algorithm SHA256).Hash.ToLower() -ne $pkg.checksum.ToLower()) { throw "El JDK descargado no coincide con su SHA-256" }
  New-Item -ItemType Directory -Force "$env:USERPROFILE\.jdks" | Out-Null
  Expand-Archive $zip -DestinationPath "$env:USERPROFILE\.jdks" -Force
  [IO.File]::Delete($zip)
  $jdk = Buscar-Jdk
}
$env:JAVA_HOME = $jdk.FullName
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk.FullName, "User")
Write-Host "JDK: $($jdk.FullName)"

# -- 2. Android SDK -------------------------------------------------------------------------
Paso "Android SDK"
$sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
$herr = Join-Path $sdk "cmdline-tools\latest"
$android = Join-Path $herr "bin\android.exe"
if (-not (Test-Path (Join-Path $herr "bin\sdkmanager.bat"))) {
  # El indice oficial de Google dice cual es la ultima version y su SHA-1.
  $indice = (Invoke-WebRequest -UseBasicParsing "https://dl.google.com/android/repository/repository2-3.xml").Content
  $trozo = $indice.Substring($indice.IndexOf('path="cmdline-tools;latest"'))
  $m = [regex]::Match($trozo, '<checksum[^>]*>([0-9a-f]+)</checksum>\s*<url>(commandlinetools-win[^<]+)</url>')
  if (-not $m.Success) { throw "No encuentro las herramientas de Windows en el indice de Google." }
  $zip = Join-Path $env:TEMP $m.Groups[2].Value
  Write-Host "Descargando $($m.Groups[2].Value) de dl.google.com..."
  Invoke-WebRequest -UseBasicParsing "https://dl.google.com/android/repository/$($m.Groups[2].Value)" -OutFile $zip
  if ((Get-FileHash $zip -Algorithm SHA1).Hash.ToLower() -ne $m.Groups[1].Value.ToLower()) { throw "La descarga no coincide con su SHA-1." }
  $destino = Join-Path $sdk "cmdline-tools"
  New-Item -ItemType Directory -Force $destino | Out-Null
  Expand-Archive $zip -DestinationPath $destino -Force
  Rename-Item (Join-Path $destino "cmdline-tools") "latest"
  [IO.File]::Delete($zip)
}
$env:ANDROID_HOME = $sdk
Write-Host "Instalando platform-tools, android-34 y build-tools (al usarlos aceptas las licencias del Android SDK:"
Write-Host "https://developer.android.com/studio/terms)"
& $android --no-metrics --sdk=$sdk sdk install "platform-tools" "platforms;android-34" "build-tools;34.0.0" "build-tools;35.0.0"
if ($LASTEXITCODE -ne 0) { throw "La instalacion del SDK ha fallado ($LASTEXITCODE)" }

# -- 3. Variables de entorno ----------------------------------------------------------------
Paso "Variables de entorno"
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
$pt = Join-Path $sdk "platform-tools"
$ruta = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not (($ruta -split ";") -contains $pt)) { [Environment]::SetEnvironmentVariable("Path", "$ruta;$pt", "User") }
Write-Host "ANDROID_HOME=$sdk (abre un PowerShell nuevo para que lo vean otros programas)"

# -- 4. Java y los certificados de Windows --------------------------------------------------
Paso "Certificados para Java y Gradle"
$gp = Join-Path $env:USERPROFILE ".gradle\gradle.properties"
New-Item -ItemType Directory -Force (Split-Path $gp) | Out-Null
if (-not (Test-Path $gp) -or -not (Select-String -Path $gp -Pattern "trustStoreType" -Quiet)) {
  Add-Content -Path $gp -Encoding ascii -Value "systemProp.javax.net.ssl.trustStoreType=Windows-ROOT"
}
Write-Host "Gradle usa los certificados de Windows ($gp)"

# -- 5. Las gafas ---------------------------------------------------------------------------
Paso "Las gafas"
$adb = Join-Path $pt "adb.exe"
$ErrorActionPreference = "Continue" # adb escribe en stderr al arrancar su servicio: no es un fallo
& $adb devices
Write-Host @"
Si arriba no sale tu dispositivo con 'device' al lado:
  - 'unauthorized': ponte las gafas y acepta 'Permitir depuracion USB' (marca 'siempre').
  - nada: modo desarrollador activado (app Meta Horizon del movil) y gafas reiniciadas; cable
    USB-C de datos; y en Windows puede hacer falta el driver ADB de Meta:
    https://developers.meta.com/horizon/downloads/package/oculus-adb-drivers/

Cuando 'adb devices' las vea:  .\quest-app\scripts\deploy.ps1
"@
