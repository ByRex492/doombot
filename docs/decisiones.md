# Registro de decisiones

Cada entrada explica **qué** se decidió, **por qué**, y **qué alternativa se descartó**.
El objetivo es que dentro de seis meses se entienda el razonamiento sin reconstruirlo de cero.

---

## D-001 — Python 3.12 en lugar del 3.14 instalado

**Contexto.** La máquina traía únicamente Python 3.14.0.

**Decisión.** Instalar Python 3.12 en paralelo. No se desinstala el 3.14: conviven mediante el
*py launcher* de Windows (`py -3.12`).

**Por qué.** Las librerías del stack de audio e IA (`onnxruntime`, `ctranslate2`, `torch`)
distribuyen *wheels*: binarios ya compilados, publicados solo para las versiones de Python que
cada proyecto soporta. Si no existe wheel para una versión, `pip` intenta compilar desde código
fuente en C++, lo que en Windows exige Visual Studio Build Tools y falla con frecuencia.
Python 3.12 es la versión con mejor cobertura de wheels para este stack.

**Descartado.** Usar 3.14 y compilar lo que hiciera falta. Coste alto, beneficio nulo.

---

## D-002 — venv en lugar de conda

**Decisión.** Entorno virtual con `venv`, el módulo estándar de Python.

**Por qué.** Conda aporta valor cuando hay que gestionar dependencias binarias ajenas a Python
(toolkits de CUDA, compiladores) desde el propio gestor de paquetes. Aquí no ocurre: Ollama
incluye su runtime CUDA propio y las wheels de PyPI ya traen los binarios que necesitan.
Conda solo añadiría peso y una segunda fuente de verdad sobre qué paquete está instalado.

---

## D-003 — Ollama como motor de inferencia local

**Decisión.** Ollama 0.33.0 como servidor de LLM.

**Verificado en esta máquina.** Detecta la GPU correctamente al arrancar:

    library=CUDA  compute=12.0  name="NVIDIA GeForce RTX 5060 Ti"
    libdirs=ollama,cuda_v13  driver=13.3  total="15.9 GiB"  available="14.8 GiB"

`compute=12.0` es la *compute capability* sm_120 de la arquitectura Blackwell. Era el principal
riesgo técnico identificado al inicio (una GPU demasiado reciente para las librerías habituales)
y queda **descartado para la capa de LLM**: Ollama 0.33 incluye runtime CUDA 13 compilado para ella.

**Pendiente de validar.** El mismo riesgo sigue abierto para `faster-whisper` (CTranslate2) en la
Capa 2. Plan B si no hubiera soporte sm_120: `whisper.cpp` compilado con CUDA o Vulkan.

**Nota operativa.** Ollama fija por defecto `num_ctx=4096` según la VRAM disponible. Suficiente
para conversación, pero habrá que subirlo cuando el asistente acumule historial.

---

## D-004 — Modelos candidatos y criterio de elección

**Decisión.** Descargar `gemma4:12b` (7,6 GB) y `qwen3:8b` (5,2 GB), medir ambos en la máquina
real y elegir con datos.

**Por qué medir en vez de elegir de antemano.** `gemma4` se publicó pocas horas antes de esta
decisión, muy por detrás del corte de conocimiento del asistente que ayuda en el proyecto.
Se pueden leer sus especificaciones, pero no hay experiencia real sobre su calidad. La única
respuesta fiable es el benchmark local: tokens/segundo y calidad de respuesta en español.

**Restricción que gobierna la elección.** El LLM **no puede ocupar toda la VRAM**: tiene que
convivir en memoria con Whisper (~1-2 GB) y Kokoro (~0,5 GB). Con 14,8 GiB utilizables, el
presupuesto realista para el modelo de lenguaje es de 7-9 GB.

**Descartados.** `qwen3.6:27b` y las variantes 26B/31B de Gemma 4: entre 17 y 20 GB en Q4.
Aunque forzando entraran, dejarían sin memoria a las capas de audio.

**Criterio de fondo.** En un asistente de voz la latencia pesa más que la inteligencia bruta:
una espera de seis segundos rompe la conversación por buena que sea la respuesta.

---

## D-005 — Idioma: español e inglés

**Decisión.** Asistente bilingüe.

**Consecuencias por capa.**

- **Wake word (Capa 2).** *No* requiere entrenar un modelo propio. Una palabra de activación es
  un patrón acústico, no una frase que haya que comprender, así que el modelo preentrenado
  `hey_jarvis` de openWakeWord sirve aunque la conversación siga en castellano.
- **STT (Capa 2).** Modelos *multilingües* de Whisper, no las variantes `.en`. Estas últimas son
  más rápidas pero solo entienden inglés. Se activa la autodetección de idioma.
- **TTS (Capa 3).** Kokoro necesita una voz por idioma. El orquestador seleccionará cuál usar a
  partir del idioma que detecte Whisper.

---

## D-006 — El orquestador se construye desde el principio

**Decisión.** El orquestador no es la última capa: nace en la Capa 1 como un bucle de texto de
unas veinte líneas y crece con cada capa nueva.

**Por qué.** Construir cinco componentes aislados, cada uno validado en su propio script de
prueba, y unirlos al final es el camino corto al infierno de integración: los problemas de
concurrencia, los formatos de audio incompatibles y la latencia acumulada solo aparecen al
juntarlo todo, que es el peor momento para depurarlos. Integrando en cada capa, siempre hay
algo funcionando de extremo a extremo.

---

## Decisiones pendientes

- **Capa 0 de contratos.** Si se definen interfaces abstractas (`LLMEngine`, `STTEngine`,
  `TTSEngine`) antes de implementar, o se escriben clases concretas directamente. Afecta al
  coste de sustituir cualquier pieza más adelante.
- **Open Interpreter (Capa 4).** Si se adopta como estaba previsto o se construye una capa
  propia de *tool calling*. A verificar su estado de mantenimiento al llegar a esa capa.

---

## D-007 — Capa 1 validada: la GPU se usa de verdad

**Medición en caliente, con `gemma4:12b` cargado:**

| Medida | Valor |
|---|---|
| VRAM antes de cargar | 2.323 MiB |
| VRAM después | 10.298 MiB |
| Consumido por el modelo | ~7,8 GB |
| `ollama ps` → PROCESSOR | **100% GPU** |

El incremento de VRAM coincide con el tamaño del modelo y no hay ni una capa en CPU. Queda
descartado el fallo silencioso (Ollama funcionando sobre CPU, unas veinte veces más lento).

---

## D-008 — Usar `/api/chat`, nunca `/api/generate`

**Síntoma.** `/api/generate` con `gemma4:12b` agotaba el límite de tokens devolviendo una
respuesta **vacía** (`done_reason: length`, 250 tokens generados, 0 caracteres de texto).

**Causa.** `/api/generate` recibe un prompt en crudo; `/api/chat` recibe mensajes con roles y
aplica la plantilla de conversación propia del modelo.

**Decisión.** Todo el cerebro habla con `/api/chat`. Además es el único endpoint que soporta
historial de conversación y *tool calling*, ambos necesarios más adelante.

---

## D-009 — Modelo elegido: `gemma4:12b`

**Benchmark en caliente** (ambos modelos residentes, mismo prompt en español):

| Modelo | Velocidad | Respuesta completa |
|---|---|---|
| gemma4:12b | 46,2 tok/s | 1,35 s |
| qwen3:8b | 71,2 tok/s | 1,02 s |

**Decisión.** `gemma4:12b`, pese a ser un 54% más lento.

**Por qué la velocidad no decide.** El habla consume 3-5 tokens por segundo de audio. A 46 tok/s
el modelo genera texto diez veces más rápido de lo que el TTS puede pronunciarlo: la voz nunca
espera. Superado ese umbral, la velocidad extra es invisible para el usuario y manda la calidad.

**Por qué Gemma en calidad.** Su español suena hablado ("funciona perfecto en zonas sin señal
o en el campo sin que te quedes colgado") frente al registro de manual de Qwen ("No requiere
datos móviles ni conexión constante"). Para algo que se escucha, esa diferencia lo es todo.
Además acepta imágenes, lo que abre vías en la Capa 4.

---

## D-010 — Dos ajustes obligatorios de Ollama

**`keep_alive` permanente.** Por defecto Ollama descarga el modelo de VRAM tras 5 minutos de
inactividad, y recargarlo cuesta **23 segundos** medidos. En un asistente de uso esporádico eso
significa media hora de espera repartida en el día. Se fija `keep_alive: -1`.

**Un solo modelo residente.** Con `gemma4:12b` y `qwen3:8b` cargados a la vez la VRAM llega a
15.349 de 16.311 MiB. No caben dos modelos más Whisper y Kokoro. Se fija
`OLLAMA_MAX_LOADED_MODELS=1`.

---

## D-011 — Linux queda fuera del alcance

**Decisión.** El proyecto es solo Windows. El segundo equipo de trabajo es un portátil Windows.

**Consecuencia.** Decae el argumento de portabilidad que respaldaba la capa de contratos: ya no
hay que escribir dos implementaciones de la Capa 4. El `.gitattributes` con normalización de
finales de línea se mantiene, porque no estorba y protege ante cambios de criterio.

---

## D-012 — Fusión de las dos historias del proyecto

**Contexto.** El proyecto creció en dos sitios sin remoto común: el sobremesa documentaba las
decisiones (4 commits) mientras el portátil construía el código (13 commits). Ninguna máquina
podía ver el trabajo de la otra, y los 4 commits del sobremesa **existían en un único disco y
sin copia de seguridad**.

**Decisión.** Fusionar con `--allow-unrelated-histories`, no rebasar, para conservar intactas
ambas historias. Resultado: 18 commits, subidos a `github.com/ByRex492/doombot`.

**Los tres conflictos** se dieron por coincidir el mismo fichero en ambas raíces:

| Fichero | Resolución |
|---|---|
| `README.md` | El del portátil: describe el proyecto que existe hoy. El del sobremesa era el plan por capas anterior al código, y su contenido único ya estaba duplicado en `notion-PROYECTO-DOOM.md` y en D-007 |
| `.gitattributes` | Base del portátil **+ recuperada** `*.sh text eol=lf` |
| `.gitignore` | Base del portátil **+ recuperadas** `*.pt`, `*.bin`, `*.mp3` |

Las versiones del portátil eran más completas —escritas ya con el código delante— pero habían
perdido cuatro reglas presentes en el sobremesa. Se recuperaron en vez de elegir un lado entero.

**Lección.** Crear el remoto es el primer paso al trabajar desde dos equipos, no el último.
`docs/migracion.md` lo señalaba como Fase 0 y quedó sin hacer; el coste fue una jornada entera
con la única copia del registro de decisiones en un solo disco.

---

## D-013 — Cerrado el riesgo de Blackwell en la capa de audio

**Contexto.** D-003 dejó abierto el único riesgo técnico serio del proyecto: la GPU es
Blackwell (sm_120), demasiado reciente, y estaba verificada para Ollama pero **no para
CTranslate2**, el motor sobre el que corre `faster-whisper`. El plan B era `whisper.cpp`.

**Medido en esta máquina** con `ctranslate2` 4.8.1:

    CUDA device count: 1
    Tipos soportados: float16, bfloat16, int8_float16, int8, int8_float32, float32

**Conclusión.** CTranslate2 ve la GPU y ofrece `float16`, que es justo lo que pide el perfil
`workstation` (`voz small cuda/float16`). **No hace falta el plan B.** La confirmación
definitiva llegará al transcribir audio real, pero la señal no deja lugar a dudas.

**Queda pendiente** explicar dos observaciones del portátil que ahora cambian de sentido: la
mala transcripción de términos técnicos ("Python" → "país AN") y el RTF oscilando entre 0,28 y
0,59. Con la GPU descartada como causa en este equipo, habrá que medirlas aquí de nuevo.
