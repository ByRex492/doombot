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

---

## D-014 — Adoptar un estándar de *skills* en la capa de acciones, no inventar uno

**Origen.** Revisión de [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) (Stanford Hazy
Research, Apache 2.0, 9k estrellas, activo a 27/08/2026).

**Decisión, para cuando se aborde la capa de acciones.** Cuando D.O.O.M tenga que ejecutar
herramientas, adoptar el estándar abierto **agentskills.io** en lugar de diseñar un formato
propio de definición de herramientas.

**Por qué.** Un formato propio obliga a escribir cada herramienta desde cero. El estándar da
acceso a catálogos existentes (~150 skills de Hermes Agent, ~13.700 comunitarias de OpenClaw)
y hace que lo que se escriba aquí sirva fuera. El coste de adoptarlo es el mismo que el de
inventarlo; el beneficio, no.

**Lo que NO se adopta de OpenJarvis.** Su framework de agentes, su empaquetado Tauri y su
estructura de proyecto. Son buenas soluciones a un problema mayor que el nuestro, y sustituir
nuestro código por el suyo destruiría el propósito del proyecto: construirlo entendiendo cada
pieza. La licencia Apache 2.0 permite reutilizar código concreto con atribución si conviene.

**Segunda idea que sí merece copiarse:** sus tres modos de ejecución —bajo demanda, programado
y continuo—. Un asistente que solo reacciona es un chat; los otros dos modos son lo que lo
convierten en asistente. Es barato preverlo en el orquestador y caro añadirlo después.

---

## D-015 — Registro de actividad y memoria semántica son dos cosas distintas

**Contexto.** Objetivo planteado: que D.O.O.M aprenda del uso real del ordenador —qué tareas se
hacen, cómo se comporta uno con el equipo—.

**Aclaración necesaria: "aprender" aquí no es reentrenar.** Ajustar un modelo con datos
personales (*fine-tuning*) es caro, lento y suele rendir **peor** que registrar, resumir y
recuperar como contexto. El módulo `memory/` ya es esa alternativa: la base está construida.

**El choque que obliga a decidir.** La memoria tiene un techo medido de **~1.500 recuerdos por
latencia** (ver el diagnóstico de la memoria). Registrar actividad del equipo —ventana activa,
aplicaciones, ficheros— produce **cientos de eventos diarios**: ese techo se agota en dos
semanas.

**Decisión.** Cuando se implemente, serán **dos almacenes separados**:

| | Registro de actividad | Memoria semántica |
|---|---|---|
| Volumen | Alto, cientos/día | Bajo, curado |
| Contenido | Eventos en bruto | Hechos y patrones |
| Acceso | Agregación por lotes | Búsqueda por significado |
| Retención | Ventana corta, se poda | Persistente |

Un proceso periódico agrega lo primero en lo segundo. Un evento en bruto no es un recuerdo;
*"suele programar por las tardes y usa VSCode con Python"* sí lo es.

**Privacidad.** Un registro así sería el fichero más sensible del equipo. Que sea local no basta:
hay que decidir de antemano qué se registra, qué nunca, y si se cifra en reposo.

---

## D-016 — El HUD es una aplicación de escritorio, aunque por dentro dibuje HTML

**Aclaración, no cambio de rumbo.** "Que no se ejecute en un HTML" y "que sea una aplicación
local" no están reñidos. `pywebview` y Tauri producen un ejecutable de escritorio con su propia
ventana, su icono y sin navegador a la vista; el HTML es solo la técnica de dibujado interna,
igual que en VSCode, Discord o Spotify.

**Por qué se mantiene.** Renunciar al HTML significa dibujar el HUD en Qt o similar, donde el
resplandor, el desenfoque y las partículas cuestan diez veces más trabajo. Lo que se descarta
es abrir una pestaña del navegador, no la tecnología de renderizado.

---

## D-017 — La capa de acciones delega en Claude Code, no en un ejecutor propio

**Contexto.** D-014 decidió el estándar para cuando D.O.O.M tuviera que ejecutar herramientas
(`agentskills.io`), pero dejó abierto *quién* las ejecuta. Escribir un ejecutor de tool-calling
propio —parsear la respuesta del modelo, mapear a funciones, gestionar el bucle de turnos— es
exactamente el tipo de infraestructura que ya existe, madura, en el propio Claude Code.

**Decisión.** `actions/claude_code.py` invoca `claude -p <tarea>` en modo no interactivo
("print"), pensado para automatización, en vez de una sesión interactiva. D.O.O.M no ejecuta
herramientas: le pide a Claude Code que las ejecute, y se queda con el resultado.

**Por qué.** El propio agente que construye este proyecto ya sabe editar ficheros, ejecutar
comandos y razonar sobre código con más profundidad de la que D.O.O.M necesitaría reinventar. La
alternativa —Open Interpreter, considerado y descartado en D-014, o un bucle de tool-calling
propio— duplica trabajo que no aporta nada distinto.

**El riesgo real: una orden de voz mal reconocida ejecutando código sin que nadie lo pidiera de
verdad.** Por eso el modo por defecto es `plan`: el agente propone lo que haría sin tocar nada.
Pasar a un modo que ejecuta (`acceptEdits`, `bypassPermissions`) es una decisión que toma quien
instala D.O.O.M, en `DOOMBOT_AGENT_PERMISSION_MODE` de su `.env` —nunca el valor de fábrica—.

**Verificado, no supuesto.** Los flags (`-p`, `--output-format json`, `--permission-mode`,
`--allowedTools`) y la forma del JSON de salida (`result`, `is_error`, `session_id`,
`duration_ms`, `total_cost_usd`) se comprobaron contra el binario real (`claude --help` y una
invocación de prueba), no se copiaron de memoria.

**Pendiente.** Probar el modo `acceptEdits` de verdad, con una tarea real, en el sobremesa. Y
decidir si `phrases.act` debería exigir una confirmación hablada extra antes de delegar, una vez
exista la capa de voz completa —hoy solo se prueba por texto—.

---

## D-018 — Las librerías CUDA de Whisper se instalan por pip, y hay que ponerlas en el PATH

**Contexto.** D-013 dejó verificado que CTranslate2 ve la GPU y ofrece `float16`. Pero al
transcribir audio real fallaba con:

    Library cublas64_12.dll is not found or cannot be loaded

**Causa.** CTranslate2 no empaqueta cuBLAS ni cuDNN: las pide al sistema por nombre. Este equipo
no tiene el CUDA Toolkit instalado, y Ollama —que sí funciona— trae su propio runtime dentro,
así que el problema no se veía en la capa del LLM.

**Decisión.** Instalarlas por pip como extra separado `voice-cuda`, no meterlas en `voice`.
Un equipo sin GPU NVIDIA transcribe en CPU y no tiene por qué descargar 1,3 GB. Se descarta el
CUDA Toolkit completo: son varios GB, es una instalación de sistema y lo que hace falta son
tres librerías.

**Lo que costó averiguar, porque el mensaje de error confunde dos fallos distintos:**

1. `os.add_dll_directory()` **no basta**. pip las deja en `site-packages/nvidia/*/bin`, un sitio
   donde Windows no mira. Registrar los tres directorios dejaba el error idéntico: CTranslate2
   resuelve la DLL por una vía que no consulta esa lista. Modificar `PATH` sí funciona.
2. Con el `PATH` puesto **seguía fallando** hasta instalar `nvidia-cuda-runtime-cu12`. cuBLAS
   se encontraba pero no cargaba, por una dependencia suya que faltaba. Era la segunda mitad
   del mensaje —"or cannot be loaded"—, que es fácil de pasar por alto.

Un detalle más, del primer intento: `os.add_dll_directory()` devuelve un gestor de contexto que
**retira el directorio al recolectarse**. Descartar el valor devuelto deja el registro sin
efecto, con un síntoma idéntico a no haberlo hecho nunca. Por eso `whisper.py` guarda los
manejadores en una lista de módulo.

**Medido aquí, con `small` en `cuda/float16`.** Audio de 5,3 s generado con la voz de Windows:

| Llamada | RTF |
|---|---|
| Primera (en frío) | 0,10 |
| En caliente | **0,04** (0,21 s) |

Transcribe 25 veces más rápido de lo que se habla. En el portátil el mismo modelo daba entre
0,28 y 0,59, y ahí quedaba la duda de si era la GPU o el throttling; con esta cifra la duda se
cierra por el otro lado. **La Capa 2 deja de estar bloqueada.**

---

## D-019 — Los ficheros entran por un buzón, no dictando una ruta

**El choque.** El objetivo de D.O.O.M es manejarlo sin manos, pero también hay que poder darle
archivos. Y un fichero no se dicta: nadie va a deletrear una ruta completa en voz alta.

**Decisión.** Partir el gesto en dos, y que solo el primero use las manos:

1. Se suelta el fichero en el **buzón** (`paths.inbox_dir()`), una carpeta fuera del repositorio.
   Un arrastrar y soltar, sin hablar.
2. Se le pide de palabra: *"lee lo último que te dejé"* o *"lee el archivo del contrato"*.

**Por qué el buzón está fuera del repositorio.** Ahí acaban documentos del usuario —facturas,
contratos, apuntes— y un `git add -A` distraído los subiría a GitHub. Es la misma razón por la
que la memoria vive en `data_dir()` y no en `PROJECT_ROOT`.

**Resolución por palabras, no por subcadena ni por parecido global.** *"el contrato"* tiene que
encontrar `contrato-alquiler-2026.md`. La subcadena falla por el artículo, y el parecido global
se hunde por la diferencia de longitud (0,42 medido). Se comparan los conjuntos de palabras
significativas, descartando artículos y preposiciones; el parecido difuso queda como segunda
vía, para erratas y para lo que Whisper oiga mal. Una ruta literal que existe gana a las dos:
escribir una ruta exacta nunca debe acabar abriendo otro fichero.

**Se recorta a 12.000 caracteres**, aproximadamente la mitad del contexto de `workstation`
(`num_ctx=8192`). Pasarse del contexto no da error: da una respuesta que ignora medio fichero
sin avisar. El recorte viaja declarado en el objeto y se anuncia por pantalla.

**Solo texto plano, código y datos tabulares.** La lista de extensiones es explícita en vez de
"inténtalo y ve qué pasa": un `.docx` o un `.xlsx` son ZIP por dentro, se leen sin lanzar
ningún error y producen caracteres ilegibles que el modelo intentaría interpretar. PDF y
ofimática quedan pendientes; requieren una dependencia y son una decisión aparte.

**El contenido va delimitado y con un aviso de no obedecerlo.** El fichero es material de
consulta. Sin la advertencia, un fichero que contenga algo con forma de instrucción se la lleva
el modelo por delante y responde *al* fichero en vez de *sobre* él.

**Descartado.** Que la orden aceptara solo rutas literales: funciona escribiendo y es inservible
hablando, justo al revés de lo que necesita el proyecto.

---

## D-020 — Cada capa declara sus órdenes; `chat.py` deja de ser el cuello de botella

**Contexto.** El proyecto va a desarrollarse con **varias sesiones de Claude trabajando en capas
distintas a la vez**, cada una en su rama. Eso convierte un problema de estilo en uno estructural.

**El problema.** `chat.py` tenía siete bloques `if orden.command == ...` encadenados en una
función de 293 líneas marcada con `# noqa: C901`. Toda capa nueva pasaba por ahí. Con una
persona es una molestia; con cinco ramas tocando las mismas veinte líneas es un conflicto de
fusión garantizado en cada una, y ninguno resoluble automáticamente porque git no sabe en qué
orden van los bloques.

**Decisión.** Un registro (`orders/`). Cada capa escribe `su_paquete/orders.py`, decora sus
manejadores con `@orden("nombre")`, y no toca nada compartido. El punto de colisión pasa a ser
un punto de extensión.

**Descubrimiento en vez de lista escrita.** `cargar()` recorre los subpaquetes de `doombot` e
importa el `orders` de los que lo tengan. Se descartó una lista explícita de módulos: sería otro
fichero común que toda capa nueva tendría que editar, y volvería el mismo problema con otro
nombre. El precio es un `pkgutil.iter_modules`, que se paga una vez.

**La `Sesion` reemplaza a las variables del bucle.** `ultimo_guardado` y `ultima_respuesta` eran
locales de `run()`, y varias órdenes las comparten —"olvida eso" necesita saber qué guardó
"recuerda que"—. Sacarlas a un objeto mutable es lo que permite que los manejadores vivan fuera
del bucle. `responder`, `con_contexto` y `preguntar` se **inyectan**: un manejador no debe
depender de que la salida sea una consola, y cuando exista la voz cambia la `Sesion` y no los
manejadores.

**Dos fallos que ahora se detectan solos, con test cada uno:**

- **Manejador huérfano.** Registrar una orden que el matcher no puede producir es código muerto
  y silencioso. Es un error fácil trabajando en paralelo: se decide un nombre en una rama y otro
  en la otra.
- **Dos capas reclamando la misma orden.** Sin comprobarlo ganaría la última importada, y el
  orden de importación depende del recorrido de `pkgutil`: el síntoma cambiaría de un equipo a
  otro. Ahora revienta al arrancar, con el nombre de las dos.

**Lo que no cambia.** Una orden definida sin manejador —`stop`, `silence`, `speak`, `repeat`—
sigue respondiendo *"entendido, pero aún no puedo hacerlo"*. `despachar` devuelve `False` y quien
llama decide. Sigue siendo una mentira a medias que se resolverá con la Capa 5, pero al menos
está localizada en un sitio.

**Verificado** recorriendo `remember`, `recall`, `forget`, `read_file` y `stop` contra Ollama
real: comportamiento idéntico al anterior.

---

## D-021 — El sintetizador: kokoro-onnx en CPU, fp32, con troceo por frase propio

**Decisión.** `kokoro-onnx` (ONNX Runtime) en vez del paquete `kokoro` (PyTorch), corriendo en
CPU con el modelo en **fp32**, no en las variantes cuantizadas. `KokoroSynthesizer`
(`src/doombot/tts/synth.py`) cumple `SpeechSynthesizer` sin heredar de él.

**Por qué kokoro-onnx y no PyTorch.** El proyecto ya carga `onnxruntime` por Whisper (D-018);
añadir `torch` entero para un modelo de 82M de parámetros es peso que no compensa. Sin
dependencia nueva de fondo, solo `kokoro-onnx` (que a su vez trae `onnxruntime`, `phonemizer` y
`espeakng-loader` —éste último empaqueta el propio `espeak-ng` para Windows, así que el binario
instalado por `winget` durante la sesión quedó de refuerzo, no hizo falta en la práctica—).

**fp32 gana a fp16 e int8 en CPU, medido, y es contraintuitivo.** Se esperaba que los cuantizados
fueran más rápidos por pesar menos en disco. Al revés:

| Modelo | RTF (frase corta) | RTF (párrafo largo) |
|---|---|---|
| fp32 (326 MB) | 0,44–0,56 | 0,44 |
| fp16 (164 MB) | 0,77–0,94 | — |
| int8 (114 MB) | 4,26–4,35 | 3,59 |

**Causa.** Este Ryzen 7 5800X (Zen 3) no acelera fp16 de forma nativa —se convierte en el propio
cálculo, coste que fp32 no paga— y el int8 de ONNX Runtime cae en kernels de referencia sin
optimizar para esta CPU en vez de las rutas VNNI que sí tendría un Intel reciente. "Más pequeño"
aquí no significaba "más rápido"; sin medir se habría enviado el int8 por ser el fichero más
liviano, y habría sido cuatro veces más lento que el que se descartó por pesar más.

**GPU descartada, y no por falta de VRAM.** `onnxruntime-gpu` 1.29 pide `cublasLt64_13.dll`
(CUDA 13 / cuDNN 9, la pareja que corresponde a esta Blackwell sm_120 — ver D-003, D-013).
A diferencia de D-018, aquí no hay wheel real: `nvidia-cublas-cu13` en PyPI es un paquete
placeholder en `0.0.1`, no la librería. Instalar el CUDA Toolkit completo para esto es la misma
opción que D-018 ya descartó por desproporcionada. `KokoroSynthesizer.from_models_dir` fuerza
`providers=["CPUExecutionProvider"]` explícitamente: dejar que kokoro-onnx probara Tensor
RT y CUDA primero solo añadía un "EP Error" ruidoso en cada arranque antes de caer en CPU igual.
No hace falta la GPU: en CPU ya va cómodamente por debajo de tiempo real, y así queda libre para
`gemma4:12b`.

**El troceo de `kokoro-onnx` no sirve para lo que `stream()` promete, así que se trocea aparte.**
Su streaming interno reparte por lotes de hasta 510 fonemas, no por frase. Medido: un párrafo
típico de D.O.O.M. de cuatro frases cabe entero en un solo lote, y `create_stream` no entrega
nada hasta tener el párrafo completo —el mismo tiempo que `say`, sin ningún beneficio—.
`KokoroSynthesizer.stream()` trocea por frase (`_frases`, con cuidado de no partir "D.O.O.M."
por sus puntos internos) y sintetiza la frase siguiente en un hilo mientras entrega la actual.
Medido sobre el mismo párrafo:

| | TTFA | Total |
|---|---|---|
| `say()` (todo de una vez) | 4,23 s | 4,23 s |
| `stream()` (por frase) | **0,40 s** | 4,25 s |

Diez veces menos espera hasta el primer sonido, por el mismo coste total: es la diferencia entre
que D.O.O.M. empiece a hablar casi al momento o que se quede en silencio cuatro segundos.

**Latencia de una frase corta** (la respuesta típica, "breve y directa" por `identity.py`):
≈1,0 s en español, ≈1,4 s en inglés, en caliente. Probado también variar `intra_op_num_threads`
de la sesión de ONNX Runtime (4/8/16 frente al automático): la diferencia fue marginal (~7%),
así que se deja la configuración por defecto en vez de añadir un parámetro que no compensa lo
que complica.

**Cadencia y pausas: parámetros nativos de Kokoro, no un estirado de audio a posteriori.**
`speed=0.85` (un 15% más lento que el 1.0 de fábrica, sin sonar arrastrado) y
`sentence_pause=0.4` / `clause_pause=0.15` (fábrica: 0,25 / 0,10). Kokoro ya calcula la duración
de cada fonema antes de vocalizar, así que ralentizar por este camino no introduce los artefactos
de un *time-stretch* posterior.

**Post-procesado (`tts/dsp.py`), deliberadamente sutil.** Pasa-altos Butterworth de fase cero a
150 Hz (por debajo de cualquier fundamental de voz, incluida una grave masculina) para el corte
de graves, y una cola de reverberación sintética —ruido con envolvente exponencial, RT60 0,3 s,
mezclada solo al 15%— para la sala pequeña. Los dos con `scipy`, ya presente por Whisper: sin
dependencia nueva. Mezcla baja a propósito: esto es la voz de un asistente que hay que entender a
la primera, no un efecto de producción.

**Voces.** El español solo tiene tres voces en el catálogo de Kokoro frente a veinte del inglés
—la falta de material de entrenamiento que ya anticipaba el encargo—. `ef_dora` (única femenina)
queda por defecto, `em_alex` como alternativa masculina, a falta de que el usuario confirme de
oído; `af_heart` para inglés. Ver la nota de sesión para el resultado de esa escucha.

**Los ficheros del modelo no se instalan por pip.** A diferencia de Whisper (`faster_whisper`) o
los embeddings (`fastembed`), que descargan solos, `kokoro-onnx` solo falla con la URL en el
mensaje si faltan. `tts/download.py` (`asegurar_modelos`) los trae la primera vez —354 MB,
`kokoro-v1.0.onnx` + `voices-v1.0.bin`— a `paths.models_dir() / "kokoro"`, y no toca los
cuantizados: no se usan, no se descargan.

**Pendiente para `main` (ver la nota de sesión):** `_ESCALA_NIVEL` en `backends/base.py`
—medida, no adivinada—; el extra `voice-tts` en `pyproject.toml`; e `identity.py`, que hoy solo
comprueba el paquete `voice` para la capacidad de hablar y no ve `tts/`.

---

## D-022 — El HUD habla con el orquestador por WebSocket, con JSON de una línea por evento

**Contexto.** El prototipo (`ui/prototipo/hud.html`) fijó el contrato `window.DOOM` —
`setState`, `amplitude`, `caption`, `reset`— pero pilotado a mano desde el propio JavaScript
(banco de pruebas) o por `evaluate_js` de pywebview. Empujar amplitud a 60 Hz con
`evaluate_js` es una llamada **síncrona** por muestra desde Python hacia el motor JS: en el
hilo de audio del orquestador eso es bloqueo donde menos se puede permitir.

**Decisión.** Un servidor WebSocket en `127.0.0.1:8765`, que abre el orquestador y al que se
conecta el HUD como cliente. Cada mensaje es una línea JSON con un campo `type`, y cada `type`
es literalmente una llamada al contrato ya fijado — no hay traducción intermedia:

```json
{"type": "state",     "value": "escuchando"}
{"type": "amplitude", "value": 0.63}
{"type": "caption",   "value": "texto"}
{"type": "reset"}
```

| `type` | Cuándo se manda | Frecuencia |
|---|---|---|
| `state` | al cambiar de estado (`dormido`\|`escuchando`\|`pensando`\|`hablando`\|`error`) | por evento |
| `amplitude` | mientras hay audio sonando (mic o TTS) | 30-60 Hz |
| `caption` | al cambiar el subtítulo (`value: null` para borrarlo) | por evento |
| `reset` | al reconectar o para forzar `dormido` con el subtítulo vacío | por evento |

**Por qué esta forma y no otra.** El mapeo 1:1 con `window.DOOM` es deliberado: el HUD no
interpreta nada, solo despacha `type` → método. Así el contrato de comportamiento sigue
viviendo en un solo sitio (el prototipo), y el transporte no añade una segunda fuente de
verdad sobre qué significa cada mensaje.

**Por qué el HUD es cliente y no servidor.** El orquestador es el proceso de larga vida que ya
existe sin interfaz gráfica (`chat.py`); el HUD es la pieza que puede no estar (se puede correr
D.O.O.M sin ventana). Que el HUD sea cliente significa que se puede cerrar y reabrir la ventana
sin reiniciar el orquestador, y que el mismo servidor podría en el futuro atender más de un
cliente (una segunda pantalla, un panel de depuración) sin cambiar nada del lado Python.

**Reconexión sin bloquear.** El cliente (en `hud.html`) reintenta cada 1,5 s si no hay
servidor, y mientras tanto el banco de pruebas sigue disponible — es como se ha desarrollado
todo el estilo, sin esperar al orquestador. En cuanto conecta, sale del banco de pruebas
(oculta el panel, dejan de mandar sus fuentes simuladas) y pasa a `fuente = 'ext'`.

**Verificado con un servidor de prueba**, no solo leído: `ui/mock_servidor.py` (con
`websockets`, no es el definitivo) sirve el mismo contrato y se comprobó en el navegador que
`hud.html` reacciona a los cuatro tipos de mensaje, incluida la reconexión al matar y
levantar el servidor de nuevo.

**Lo que pide a integración**, porque toca ficheros que `capa/hud` no puede editar
(ver nota de sesión): añadir `pywebview` y `websockets` a `pyproject.toml`, y que el
orquestador (`chat.py` o un módulo nuevo suyo) abra el servidor WS con este mismo contrato y
empuje `Audio.level()` (D-021, ya en la escala 0-1 que espera `amplitude`) a 30-60 Hz mientras
suena mic o TTS.

**Resuelto por integración**, en el mismo día: `hud_server.py` abre justo ese servidor desde
`chat.py`, con `websockets` en el extra `hud` de `pyproject.toml` junto a `pywebview`. El nivel
que empuja no es simulado — lo mide `Player` (D-023) bloque a bloque mientras suena la voz
real.

**No resuelto, heredado del encargo.** La transparencia real de ventana en Windows sigue sin
solución: WebView2 no la soporta, y el apaño con `LWA_COLORKEY` da un recorte binario que
destroza el resplandor del anillo. `ui/app.py` (el lanzador de pywebview) va con ventana
opaca sin marco, como ya preveía el encargo. Si aparece algo mejor, es una entrada propia en
este fichero, no una reescritura de esta.

---

## D-023 — Reproducir es de la capa de voz, y va en cola con un hilo por etapa

**Contexto.** D-021 dejó el sintetizador produciendo `Audio` y sin reproducir nada, a
propósito. Faltaba la otra mitad: que suene, que se pueda cortar, y que la interfaz sepa cuánto
está sonando. `voice/player.py` y `voice/speaker.py`.

**Tres etapas en paralelo, cada una en su hilo.** Modelo → frases → audio → altavoz:

```
tokens del LLM  --(hilo del bucle)-->  frases completas
                --(hilo de síntesis)-->  Audio de cada frase
                --(callback de la tarjeta)-->  sonido, 30 ms cada vez
```

Sin el hilo de síntesis, cada frase bloquearía al consumidor del modelo medio segundo y el
chorro de tokens se atascaría justo mientras D.O.O.M habla. Con él, el modelo sigue generando,
Kokoro sintetiza la frase anterior y la tarjeta reproduce la anterior a esa. **Medido: primer
audio a 1,18 s del inicio de la respuesta**, con el chorro del modelo consumido en 0,78 s. Sin
trocear habría que esperar a la respuesta entera.

**El troceo es incremental y retiene las frases cortas.** `_frases` del sintetizador parte un
texto ya completo; aquí el texto llega a pedazos. `partir_incremental` decide en cada pedazo si
hay una frase cerrada. Dos detalles que salieron probando:

- Los puntos internos de "D.O.O.M." no cierran nada porque van pegados a la letra siguiente:
  la condición "seguido de espacio" los descarta sola. Un *lookbehind* para protegerlos, que
  era la primera versión, bloqueaba además el punto final de la sigla y dejaba sin cerrar
  cualquier frase que acabara en mayúscula.
- Una frase corta al final del pedazo se **retiene** en vez de soltarse: "Hola." llega antes
  de saber que detrás viene "¿Qué tal estás?", y sintetizarla sola suena entrecortado y paga
  el coste fijo de Kokoro. Un test comprueba que llegando carácter a carácter salen las mismas
  frases que con el texto entero.

**El *barge-in* es vaciar dos colas.** `Speaker.stop()` descarta las frases pendientes de
sintetizar y `Player.stop()` las muestras pendientes de sonar; el siguiente bloque que pida la
tarjeta sale en silencio. Medido: **cero bloques con sonido tras el `stop`**, y el reproductor
avisa de que se ha quedado callado (`on_idle`), que es lo que pone el HUD en `dormido`. Es el
corte a mano —la orden `para`—; el automático por eco llegará con el micrófono abierto.

**El nivel se mide en el callback de la tarjeta**, bloque a bloque, 30 ms cada uno: 33 avisos
por segundo, dentro de los 30-60 Hz del HUD, y en ventanas lo bastante parecidas a los 50 ms
con los que se midió `_ESCALA_NIVEL` (D-021). Medido con voz real: mediana 0,44, que es la
cifra de D-021 clavada; el p90 llega a 1,0 porque ventanas más cortas son más picudas, y es
aceptable. `Audio.level()` se vectorizó con numpy para no meter un bucle de Python en el hilo de
audio.

**`wait()` cuenta pendientes, no mira dos señales.** La primera versión comprobaba "cola vacía
y el hilo no está sintetizando", y entre sacar de la cola y marcar el hilo ocupado había un
hueco en el que creía que no quedaba nada. Un contador que sube al encolar y baja al terminar
no tiene ese hueco. Lo detectó un test.

**`stop` y `repeat` dejan de ser promesas vacías.** `stop` corta el `Speaker`; `repeat` dice
`Sesion.ultima_respuesta`, que existe desde D-020 —estaba mal clasificada como orden de voz: por
escrito tiene el mismo sentido—. Y `Sesion.decir()` habla además de imprimir, así que las
respuestas fijas de las órdenes ("Apuntado", "Olvidado") también suenan.

**Cedido a `capa/hud`: el transporte.** Se empezó un `bridge/` propio y se descartó al ver que
la sesión de la interfaz ya tenía `hud_server.py` con el mismo contrato, el mismo puerto y
cableado en `chat.py`. Duplicarlo era el error; la `Sesion` apunta al suyo.

---

## D-024 — El bucle manos libres reutiliza la orquestación del modo escrito

**Contexto.** Con la Capa 2 (oír, D-013), el sintetizador (D-021), el reproductor (D-023) y el
transporte al HUD (D-022) ya construidos, faltaba la pieza que los une en lo que el proyecto
persigue desde el principio: hablarle sin manos. `python -m doombot voz`.

**Decisión.** No un bucle de voz nuevo, sino **la misma orquestación que el modo escrito**. Se
extrajo de `chat.py` el núcleo que atiende una frase —`_atender`: reconocer orden y despachar,
o pasar al modelo con el contexto de la memoria— y ahora lo llaman por igual el bucle de teclado
y el de voz. Lo único que cambia entre los dos modos es de dónde entra el texto (`input()` o el
`Listener`) y por dónde sale la respuesta (pantalla o altavoz), y de eso ya se encargaban
`preguntar` y `responder` en la `Sesion`.

**Por qué importa que sea el mismo código y no una copia.** Una orden nueva, un cambio en cómo
se consulta la memoria, un arreglo en el manejo de estados: pasa a valer en los dos modos a la
vez. Dos bucles paralelos se habrían desincronizado al primer cambio —es el mismo error que
D-020 evitó dentro de `chat.py`, ahora entre modos—.

**El motor común (`_arrancar` / `_Motor`).** El montaje —perfil, LLM, memoria, agente, HUD,
voz— también se comparte. El orden es deliberado: el LLM es imprescindible y se comprueba
primero (por eso `voz` se planta con "Ollama no responde" antes de tocar el micrófono); el HUD
y la voz son opcionales y nunca impiden arrancar.

**El turno no se solapa con la respuesta.** Tras atender una frase, el bucle espera a que
D.O.O.M termine de hablar (`speaker.wait`) antes de reabrir el micrófono. Es una decisión
provisional y consciente: sin cancelación de eco, escuchar mientras suena el altavoz haría que
se oyera a sí mismo y se interrumpiera solo. El *barge-in* de verdad —hablarle encima para
cortarlo— necesita AEC (referencia por *loopback* + speexdsp), que es la pieza más frágil que
queda y va aparte.

**Estados al HUD, el turno entero.** Los del `Listener` (escuchando, transcribiendo) y los de
la respuesta (pensando, hablando, dormido) van al mismo `ServidorHUD`, así que el orbe refleja
la interacción completa y no solo la mitad hablada.

**Sin probar con micrófono real.** Las pruebas de micrófono están pospuestas por decisión del
usuario. El bucle está construido, cableado y validado con dobles (`_atender`) y con arranque
en seco; falta la validación con voz de verdad, que es del usuario cuando levante la pausa.

---

## D-025 — `openwakeword.Model` necesita las rutas de los auxiliares a mano, no solo la del wakeword

**Contexto.** Primera prueba con micrófono real (el usuario levantó la pausa de D-024). Fallo
inmediato al decir "hey jarvis":

    [ONNXRuntimeError] : 3 : NO_SUCHFILE : Load model from
    C:\...\.venv\Lib\site-packages\openwakeword\resources\models\melspectrogram.onnx failed

pese a que `wake.py` ya descargaba ese fichero —y los progress bars lo confirmaban al 100%— a
`models_dir()/openwakeword`, fuera del `.venv`, tal y como documenta D-013 y el propio
docstring de `_pesos()`.

**Causa.** Dos sitios distintos, y solo uno de ellos configurable. `Model(wakeword_models=[...])`
acepta la ruta del modelo de la palabra como parámetro, pero `melspectrogram.onnx` y
`embedding_model.onnx` —que openWakeWord necesita siempre, para cualquier palabra— los busca
`AudioFeatures.__init__` en una ruta **fija, relativa al propio paquete instalado**
(`site-packages/openwakeword/resources/models/`) cuando no se le pasa nada. `_pesos()` sí los
descargaba a `carpeta` —`download_models()` trae los auxiliares pase lo que pase, es su propio
comportamiento por defecto—, pero `_load()` nunca le decía a `Model` dónde estaban: la ruta que
mira por defecto se queda vacía siempre, `rm -rf .venv` o no.

**Decisión.** Pasar `melspec_model_path` y `embedding_model_path` explícitos a `Model(...)`,
apuntando a los mismos ficheros que `_pesos()` ya deja en `carpeta`. Son kwargs que `Model`
reenvía tal cual a `AudioFeatures` —revisado en el código de la librería, no adivinado—, así que
no hace falta tocar nada dentro del `.venv` ni duplicar la descarga.

**`_pesos()` pasa a comprobar los tres ficheros, no solo el de la palabra.** Antes, una carpeta
con el wakeword pero sin los auxiliares —por ejemplo, una copia a medias entre equipos— se daba
por buena y el fallo aparecía más tarde, en `_load()`, con un error de onnxruntime mucho menos
claro que el que puede dar `_pesos()` con nombres de fichero de por medio.

**Por qué no se detectó antes.** D-024 lo dejó anotado sin rodeos: "sin probar con micrófono
real". `_load()` tenía un doble inyectable (`loader`) para los tests, y el doble nunca ejercita
la construcción real de `Model` ni sus rutas. El camino feliz —fichero de la palabra presente,
`Model()` sin más argumentos— nunca se había recorrido de verdad hasta esta prueba.

**Verificado**, no solo corregido a ciegas: `WakeWord().model` carga sin excepción contra el
`openwakeword` real instalado, con los tres ficheros ya descargados por el intento anterior. Un
test nuevo (`tests/test_wake.py`) fija el contrato con un doble de `Model` que registra los
kwargs recibidos, para que una regresión futura —alguien que quite las rutas explícitas
"porque ya no hacen falta"— se detecte sin necesitar un micrófono delante.

---

## D-026 — Continuidad de conversación: historial como mensajes, recortado por perfil

**Contexto.** Marcado desde la sesión del 01/09 como "el hueco más grande para el uso por
texto": cada pregunta llegaba al modelo sin saber nada de las anteriores. D-008 ya había fijado
`/api/chat` sobre `/api/generate` precisamente porque es "el único endpoint que soporta
historial de conversación", pero nunca se llegó a mandar ninguno.

**Decisión.** `TextGenerator.generate`/`.stream` ganan un parámetro `historial:
Sequence[Turno] = ()`, con `Turno = dict[str, str]` (`{"role": "user"|"assistant", "content":
texto}`) — el mismo formato que Ollama ya monta en su lista `messages` y que Anthropic usa en
la suya, así que ningún backend traduce nada, solo inserta los turnos entre el sistema y la
pregunta actual (Ollama) o antes de ella (Anthropic, donde el sistema va en su propio campo,
no como mensaje).

`Sesion` (en `orders/registry.py`) guarda el historial completo (`historial: list[dict[str,
str]]`). Se llena en un único sitio, `_responder()` en `chat.py`, con `sesion.entrada` (el texto
crudo, no el que ya lleva pegado el contexto de memoria) y `sesion.ultima_respuesta` — y como
`_responder` es adonde llega cualquier llamada a `sesion.responder(...)`, tanto el turno normal
como el que dispara la orden `recall` quedan en el historial sin que su manejador sepa nada de
esto: es la misma razón por la que D-020 inyecta `responder` en la `Sesion` en primer lugar.

**Por qué no se guarda un turno cuando falla.** Un `BackendError` deja `ultima_respuesta` vacía;
guardarlo de todos modos dejaría un hueco `{"role": "assistant", "content": ""}` en el próximo
historial, y con él una pregunta que el modelo "respondió" con nada.

**El recorte vive en `chat.py`, no en los backends.** `_recortar_historial()` guarda los turnos
más recientes que quepan en una fracción (0,3) del `llm_num_ctx` del perfil activo, a ~4
caracteres por token —la misma clase de aproximación que D-019 usa para el buzón, sin arrastrar
un tokenizador solo para esto—. Que dependa del perfil (D-004) importa: el portátil recorta
antes que el sobremesa sin que nadie tenga que acordarse de ajustarlo a mano. Se guarda el
historial *entero* en la `Sesion` y se recorta solo al construir cada petición, así que nada se
pierde de verdad mientras dure el proceso, aunque el modelo deje de verlo.

**Verificado contra Ollama real**, no solo con dobles: "Me llamo Miguel y mi color favorito es
el azul" en el turno uno, "¿Cómo me llamo y cuál es mi color favorito?" en el dos, con el
historial de por medio → "Te llamas Miguel y tu color es el azul". Sin el parámetro, el modelo
no tiene forma de saberlo.

**Descartado.** Construir el historial dentro del propio `prompt` (concatenar turnos anteriores
como texto plano, al estilo de `_con_contexto` con la memoria) en vez de como mensajes de
verdad. Funcionaría, pero tirar por la vía que ya soporta el endpoint —la razón de ser de
D-008— es gratis y no folclor: el modelo ve la estructura de turnos tal cual la entiende su
propia plantilla de conversación, en vez de un bloque de texto que tiene que reinterpretar.
