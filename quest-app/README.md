# D.O.O.M para Meta Quest 3 / 3S

El orbe de D.O.O.M en tu habitación (realidad mixta), con paneles que coges y mueves con las manos:
**Sistema** (hora, tiempo, batería, modelos), **Registro** (la conversación, con los modos), **Aplicaciones**
(abrir apps y webs), **Ajustes** (aspecto, claves, modelos, memoria, voz, cámara y n8n) y los **paneles
de información** que D.O.O.M coloca cuando se lo pides. Funciona solo en las gafas, sin PC.

## Instalarla en las gafas

### Lo que hace falta una vez
1. **Modo desarrollador** en las gafas: app Meta Horizon del móvil → Dispositivos → tus gafas →
   Ajustes de las gafas → Modo desarrollador. Reinicia las gafas.
2. **Cable USB-C de datos**. Al conectarlas, dentro de las gafas, acepta «Permitir depuración USB»
   (marca «Permitir siempre desde este ordenador»).
3. **JDK 17 y Android SDK**. En Windows lo hace todo un script, sin pedir administrador (probado en
   Windows 11 el 15/10/2026):
   ```
   powershell -ExecutionPolicy Bypass -File .\quest-app\scripts\preparar-windows.ps1
   ```
   Instala el JDK 17 (zip oficial de Adoptium, comprobado), el Android SDK con la Android CLI (sin
   métricas), deja `JAVA_HOME`, `ANDROID_HOME` y `adb` en el PATH, y hace que Java use los
   certificados de Windows (si tu antivirus inspecciona HTTPS, como Norton, sin eso Gradle no
   descarga nada). Si `adb devices` no ve las gafas, instala el driver ADB de Meta (*Oculus ADB
   Drivers*, en developers.meta.com).
   - **Linux (portátil)**: JDK en `~/.jdks`, SDK en `~/Android/Sdk`. Para que `adb` vea las gafas
     sin `sudo`: `sudo apt install android-sdk-platform-tools-common`.

### Cada vez
```
quest-app\scripts\deploy.ps1          # Windows: release (fluida)
quest-app\scripts\deploy.ps1 -Debug   # Windows: depuración
quest-app/scripts/deploy.sh           # Linux
```
Compila, instala, abre D.O.O.M en las gafas y muestra su log. La app queda en tu biblioteca, en
**Orígenes desconocidos**. La versión *release* va firmada con la clave de depuración de tu equipo:
es para tus gafas, no para la tienda.

## Primer arranque
1. Se abre **Ajustes** con un **QR** y un **PIN**. Escanea el QR con el móvil (en la misma Wi-Fi),
   escribe el PIN y pega tus claves (Groq, NVIDIA, Gemini, OpenRouter...). También se pueden escribir
   en las propias gafas, con el teclado virtual.
2. En «Cadena de modelos», «Ver modelos» y añade los que quieras, por orden. Se piden al proveedor
   en ese momento; no hay ninguno fijo en la app.
3. «Guardar todo». Las claves se guardan **cifradas en las gafas** y no salen de ellas.
4. La primera vez, D.O.O.M baja los modelos de «hey jarvis» (3,5 MB) y pide el micrófono.

## Uso
- **El brazalete**: levanta la muñeca izquierda y mírala. Aparece un panel pequeño, como un reloj,
  con todo a mano: abrir o minimizar cada ventana, curvarlas, cambiarles el tamaño, encender o apagar
  el micrófono y «hey jarvis», recolocar, modo, tema, volumen, vigilante y ajustes. «Fijar» lo deja
  siempre a la vista.
- **Cada ventana** tiene en su cabecera ◠ (curvarla o volverla plana), − y + (tamaño) y _
  (minimizar). Una ventana minimizada se vuelve a abrir desde el brazalete, en el mismo sitio y con su
  tamaño. Todo eso se recuerda al cerrar la app. «Esquinas», en el brazalete, activa las asas de Meta
  para redimensionar arrastrando las esquinas (experimental).
- **«Hey jarvis»** y habla; o el botón «Hablar». Te escucha hasta que te callas y responde en
  voz alta según escribe (por frases), con subtítulos.
- **Pellizco** (índice y pulgar) sobre un botón: pulsar. **Pellizcar y arrastrar** un panel o la
  burbuja: moverlo por la habitación. Con mandos, el gatillo hace lo mismo.
- **Órdenes directas, sin modelo**: «para», «ven aquí», «ajustes», «olvida todo» (conversación
  nueva), «recuerda que…» (lo apunta sobre ti) y «olvida eso».
- **Modos**, encima del registro: Global, Investigación, Diseño, Programación y Ciencias, como en la
  ventana de escritorio.
- Pídele: «ábreme YouTube», «¿quién ganó ayer la liga?» (busca y lee fuentes), «¿cuánto es 3,2 al
  cubo entre 7?», «¿qué estoy viendo?» / «lee esto» (cámara), «pon en un panel la lista de la
  compra», «activa el flujo riego del jardín» (n8n, te pide confirmación), «sube el volumen».
- **Personalizar** (en Ajustes, o desde el móvil con selector de color): los temas de escritorio
  (Jarvis, Holograma, Neón, Matriz, Glaciar, Carmesí), **tus propios perfiles de color** con nombre
  (crear, editar, renombrar, duplicar, borrar), brillo y velocidad.

## Privacidad
- Lo que dices, lo que el agente lee y las fotos de «¿qué estoy viendo?» van al proveedor de IA
  que elijas. La cámara solo se usa cuando la pregunta lo pide (o en el modo vigilante, apagado
  por defecto), y mientras captura el orbe enseña «● CÁMARA».
- «Hey jarvis» se reconoce en las gafas: nada sale hasta que la oye.
- Del móvil a las gafas, las claves van por la Wi-Fi de casa sin cifrar (con token, PIN y 10 min).

## Lo que no hace (todavía)
- El orbe es un panel con el dibujo del HUD, no una malla 3D (ver D-041).
- No puede cambiar ajustes del sistema de las gafas (brillo, Wi-Fi): Android no lo permite a una app.
- Abrir otra app inmersiva cierra D.O.O.M: Horizon OS solo muestra una a la vez.
