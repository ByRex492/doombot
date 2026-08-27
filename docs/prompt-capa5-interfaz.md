# Prompt para la sesión paralela: interfaz y voz

Copiar íntegro en un chat nuevo. Está pensado para ser autosuficiente: esa sesión
no tiene acceso a la conversación principal.

---

## CONTEXTO

Estoy construyendo **DOOM**, un asistente personal por voz que funciona 100% en local en mi
PC, sin llamadas a la nube. El proyecto va por capas y ya tengo validada la primera. Esta
conversación es una **rama paralela** dedicada exclusivamente a dos cosas: la **interfaz
gráfica** y la **voz**. La capa de razonamiento y la de audio de entrada las llevo en otro
chat, así que no hace falta que las toques.

## MI HARDWARE

- CPU AMD Ryzen 7 5800X · 32 GB RAM
- GPU NVIDIA RTX 5060 Ti, 16 GB VRAM (**14,8 GiB realmente utilizables**), driver 610.62, CUDA 13.3
- Arquitectura Blackwell, compute capability sm_120 (relevante: algunas librerías aún no la soportan)
- Windows 11 Pro · 1 TB SSD

## LO QUE YA ESTÁ DECIDIDO Y MEDIDO (no hace falta rediscutirlo)

**Capa 1 — Cerebro.** Ollama 0.33.0 con `gemma4:12b`. Verificado por medición en mi máquina:
100% en GPU, 46,2 tok/s, ~7,8 GB de VRAM ocupados. Se usa el endpoint `/api/chat` (nunca
`/api/generate`, que devolvía respuestas vacías). `keep_alive` permanente y un solo modelo
residente a la vez.

**Presupuesto de VRAM — esta es la restricción que lo gobierna todo.** El LLM se come 7,8 GB
de los 14,8 disponibles. Quedan **unos 7 GB** para repartir entre Whisper y el TTS. Cualquier
propuesta tuya tiene que caber ahí.

**Idioma:** bilingüe, español e inglés.

**Capa 2 — Oídos (en marcha en el otro chat):** openWakeWord con el modelo preentrenado
`hey_jarvis` + faster-whisper multilingüe.

## LO QUE QUIERO DE ESTA CONVERSACIÓN

### A. La interfaz gráfica

Un HUD tipo Siri o JARVIS: **no copiado, pero de esa familia visual**. Un orbe u onda centrada
sobre fondo oscuro, que reacciona en tiempo real a la voz, con animaciones fluidas y un color
de acento.

Decisiones técnicas ya tomadas, dime si las cambiarías:

- **`pywebview`** para la ventana: navegador embebido en ventana nativa, con Python llamando a
  JavaScript y al revés. Elegido porque el resplandor, el desenfoque y las partículas son
  triviales en Canvas/CSS y un suplicio en Qt o Tkinter, y porque me deja toda la lógica en Python.
- `frameless=True`, `transparent=True`, `on_top=True` para el HUD flotante. **La transparencia
  real en Windows está sin verificar**: si no funciona, necesito alternativa.
- **La interfaz no decide nada.** El orquestador emite eventos de cambio de estado más un chorro
  continuo de amplitud del audio (30-60 veces por segundo). La interfaz solo escucha y anima.
  Así puedo rehacerla entera sin tocar las capas de audio.

**Máquina de estados a representar:**

```
DORMIDO ──wake word──> ESCUCHANDO ──silencio──> PENSANDO ──> HABLANDO ──> DORMIDO
```
Más un estado de ERROR.

**Importante sobre mí: no tengo ni idea de diseño y no sé usar herramientas de diseño.** No
me mandes a Figma. La forma de trabajar que quiero es que **tú generes prototipos que corran
de verdad** —una página HTML que yo abro y veo animándose, con amplitud simulada— y yo te diga
qué cambiar. Yo no sé diseñar, pero sí sé juzgar lo que veo. Itera conmigo así.

### B. La voz

Bilingüe, y tiene que convivir en VRAM con el LLM y con Whisper.

Panorama que ya he mirado, verifícalo y corrígeme si está desactualizado:

| Motor | Licencia | Primer audio | Clona voz |
|---|---|---|---|
| Kokoro-82M | Apache 2.0 | ~45 ms | No |
| Chatterbox Multilingual v3 | MIT | — | Sí |
| Qwen3-TTS | Apache 2.0 | ~97 ms | Sí, desde 3 s |
| XTTS-v2 | CPML (no comercial) | ~320 ms | Sí, el mejor |

**Punto de partida: Kokoro**, por velocidad, licencia y consumo bajo.

**Restricción que no quiero saltarme:** nada de clonar la voz de una persona real identificable
(actores, dobladores, famosos) sin su consentimiento. Descartado también por motivos técnicos:
el audio de película lleva música, efectos y reverberación, y da clones sucios. Las vías válidas
son voz de catálogo, clonar **mi propia voz**, o bancos de voz con licencia.

**El efecto "IA de película" que busco** viene sobre todo de tres cosas que no dependen del
modelo: el registro del *system prompt* (pausado, formal, sin coletillas de chatbot), la
cadencia (algo más lento de lo normal, pausas limpias) y un procesado ligero del audio
(reverberación de sala pequeña, recorte de graves). Quiero que trabajemos eso, no solo el timbre.

### C. Cómo conectar todo

Me interesa especialmente resolver bien tres cosas que sé que son las difíciles:

1. **Streaming por frases:** trocear la salida del LLM en frases completas y sintetizar y
   reproducir mientras el modelo sigue generando, para que empiece a hablar en ~1 s y no en 5.
2. ***Barge-in*:** poder interrumpirlo mientras habla. Es lo que da sensación de producto acabado.
3. **Cancelación de eco:** consecuencia del anterior — si el micrófono sigue abierto mientras el
   altavoz suena, DOOM se oye a sí mismo y se interrumpe solo.

Tengo apuntadas las librerías `RealtimeTTS` y `RealtimeSTT` (github.com/KoljaB) como candidatas
para el troceado y la reproducción en streaming. Evalúa si compensan o si es mejor escribirlo.

## CÓMO QUIERO QUE TRABAJES CONMIGO

1. **Explícame la teoría** de cada componente: qué hace, por qué esa opción y no otra, y qué papel
   juega. No des por hecho que conozco las herramientas.
2. **Dame el código completo y comentado**, explicando los bloques relevantes.
3. **Vamos paso a paso**, validando cada cosa antes de seguir. Nada de generarlo todo de golpe.
4. **Pídeme confirmación explícita** antes de instalar software o ejecutar comandos con efectos
   en el sistema.
5. **No te fíes de los benchmarks de blogs.** Cuando haya que elegir, medimos en mi máquina, que
   es lo que hicimos con el LLM y por eso las cifras de arriba son fiables.
6. **Prioriza herramientas gratuitas y de código abierto.**

## LO QUE **NO** DEBES HACER

- No toques las Capas 1 y 2 (LLM y entrada de audio): se llevan en la conversación principal.
- No propongas clonar voces de personas reales identificables.
- No me mandes a aprender una herramienta de diseño.

## ENTREGABLES QUE ESPERO

1. Un **prototipo del HUD funcionando**, iterado hasta que me convenza, con los cinco estados.
2. Una **decisión de voz razonada y medida** en mi máquina: motor, voz concreta, consumo de VRAM
   y latencia real hasta el primer audio.
3. El **contrato de comunicación** entre orquestador e interfaz: qué eventos se emiten, con qué
   formato y a qué frecuencia. Esto es lo que luego tengo que integrar en el proyecto principal.
4. Un **resumen final de decisiones** en formato breve, que pueda pegar en la conversación
   principal para incorporarlo al registro `docs/decisiones.md` del repositorio.

## PRIMERA TAREA

Confirma que entiendes el planteamiento, dime si cambiarías alguna de las decisiones técnicas
que ya he tomado (sobre todo `pywebview` y Kokoro), y después **monta el primer prototipo del
HUD** para que empecemos a iterar sobre algo que se vea.
