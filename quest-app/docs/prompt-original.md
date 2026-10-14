# Encargo original (14/10/2026)

Texto del usuario, tal cual, que define la app de la Quest. Las desviaciones están en D-041.

---

Quiero crear la versión nativa de D.O.O.M para Meta Quest 3: un asistente tipo JARVIS de Iron Man,
en realidad mixta, que funcione solo en las gafas, sin PC. Este repo es la versión de escritorio en
Python; úsalo como referencia de diseño, no como dependencia.

## Antes de escribir código
1. Lee CLAUDE.md, README.md y estos ficheros, porque vamos a portar sus ideas:
   - src/doombot/backends/proveedores.py → catálogo de proveedores OpenAI-compatibles (Groq, Gemini, NVIDIA...)
   - src/doombot/phrases/matcher.py y los orders.py → capa refleja de órdenes sin LLM
   - src/doombot/identity.py → personalidad y prompt de sistema
   - ui/prototipo/hud.html → estados del orbe (dormido/escuchando/pensando/hablando/error) y sus parámetros
2. Consulta la documentación ACTUAL de Meta antes de elegir versiones (no te fíes de tu memoria):
   Meta Spatial SDK, su Passthrough Camera API en Kotlin (Camera2, Horizon OS v76+) y el repo de
   ejemplos Meta-Passthrough-Camera-API-Samples. Si algo de este prompt contradice la doc, manda la doc.
3. Trabaja en la rama `tarea/quest-nativa` y en una carpeta nueva `quest-app/`, con su propio CLAUDE.md.
   No toques el código Python. Abre una entrada nueva en docs/decisiones.md para esta decisión.
4. Antes de empezar, enséñame el plan de la fase 0 y la lista de lo que tengo que instalar yo
   (JDK, Android SDK, adb, modo desarrollador...). Espera mi OK.

## Stack
- Kotlin + Meta Spatial SDK, Gradle, minSdk el que exija la doc (34+). UI de paneles en Jetpack Compose.
- Todo se compila y se instala desde la terminal: `./gradlew installDebug` + `adb`. Nada que requiera
  abrir Android Studio a mano.
- Sin modelos locales pesados. Toda la IA por API, con proveedores intercambiables detrás de interfaces
  (igual que los Protocol de backends/base.py): LlmProvider, VisionProvider, SttProvider, TtsProvider.
- Proveedores OpenAI-compatibles configurables (base_url + api_key + modelo), Groq por defecto. Los
  modelos disponibles se leen en tiempo de ejecución de GET /models; NO los dejes fijos en el código.

## Claves y configuración: NUNCA en el código
- Las claves se guardan cifradas en el dispositivo (Android Keystore + DataStore). Nada de claves en el
  repo, en BuildConfig ni en logs. Añade un test o lint que falle si aparece algo con forma de clave
  (gsk_, AIza, sk-, nvapi-).
- Servidor de configuración embebido en la app (Ktor o NanoHTTPD), solo en la red local:
  - Al abrir "Ajustes", el panel muestra un QR con http://<ip-gafas>:<puerto>/?t=<token de un solo uso>
    y un PIN de 6 dígitos. Sin token+PIN no responde.
  - La página web (móvil) permite: añadir/quitar proveedores y claves, elegir el modelo para cada uso
    (chat, visión, STT, TTS), editar la personalidad, probar cada clave con un botón.
  - El servidor se apaga solo a los 10 minutos o al cerrar Ajustes.
- También un panel mínimo de ajustes dentro de las gafas, para cuando no hay móvil a mano.
- En debug, opcionalmente, leer claves de `quest-app/local.properties` (en .gitignore) para desarrollar rápido.

## Funciones, por fases. Cada fase termina instalada en mis gafas y probada por mí.

Fase 0, esqueleto: app Spatial SDK con passthrough, un panel flotante "Hola, Mi Señor" y el script
`quest-app/scripts/deploy.ps1` (compilar + instalar + abrir + logcat filtrado).

Fase 1, el orbe: el HUD de hud.html en 3D, con los mismos 5 estados y la misma lógica (amplitud con
ataque rápido y caída lenta). Te sigue con pereza; con un pellizco se ancla en la habitación. Subtítulos debajo.

Fase 2, conversación por voz:
- Micro de las gafas → VAD en el dispositivo → STT por API (Whisper de Groq por defecto) → LLM → TTS.
- TTS por defecto: el TextToSpeech de Android (gratis y offline). TTS por API opcional y configurable.
- Activación: push-to-talk con gesto de pellizco primero; después, palabra de activación local
  ("hey jarvis", openWakeWord en ONNX con onnxruntime-android) si el rendimiento lo permite.
- Barge-in: si hablo mientras responde, se calla.
- Respuestas en streaming y TTS por frases (como D-021) para que empiece a hablar cuanto antes.
- Port de la capa refleja de órdenes (para, silencio, etc.) sin pasar por el LLM.

Fase 3, visión con la Passthrough Camera API:
- Permisos android.permission.CAMERA + horizonos.permission.HEADSET_CAMERA en tiempo de ejecución.
- Captura bajo demanda, no continua: cuando digo cosas como "¿qué estoy viendo?", "lee esto",
  "¿qué es esto?", toma un fotograma, lo reduce (~1024 px, JPEG) y lo manda a un modelo con visión
  (elegido en Ajustes) junto con la pregunta.
- Indicador visible en el HUD siempre que la cámara esté capturando.
- Modo opcional "vigilante": un fotograma cada N segundos (configurable, apagado por defecto), con
  cuidado de los límites de peticiones del plan gratuito.

Fase 4, toque JARVIS: memoria de hechos sobre mí (persistida en local), personalidad configurable,
paneles con información (hora, tiempo, lo que le pida mostrar) colocables en la habitación, y
disparar mis webhooks de n8n con lista blanca y confirmación hablada (como D-030/D-031).

## Reglas de trabajo
- Mensajes, comentarios y docs en español, con el mismo estilo del repo (explicar el porqué).
- Al terminar cada fase: una nota en docs/NOTAS_SESION/, commit narrativo y una lista de "cómo probarlo".
- Si una API de Meta no existe o ha cambiado, para y dímelo; no te inventes la API.
- Pregúntame antes de añadir dependencias pesadas o servicios de pago.

---

**Añadido el mismo día**: el usuario pidió hacerlo todo de una vez para instalarlo cuanto antes
(burbuja centrada y movible, paneles de sistema movibles con las manos, claves desde el móvil, abrir
apps y enlaces) y dio permiso para instalar lo necesario. Y después: "mete todas las acciones de
control de la aplicación desde las gafas".
