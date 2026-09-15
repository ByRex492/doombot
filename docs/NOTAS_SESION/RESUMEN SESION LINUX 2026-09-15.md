# Resumen sesión Linux — 2026-09-15

Sesión larga desde el equipo Linux (no el sobremesa), con Claude Code. `main` local iba **38
commits por detrás** de `origin/main` al empezar -todo el trabajo de la sesión del sobremesa
entre el 10 y el 13/09 (TTS, HUD, Capa 2 en GPU, `capa4-acciones`)-; *fast-forward* limpio, sin
nada que fusionar a mano. Todo lo de aquí quedó **subido a `origin/main` directamente**, commit a
commit: no hubo rama `tarea/*` de por medio.

Esta máquina no tiene `.venv` propio ni Ollama arrancado. Cada verificación de esta sesión montó
un entorno virtual temporal, corrió `ruff` y `pytest -m "not hardware"`, y se borró al terminar.
**Nada de esto se probó con Ollama, Whisper ni n8n reales** -solo con dobles de prueba-, ni con
el hardware de audio de un A50 delante.

## Qué se hizo, en orden

### 1. Dos bugs reales, encontrados y arreglados

- **`actions/claude_code.py` no resolvía `claude.cmd` en Windows.** `subprocess.run(["claude",
  ...])` sin `shell=True` no prueba las extensiones de `PATHEXT` -a diferencia de `cmd.exe`-, así
  que fallaba con `FileNotFoundError` aunque `claude.cmd` estuviera en el `PATH` y funcionara
  desde una consola interactiva. Es el fallo que la sesión del 13/09 ("Capa 4") ya había
  encontrado y sorteado a mano con `DOOMBOT_AGENT_BINARY=<ruta completa>`, sin tocar el código.
  Arreglado con `shutil.which()`, resuelto una vez en el constructor; `resolver` es inyectable
  para probarlo sin depender del `PATH` real de la máquina que corre los tests.
- **Dos tests de `test_capture.py` tocaban hardware de audio real sin querer**, por no pasar
  `opener` (la costura que ya existía para esto). En Windows nunca se notó porque los índices de
  dispositivo del test no correspondían a nada real; en este Linux, el índice 10 es un micrófono
  real que capta sonido ambiente, y el test fallaba (`10 == 1`) -el mismo tipo de fallo silencioso
  entre equipos que el proyecto lleva evitando desde D-013, esta vez en sus propios tests.

### 2. n8n: dirección decidida y construida (D-030)

Quedó pendiente desde el 31/08 sin decidir a propósito. Se eligió: **D.O.O.M dispara *workflows*
de n8n, nunca al revés** -sin servidor nuevo escuchando entradas ajenas-. Orden nueva "activa el
flujo: `<nombre>`" (`actions/n8n.py`, `N8nClient`, mismo patrón que `OllamaGenerator`). La
salvaguarda es una lista blanca en `.env` (`DOOMBOT_N8N_WORKFLOWS`, resuelta normalizada), no la
URL construida directamente del nombre dicho.

**Importante para el sobremesa:** el n8n contra el que esto se pensó vive **en este equipo
Linux** (`~/n8n` con Docker, puerto 5678, con automatizaciones reales ya conectadas -Jira, entre
otras-). `DOOMBOT_N8N_BASE_URL` en el sobremesa tendría que apuntar a este equipo por red para que
la orden llegue a algo real, o habría que levantar un n8n propio allí. Sin configurar, la orden
avisa con un mensaje claro en vez de fallar raro.

### 3. Confirmación hablada antes de una acción real (D-031)

Pendiente anotado en D-017 desde que no existía voz completa; ya existe (TTS, HUD y barge-in
cerrados desde el 10-13/09). Antes de ejecutar de verdad se pregunta y se espera una respuesta
afirmativa (`phrases.es_afirmacion`): "act" solo si el modo del agente no es `plan` -en `plan` ya
no hay nada real que proteger-, "flow" siempre -un webhook no tiene equivalente a `plan`-.
Silencio o cualquier respuesta no reconocida cuenta como negativa.

`Sesion.preguntar` deja de estar fijado a `input()`: en modo voz (`run_voz`) pasa a ser un cierre
que dice la pregunta con el `Speaker` ya montado y escucha con el mismo `Microphone`/
`WhisperTranscriber` del `Listener`, sin repetir la palabra de activación -se sigue en el mismo
turno-. El modo escrito sigue usando `input()` sin cambios. **Sin probar con voz real**: toda la
verificación fue con dobles (`tests/test_actions_orders.py`).

### 4. Enrutador Ollama↔Claude: manual, no automático (D-032)

Mismo pendiente sin decidir del 31/08 que n8n, pero aquí se decidió **no** construir el
automatismo: nadie ha medido todavía qué criterio (longitud, palabras clave...) justificaría
escalar solo, y la propia sesión que lo escribiría es la misma Claude a la que enrutaría -conflicto
de interés real, no solo formal-. En su lugar, orden manual "pregunta a Claude: `<algo>`"
(`backends/orders.py`): presta `sesion.gen` por un `AnthropicGenerator` durante ese turno y lo
devuelve después, reutilizando `_responder()` entero -streaming, voz, historial- en vez de
duplicar ese camino. Necesita `DOOMBOT_ANTHROPIC_API_KEY` en `.env`; sin ella, el aviso ya lo da
`AnthropicGenerator.stream()`.

### 5. Documentación puesta al día

`README.md` se había quedado describiendo solo la Capa 2 (oír, sin hablar): sin TTS, sin HUD, sin
acciones, sin n8n, sin las órdenes por encima de las básicas. Se amplió con todo eso, más una
tabla de extras de instalación (`voice`, `voice-cuda`, `voice-tts`, `voice-aec`, `hud`).
`docs/estructura.md` gana la mención de `actions/n8n.py`. El docstring de `__main__.py` gana
`voz` y `voz-descargar`, que llevaban semanas cableados en `main()` sin aparecer ahí.

## Qué hacer primero al retomar en el sobremesa

1. `git pull` -ya es fast-forward puro, sin conflictos esperados: no hay rama `tarea/*` de por
   medio, todo entró directo a `main`.
2. **Probar de verdad con voz, Ollama y n8n reales** lo que aquí solo se probó con dobles:
   - Las tres órdenes nuevas: `activa el flujo`, `pregunta a claude`, y la confirmación hablada de
     `ejecuta esto` en un modo que no sea `plan`.
   - Que `preguntar_voz` (el cierre nuevo en `run_voz`) suena bien y escucha la respuesta sin
     pisar la síntesis -no se ha oído ni una vez de verdad.
3. Decidir `DOOMBOT_N8N_BASE_URL` para el sobremesa (ver punto 2 de arriba: n8n vive en el Linux).
4. Poner `DOOMBOT_ANTHROPIC_API_KEY` si se quiere usar "pregunta a claude" ahí.
5. `pytest -m "not hardware"` con Ollama real delante, para confirmar que los 360 tests que
   pasaron aquí con dobles siguen en verde con el backend de verdad.
6. Seguía pendiente de sesiones anteriores y sigue sin tocarse: abrir `obsidian/` en la app real
   de Obsidian, y las ideas sin construir de siempre (criterio automático del enrutador -ahora con
   la versión manual ya en uso, puede que surjan pistas de cuándo hace falta-, confirmación
   hablada ya cerrada así que ese punto de la lista antigua queda resuelto).
