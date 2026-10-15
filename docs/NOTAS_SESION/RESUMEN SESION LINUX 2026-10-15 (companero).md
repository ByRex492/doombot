# Resumen de sesión — Linux (portátil), 15/10/2026 — personalidad, taller y voz

Rama: `tarea/companero`, sacada de `main` tras fusionar la memoria (D-043). Decisiones: **D-044,
D-045 y D-046**.

**Alcance acordado con el usuario:** D.O.O.M es de uso personal. Nada laboral: ni Jira ni el n8n de
trabajo del portátil. El código de n8n (D-030) se queda, sin configurar. El objetivo es un
compañero por voz, con personalidad y memoria, que construye proyectos de código (juegos, apps)
con autonomía total en su equipo.

## Qué se ha hecho

- **Personalidad (D-044).**
  - Perfil > *Su personalidad*: se elige un estilo (Compañero por defecto, J.A.R.V.I.S., Mentor,
    Colega gamer, Sobrio) y se retoca. Va en `obsidian/personalidad.md` y entra en cada orden.
  - El prompt habla como una persona y entiende la intención: «steam» a secas abre Steam. Ya no
    dice «Voy a responder.» antes de un saludo.
- **Taller (D-045).**
  - `~/taller` (`DOOMBOT_TALLER`): autonomía total dentro, con punto de control antes de cada
    orden en un git en la sombra, y `deshacer_cambios`.
  - Lo que sale del taller se sigue preguntando.
  - Herramientas nuevas: `editar_fichero`, `buscar_texto`, `proceso`, `crear_proyecto` y
    `ver_cambios`.
  - Diario por proyecto en `.doom/diario.md`.
- **Voz en la ventana (D-046).**
  - Botón 🎙 o Ctrl+Espacio, manos libres con «Hey Jarvis» (en Sistema), y respuestas habladas.
  - «Para» le corta, y los permisos se contestan hablando.
  - Transcribe con Whisper local o, si no está, con Groq (`DOOMBOT_STT`).

## Verificado

- Todos los tests (`pytest -m "not hardware"`) y ruff en verde.
- `conftest.py` aparta el taller, el vault y la voz: los tests no tocan `~/taller` ni abren el
  micrófono.
- **Con la cadena real, en temporales:**
  - saludo natural usando el nombre del perfil;
  - «steam» → abrió Steam (una app de mentira, para no abrir nada en el equipo);
  - creó y probó un proyecto en el taller sin un solo permiso;
  - «deshaz lo último» preguntó y deshizo.
- La interfaz, en la demostración (`#demo`): botón del micrófono con sus estados, Sistema (Taller,
  Voz, manos libres) y el editor de personalidad.

## Sin verificar — pendiente en el sobremesa

**Nada de audio real.** El portátil no tiene el stack de voz instalado, y no se ha abierto el
micrófono con el usuario delante. Hay que probar:
1. 🎙 y Ctrl+Espacio: graba, transcribe con Whisper GPU y ejecuta.
2. Que conteste hablando con Kokoro, y que «para» lo corte.
3. Manos libres con «Hey Jarvis». Comprobar que su propia voz no la dispara.
4. Un permiso contestado con «sí» o «no».
5. El taller con un proyecto de verdad (Godot o pygame): `proceso lanzar`, leer errores y
   deshacer.

Después de probarlo, fusionar `tarea/companero` a `main`.

Pendiente de antes, sin cambios: `tarea/quest-nativa` (D-041 y D-042), y los cambios de la Quest
que siguen sin subir en el sobremesa.
