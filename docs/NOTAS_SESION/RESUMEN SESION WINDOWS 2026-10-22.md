# Resumen sesión Windows — 2026-10-22 (sobremesa)

Rama **`tarea/windows-taller-pyav`**, sacada de `main` (baf81de). Sin fusionar: lo hace el usuario.

## Puesta al día (20 y 22/10)
- Lo de la Quest de este equipo (14-15/10) está en **`tarea/quest-sobremesa`**. Ojo: el portátil
  también movió `tarea/quest-nativa`; las dos ramas de la Quest habrá que juntarlas.
- Extras instalados, voces de Kokoro y Whisper `small` descargados. El micrófono predeterminado es
  el de los auriculares **A50** (no el virtual del Oculus): no hace falta `DOOMBOT_AUDIO_INPUT`.
- Whisper en la RTX 5060 Ti: la primera vez de cada arranque, unos 6 s (la primerísima, 40 s,
  compilando CUDA para la tarjeta); después, 0,16 s por frase. Probado con una frase dicha por
  Kokoro, sin micrófono.
- **Lo que escribe la consola de Claude Code fuera del proyecto puede no llegar al Windows real**
  (queda en un entorno aislado): las voces bajadas desde ahí no las veía la ventana. Las descargas
  de modelos se hicieron desde el panel de Terminal, que es el entorno real. El `.venv` sí es real.
- `.venv\Lib\site-packages\doombot_truststore.pth` (el arreglo de Norton del 15/10, fuera del
  repo) chocaba con el `truststore` de pip: ahora no se activa si existe `DOOM_SIN_TRUSTSTORE`.
  Para instalar con pip: `$env:DOOM_SIN_TRUSTSTORE = "1"` antes (pip usa los certificados de
  Windows por su cuenta).

## Arreglado en esta rama
- **PyAV**: faster-whisper 1.2.1 llama a `av.open(..., metadata_errors=...)` y PyAV 19 quitó ese
  parámetro: cada transcripción fallaba con `TypeError`. `pyproject.toml` (extra `voice`) fija
  `av>=11,<19`, y `test_whisper.py` lee un WAV de verdad con faster-whisper: falla con PyAV 19
  (comprobado) y pasa con 18.
- **El taller en Windows** (D-045), tres huecos reales que los tests de Linux destapaban:
  - `/home`, `/data`... entre comillas («`shutil.rmtree('/home')`») se tomaban por opciones de cmd
    (`/s`, `/q`) y no se miraban. Ahora solo es opción la palabra suelta.
  - Una ruta que empieza por `/` o `\` sin unidad es la raíz de la unidad actual (`C:\home`), no
    una ruta sin comparar. `type \Windows\win.ini` también se reconoce como ruta.
  - `$HOME` (y `${HOME}`) cuenta como la carpeta del usuario aunque Windows no tenga esa variable:
    PowerShell y bash sí la expanden.
  - Los casos van en la tabla de Windows de `test_taller.py`; la de Linux da lo mismo que antes
    (20 casos, comprobados con `plataforma="linux"`).
- El test del diario leía sin codificación (cp1252 en Windows); ahora UTF-8, como lo escribe el
  taller.

Suite sin hardware en Windows: **771 en verde**.

## Pendiente
- La prueba 1 de la voz (sección 5 del traspaso del 15/10): pulsar para hablar en la ventana.
- Juntar `tarea/quest-sobremesa` y `tarea/quest-nativa`.
- `build/exe` (ejecutable) sigue con lo del 15/10 y con PyAV 19 dentro: recompilar.
