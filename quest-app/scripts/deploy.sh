#!/usr/bin/env bash
# Compila D.O.O.M, lo instala en las gafas, lo abre y enseña su log.
# Uso: quest-app/scripts/deploy.sh          (desde cualquier carpeta)
set -euo pipefail
cd "$(dirname "$0")/.."

ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_HOME
# Hace falta un JDK 17 completo (con javac), no solo el de ejecucion.
if [ -z "${JAVA_HOME:-}" ] || [ ! -x "$JAVA_HOME/bin/javac" ]; then
  for d in "$HOME"/.jdks/jdk-17* /usr/lib/jvm/java-17-openjdk-amd64; do
    if [ -x "$d/bin/javac" ]; then export JAVA_HOME="$d"; break; fi
  done
fi
[ -x "${JAVA_HOME:-}/bin/javac" ] || { echo "Falta un JDK 17 con javac (ver quest-app/README.md)."; exit 1; }
[ -f local.properties ] || echo "sdk.dir=$ANDROID_HOME" > local.properties

ADB="$ANDROID_HOME/platform-tools/adb"
if ! "$ADB" get-state >/dev/null 2>&1; then
  echo "No veo las gafas. Conectalas por USB-C, acepta 'Permitir depuracion USB' dentro de ellas"
  echo "y comprueba con: $ADB devices"
  exit 1
fi

./gradlew installDebug
"$ADB" shell am start -n com.doombot.quest/.DoomActivity
sleep 2
echo "--- log de D.O.O.M (Ctrl+C para salir) ---"
"$ADB" logcat -v time --pid="$("$ADB" shell pidof -s com.doombot.quest)"
