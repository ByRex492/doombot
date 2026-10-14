# Compila D.O.O.M, lo instala en las gafas, lo abre y enseña su log (Windows).
# Uso, desde PowerShell:  .\quest-app\scripts\deploy.ps1          (version release: fluida)
#                         .\quest-app\scripts\deploy.ps1 -Debug   (version de depuracion)
param([switch] $Debug)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
$adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
if (-not (Test-Path $adb)) { Write-Host "No encuentro el Android SDK en $env:ANDROID_HOME. Ejecuta antes scripts\preparar-windows.ps1."; exit 1 }
# Hace falta un JDK 17 completo (con javac).
if (-not $env:JAVA_HOME -or -not (Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe"))) {
  $jdk = Get-ChildItem "$env:USERPROFILE\.jdks", "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "jdk-17*" -and (Test-Path (Join-Path $_.FullName "bin\javac.exe")) } | Select-Object -First 1
  if (-not $jdk) { Write-Host "Falta un JDK 17. Ejecuta antes scripts\preparar-windows.ps1."; exit 1 }
  $env:JAVA_HOME = $jdk.FullName
}
if (-not (Test-Path "local.properties")) {
  "sdk.dir=" + ($env:ANDROID_HOME -replace '\\', '\\' -replace ':', '\:') | Out-File -Encoding ascii local.properties
}

# adb y gradle escriben avisos en stderr; en PowerShell 5.1 con "Stop" eso seria una excepcion.
$ErrorActionPreference = "Continue"
$estado = (& $adb get-state 2>&1 | Out-String).Trim()
if ($estado -ne "device") {
  if ($estado -match "unauthorized") {
    Write-Host "Las gafas estan conectadas pero sin autorizar: pontelas y acepta 'Permitir depuracion USB'."
  } else {
    Write-Host "No veo las gafas. Conectalas por USB-C, acepta 'Permitir depuracion USB' dentro de ellas"
    Write-Host "y comprueba con: & '$adb' devices   (en Windows puede hacer falta el driver ADB de Meta)"
  }
  exit 1
}

$tarea = if ($Debug) { "installDebug" } else { "installRelease" }
& .\gradlew.bat $tarea --console=plain
if ($LASTEXITCODE -ne 0) { Write-Host "La compilacion o la instalacion han fallado (arriba esta el motivo)."; exit 1 }

& $adb shell am start -n com.doombot.quest/.DoomActivity | Out-Null
Start-Sleep -Seconds 2
$appPid = (& $adb shell pidof -s com.doombot.quest | Out-String).Trim()
if (-not $appPid) { Write-Host "La app no ha arrancado. Log de errores:"; & $adb logcat -d -v time "*:E" | Select-Object -Last 40; exit 1 }
Write-Host "--- log de D.O.O.M (Ctrl+C para salir) ---"
& $adb logcat -v time --pid=$appPid
