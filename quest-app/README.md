# D.O.O.M para Meta Quest 3 / 3S

El orbe de D.O.O.M en tu habitación (realidad mixta), con paneles que coges y mueves con las manos:
**Sistema** (hora, tiempo, batería, modelos), **Registro** (la conversación), **Aplicaciones**
(abrir apps y webs) y **Ajustes** (claves y modelos, desde las gafas o desde el móvil).

## Instalarla en las gafas

### Lo que hace falta una vez
1. **Modo desarrollador** en las gafas: app Meta Horizon del móvil → Dispositivos → tus gafas →
   Ajustes de las gafas → Modo desarrollador. Reinicia las gafas.
2. **Cable USB-C de datos** y, dentro de las gafas, aceptar «Permitir depuración USB».
3. **JDK 17 completo** (con `javac`) y **Android SDK** (`platform-tools`, `platforms;android-34`).
   - **Windows (sobremesa)**:
     - instalar Temurin 17 desde https://adoptium.net (marca «Set JAVA_HOME»);
     - bajar las *command-line tools* de Windows desde https://developer.android.com/studio,
       descomprimir en `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest` y ejecutar
       `sdkmanager "platform-tools" "platforms;android-34"`;
     - si `adb devices` no ve las gafas, instalar el driver ADB de Meta (*Oculus ADB Drivers*,
       en developers.meta.com).
   - **Linux (portátil)**: ya está todo instalado (JDK en `~/.jdks`, SDK en `~/Android/Sdk`). Para
     que `adb` vea las gafas sin `sudo`: `sudo apt install android-sdk-platform-tools-common`.

### Cada vez
```
quest-app/scripts/deploy.ps1     # Windows
quest-app/scripts/deploy.sh      # Linux
```
Compila, instala, abre D.O.O.M en las gafas y muestra su log. La app queda en tu biblioteca, en
**Orígenes desconocidos**.

**Sin compilar en el sobremesa**: si ya tienes el APK (`app/build/outputs/apk/debug/app-debug.apk`,
compilado en el portátil), basta con `adb install -r app-debug.apk`; solo hace falta `platform-tools`.

## Primer arranque
1. Se abre **Ajustes** con un **QR** y un **PIN**. Escanea el QR con el móvil (en la misma Wi-Fi),
   escribe el PIN y pega tus claves (Groq, NVIDIA, Gemini...). También se pueden escribir en las
   propias gafas, con el teclado virtual.
2. En «Cadena de modelos», pulsa «Ver modelos» y añade los que quieras, por orden. Se piden al
   proveedor en ese momento; no hay ninguno fijo en la app.
3. «Guardar todo». Las claves se guardan **cifradas en las gafas** y no salen de ellas.

## Uso
- **Pellizco** (índice y pulgar) sobre un botón: pulsar. **Pellizcar y arrastrar** un panel o la
  burbuja: moverlo por la habitación. Con mandos, el gatillo hace lo mismo.
- **Hablar**: botón «Hablar» bajo la burbuja. Te escucha hasta que te callas, y responde con
  subtítulos (y voz, si las gafas tienen voz en español).
- **«Para»**, **«ven aquí»**, **«ajustes»**, **«olvida todo»**: órdenes directas, sin modelo.
- **«Recolocar»**: todo vuelve delante de ti. **«Seguirme»** (en Ajustes): la burbuja te acompaña.
- Pídele cosas como «ábreme YouTube», «busca recetas de paella», «sube el volumen», «¿cuánta batería
  me queda?».

## Lo que no hace (todavía)
- No ve la habitación (la cámara es la fase 3 del plan).
- No recuerda entre sesiones ni dispara n8n (fase 4).
- No puede cambiar ajustes del sistema de las gafas (brillo, Wi-Fi): Android no lo permite a una app.
- Palabra de activación («hey jarvis»): de momento se pulsa «Hablar».
