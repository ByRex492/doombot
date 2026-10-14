# Resumen sesión Linux — 2026-10-14 (D.O.O.M para Quest)

Rama **`tarea/quest-nativa`**, carpeta **`quest-app/`** (ver su `CLAUDE.md` y `README.md`).
Decisión: **D-041**. Encargo completo: `quest-app/docs/prompt-original.md`.

## Qué hay
App de realidad mixta para Quest 3/3S, compilada en el portátil y **sin probar en unas gafas**
(no estaban conectadas). En una sola tanda, por petición del usuario, lleva casi todo de las fases 0
a 2 del encargo:
- **Passthrough**, y la escena construida en código (sin Spatial Editor).
- **Paneles que se cogen y se mueven con las manos** (`Grabbable`): el orbe (los 5 estados de
  `hud.html` y subtítulos), Sistema, Registro, Aplicaciones y Ajustes. «Recolocar» los trae
  delante; «Seguirme», el orbe te acompaña.
- **Agente** con cadena de modelos; herramientas: abrir app o enlace, volumen, batería, listar apps.
- **Voz**: «Hablar», VAD, Whisper por API, TTS de Android o subtítulos. Capa refleja («para», «ven
  aquí», «ajustes», «olvida todo»).
- **Ajustes completos desde las gafas y desde el móvil** (QR + PIN, 10 minutos). Claves cifradas
  (Keystore + DataStore).

## Instalado en el portátil
- **JDK 17 completo** (Temurin) en `~/.jdks/jdk-17.0.20.1+1`: el del sistema no traía `javac`.
- **Android SDK** en `~/Android/Sdk`: `cmdline-tools`, `platform-tools`, `platforms;android-34`,
  `build-tools` 34 y 35. `ANDROID_HOME` en `~/.bashrc`.
- **VS Code**: extensiones `fwcd.kotlin` y `vscjava.vscode-gradle`.
- **Plantillas y ejemplos oficiales de Meta**, de referencia, en `~/Documents/quest-ref/` (fuera del
  repo).

## Cómo probarlo (en el sobremesa, con las gafas)
1. Instalar JDK 17 y Android SDK en Windows (`quest-app/README.md`), conectar las gafas con el modo
   desarrollador activado y comprobar `adb devices`.
2. `git switch tarea/quest-nativa` y `quest-app\scripts\deploy.ps1`.
3. En las gafas:
   - [ ] Se ve la habitación (passthrough) con la burbuja centrada y los paneles alrededor.
   - [ ] Pellizcar y arrastrar mueve la burbuja y cada panel; los botones responden al pellizco.
   - [ ] Al ser la primera vez, se abre Ajustes con QR y PIN; desde el móvil se pegan las claves y se
     elige la cadena. Probar también a ponerlas desde las gafas con el teclado virtual.
   - [ ] «Hablar»: pide el permiso del micrófono, escucha, y el orbe reacciona a la voz.
   - [ ] «Ábreme YouTube», «busca el tiempo en Madrid», «sube el volumen».
   - [ ] Hay voz en español, o se avisa de que no y responde en subtítulos.
   - [ ] «Para» corta en seco; «Recolocar» trae todo delante.
   - [ ] El panel Aplicaciones lista las apps y las abre.
4. Si algo falla, el log está en la consola que deja abierta `deploy.ps1`.

## Pendiente
- Lo que falle en las gafas (nada se ha ejecutado allí).
- **Fase 3** (cámara, Horizon OS v76+), **fase 4** (memoria, n8n), palabra de activación,
  streaming y TTS por frases, e interfaces separadas por proveedor (ver desviaciones en D-041).
