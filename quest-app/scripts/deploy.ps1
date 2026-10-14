# Compila D.O.O.M, lo instala en las gafas, lo abre y enseña su log (Windows).
# Uso, desde PowerShell:  .\quest-app\scripts\deploy.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not $env:ANDROID_HOME) { $env:ANDROID_HOME = Join-Path $env:LOCALAPPDATA "Android\Sdk" }
if (-not (Test-Path (Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"))) {
  Write-Host "No encuentro el Android SDK en $env:ANDROID_HOME (ver quest-app\README.md)."; exit 1
}
# Hace falta un JDK 17 completo (con javac).
if (-not $env:JAVA_HOME -or -not (Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe"))) {
  $jdk = Get-ChildItem "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java", "$env:USERPROFILE\.jdks" -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "jdk-17*" -and (Test-Path (Join-Path $_.FullName "bin\javac.exe")) } | Select-Object -First 1
  if (-not $jdk) { Write-Host "Falta un JDK 17 (ver quest-app\README.md)."; exit 1 }
  $env:JAVA_HOME = $jdk.FullName
}
if (-not (Test-Path "local.properties")) {
  "sdk.dir=" + ($env:ANDROID_HOME -replace '\\', '\\' -replace ':', '\:') | Out-File -Encoding ascii local.properties
}

$adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
& $adb get-state 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "No veo las gafas. Conectalas por USB-C, acepta 'Permitir depuracion USB' dentro de ellas"
  Write-Host "y comprueba con: & '$adb' devices   (en Windows puede hacer falta el driver ADB de Meta)"
  exit 1
}

.\gradlew.bat installDebug
& $adb shell am start -n com.doombot.quest/.DoomActivity
Start-Sleep -Seconds 2
Write-Host "--- log de D.O.O.M (Ctrl+C para salir) ---"
$appPid = (& $adb shell pidof -s com.doombot.quest).Trim()
& $adb logcat -v time --pid=$appPid
