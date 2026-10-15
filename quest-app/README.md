# D.O.O.M para Meta Quest 3 / 3S

La burbuja de D.O.O.M en 3D en tu habitación (realidad mixta), con ventanas que coges, mueves y
cambias de tamaño con las manos, y un menú en la muñeca:
**Sistema** (hora, tiempo, batería, modelos), **Registro** (la conversación), **Aplicaciones**
(abrir apps y webs) y **Ajustes** (claves y modelos, desde las gafas o desde el móvil).

## Instalarla en las gafas

### Lo que hace falta una vez
1. **Modo desarrollador** en las gafas: app Meta Horizon del móvil → Dispositivos → tus gafas →
   Ajustes de las gafas → Modo desarrollador. Reinicia las gafas.
2. **Cable USB-C de datos** y, dentro de las gafas, aceptar «Permitir depuración USB».
3. **JDK 17 completo** (con `javac`) y **Android SDK** (`platform-tools`, `platforms;android-34`).
   - **Windows (sobremesa)**: lo hace todo un script, una vez:
     ```
     powershell -ExecutionPolicy Bypass -File .\quest-app\scripts\preparar-windows.ps1
     ```
     Instala el JDK 17 con winget y el Android SDK, y deja `ANDROID_HOME` y `adb` en el PATH. Te
     pide aceptar las licencias. A mano, por si falla:
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
- **La burbuja** es un objeto 3D: cógela con la mano (pellizco o puño cerrado dentro de ella) para
  moverla; con las dos manos, sepáralas o júntalas para hacerla más grande o más pequeña. Debajo
  lleva los subtítulos y los botones «Hablar» y «Para».
- **Las ventanas** se mueven con la barra que aparece debajo al acercar la mano, y cambian de
  tamaño desde las esquinas, como las ventanas de las Quest. El contenido se recoloca al nuevo
  tamaño.
- **El brazalete**: gira la palma de la mano izquierda hacia la cara y mírala. Aparece un menú en
  la muñeca con Hablar, Para, Aquí (lo trae todo delante), Ventanas (esconderlas o enseñarlas) y
  Ajustes. En Ajustes se cambia de mano, de tamaño o se apaga.
- **Hablar**: te escucha hasta que te callas y responde con subtítulos (y voz, si las gafas tienen
  voz en español).
- **«Para»**, **«ven aquí»**, **«ajustes»**, **«olvida todo»**: órdenes directas, sin modelo.
- Pídele cosas como «ábreme YouTube», «busca recetas de paella», «sube el volumen», «¿cuánta batería
  me queda?».

## Lo que no hace (todavía)
- No ve la habitación (la cámara es la fase 3 del plan).
- No recuerda entre sesiones ni dispara n8n (fase 4).
- No puede cambiar ajustes del sistema de las gafas (brillo, Wi-Fi): Android no lo permite a una app.
- Palabra de activación («hey jarvis»): de momento se pulsa «Hablar».
