# Traspaso al sobremesa — 2026-10-14

Lo que falta para seguir en el sobremesa (Windows, con GPU) el trabajo hecho estos dos días desde
el portátil Linux. Todo lo de abajo ya está en `main`; el detalle de cada cosa, en
`RESUMEN SESION LINUX 2026-10-13.md`, `RESUMEN SESION LINUX 2026-10-14.md` y en
`docs/decisiones.md` (D-033 a D-040).

## 1. Poner el sobremesa al día

```
git fetch
git switch main
git pull
pip install -e ".[dev,hud,agent-web]"
python -m playwright install chromium
pytest -m "not hardware"
```

- **`.env`**: no viaja con el repositorio. Copiar a mano desde el `.env` del portátil:
  - las claves `DOOMBOT_GROQ_API_KEY`, `DOOMBOT_GEMINI_API_KEY` y `DOOMBOT_NVIDIA_API_KEY`;
  - `DOOMBOT_LLM_BACKEND=varios` y `DOOMBOT_AGENT_BRAIN=varios`;
  - la cadena de modelos, añadiendo al final el Ollama local:
    ```
    DOOMBOT_MODELOS=groq:openai/gpt-oss-120b,nvidia:nvidia/nemotron-3-super-120b-a12b,groq:qwen/qwen3.8-27b,gemini:gemini-3.5-flash-lite,nvidia:nvidia/nemotron-3-ultra-550b-a55b,gemini:gemini-3.8-flash,groq:openai/gpt-oss-20b,openrouter:openai/gpt-oss-120b:free,ollama:gemma4:12b
    ```
  - opcionales: `DOOMBOT_AGENT_REFINAR=auto` (es el valor por defecto) y `DOOMBOT_JINA_API_KEY`.
- **Ni el historial de conversaciones ni los proyectos viajan**: viven en la carpeta de datos de
  cada equipo, y en el sobremesa se empieza de cero. Si se quisieran pasar, se copia la carpeta
  `conversaciones/` de la carpeta de datos.

## 2. Pendiente de probar en Windows (no se ha podido desde Linux)

1. **La ventana**:
   - que `python -m doombot ventana` abre con WebView2 y el núcleo se ve;
   - que el navegador propio (Playwright) funciona desde la ventana.
2. **Acceso directo de Windows**: el de Linux existe (`python -m doombot lanzador`); el de Windows
   falta por hacer.
3. **Agente con apps de Windows**: que "abre la calculadora" encuentra el acceso del menú Inicio, y
   que cerrar ventanas (`tasklist` y `taskkill`) funciona.
4. **Ollama en la cadena** (`ollama:gemma4:12b`):
   - cuánto tarda;
   - si el repaso de respuestas (D-039) lo hace un modelo en la nube o el local;
   - si resume bien los chats de un proyecto (D-040).
5. **Proyectos de verdad**: un proyecto con dos chats (diseñar una app en uno, seguir el diseño en
   otro) con modelos reales.
6. **El modo `siempre` del repaso** a lo largo de un día: cuánta cuota gratuita se gasta.

## 3. D.O.O.M para Meta Quest 3S (sin empezar)

**Estado: solo el plan.** No hay código ni rama todavía.
- El plan de la fase 0 y los datos de la documentación de Meta están en la conversación del
  portátil del 14/10.
- El prompt completo del usuario debería guardarse en `quest-app/` al empezar.
- Mockup de la interfaz (privado): https://claude.ai/artifact/EBRy1BsPGh2mqqQAKhsz12

**Datos comprobados en la documentación de Meta el 14/10/2026:**
- Spatial SDK **0.14.0** (Maven Central, 11/09/2026); AGP 8.11.1, Gradle 9.4.1, Kotlin 2.1.0 y
  **JDK 17**.
- `minSdk`, `compileSdk` y `targetSdk` **34**. Horizon OS v69+ para Spatial SDK, **v76+ para la
  cámara** (Camera2).
- Cámara: los permisos `android.permission.CAMERA` y `horizonos.permission.HEADSET_CAMERA`, ambos en
  tiempo de ejecución. Las cámaras de passthrough se detectan con
  `com.meta.extra_metadata.camera_source` = 0.
- La cámara no funciona en el simulador ni por Quest Link: se prueba siempre en las gafas.
- Meta da por soportados Mac y Windows; en el **sobremesa Windows no hay el riesgo de Linux** (que el
  plugin de Gradle eche en falta Spatial Editor).

**Ya hecho en el portátil, y que habría que repetir en el sobremesa si se trabaja allí:**
- **JDK 17**: el portátil ya lo tenía.
- **Android SDK** en `~/Android/Sdk`: `cmdline-tools` (16111833), `platform-tools` (adb 1.0.41),
  `platforms;android-34` y `build-tools;34.0.0`, con la licencia aceptada.
  - En Windows: bajar las *command-line tools* de Windows desde developer.android.com, descomprimir
    en `%LOCALAPPDATA%\Android\Sdk\cmdline-tools\latest` y ejecutar el mismo `sdkmanager` (ahora
    avisa de que está obsoleto y usa la herramienta `android`; funciona igual).
  - Definir `ANDROID_HOME` y añadir `platform-tools` al `PATH`.
  - Windows puede necesitar el driver USB de Meta para `adb`.

**Falta, antes de la fase 0:**
1. En el portátil: `ANDROID_HOME` en `~/.bashrc` y `sudo apt install android-sdk-platform-tools-common`
   (reglas udev para que `adb` vea las gafas).
2. Cuenta de desarrollador: crear la organización con la cuenta de las gafas en
   https://developers.meta.com/horizon/manage/organizations/create/
3. Modo desarrollador: en la app Meta Horizon del móvil, Dispositivos → gafas → Ajustes → Modo
   desarrollador. Reiniciar las gafas.
4. Conectar por USB-C (cable de datos), aceptar la depuración USB en las gafas y comprobar que
   `adb devices` las muestra.
5. Comprobar en las gafas que Horizon OS es **v76 o superior** (para la fase 3).
6. Decidir dos cosas:
   - **dónde compilar**: portátil Linux o sobremesa Windows (habrá `deploy.sh` y `deploy.ps1`, y el
     código es el mismo);
   - el identificador de la app (propuesto: `com.doombot.quest`).

**Fase 0, en cuanto haya OK:**
- rama `tarea/quest-nativa`, carpeta `quest-app/` con su `CLAUDE.md`, y una entrada D-041;
- proyecto Gradle con esas versiones;
- actividad inmersiva con passthrough y un panel de Compose "Hola, Mi Señor";
- `scripts/deploy.sh` y `deploy.ps1`;
- test que falla si hay algo con forma de clave (`gsk_`, `AIza`, `sk-`, `nvapi-`);
- `local.properties` en `.gitignore`.

Lo primero, compilar la plantilla oficial de Meta para confirmar que el entorno sirve.

## 4. Otro equipo (amarinosa)

Sigue con la versión vieja de la app. Hay que hacer `git switch main && git pull` y, después, seguir
"La aplicación" del README: extras `hud` y `agent-web`, GTK del sistema y enlaces de `gi` y `cairo`.

## 5. Ideas en cola (sin empezar)

- **Prompt Guard de Groq**: avisar cuando una página leída intenta dar órdenes al agente.
- **Ordenar fragmentos por significado** con los embeddings que ya tiene el proyecto.
- **Memoria entre proyectos** (`memory/`) y **tareas programadas**.
- **Voz en la ventana**: que el núcleo reaccione al micrófono y a Kokoro, como el HUD.
