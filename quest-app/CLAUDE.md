# D.O.O.M para Meta Quest — contexto para Claude Code

App nativa de realidad mixta para Meta Quest 3/3S: el orbe de D.O.O.M en tu habitación, con
paneles que se cogen y se mueven con las manos. Es una app **independiente** de la de escritorio
(Python): usa sus ideas como referencia de diseño, no su código. El encargo completo del usuario
está en `docs/prompt-original.md`; la decisión de arquitectura, en `../docs/decisiones.md`
(**D-041**).

## Leer primero
1. `docs/prompt-original.md`: qué se pidió, por fases, y las reglas de trabajo.
2. D-041 en `../docs/decisiones.md`: por qué así y qué se descartó.
3. La nota más reciente de `../docs/NOTAS_SESION/` sobre la Quest.

## Stack (comprobado el 14/10/2026 contra la plantilla oficial y Maven Central)
- Kotlin 2.1.0, AGP 8.11.1, Gradle 9.4.1 (wrapper), **JDK 17 completo** (con `javac`).
- Meta Spatial SDK **0.14.0**: `meta-spatial-sdk`, `-toolkit`, `-vr`, `-isdk` (manos), `-compose`.
- `minSdk`/`compileSdk`/`targetSdk` 34 (Horizon OS = Android 14); Horizon OS v69+.
- Compose (Material 3) para los paneles; DataStore + Android Keystore para la configuración;
  NanoHTTPD para los ajustes desde el móvil; ZXing para el QR; **onnxruntime-android 1.31** para
  «hey jarvis» (solo `arm64-v8a`; los modelos de openWakeWord se bajan en las gafas, no van aquí).
- Passthrough Camera API (fase 3): Camera2 con `com.meta.extra_metadata.camera_source`/`position`
  como `CameraCharacteristics.Key<Int>`, según la doc de Meta del 15/10/2026. Horizon OS v74+.
- `IsdkFeature` no se registra a mano: desde 0.14 lo hace `VRFeature` (registrarlo está obsoleto).
- **Sin Spatial Editor**: la escena se construye en código (`DoomActivity`). Así compila igual en
  Linux. No añadas `scenes { exportItems {...} }` al bloque `spatial`: obliga a tener el CLI de
  Spatial Editor instalado.

## Compilar e instalar
```
scripts/deploy.sh         # Linux: compila, instala, abre la app y muestra su log
scripts\deploy.ps1        # Windows: lo mismo, en release (-Debug para depuracion)
./gradlew assembleRelease # solo compilar
./gradlew testDebugUnitTest
```
`local.properties` (no se versiona) lleva `sdk.dir`; los scripts lo crean. En Windows, desde una
consola sin la carpeta actual en la ruta de busqueda, llama a `.\gradlew.bat`, no a `gradlew.bat`.

## Estructura
| Fichero | Qué |
|---|---|
| `DoomActivity.kt` | Escena: passthrough, registro de paneles (cada ventana plana y curva), colocación, "Seguirme", el brazalete en la muñeca |
| `Ventanas.kt` | Las ventanas y su estado: abierta, curva, tamaño (se guarda) |
| `ui/Brazalete.kt` | El brazalete y los mandos de cada ventana (◠ − + _) |
| `Controlador.kt` | Une las piezas: lo que pulsa un panel llega aquí |
| `Estado.kt` | Estado compartido de Compose (`Doom`): orbe, subtítulos, registro, tiempo... |
| `ui/Orbe.kt` | El orbe, port de `ui/prototipo/hud.html` (mismos 5 estados y parámetros) |
| `ui/Paneles.kt` | Sistema, Registro, Aplicaciones, Ajustes |
| `ia/Interfaces.kt` | Contratos `LlmProvider`, `SttProvider`, `VisionProvider`, `TtsProvider` |
| `ia/ClienteIA.kt` | Proveedores compatibles con OpenAI: chat (con streaming), STT, visión, TTS |
| `ia/Agente.kt` | Bucle de herramientas con cadena de modelos (D-033/D-034), en streaming |
| `ia/Modos.kt` | Global y las skills de `skills/` (D-038) |
| `sistema/Acciones.kt` | Las herramientas: apps, enlaces, buscar/leer web, calcular, mirar, paneles, n8n, volumen, batería |
| `sistema/Web.kt`, `N8n.kt` | `buscar_web`/`leer_url` (port de `agent/web.py`); flujos de n8n con lista blanca |
| `vision/Camara.kt` | Un fotograma de la Passthrough Camera API |
| `voz/` | Grabación con VAD, «hey jarvis» (`PalabraActivacion`), voz por frases (`Frases`, `Voz`), capa refleja |
| `ui/Personalizar.kt` | Temas, perfiles de color propios, modos, memoria, voz/visión/n8n, paneles de información |
| `ajustes/ServidorAjustes.kt` + `assets/ajustes.html` | Ajustes desde el móvil (QR + PIN) |
| `datos/Almacen.kt`, `Aspecto.kt` | Configuración y claves cifradas; el aspecto (mismas reglas que `preferencias.py`) |

## Reglas
- **Ninguna clave en el código, en BuildConfig ni en logs.** La tarea `comprobarClaves` (antes de
  cada compilación) falla si algo tiene forma de clave (`gsk_`, `AIza`, `sk-`, `nvapi-`).
- **Los modelos no se dejan fijos**: se piden a `GET /models` en tiempo de ejecución; `sugeridos`
  solo preselecciona.
- **No inventar la API de Meta**: antes de usar una clase del SDK, mirar su firma con `javap` en el
  `.aar` de la caché de Gradle, o un ejemplo de `meta-quest/Meta-Spatial-SDK-Samples`.
- Comentarios, mensajes y docs en español, explicando el porqué (como el resto del repo).
- Rama `tarea/quest-nativa`. No tocar el código Python desde aquí.
