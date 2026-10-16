# Traspaso al sobremesa — 2026-10-15

**Para la sesión de Claude Code del sobremesa (Windows 11, RTX 5060 Ti).** El usuario trabajó hoy
con Claude Code en el portátil Linux, y esa conversación no se ve desde aquí: esta nota es todo lo
que hace falta para seguir. Después de leerla, lee las decisiones D-043 a D-046 de
`docs/decisiones.md`. El usuario dará las siguientes instrucciones.

## 1. Quién es el usuario y cómo trabaja

- **Escribe en español y hay que contestarle en español**, claro y sin jerga. Los informes, con
  lo hecho, lo comprobado y lo que queda sin probar, dicho sin rodeos.
- **D.O.O.M es de uso personal.** Nada laboral entra en el proyecto: ni Jira, ni las
  automatizaciones de trabajo del n8n que corre en el portátil. El código de n8n de D-030 sigue
  ahí, sin configurar; no construir encima.
- **La meta que ha marcado**: un compañero con personalidad y memoria, que le ayude a construir
  proyectos de código (juegos, apps), como **asistente de voz con autonomía total en el equipo
  donde esté instalado**. Quiere que sea lo más humano posible, que entienda la intención y no
  solo palabras clave («steam» a secas, o «abre steam», tiene que abrir Steam). Aún no ha decidido
  qué tareas automáticas quiere.
- **Reglas que ha dejado claras:**
  - Sus claves de API no se leen, ni se imprimen, ni se escriben. Como mucho se comprueba si
    están vacías. Si intenta pegarlas en el chat, decirle que no lo haga.
  - No abrir ni cerrar ventanas de D.O.O.M mientras él lo está usando.
  - No hacer capturas de su escritorio mientras usa el equipo.
  - Los tests no escriben nunca en sus datos reales. `conftest.py` aparta la carpeta de datos, el
    vault, el taller y la voz.
  - Las licencias y los términos los acepta él.
  - Fusionar a `main` solo cuando lo pide. El trabajo nuevo va en ramas `tarea/<algo>` (ver
    `CLAUDE.md`).
  - Al cerrar sesión: nota en `docs/NOTAS_SESION/` y `git push`.
- **Las claves de los modelos** son de su cuenta, no del equipo: la misma vale en todos sus
  dispositivos y no hace falta generar una nueva en cada instalación. Se le recomendó guardarlas
  en un gestor de contraseñas (Bitwarden) y pegarlas en Primeros pasos.

## 2. Estado de las ramas (15/10, tarde)

- **`main`** tiene todo lo de hoy, fusionado y subido: memoria y perfil (D-043), personalidad
  (D-044), taller (D-045) y voz en la ventana (D-046). Pasan todos los tests (más de 700) en Linux.
- **`tarea/quest-nativa`**, sin fusionar: la app nativa de las Meta Quest 3S (`quest-app/`, D-041)
  rehecha en 3D (D-042). Su nota es `RESUMEN SESION LINUX 2026-10-15 (quest 3D).md`, que está en
  esa rama.
- **Ojo:** el 14/10 la app de la Quest funcionó en las gafas desde **este** equipo, pero esos
  cambios (un «brazalete», entre otros) **nunca se subieron a GitHub**. Antes de cualquier
  `git pull` o `git switch` que toque `quest-app/`:
  ```
  git status
  git switch -c tarea/quest-sobremesa
  git add quest-app
  git commit -m "Quest: cambios del sobremesa del 14-15/10"
  git push -u origin tarea/quest-sobremesa
  ```
  Antes, la identidad de git de este equipo: `git config --global user.name "ByRex492"` y
  `git config --global user.email` con su correo. La nota de Windows del 15/10 dice que faltaba.

## 3. Poner el sobremesa al día

```
git fetch
git switch main
git pull
pip install -e ".[dev,voice,voice-cuda,voice-tts,voice-aec,hud,agent-web]"
python -m doombot voz-descargar
pytest -m "not hardware"
```

- `voice` ya trae `fastembed`, que usa la memoria (extra `memoria`). El modelo de embeddings
  (~220 MB) se descarga solo la primera vez que hace falta.
- Ajustes nuevos en `.env`, opcionales (ver `.env.example`):
  - `DOOMBOT_TALLER`: por defecto `~/taller`, es decir, `C:\Users\<usuario>\taller`;
  - `DOOMBOT_STT=auto`: Whisper local si está instalado; si no, Groq.
- Este equipo inspecciona HTTPS con Norton, y en el `.venv` está resuelto con `truststore`
  (`doombot_truststore.pth`, nota de Windows del 15/10). Si se recrea el `.venv`, hay que repetirlo.
- **El ejecutable** (`build/exe/compilar.ps1`) copia `.env` dentro de `dist/DOOM/`, así que esa
  carpeta lleva las claves. Hay que recompilarlo para que tenga lo de hoy.

## 4. Qué se hizo hoy, en corto

- **Memoria (D-043)**, en el botón **Perfil** de la cabecera:
  - **perfil**: sus datos y hechos sueltos en `obsidian/usuario.md`, que viaja con git y entra
    en cada orden;
  - **recuerdos**: `memory.db` local, buscados por significado y solo cuando vienen a cuento;
    aparecen con ◈ en el registro;
  - herramientas `anotar_sobre_usuario` (siempre pide permiso), `recordar`, `buscar_en_memoria`
    y `olvidar_recuerdo`;
  - las contraseñas, claves y datos bancarios se rechazan siempre.
- **Personalidad (D-044)**: en Perfil > «Su personalidad», guardada en
  `obsidian/personalidad.md`, con estilos de partida.
  - El prompt del agente se reescribió para hablar como una persona y entender la intención.
- **Taller (D-045)**:
  - dentro de `~/taller` el agente crea, edita, borra, ejecuta e instala sin preguntar;
  - antes de cada orden guarda un punto de control en un git en la sombra
    (`<datos>/taller/*.git`), y `deshacer_cambios` vuelve atrás;
  - lo que sale del taller se pregunta: `sudo`, instalar en el sistema, `git push`, `ssh`,
    `curl|sh`, `pip` fuera de un venv o rutas de fuera;
  - herramientas nuevas: `editar_fichero`, `buscar_texto`, `proceso` (juego o servidor en
    marcha), `crear_proyecto`, `ver_cambios`;
  - diario por proyecto en `.doom/diario.md`.
- **Voz en la ventana (D-046)**:
  - 🎙 o Ctrl+Espacio para hablar, y Manos libres con «Hey Jarvis» en la pestaña Sistema;
  - responde hablando con Kokoro lo que se le pide por voz;
  - «para» le corta, y los permisos se contestan con un «sí» o un «no»;
  - lo que se oye va al agente, no a las palabras clave de la consola.

## 5. Lo primero que hay que probar aquí (no se pudo en el portátil)

El portátil no tiene instalado el stack de voz, y el micrófono no se abrió con el usuario delante.
**Nada de la voz se ha probado con audio real.** Con `python -m doombot ventana`:

1. **Pulsar para hablar**: 🎙 o Ctrl+Espacio → graba, transcribe con Whisper en la GPU y ejecuta.
   En la pestaña Sistema, «Voz» debe decir «oye · habla».
   - Según `voice/capture.py`, el micrófono predeterminado de este equipo es el virtual del
     Oculus. Fijar `DOOMBOT_AUDIO_INPUT` en `.env` si no oye.
2. **Que responda hablando**, y que «para» y el botón Detener le corten.
3. **Manos libres** con «Hey Jarvis». Comprobar que su propia voz no la dispara cuando habla.
4. **Un permiso contestado hablando**, por ejemplo con algo fuera del taller.
5. **El taller con un proyecto de verdad** (pygame o Godot), y lo que tarda el primer punto de
   control en un proyecto grande:
   - «créame un juego de la serpiente en Python en el taller y pruébalo»;
   - «lánzalo», «mira los errores», «deshaz lo último».
6. **Memoria y personalidad**:
   - rellenar Perfil y elegir personalidad;
   - decirle «recuerda que…» y preguntárselo en una conversación nueva.

**Dónde mirar si algo falla:**
- la voz: `ventana/voz.py` y su uso en `ventana/puente.py`;
- la interfaz: `ui/ventana/doom.html`, busca `pintarVoz` y `mostrarPerfil`;
- el taller: `agent/taller.py` y `agent/sistema.py`;
- la memoria: `agent/memoria.py`.

## 6. Puntos débiles probables en Windows (escrito pensando en Linux)

- **Actualización del 16/10:** `comando_libre` del taller ya tiene reglas de Windows (rutas `C:\`,
  opciones de cmd, `py -m pip` y comandos de administración), probadas desde Linux con 21 casos
  (D-045). El prompt le dice que use `python` o `py` y cmd.exe. Falta verlo en este Windows de
  verdad.
- **Novedad del 16/10: ve (D-047).** «Mira mi pantalla» o pegar una imagen en el chat. Probar que
  la ventana se minimiza, captura y vuelve. Nunca se ha capturado una pantalla de verdad.
- **Los procesos del taller** se matan con `taskkill /T /F`, sin probar.
- **El git en la sombra** con rutas de Windows y `core.autocrlf=false`, sin probar.
- **Transcribir en Groq** a través de Norton: debería ir con `truststore`, sin probar.

## 7. Ideas pendientes, ya habladas con el usuario (no empezar sin que lo pida)

1. **Rutinas y automatización.** Se investigó y se recomendó:
   - rutinas propias de D.O.O.M: instrucciones guardadas en `obsidian/rutinas/`, lanzadas a
     mano o a una hora;
   - después, convertir las que se repiten en scripts de Python aprobados, que se vuelven a
     aprobar si cambian.

   n8n se descartó porque el del portátil es de trabajo. El usuario aún tiene que decidir qué
   tareas quiere.
2. **Que vea**: capturas de pantalla o fotos a un modelo con visión (Gemini Flash es gratis),
   solo cuando él lo pida.
3. **Las gafas como pantalla del sobremesa**: que la app de la Quest hable con el D.O.O.M del PC
   por la red de casa, en vez de llevar su propio agente reducido.
4. **Escudo contra instrucciones escondidas** en lo que lee de internet, por ejemplo con Prompt
   Guard. Gana importancia con la autonomía del taller.
5. **Copiar las claves de otro D.O.O.M de la red con un PIN** en Primeros pasos, para no tener
   que pegarlas en cada equipo.
6. **La consola de voz** (`python -m doombot chat`) sigue con palabras clave. La ventana ya es el
   asistente de voz, así que no se ha tocado.

## 8. Primer mensaje sugerido en esta sesión

> Lee `docs/NOTAS_SESION/TRASPASO AL SOBREMESA 2026-10-15.md` y lo que te mande leer. Después te
> digo qué hacemos.
