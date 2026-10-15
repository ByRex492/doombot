# Resumen sesión Windows — 2026-10-15

Equipo nuevo con Windows 11 y una RTX 5060 Ti (16 GB → perfil `workstation`), con Claude Code.
Rama **`main`**, a petición del usuario. Nada commiteado todavía: git no tiene `user.name` ni
`user.email` en este equipo.

## Puesta en marcha desde cero

Git, VS Code (con las 13 extensiones de `.vscode/extensions.json`), ripgrep, Python 3.12.10,
Ollama 0.40.4 con `gemma4:12b` y `OLLAMA_MAX_LOADED_MODELS=1`. `.venv` con todos los extras
(`dev,voice,voice-cuda,voice-tts,voice-aec,hud,agent-web`) y Chromium de Playwright. `.env` con
`varios` para el chat y el agente y la cadena del traspaso del 14/10; las cuatro claves (Groq,
Gemini, NVIDIA, OpenRouter) responden.

## Arreglos

- **La ventana no abría en Windows** (`ventana/__init__.py`): se le pasaba `doom.svg` como icono y
  WinForms solo carga `.ico`; `System.Drawing.Icon` lanzaba una excepción de .NET que mataba el
  proceso sin pasar por Python. Ahora `_icono()` usa `ui/ventana/doom.ico` en Windows (mismo
  núcleo, renderizado del SVG) y el SVG en el resto. Tests en `test_lanzador.py`.
- **`test_lanzador` fallaba en Windows**: comparaba rutas de Linux construidas con `Path`, que en
  Windows salen con `\`. Ahora `PurePosixPath`.
- **OpenRouter retiró `openai/gpt-oss-120b:free`** (solo queda el de pago). El sugerido de
  `proveedores.py` y el ejemplo de `.env.example` pasan a `nvidia/nemotron-3-super-120b-a12b:free`,
  comprobado con herramientas el 15/10. `google/gemma-4-31b-it:free` existe pero estaba saturado.
- **Norton 360 inspecciona HTTPS** (Web/Mail Shield) y firma con su propia raíz, que Windows conoce
  y `certifi` no: fallaba toda descarga de modelos desde Python (`CERTIFICATE_VERIFY_FAILED`). En
  este equipo se resuelve fuera del repo con `truststore`: un `.pth` en el `.venv`
  (`doombot_truststore.pth`) y lo mismo en el ejecutable. No se ha tocado Norton.

Suite sin hardware: 601 en verde.

## Ejecutable

`build/exe/` (ignorado por git, **no versionado**): `doom.spec`, `doom_entry.py`, `compilar.ps1`
y un hook para `webrtcvad-wheels`. Genera `dist/DOOM/` (~2,5 GB, casi todo CUDA) en unos 2 min:
`DOOM.exe` abre la ventana y `doombot.exe` es la CLI. Es `--onedir` porque `PROJECT_ROOT` sale de
`__file__`: congelado cae en `dist/DOOM/`, donde `compilar.ps1` copia `ui/`, `skills/`, `obsidian/`,
`profiles.toml` y `.env`. **Ojo**: el ejecutable usa su propia copia `dist/DOOM/.env`.

Verificado: diagnóstico, pregunta al modelo local, lista de micrófonos y la ventana abierta.
Sin verificar desde el ejecutable: voz completa (Whisper en CUDA, Kokoro) y el navegador del agente.

Acceso directo "D.O.O.M" en el Escritorio y el menú Inicio: `.venv\Scripts\pythonw.exe -m doombot
ventana`, con el icono del núcleo. Es el pendiente 2 del traspaso, pero hecho a mano y no con
`python -m doombot lanzador`, que sigue siendo solo de Linux.

## Perfiles de color propios (D-036)

Pedido: además de los temas fijos, crear perfiles de color propios, guardarlos, cambiar entre
ellos y editarlos. En Personalizar hay ahora una sección **Mis perfiles**:

- **+ Nuevo perfil** crea uno con los colores de ese momento y lo deja activo para nombrarlo.
- Con un perfil propio activo, cambiar un color lo cambia en el perfil; el nombre se cambia al
  salir del campo o con Intro. **Duplicar** y **Borrar perfil** (doble clic, como en los menús;
  un clic fuera lo cancela).
- Con un tema fijo, tocar un color pasa a «propio» como antes, y **Guardar como perfil** lo
  conserva con el nombre escrito.
- **Restablecer** vuelve al aspecto de fábrica sin borrar los perfiles.

`preferencias.py` valida la lista `perfiles` (id `perfil-…`, nombre de una línea y hasta 32
caracteres, dos colores `#rrggbb`, máximo 24) y, con un perfil activo, pinta sus colores. Probado
en `doom.html#demo` con clics y teclado reales, y con tests en `test_preferencias.py`.

## Pendiente

- Commit y push de lo de arriba (falta la identidad de git en este equipo).
- Decidir si el empaquetado de `build/exe/` pasa al repo (sustituiría a `ui/build.py`, que solo
  empaqueta el prototipo del HUD) y si `paths.py` debe saber que está congelado.
- **Seguridad del agente** (`agent/sistema.py`, `es_solo_lectura`): varios programas de la lista
  de solo lectura escriben o ejecutan sin confirmación (`find -fprintf`, `sort -o`, `uniq a b`,
  `tree -o`, `git diff --output`, `rg --pre`), `grep -r . ~/.ssh` lee claves porque `es_sensible`
  no mira la carpeta final, y `echo %DOOMBOT_..._API_KEY%` (Windows) o `cat /proc/self/environ`
  enseñan las claves. Visto, sin arreglar.
