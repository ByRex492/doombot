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

---

## D-027 — Barge-in real: cancelación de eco (`pyaec`) + VAD (`webrtcvad`), sin compilar nada

**Contexto.** D-024 dejó pendiente "la pieza más frágil que queda": interrumpir a D.O.O.M
hablándole encima, no solo con la orden `para`. El obstáculo de fondo es acústico, no de
código: con el micrófono abierto mientras suena el altavoz, D.O.O.M se oye a sí mismo y
cualquier detector de voz dispararía con su propio eco, no con el usuario.

**Decisión.** Cancelación de eco (AEC) de verdad, con referencia por *loopback* de software
—lo que `Player` manda de verdad a la tarjeta, no una suposición— y `pyaec` (bindings de
`ctypes` a `aec-rs`, del mismo autor que `kokoro-onnx` y `espeakng-loader`) como filtro
adaptativo. Sobre la señal ya sin eco, `webrtcvad` decide si lo que queda es voz de verdad.

**Por qué estas dos librerías y no otras.** El resto de candidatas obvias —`speexdsp`,
`webrtc-audio-processing`, el propio `webrtcvad` original— piden compilar en Windows, el mismo
problema que D-001 fijó Python 3.12 para evitar: sin wheel, `pip` intenta compilar y falla sin
un compilador instalado. Verificado antes de elegir, no supuesto: `pip download` sobre cada una
mostró qué se instala de verdad en este equipo.

- `pyaec` trae un `aec.dll` precompilado para `win_amd64` dentro del wheel (~180 KB): no hay
  nada que compilar.
- `webrtcvad-wheels` es el mismo `webrtcvad` de siempre —se importa igual, como `webrtcvad`—
  pero publicado con wheels `cp312-win_amd64` reales, a diferencia del paquete original.

**Verificado con una señal sintética antes de tocar nada real.** Un tono conocido como
"referencia", una copia atenuada (0,6x) y retrasada como "eco" mezclada con "voz" real solo en
la segunda mitad: el AEC atenúa el eco puro **~15,6x**, y dos tests (`test_eco.py`) fijan ese
comportamiento contra la librería real, no contra un doble —lo que hay que verificar es si el
algoritmo de verdad cancela, no si un mock hace lo que se le ha dicho—.

**Un eco perfecto (retardo y atenuación cero) es un caso degenerado, no el más fácil.** La
primera versión del test le daba al AEC la misma señal como referencia y como micrófono, sin
retardo: confundía al filtro más que ayudarlo, y disparaba falsos positivos. Un eco acústico
real siempre lleva algo de retardo y pérdida —el trayecto altavoz-aire-micrófono nunca es
instantáneo ni perfecto—; el test se corrigió para simular eso, y ahí sí deja de disparar tras
converger.

**Arquitectura de las piezas.**

```
Player (24 kHz) --on_reference--> ReferenciaEco --remuestrea a 16 kHz--> anillo de 2 s
                                                                              |
Microfono (16 kHz) --bloques de 20 ms--> MonitorBargeIn.procesar() <---------+
                                                |
                                    Aec.cancel_echo()  ->  webrtcvad.is_speech()
                                                |
                              3 bloques seguidos de voz -> Speaker.stop()
```

`ReferenciaEco` vive en su propio hilo: `Player._callback` **no puede bloquear** (lo dice ya su
propio docstring), así que solo encola el bloque en bruto; el remuestreo con `scipy` —más
pesado que una copia— ocurre en un hilo aparte, no en el callback de audio en tiempo real.

**20 ms de bloque, no los 50 ms del resto de la voz.** `webrtcvad` solo admite 10, 20 o 30 ms.
El detector de la palabra de activación sigue con sus 50 ms —no comparten bloque, cada uno abre
su propio flujo del micrófono en su momento—.

**Tres bloques seguidos para disparar, no uno.** Un carraspeo o un resto de eco mal cancelado
en un único bloque de 20 ms no debe cortar a D.O.O.M a media frase. El número es a ojo —medirlo
con barge-in real, hablándole encima de verdad, queda para cuando el usuario lo pruebe con el
micrófono conectado, igual que D-024 y D-025—.

**El alcance es deliberadamente estrecho.** Interrumpir corta el audio (el mismo mecanismo que
la orden `para`) y nada más: no se pone a escuchar automáticamente lo que sigue diciendo el
usuario tras cortar. Para eso hace falta la palabra de activación otra vez, como con cualquier
otro turno. Ampliarlo es una decisión aparte si hace falta, no una que convenga colar aquí.

**Todo opcional en cadena, como el resto de la voz (D-021, D-023, D-024).** Sin `pyaec` o
`webrtcvad-wheels` instalados (extra `voice-aec`), `montar_voz` sigue devolviendo un `Speaker`
que habla; `barge_in` queda en `None` y "para" sigue siendo la única forma de cortar. Nunca
bloquea el arranque, igual que el HUD o la propia síntesis.

**De paso, `numpy` pasa a dependencia base.** Era ya una dependencia de facto desde D-023
—`chat.py` importa `voice.speaker`→`voice.player` sin condición, y ese módulo usa `numpy` sin
comprobarlo—, solo que nadie lo había declarado en `pyproject.toml`. Con `voice/eco.py` sumando
otro import incondicional de la misma cadena, dejarlo sin declarar habría hecho que un
`python -m doombot chat` sin ningún extra de voz instalado fallara al arrancar, con un
`ModuleNotFoundError` que no señala a ninguna dependencia opcional.

**Pendiente, con honestidad.** Todo lo de arriba está verificado con señales sintéticas y con
la librería real, pero no con un micrófono y un altavoz reales en la misma sala —los que hay en
esta máquina ahora mismo no soportan la API de lectura bloqueante que usa `Microphone`
(WDM-KS), y el auricular Bluetooth que sí funcionaba (D-024, D-025) estaba apagado al escribir
esto—. La prueba que de verdad importa —¿hablarle encima corta a D.O.O.M sin que se interrumpa
solo con su propio eco?— la tiene que hacer el usuario, con el micrófono conectado.

---

## D-028 — El micrófono elegido puede ser una instancia muerta, y WASAPI pide su propio ajuste

**Contexto.** Primera prueba de D-027 con el A50 conectado de verdad. Dos fallos en cadena,
ninguno del barge-in en sí:

1. `python -m doombot micro probar` con el dispositivo que `DOOMBOT_AUDIO_INPUT=A50 Mic`
   resolvía solo: **pico 0.000 exacto**, el caso que el propio código ya sabía nombrar
   ("ese dispositivo no entrega señal") pero no evitar.
2. Con el índice de WASAPI a mano (`micro probar 32`): `InputStream` fallaba con
   `Invalid sample rate`, aunque WASAPI "suele aceptar más formatos" según el mensaje de error
   que el propio código ya daba.

**Causa 1: reconectar un USB/Bluetooth crea instancias nuevas, no reutiliza la vieja.** Windows
había registrado "A50 Mic", "2- A50 Mic" y "3- A50 Mic" como dispositivos separados de
conexiones distintas, las tres con el mismo nombre visible. `_resolve()` se quedaba con la
**primera** que encajara por nombre, bajo el supuesto —escrito en el propio comentario, y
erróneo— de que la primera es "la de la API por defecto del sistema". Medido: la primera era
DirectSound, y esa instancia concreta abría sin ningún error pero no entregaba ni una muestra.

**Decisión 1.** Cuando varias candidatas comparten nombre, gana la que hable WASAPI si hay
alguna. No por dogma —"WASAPI es mejor"—, sino porque además es la única con la que
`_wasapi_auto_convert` (más abajo) puede arreglar el problema 2, y en la práctica fue la única
de las tres que entregó audio real.

**Causa 2: WASAPI en modo compartido solo admite el formato nativo del dispositivo**, casi
nunca los 16 kHz que este módulo pide siempre (Whisper y openWakeWord, D-005, D-013). Sin
avisar de qué falta, `InputStream` simplemente rechaza la tasa.

**Decisión 2.** `extra_settings=sd.WasapiSettings(auto_convert=True)` cuando el dispositivo
resuelto es WASAPI. Verificado contra el A50 real: sin el ajuste, `Invalid sample rate`; con
él, el flujo abre y entrega muestras a 16 kHz aunque el dispositivo funcione nativamente a otra
tasa. No afecta a MME ni a DirectSound —no conocen `WasapiSettings`, y pasárselo fallaría—, de
ahí que se compruebe la API antes de construirlo.

**Ninguno de los dos fallos es nuevo de D-027.** Ya existían en `voice/capture.py` desde que se
escribió (D-013 y antes); simplemente nadie había conectado un dispositivo con instancias
duplicadas y una API que exige `auto_convert` a la vez, porque las pruebas de micrófono estaban
pospuestas (D-024) hasta esta sesión.

**Verificado con el hardware real**, no solo con el mensaje de error leído: `Microphone(32)`
abre y lee muestras del A50 por WASAPI; `Microphone("A50 Mic")` resuelve ahora directamente a
ese mismo índice, sin que el usuario tenga que buscarlo a mano. `tests/test_capture.py` fija
las dos decisiones con dobles (una API WASAPI falsa, una lista de candidatos con instancias
repetidas), para que un cambio futuro en `_resolve()` no vuelva a preferir la instancia
equivocada en silencio.

---

## D-029 — Precalentar Ollama al arrancar, no en la primera pregunta

**Contexto.** Sesión de pruebas con voz real: respuestas que unas veces tardaban 1-2 s y otras
9-22 s para el mismo prompt trivial, sin patrón aparente. Se sospechó primero de un modelo
alternativo más rápido.

**Medido antes de tocar nada.** Con la GPU cargada de otras aplicaciones (Steam, Epic, juegos
de fondo), el mismo prompt osciló entre 1,6 s y 16 s. Al día siguiente, con la GPU casi vacía
(14,8 GiB libres de 16,3, 3% de uso) y **sin ningún modelo residente en Ollama**
(`ollama ps` vacío —el servidor lleva un rato sin recibir peticiones—), la primera llamada
tardó **9,4 s** y las cuatro siguientes 1,2-2,6 s. La variación no era el modelo: era si estaba
ya cargado en VRAM o no, agravado por lo que otras aplicaciones dejaran libre en ese momento.

**Decisión.** No cambiar de modelo —D-009 ya midió que por encima de ~5 tok/s la velocidad de
generación es imperceptible en voz, y cualquier modelo pagaría el mismo coste de carga en
frío—. En su lugar, `OllamaGenerator.precalentar()` fuerza esa carga **al arrancar**
(`_arrancar()` en `chat.py`), con un aviso en pantalla ("Cargando el modelo en la GPU...", y
cuánto ha tardado), en vez de dejar que la pague la primera pregunta real, justo cuando el
usuario ya está esperando una respuesta y no sabe si el asistente se ha quedado colgado.

**Por qué un `generate()` de verdad y no un endpoint de "solo cargar".** En Ollama, cargar el
modelo en VRAM y generar son la misma operación: no hay un endpoint aparte que solo cargue sin
generar nada. Un prompt de un carácter (`"."`) paga ese coste con el mínimo de tokens posible.

**Solo para Ollama.** `AnthropicGenerator` no carga ningún modelo local —vive en un servidor
ajeno—, así que `precalentar()` no es parte del contrato `TextGenerator`: es un extra propio de
`OllamaGenerator`, y `_arrancar()` lo detecta con `isinstance`, no con un método que todo
backend tendría que fingir tener.

**Un fallo aquí no bloquea el arranque.** Si `precalentar()` no puede completar, se avisa y se
sigue: fallará igual en la primera pregunta real, y no hay nada que ganar deteniendo el
programa por algo que `gen.is_available()` ya comprobó por encima una línea antes.

**Verificado descargando el modelo a mano** (`keep_alive: 0` contra `/api/generate`) y
comprobando que `_arrancar()` lo recarga solo, con el tiempo real impreso: 9,2 s, antes de que
aparezca el mensaje de "Escribe /ayuda...". Sin esto, esos mismos 9 s los habría pagado la
primera vez que alguien le preguntara algo por voz.

---

## D-030 — n8n: D.O.O.M dispara workflows, nunca al revés

**Contexto.** Idea anotada desde la sesión de Linux del 31/08 y dejada sin decidir a propósito:
n8n corre en ese equipo (`~/n8n`, Docker, puerto 5678) con automatizaciones reales conectadas
—no un entorno de pruebas—, y había dos direcciones posibles: D.O.O.M dispara *workflows* de
n8n, o n8n dispara acciones de D.O.O.M por *webhook*.

**Decisión.** Solo la primera dirección, por ahora. D.O.O.M expone una orden de voz nueva,
`"activa el flujo: <nombre>"` (`phrases/matcher.py`, orden `flow`), que llama a un webhook de
n8n vía `actions/n8n.py` (`N8nClient`). n8n nunca inicia nada en D.O.O.M: no hay servidor HTTP
nuevo escuchando entradas ajenas, solo un cliente que sale.

**Por qué esta dirección y no la otra.** La dirección contraria —n8n disparando acciones de
D.O.O.M— exige que D.O.O.M reaccione a eventos externos sin que nadie lo haya pedido por voz: si
suena por sí solo estando el usuario delante o no, en qué máquina, y qué hace si nadie contesta
son preguntas de producto reales, no solo técnicas, y no estaban respondidas. La dirección
elegida no las plantea: el usuario sigue siendo quien inicia todo, igual que con `act` (D-014).

**El problema real: un webhook no tiene modo `plan`.** El agente de acciones (D-014) tiene un
modo por defecto que propone sin ejecutar, pensado exactamente para esto: una orden de voz mal
reconocida no debe disparar algo real. Un webhook de n8n no tiene ese punto intermedio —en
cuanto llega la petición, el *workflow* corre—, así que la misma salvaguarda no se puede
replicar ahí.

**La salvaguarda es una lista blanca, no la URL construida del nombre dicho.** `N8nClient`
resuelve el nombre hablado contra `DOOMBOT_N8N_WORKFLOWS` (`.env`, pares `nombre:ruta`) y solo
llama al webhook si hay una entrada exacta, tras normalizar igual que el resto de órdenes de voz
(`phrases.matcher.normalize`, D-013 y anteriores: sin tildes, mayúsculas ni puntuación, tolerante
a lo que devuelve Whisper). Construir la URL directamente del nombre dicho —`{base_url}/webhook/
{nombre}`— se descartó: un fallo de reconocimiento podría entonces disparar cualquier webhook
cuyo nombre coincidiera por casualidad, sin que existiera ningún punto donde decir que no.

**Por qué no vive dentro de `claude_code.py`.** Son dos formas de "actuar" con perfiles de
riesgo distintos —una tiene modo `plan`, la otra no puede tenerlo— y mezclarlas en una sola clase
habría ocultado esa diferencia. `actions/n8n.py` es su propio módulo, con su propia orden
(`flow`, separada de `act`) y su propio manejador en `actions/orders.py`; ambos comparten paquete
porque los dos son la capa que toca el mundo real, no porque compartan implementación.

**Verificado sin n8n real delante**, con el mismo criterio que `test_ollama.py`: un cliente HTTP
falso en `tests/test_n8n.py` comprueba la resolución contra la lista blanca, el aviso cuando el
nombre no está en ella, y que no se construye ninguna URL a partir de texto sin verificar.

---

## D-031 — Confirmación hablada antes de una acción real

**Contexto.** D-017 dejó anotado un pendiente: "confirmación hablada extra antes de que 'act'
ejecute de verdad, una vez exista la capa de voz completa". La voz ya está cerrada de punta a
punta (TTS, HUD, barge-in), así que la condición que lo bloqueaba ya no aplica. Con D-030 además
hay una segunda acción real -disparar un *workflow* de n8n- con el mismo problema: nada evita
que una orden de voz mal reconocida la dispare.

**Decisión.** Antes de ejecutar de verdad, se pregunta y se espera una confirmación explícita:

- `act`: solo si `DOOMBOT_AGENT_PERMISSION_MODE` no es `plan`. En `plan` el agente ya propone sin
  tocar nada (D-014); preguntar además sería un paso de más sin nada real que proteger.
- `flow`: siempre. Un webhook de n8n no tiene un modo `plan` equivalente (D-030), así que aquí la
  confirmación **es** la única salvaguarda además de la lista blanca.

Silencio, "no", o cualquier respuesta que no sea una afirmación reconocida (`phrases.es_afirmacion`:
"sí", "confirmo", "adelante", "hazlo"...) cuenta como negativa. Ante la duda de si se entendió
bien la respuesta, no ejecutar es la opción segura -mismo criterio que el umbral de similitud de
la memoria (D-015): preferible no actuar a actuar sobre algo que no se confirmó con claridad-.

**Cómo se pregunta y se escucha, sin repetir la palabra de activación.** `Sesion.preguntar` ya
existía como costura -la usa `read_file` para "¿qué quieres saber de él?"-, pero en voz estaba
fijada a `input()`, que bloquea el hilo esperando teclado y no tiene sentido en manos libres. En
modo voz (`chat.py: run_voz`), `preguntar` pasa a ser un cierre que dice la pregunta con el
`Speaker` ya montado y graba con `Microphone.record_until_silence()` -el mismo micrófono y el
mismo `WhisperTranscriber` del `Listener`, no una segunda instancia-, sin pasar por el detector de
palabra de activación: seguir en el mismo turno de conversación es lo que permite responder
"confirmo" sin decir "DOOM" otra vez. El modo escrito sigue usando `input()` sin cambios.

**Por qué una intersección de conjuntos y no el mismo aparato de erratas que `PhraseMatcher`.**
Una respuesta de confirmación es una o dos palabras, no una frase larga con margen para que el
parecido difuso aporte algo; comparar contra un conjunto fijo de afirmaciones normalizadas
(`es_afirmacion`) es suficiente y no arrastra el umbral de erratas (D-013) a un sitio donde no
hace falta.

**Verificado con dobles**, sin agente ni n8n real: `tests/test_actions_orders.py` comprueba que
`plan` no pregunta, que un modo que ejecuta sí y respeta la respuesta, que `flow` pregunta
siempre, y que negarse o no configurar nada deja la acción real sin lanzarse -en ningún caso se
llama al agente ni a n8n-. `tests/test_phrases.py` cubre `es_afirmacion` aparte, incluida la
palabra suelta frente al fragmento dentro de otra ("así" no es "sí").

---

## D-032 — Enrutador Ollama↔Claude: manual primero, automático sin decidir todavía

**Contexto.** Idea anotada desde el 31/08 junto a la de n8n, y en el mismo estado: "los criterios
de cuándo escalar a Claude son una decisión de producto, no algo que debiera decidir yo solo"
-la sesión que lo escribió lo dijo de sí misma, y sigue siendo cierto ahora: quien construye esta
sesión es la misma Claude a la que enrutaría, y decidir sola cuándo merece la pena invocarse a sí
misma es exactamente el conflicto de interés que esa nota ya evitaba-.

**Decisión.** Ningún criterio automático todavía. En su lugar, una orden de voz manual: "pregunta
a Claude: `<algo>`" (`ask_claude`, `backends/orders.py`) manda esa pregunta puntual a
`AnthropicGenerator` en vez de al backend configurado en `DOOMBOT_LLM_BACKEND`, sin cambiar cuál
es el backend por defecto para el resto de la conversación.

**Por qué no se inventan criterios ahora.** Longitud del mensaje, palabras clave, complejidad
percibida... cualquiera de esos heurísticos se puede escribir, pero ninguno sale de una necesidad
medida -a diferencia de, por ejemplo, D-029 (el precalentado de Ollama), que sí vino de tiempos
reales observados-. Construir el automatismo sin ese dato sería fijar una decisión de producto
sobre una suposición, exactamente lo que la nota original quería evitar. La orden manual deja
resuelto lo que sí se puede resolver hoy sin adivinar nada: que el usuario pueda pedir a Claude
cuando él -no un heurístico- decide que le importa más la calidad de razonamiento que la latencia
o el coste.

**Por qué presta el generador en vez de escribir un camino de respuesta aparte.** `_responder()`
en `chat.py` ya sabe generar en streaming, hablar si hay voz (`Speaker.speak_stream`), e ir
guardando el turno en `sesion.historial`; reescribir eso para un segundo backend habría duplicado
esa lógica con el riesgo de que diverja con el tiempo. En su lugar, la orden cambia
`sesion.gen` por un `AnthropicGenerator.from_config()` recién construido, llama a
`sesion.responder()` -que usa `sesion.gen` internamente, sea cual sea- dentro de un `try`, y lo
devuelve al backend original en el `finally`, pase lo que pase. El turno queda en el historial
igual que cualquier otro; lo único que cambió fue quién lo generó.

**Sin clave de Anthropic configurada, el aviso ya existe y no hay que duplicarlo.**
`AnthropicGenerator.stream()` ya comprueba `DOOMBOT_ANTHROPIC_API_KEY` y lanza `BackendError` si
falta (ver `backends/anthropic.py`), y `_responder()` ya sabe mostrar ese error sin propagarlo ni
guardar un turno vacío en el historial. Repetir esa comprobación en `backends/orders.py` habría
sido el mismo mensaje escrito dos veces.

**Verificado con dobles**: `tests/test_ask_claude_order.py` comprueba que se presta un
`AnthropicGenerator` de verdad durante el turno, que el backend original vuelve después -incluso
si `responder()` falla a medias-, y que sin argumento no se toca nada.

---

## D-033 — Agente local con bucle propio: cerebro intercambiable, autónomo salvo en lo irreversible

**Contexto.** Se pidió un agente "como Claude": recibir órdenes escritas -de momento, no voz- y
cumplirlas solo, contando lo que hace y qué aplicaciones abre, con acceso a todo el equipo:
aplicaciones, navegadores, y un navegador que controle por dentro. Lo que había era
`actions/claude_code.py`, que delega en `claude -p`: sirve para tareas de código en un
repositorio, pero no abre aplicaciones ni maneja un navegador, depende de la nube y cuesta
dinero por uso, en contra del "coste económico: ninguno" de `capa4-investigacion.md`.

**Decisión.** Un paquete nuevo, `agent/`, con un bucle propio (pensar → herramienta → observar)
y cuatro familias de herramientas: ficheros, comandos, aplicaciones instaladas y navegador. Tres
elecciones las tomó el usuario explícitamente, el 13/10/2026:

1. **Cerebro intercambiable.** El bucle habla con un `ToolCaller` nuevo de `backends/base.py`
   con tipos neutros (`EspecHerramienta`, `LlamadaHerramienta`, `PasoModelo`,
   `ResultadoHerramienta`); `OllamaGenerator` y `AnthropicGenerator` lo cumplen con un método
   `paso()` cada uno, traduciendo a su formato -Ollama con rol `tool`, Anthropic con bloques
   `tool_use`/`tool_result`-. `DOOMBOT_AGENT_BRAIN` elige, separado de `DOOMBOT_LLM_BACKEND`:
   se puede conversar con Ollama y dejar que actúe Claude. Es el mismo patrón que D-032 aplicó a
   `TextGenerator`.
2. **Autónomo, confirma lo irreversible.** Abrir apps, navegar, leer y buscar van solos;
   sobrescribir, cerrar una app, ejecutar un comando que no sea de solo lectura, enviar un
   formulario o pulsar algo tipo comprar/enviar/aceptar, se preguntan. Es D-031 llevado de
   "antes de toda acción" a "antes de lo que no se deshace", que es lo que hace usable un agente.
3. **Navegador propio, aparte del del usuario.** Chromium por Playwright (extra `agent-web`) con
   perfil en `data_dir()/navegador-agente`, con ventana para que se vea lo que hace. No tiene las
   sesiones ni las contraseñas del usuario. Para enseñarle una página al usuario se usa su
   navegador normal (`webbrowser`), donde el agente no lee nada.

**Las salvaguardas viven en el bucle, no en las herramientas.** Lista blanca (lo que no está en
el catálogo devuelve un error al modelo), confirmación, límite de 20 pasos, salidas truncadas
(cabeza y cola con nota de continuación) y resultados viejos enmascarados en lo que se envía al
modelo -no en lo guardado-, las dos técnicas del punto 4 de `capa4-investigacion.md`. Una
negativa del usuario vuelve al modelo como resultado ("no la repitas"), para que no insista. Cada
herramienta declara cuándo es irreversible en función de sus argumentos (`confirmar(args)`): el
riesgo de `ejecutar_comando` depende del comando.

**Ficheros sensibles: leer también se confirma.** Con navegador propio y comandos libres de
solo lectura, una página con instrucciones ocultas podría pedir leer `~/.ssh/id_rsa` y llevarlo a
una URL: navegar no se confirma. Así que leer claves, `.env`, credenciales o perfiles de
navegador se pregunta, y crear ficheros de arranque automático (`.bashrc`, `autostart`,
`Startup`) también, aunque no existieran. El agente no escribe en campos de contraseña: con
Claude detrás, saldría de la máquina. Y todo lo leído de páginas y ficheros va marcado como datos,
no órdenes, en el resultado y en el prompt.

**Reconocer aplicaciones sin adivinar ejecutables.** Cada sistema ya tiene la lista: `.desktop`
en Linux, accesos `.lnk` del menú Inicio en Windows, `.app` en macOS. Se busca por nombre, por
nombre genérico, por palabras clave y por las categorías estándar (`WebBrowser`,
`FileManager`...), con un diccionario corto español → categoría. Medido en el portátil Linux: sin
categorías, "navegador" no encontraba Firefox y "archivos" no encontraba nada, porque GNOME
traduce los nombres con gettext y no en el `.desktop`.

**Descartado.**
- *Seguir solo con `claude -p`.* No abre aplicaciones ni maneja un navegador, y ata la capa de
  acciones a la nube. Se queda como está, para tareas de código (`act`).
- *MCP para las herramientas.* Descartado ya por contexto en `capa4-investigacion.md`.
- *Controlar el escritorio por capturas y clics* (lo que Anthropic llama *computer use*). Pide
  un modelo con visión y es otro orden de riesgo; queda para una fase posterior, si hace falta
  tras usar esto.
- *El Chrome real del usuario.* Más potente, pero el agente actuaría con sus cuentas.

**Relación con D-014.** Las herramientas de aquí son funciones, no *skills*. El estándar
agentskills.io sigue vigente para cuando haga falta empaquetar procedimientos de varios pasos
encima de ellas.

**Verificado en el portátil Linux, sin modelo.** 408 tests sin hardware, con un cerebro de
guion. Contra el escritorio real (GNOME, X11): descubre 55 aplicaciones, y un guion que abre la
Calculadora, ve su ventana y la cierra -con su confirmación- funciona de punta a punta.
**Sin medir:** ningún modelo real ha llevado este bucle todavía -ni Ollama ni Claude- y el
navegador propio no se ha lanzado (Playwright no instalado aquí).

**Pendiente.** Medir en el sobremesa con `gemma4:12b` cuántas órdenes resuelve bien, y con
Claude como referencia, antes de decidir el cerebro por defecto. El agente por voz (la orden
`agente` ya existe en el chat, falta probarla hablada). Que el HUD muestre los pasos.

**Adenda (13/10/2026): investigar sin dar vueltas.** El registro de una investigación real
("investiga la discografía de Saiko", 11 pasos) enseñó cuatro fallos. Los tres primeros eran
de las herramientas del navegador, no del modelo:
- *Buscó cuatro veces.* La página de DuckDuckGo se pinta con JavaScript y `leer_pagina` la leía
  antes de que hubiera resultados. Ahora hay una herramienta `buscar_web` que pide la versión sin
  JavaScript (`html.duckduckgo.com`) con `httpx` y devuelve una lista numerada de título, enlace y
  resumen. No abre el navegador, así que es rápida y no depende de cuándo termina de cargar.
- *La sección que buscaba caía fuera del recorte.* En Wikipedia, "Discografía" está más allá de
  los 4.000 caracteres que se leían. `leer_pagina(buscar="…")` devuelve ventanas de texto
  alrededor de cada aparición del término, sin distinguir tildes ni mayúsculas. Pulsar un enlace
  del índice no servía: mueve la vista, pero se sigue leyendo la página entera desde arriba.
- *Más enlaces que contenido.* Se lee solo el contenedor principal (`#mw-content-text`, `main`,
  `article`...) y como mucho 25 elementos, no 60 de menús y pies de página.
- *Respuesta sin fuentes, y un nombre ambiguo* (una banda chilena y un cantante español). Va al
  prompt: buscar primero, abrir de una a tres fuentes fiables, no repetir búsquedas, decir si un
  nombre es ambiguo y citar siempre los enlaces.

*Descartado:* una API de búsqueda con clave (Brave, Tavily). Sería otra clave más que conseguir
en cada equipo, y la versión HTML de DuckDuckGo basta. Si algún día empieza a pedir captcha,
`buscar_web` devuelve el error y sugiere `navegar` a la página del buscador. Verificado en real:
la búsqueda da 10 resultados, y `leer_pagina(buscar="Discografía")` en la página de Wikipedia
devuelve los álbumes directamente.

---

## D-034 — Varios modelos gratuitos: en cadena para no depender de uno, en consejo para contrastar

**Contexto.** Pedido del usuario, 13/10/2026: usar modelos **gratuitos**, buenos, y **varios**,
para tener comprobaciones de modelos distintos y no depender de uno. Sin GPU en el portátil,
"gratis" no puede ser solo Ollama local: las capas gratuitas de proveedores en la nube son lo
que da modelos grandes aquí.

**Estado de las capas gratuitas, a 13/10/2026** (cambian a menudo; verificar en cada panel):

| Proveedor | Gratis | Herramientas | Nota |
|---|---|---|---|
| Groq | ~30 peticiones/min, ~1.000/día por modelo | Sí, en todos sus modelos (documentado) | `openai/gpt-oss-120b`, `llama-3.3-70b-versatile`, `qwen/qwen3.8-27b` |
| Gemini (Google AI Studio) | Límites en el panel de AI Studio | Sí, por su capa compatible con OpenAI (beta) | Puede usar las peticiones gratuitas para mejorar sus productos fuera del EEE |
| NVIDIA NIM | ~40/min por modelo | No verificado | Requiere programa de desarrolladores |
| OpenRouter (`:free`) | 20/min, **50/día** | Según modelo | Demasiado poco para un agente; solo de reserva |
| Mistral | Créditos mensuales | Sí | El plan gratuito pide aceptar entrenamiento con tus datos |

Fuentes: documentación de Groq (modelos y *tool use*) y de Gemini (compatibilidad OpenAI),
comparativas de OpenRouter y dev.to de octubre de 2026.

**Decisión.**

1. **Un solo backend para todos**: `backends/openai_compat.py`. Casi todos los proveedores
   gratuitos hablan el formato de OpenAI (`/chat/completions` con `tools`), así que una clase
   cubre Groq, Gemini, OpenRouter, NVIDIA, Mistral, Cerebras y GitHub Models. Cumple
   `TextGenerator` y `ToolCaller`. El catálogo (URL y dónde se saca la clave) está en
   `backends/proveedores.py`; la configuración es `DOOMBOT_MODELOS=proveedor:modelo,...` y una
   `DOOMBOT_<PROVEEDOR>_API_KEY` por proveedor. Ollama y Anthropic entran en la misma lista con
   sus backends propios (`ollama:gemma4:12b`).
2. **`Cadena`: no depender de uno.** Responde el primero; si falla (sin conexión, clave mala, o
   429 de cuota gratuita agotada), el siguiente, avisando del cambio. Un modelo sin cuota se
   aparta 60 s para no gastar una petición en él en cada paso del agente, pero sigue al final por
   si es el único. En *streaming*, solo se cambia antes del primer trozo. Es `varios` en
   `DOOMBOT_LLM_BACKEND` y en `DOOMBOT_AGENT_BRAIN`.
3. **`Consejo`: contrastar.** La misma pregunta a todos en paralelo, y un juez (la propia
   cadena) que da la respuesta final diciendo en qué discrepan. `/contrasta` en la consola del
   agente, `contrasta ...` en el chat. Si solo responde uno, se dice: "sin contraste".
4. **Segunda opinión antes de lo irreversible.** En el agente, cuando una acción va a pedir
   confirmación, un modelo **distinto del que la propuso** lee la orden del usuario y la acción
   -no la página ni el fichero que la motivó- y dice "BIEN" u "OJO". Su opinión se añade a la
   pregunta; no decide nada. El motivo: el modelo que propone es el peor juez de su propuesta,
   sobre todo si una página le ha colado instrucciones; otro que no ha visto esa página no
   arrastra el engaño.

**Por qué no un voto automático en cada paso del agente.** Triplicaría las peticiones y la cuota
gratuita se acaba antes; además, en la mayoría de pasos (abrir, leer, buscar) no hay nada que
arbitrar. El contraste se gasta donde importa: preguntas de datos (`contrasta`) y acciones
irreversibles (revisor).

**Privacidad, dicho claro.** Con estos proveedores, lo que el agente lee -páginas, ficheros,
títulos de ventanas- sale del equipo. Algunos planes gratuitos usan esas peticiones para entrenar.
Para lo que no deba salir, `ollama:` en la lista, en el sobremesa.

**Verificado sin claves**: 432 tests con transportes falsos y modelos de juguete; la consola con
`varios` y sin claves dice exactamente cuáles faltan y dónde se crean. **Sin verificar**: ningún
proveedor real todavía, ni los nombres exactos de modelo de Gemini y NVIDIA en sus capas
gratuitas (`gemini-3.8-flash` sale de los ejemplos de la documentación de Google;
`nvidia/nemotron-3-super-120b-a12b`, de una comparativa).

---

## D-035 — La aplicación: una ventana con un planeta, el registro del agente y un chat

**Contexto.** Pedido del usuario, 13/10/2026: una interfaz propia "como Claude Code", que no abra
un HTML en el navegador; una esfera "como un planeta" que reaccione a las consultas, y un chat
debajo que procese la orden y vaya diciendo lo que piensa y qué aplicaciones o enlaces abre
mientras trabaja. Además, que la interfaz cambie según la herramienta que use el agente.

**Decisión.**

1. **Ventana propia con pywebview** (`python -m doombot ventana`), confirmando D-016: sin
   pestaña ni barra de direcciones, con su título y su icono en la barra de tareas. WebKitGTK en
   Linux, WebView2 en Windows. Dibujar en HTML dentro de una ventana es lo que hacen VS Code o
   Discord; lo descartado sigue siendo abrir una pestaña del navegador.
2. **Interfaz nueva, `ui/ventana/doom.html`**, aparte del HUD de voz (`ui/prototipo/hud.html`):
   el HUD es solo la esfera para la voz; esto es la aplicación entera. Mismo principio que el
   HUD: la interfaz no decide nada, recibe eventos y anima.
3. **El planeta, en WebGL**: esfera iluminada con continentes, nubes y venas de energía de ruido
   procedural, atmósfera y una luna. Cada **modo** es un juego de números (color de atmósfera,
   energía) y el planeta se desliza hacia el del modo actual: reposo, pensando, `web`, `apps`,
   `ficheros`, `terminal`, esperando permiso, respondiendo, error. La energía acelera la rotación
   y la luna; cada evento y cada palabra de la respuesta dan un latido. Sin WebGL, una esfera 2D
   con halo: se pierde detalle, no función.
4. **El modo sale de la herramienta.** Cada `Herramienta` declara su `familia`, y el bucle del
   agente avisa por `observar("herramienta", {nombre, familia})` antes de ejecutarla. La
   consola no lo usa; la ventana sí.
5. **Ventana y agente en el mismo proceso, por `js_api`, no por WebSocket.** D-022 eligió
   WebSocket para conectar dos programas; aquí hay uno, y abrir un puerto para hablar consigo
   mismo es superficie sin necesidad. Python pinta con `DOOM.evento({tipo, ...})`.
6. **Un solo hilo para el agente.** pywebview atiende cada llamada de JavaScript en un hilo
   distinto, y Playwright solo funciona desde el hilo que lo creó: sin hilo fijo, la segunda
   orden que tocara el navegador propio reventaría.
7. **Confirmaciones como botones**, con la segunda opinión (D-034) debajo, y **Parar** en el
   sitio de Enviar mientras trabaja: el agente para entre paso y paso (`Agente.parar()`), y una
   confirmación pendiente cuenta como "no".
8. **Los enlaces nunca navegan dentro de la ventana**: se abren en el navegador del usuario, y
   solo si son `http(s)`, para que un texto del modelo no pueda lanzar `file://` u otros
   esquemas.

**Verificado en el portátil Linux.** 445 tests sin hardware (9 del puente con una ventana
falsa). La ventana real abierta con pywebview sobre WebKitGTK, con un cerebro de guion y las
herramientas reales: encontró la Calculadora, la abrió, vio su ventana y escribió la respuesta;
captura revisada. El flujo completo -modos, permiso con segunda opinión, respuesta palabra a
palabra- revisado también con `doom.html#demo`.

**Sin verificar.** Con un modelo real (faltan las claves). En Windows (WebView2) y empaquetada
como ejecutable. La voz: el planeta todavía no reacciona al nivel del micrófono ni de Kokoro,
como sí hace el HUD; es el siguiente paso natural, juntando los dos.

**Ampliación, mismo día: primeros pasos.** Pedido: una pantalla antes del chat con los enlaces y
las instrucciones de lo que necesita el agente. Sale sola si no hay ningún modelo utilizable, y
siempre desde la cabecera. Por proveedor: pasos para sacar la clave, enlace, caja para pegarla,
**Guardar** (`config.guardar_en_env`: sustituye la línea, conserva comentarios, rechaza saltos de
línea para que una clave pegada con basura no cuele otra variable, y deja `.env` en `0600`) y
**Probar** (una petición mínima). La clave no vuelve a la ventana: solo sus cuatro últimos
caracteres. Guardar una clave también la añade a `DOOMBOT_MODELOS` y, si el agente no tenía
cerebro elegido, pone `DOOMBOT_AGENT_BRAIN=varios`: sin eso la clave no se usaría. Los textos de
cada proveedor viven en el catálogo (`backends/proveedores.py`), no en la ventana. Verificado:
con las claves reales del usuario, Groq (`openai/gpt-oss-120b`) y Gemini (`gemini-3.8-flash`)
responden -lo que confirma el nombre de modelo de Gemini, que D-034 dejó sin verificar-.

---

## D-036 — Aspecto propio: HUD holográfico estilo JARVIS, personalizable en color y luz

**Contexto.** 13/10/2026. La primera ventana (D-035) se parecía a cualquier otra interfaz
oscura genérica. El usuario pidió una identidad propia, "medio cyberpunk, similar a JARVIS", con
dos referencias: un HUD azul con un núcleo de anillos concéntricos y pistas de circuito hacia
paneles de datos, y una esfera holográfica dorada de filamentos. Y que colores y luz se puedan
personalizar.

**Decisión.**

1. **Un núcleo holográfico en lugar del planeta**: disco oscuro con anillos segmentados que
   giran a contrapelo, grupos de marcas radiales, una esfera de alambre (paralelos, meridianos y
   170 partículas) con tres órbitas inclinadas, y un anillo brillante alrededor de una pupila
   oscura. Cada herramienta tiene un gesto propio además del color: barrido de radar (`web`),
   segmentos en cadena (`apps`), línea de lectura (`ficheros`), anillo de caracteres
   (`terminal`), anillo de aviso parpadeante (permiso) y temblor (error).
2. **Canvas 2D con mezcla aditiva y una pasada de resplandor casera** (la escena reducida a 1/4
   y 1/8 y vuelta a ampliar en modo `lighter`), no WebGL ni `ctx.filter`: así no depende de qué
   soporte WebKitGTK o WebView2 y el brillo es un solo número (`luz`).
3. **Composición HUD**: paneles SISTEMA (reloj, estado, carga, modelos, segunda opinión) y
   ACTIVIDAD (herramienta actual, pasos, permisos, lo abierto), unidos al núcleo por pistas de
   circuito con codos a 45° por las que corren pulsos de datos al pensar y en cada evento.
   Marcos con esquinas, rejilla y bloques de datos tenues de fondo, efecto CRT opcional. Por
   debajo de 1120 px se quita el panel derecho; por debajo de 820, también el izquierdo.
4. **Personalizar**: seis temas (Jarvis, Holograma, Neón, Matriz, Glaciar, Carmesí), dos colores
   propios, brillo y resplandor, intensidad de rejilla y circuitos, velocidad, y tres
   interruptores (color por herramienta, pulsos, CRT). Permiso y error conservan siempre ámbar y
   rojo: son avisos, no decoración.
5. **Las preferencias son estado local**: `data_dir()/ventana.json`, fuera del repositorio
   (`ventana/preferencias.py`). Todo pasa por `limpiar()` -claves conocidas, colores `#rrggbb`,
   números en su rango- porque esos valores acaban en el CSS de la ventana.

**Verificado.** 463 tests (5 de preferencias). La ventana real en este Linux con eventos
simulados: reposo, navegador con el registro, permiso, y los temas holograma y neón; capturas
revisadas. Un fallo visto en ellas y arreglado: el cajón de ajustes usaba la clase `abierto`,
que ya era la de las etiquetas de "lo abierto", y enmarcaba sus rótulos.

**Sin verificar.** En Windows (WebView2) y el rendimiento en un equipo más lento: el núcleo se
redibuja entero en cada fotograma.

---

## D-037 — Enseñar en vez de contar: el núcleo se transforma en gráficas, esquemas o dibujos

**Contexto.** 13/10/2026. El usuario pidió al agente representar unos vectores y, sin forma de
dibujar, el agente acabó escribiendo un script de matplotlib. Pedido: que si se le dice
"represéntamelo", el núcleo cambie a una gráfica o un esquema, y no solo para matemáticas
("dibújame un caballo"). Con una condición explícita: no cargar mucho la aplicación.

**Decisión.**

1. **Una herramienta, `mostrar_visual`, que solo existe donde hay pantalla.** `montar()` la añade
   si recibe `pantalla` -la ventana se la pasa; consola y voz, no-, y el prompt gana una línea que
   le dice al modelo cuándo usarla. Familia `visual`: el núcleo pasa al modo "representando".
2. **Dos formas, según lo que haya que enseñar.**
   - `grafica`: el modelo describe ejes, vectores, puntos, segmentos y funciones; la ventana los
     dibuja con precisión (rejilla con paso "bonito", flechas, etiquetas, leyenda). El modelo da
     coordenadas, no píxeles: los vectores quedan donde tienen que estar. Las funciones se
     evalúan con un intérprete propio de fórmulas (`+ - * / ^`, paréntesis, `sin cos tan sqrt abs
     exp log ln`, `pi`, `e`), nunca con `eval`.
   - `svg`: dibujos y esquemas libres. Los modelos escriben SVG razonablemente bien, y un
     `stroke="currentColor"` toma el color del tema.
3. **El SVG se reconstruye desde cero con lista blanca** (`agent/visual.py`, `limpiar_svg`):
   solo formas, texto, degradados y marcadores; fuera `script`, `foreignObject`, `image`, `a`,
   `style`, cualquier `on*`, `href`, y `url()` que no apunte dentro del propio dibujo. Motivo: la
   ventana tiene `js_api` hacia Python; un dibujo con código -de un modelo equivocado o de una
   página que le coló instrucciones- podría pedir cosas al agente. Se rechaza todo `DOCTYPE`
   antes de leer el XML, lo que corta XXE y la expansión de entidades sin añadir `defusedxml`. La
   ventana además lo importa como XML (nunca como HTML) y vuelve a quitar lo peligroso.
4. **Ligero, como se pidió**: ninguna librería nueva. Mientras hay un visual, el núcleo se queda
   de fondo y deja de redibujarse. "Ampliar" usa también el sitio del registro; "Núcleo" vuelve;
   una orden nueva devuelve el núcleo, y cada visual queda en el registro con "Ver".

**Arreglos en el mismo cambio, vistos con las claves reales del usuario.**
- *Gemini 3 rechazaba la conversación* ("missing a thought_signature"): firma su razonamiento en
  `tool_calls[].extra_content.google.thought_signature` y exige recibirlo de vuelta. Ahora
  `LlamadaHerramienta.extra` lo guarda y `openai_compat` lo devuelve; a las llamadas de otro
  modelo de la cadena se les pone el valor de relleno documentado por Google,
  `skip_thought_signature_validator`.
- *Groq se quedaba "sin cuota" a los pocos pasos*: su límite gratuito es por minuto (~8.000
  tokens). Si responde 429 con `Retry-After` de pocos segundos, se espera y se reintenta una vez;
  el agente reenvía menos de lo leído (3.500 caracteres por resultado, 3 resultados enteros); y si
  todos los modelos están sin cuota, se dice claro en vez de un volcado de errores.
- *Gemini saturado* (503, "high demand") cuenta como pasajero, igual que un 429, y el tiempo
  máximo de respuesta baja de 120 a 60 s: mejor el siguiente de la cadena que esperar.

**Verificado.** 489 tests (filtro de SVG con scripts, manejadores, enlaces, `foreignObject`,
`DOCTYPE`, entidades; gráficas; firma de Gemini; reintento). En la vista previa: la gráfica de
vectores con sus etiquetas y el caballo, normal y ampliado.

**Ampliación, mismo día: refinar los dibujos.** El usuario probó en real: los vectores salieron
bien pero sin números en los ejes, y "la silueta de un caballo" fue una mancha negra.

- *Gráficas*: se rotula el 0 en el origen y el nombre de cada eje; los números, más grandes y
  menos tenues. La herramienta dice ahora "para matemáticas, SIEMPRE `grafica`, nunca un dibujo".
- *Dibujante*: el agente ya no improvisa el SVG; describe el encargo y lo dibuja un modelo con
  instrucciones solo de dibujo -planificar en un comentario las partes y su sitio, componer con
  formas geométricas, nunca negro ni blanco- y un ejemplo de método (una taza; con un perro de
  ejemplo, `gpt-oss-120b` dibujaba perros). Un SVG inválido se pide una vez más.
- *Medido, no supuesto* (13/10/2026, "un caballo de perfil", mismas instrucciones): de los
  modelos gratuitos de Groq, solo `qwen/qwen3.8-27b` dibujó un caballo reconocible, en 2 s;
  `gpt-oss-120b`, un perro; `gpt-oss-20b`, peor. Gemini estaba saturado y no se pudo medir.
  Orden por defecto del dibujante: `groq:qwen/qwen3.8-27b`, después Gemini, después el resto de
  la cadena (`DOOMBOT_MODELO_DIBUJO` lo cambia; el dibujante no necesita estar en
  `DOOMBOT_MODELOS`).
- *Red de seguridad en la ventana*: los rellenos negros o blancos se recolorean al tema (el CSS
  manda sobre los atributos del SVG), y cada dibujo se encuadra solo -se mide lo dibujado y el
  `viewBox` se ajusta-, porque los modelos a veces dibujan descentrados o medio fuera.
- *La cadena*: un modelo que agota el tiempo de respuesta cuenta como pasajero, como un 429, y se
  aparta un rato.

**Límite honesto.** La calidad del trazo depende del modelo: con los gratuitos, los animales y
objetos salen reconocibles pero sencillos, y alguno sale mal. Gemini, cuando no está saturado, o
un modelo de pago dibujarían mejor.

**Cambio de rumbo, mismo día: solo gráficas y estadística.** Probados en real, los dibujos libres
no fueron lo bastante precisos ni con el dibujante, y el usuario decidió dejar la herramienta para
gráficas y estadística. Se quitó todo lo de dibujo -el dibujante y sus instrucciones, el filtro de
SVG, el encuadre automático, `DOOMBOT_MODELO_DIBUJO`-, y la herramienta pasó a ser
`mostrar_grafica` (`agent/graficas.py`):

- `grafica`: lo de antes, matemáticas en ejes.
- `estadistica`: barras (también varias series), líneas, sectores, histograma y dispersión con
  recta de regresión. **Los cálculos se hacen en Python, no en el modelo**: total, media, mediana,
  desviación típica, máximos y mínimos con su categoría, porcentajes, intervalos del histograma
  (regla de Sturges si no se dicen) y regresión lineal con `r`. La herramienta se los devuelve al
  modelo con la indicación de usarlos al explicar: los modelos fallan en la aritmética, y así no
  la necesitan. Los datos mal formados se rechazan con el motivo -"la serie X tiene 2 valores y
  hay 3 categorías"- para que el modelo lo corrija en el paso siguiente.

Verificado: 488 tests (estadísticos exactos: histograma de 1..10 en 5 intervalos de 2, regresión de
`y = 2x + 1` con `r = 1`); los cinco tipos pintados en la vista previa.

**Ampliación: icono propio.** `python -m doombot lanzador` escribe un `.desktop` en la carpeta de
aplicaciones del usuario -no del sistema: sin sudo, se quita borrando un fichero- que apunta al
Python del `.venv`, y lo añade al final de los favoritos del dock de GNOME. La ventana se llama
`doombot` para el escritorio (`GLib.set_prgname` antes de arrancar GTK; antes era un
`__main__.py` genérico) y el `.desktop` lo declara en `StartupWMClass`: así el dock asocia la
ventana a su icono. El icono (`ui/ventana/doom.svg`) es el núcleo del HUD. Verificado: el
`.desktop` pasa `desktop-file-validate` y la ventana abierta desde él tiene `WM_CLASS` `doombot`.
Pendiente: el equivalente en Windows (acceso en el menú Inicio).

---

## D-038 — Skills como modos de conversación que aprenden, y conversaciones por carpetas

**Contexto.** 13/10/2026. Pedido del usuario: "agentes profesionales con distintas utilidades"
-diseño, conversación e investigación en internet, programación, ciencias- que sean las propias
skills de D.O.O.M y funcionen como modos de conversación, pero que a la vez realimenten a la IA;
poder elegir uno según la tarea o usar una versión global de todo. Y un historial de
conversaciones por temas o carpetas, como Claude Code.

**Decisión.**

1. **Skills en el estándar de D-014, por fin.** Una carpeta por skill con su `SKILL.md`
   (agentskills.io): `name`, `description` e instrucciones; lo propio de D.O.O.M en `metadata`
   (`titulo`, `color`, `modelos` preferidos) y en `allowed-tools`. Viven en `skills/` del
   repositorio y, las personales, en `data_dir()/skills` (una personal sustituye a la del mismo
   nombre). Cuatro de serie: `diseno`, `investigacion`, `programacion`, `ciencias`. Añadir una es
   añadir una carpeta, sin código.
2. **Un modo reconfigura el agente, no crea otro** (`agent/skills.py`, `Modos.aplicar`): sus
   instrucciones (las de la skill más lo aprendido), sus herramientas (las de `allowed-tools`) y el
   orden de los modelos (los preferidos delante, montándolos aparte si no estaban en la cadena).
   El parser del frontmatter es propio y mínimo: no se añade PyYAML para leer `clave: valor`.
3. **El modo global lo tiene todo** y ve el catálogo de skills (nombre y descripción: la
   "divulgación progresiva" del estándar, unos 20 tokens por skill), con `consultar_skill` para
   pedirle una respuesta a un experto con sus instrucciones y sus modelos.
4. **Realimentación: `aprender`.** En cualquier modo, el agente apunta una preferencia o corrección
   del usuario en el ámbito del modo (`data_dir()/aprendizajes/<modo>.md`, texto legible). Cada
   modo lee lo suyo y lo global; el modo global lee un resumen de todos -lo que enseñas a
   Programación lo sabe también la IA general-, pero un modo no ve lo de los demás. **Apuntar se
   confirma** con un clic: lo apuntado entra en el prompt de todas las conversaciones futuras, y
   una página con instrucciones ocultas podría intentar que el agente "aprendiera" algo suyo.
   Desde el selector de modo se ve lo aprendido y se puede olvidar nota a nota.
5. **`calcular`**, en todos los modos: aritmética de verdad con `math`, analizada con `ast` y una
   lista blanca (números, operadores, unas constantes y funciones), nunca `eval`, con topes para
   que una potencia o un factorial enormes no cuelguen el proceso. El modo Ciencias obliga a usarla.
6. **Historial por carpetas** (`ventana/historial.py`): un JSON por conversación en
   `data_dir()/conversaciones` -estado privado, fuera del repositorio-, con lo que se ve en el
   registro (para volver a pintarlo) y el estado del agente (para retomarla, no solo releerla),
   incluida la firma de Gemini de cada llamada. Carpetas que existen aunque estén vacías.
   Crear, renombrar, mover y borrar conversaciones y carpetas desde la ventana; borrar una carpeta
   no borra sus conversaciones. Los identificadores que llegan de la ventana se validan contra un
   patrón antes de ser nombre de fichero.

**En la ventana**: pestañas *Conversaciones* / *Sistema* a la izquierda, con el árbol de carpetas;
selector de modo junto a la línea de órdenes, con el color de cada skill; una conversación se
crea al primer mensaje, se guarda al acabar cada orden y se reproduce sin animaciones al abrirla.

**Un error propio, visto y cerrado.** Los primeros tests del puente guardaron conversaciones de
prueba en la carpeta de datos real del usuario. Se borraron, y `tests/conftest.py` dirige ahora
`DOOMBOT_DATA_DIR` a una carpeta temporal en todos los tests: ninguno puede volver a escribir en
los datos de quien los ejecuta.

**Verificado.** 529 tests (skills reales y de prueba, modos, lo aprendido, calculadora con
intentos de ejecutar código, historial con identificadores maliciosos, puente creando, guardando y
retomando conversaciones). La ventana, en la vista previa con datos simulados: árbol, selector de
modo con lo aprendido, conversación reabierta. **Sin verificar**: con modelos reales eligiendo
herramientas en cada modo.

**Ampliación de D-034, 13/10/2026 (tarde): más modelos con las mismas claves.** Cada modelo tiene
su propia cuota gratuita, así que varios del mismo proveedor multiplican la capacidad sin cuentas
nuevas. Probados con una herramienta, con las claves del usuario: funcionan `groq:qwen/qwen3.8-27b`,
`groq:openai/gpt-oss-20b` y `gemini:gemini-3.5-flash-lite` (menos de 1 s); Gemini 3.5/3.6/3.7/3.8
Flash, saturados ese día; Gemini 2.5, 404 para esta cuenta; `gemma-4-31b-it`, sin respuesta. La
cadena por defecto pasa a cinco modelos, los saturados detrás. Y un modelo que sigue fallando se
aparta cada vez más tiempo (1, 2, 4… hasta 15 min), volviendo a cero al primer acierto: con un
minuto fijo, un Gemini saturado durante horas costaba una espera en cada orden.


---

## D-039 — Refinar las respuestas: repaso final por otro modelo, y leer páginas sin navegador

**Contexto.** 14/10/2026. Pedido del usuario: modelos gratuitos útiles para refinar las respuestas.
Investigado ese día, con sus claves para lo que se podía comprobar:

- **Groq** (`/models` de su cuenta): ya no están `groq/compound` (su sistema con búsqueda web,
  retirado el 21/09/2026) ni `llama-3.3-70b-versatile`, que la tabla de D-034 todavía cita. Han
  aparecido `llama-prompt-guard-2-22m`/`86m` (detectan instrucciones colocadas en un texto) y
  `gpt-oss-safeguard-20b`.
- **Gemini con búsqueda de Google y citas** no entra en el plan gratuito: con la herramienta de
  búsqueda, `gemini-3.5-flash-lite` dio 429; sin ella, el mismo modelo respondió.
  `gemini-2.5-flash`, el que la traía gratis, "ya no está disponible para usuarios nuevos".
- **Cerebras** ya no tiene plan gratuito desde julio de 2026 (5 $ de prueba con tarjeta).
  **GitHub Models** limita a 8.000 tokens de entrada por petición. **Cohere**, 1.000 llamadas al
  mes en total. Ninguno sirve para el agente.

**Decisión.**

1. **Repaso final** (`agent/refinado.py`). Cuando el agente termina, un modelo de la cadena
   **distinto del que ha respondido** recibe lo pedido, extractos de lo consultado en esa tarea y
   el borrador. Comprueba datos contra lo consultado, fuentes, claridad, y que la respuesta no
   empiece con lo que el agente "iba a hacer". Si está bien, dice `OK` y se da el borrador; si
   no, devuelve la respuesta corregida, que es la que se muestra y la que queda en la
   conversación. El porqué es el de la segunda opinión (D-034): quien ha escrito un dato mal lo
   vuelve a dar por bueno al releerse.
   - **Cuándo** (`DOOMBOT_AGENT_REFINAR`): `auto` (por defecto) repasa lo que se apoya en algo
     consultado (`buscar_web`, `leer_url`, `navegar`, `leer_pagina`, `leer_fichero`,
     `consultar_skill`) o pasa de 600 caracteres. "He abierto la calculadora" no gasta petición.
     `siempre` y `no` hacen lo que dicen.
   - **Nunca deja sin respuesta**: si el repaso falla, se da el borrador y se dice; si devuelve
     algo de menos de un cuarto del borrador, se toma por un comentario y también se da el
     borrador.
   - **Lo consultado va recortado** (6.000 caracteres en total, las 4 fuentes últimas), por el
     límite de tokens por minuto de las capas gratuitas. Por eso el prompt le dice que no quite
     un dato solo porque no aparezca en los extractos, sino lo que lo contradiga.
2. **`leer_url`, leer páginas sin navegador** (Jina Reader, `r.jina.ai`). Devuelve el texto de la
   página sin imágenes, con los enlaces como texto y sin `nav`/`header`/`footer`/`aside`: el
   anexo de discografía de Wikipedia pasa de 20.000 caracteres a 4.700, empezando por el
   contenido. Lee también páginas que se pintan con JavaScript (la predicción de AEMET). Es lo
   primero para leer fuentes; `navegar` queda para pulsar o rellenar, o si `leer_url` falla.
   Con `buscar` va a una sección, sobre lo ya leído (guarda las 8 últimas páginas) sin volver a
   pedirla. Sin clave, 20 lecturas por minuto; con `DOOMBOT_JINA_API_KEY` (gratuita), 200.
3. **Arreglo de paso**: la segunda opinión elegía "otro modelo" mirando la cadena del arranque,
   pero cada modo monta la suya (D-038). En un modo podía revisar el mismo modelo que había
   propuesto la acción. Revisor y repaso miran ahora la cadena que usa el agente en ese momento.

**Descartado.**
- **Elegir el contenido con `X-Target-Selector`** en vez de quitar menús: si el selector no está en
  la página, Jina responde 422 en vez de la página.
- **Votar entre varios modelos cada respuesta**: triplica las peticiones, y el consejo
  (`contrasta`) ya existe para cuando el usuario lo pide.
- **El modelo de recompensa de NVIDIA**, para puntuar respuestas: no se pudo confirmar cómo
  devuelve la nota por su API gratuita.

**Privacidad.** La dirección de cada página leída sale hacia Jina, que la descarga. Las
direcciones locales (`localhost`, IP privadas, `.local`, nombres sin dominio) nunca: `leer_url`
las rechaza y sugiere `navegar`.

**Verificado en real**, con las claves del usuario:
- **El repaso, con dos borradores.** Uno con errores puestos a propósito ("cinco álbumes y
  treinta sencillos" frente a 7 y 29 de la fuente) salió corregido por
  `groq/qwen/qwen3.8-27b`; el correcto, sin cambios.
- **Una orden completa**, "¿En qué año se fundó Saiko y quién la fundó?": `buscar_web`, tres
  `leer_url` (con `buscar`) y la respuesta con su fuente. Groq llegó a su límite a mitad y siguió
  Gemini; repasó `gpt-oss-20b`.
- **Tests**: los de `leer_url` (cabeceras, menús, sin repetir la petición, direcciones locales,
  429), los del repaso (otro modelo, OK, cuándo merece, fallo) y el del revisor en un modo.

**Sin verificar**: en Windows, y el modo `siempre` con la cuota de un día entero de uso.

---

## D-040 — Proyectos: las carpetas comparten instrucciones, notas y lo decidido en cada chat

**Contexto.** 14/10/2026. Pedido del usuario: carpetas o proyectos "como los de Claude", con varios
chats que se retroalimenten. Ejemplo: diseñar una aplicación con una temática en un chat, generar su
diseño en otro, y que un tercero siga esa línea. Las carpetas de D-038 solo ordenaban; cada chat
empezaba sin saber nada de los demás.

**Decisión.** Una carpeta **es** un proyecto. No hay una entidad aparte: las conversaciones ya
viven en carpetas, y así no hay que migrar nada.

1. **Qué recibe cada chat del proyecto** (al final de su prompt, en cualquier modo):
   - las **instrucciones** del proyecto, escritas por el usuario;
   - las **notas**: decisiones clave apuntadas con `anotar_en_proyecto`;
   - el **resumen de cada otra conversación** del proyecto.

   Todo recortado a 5.000 caracteres, porque cada paso del agente lo reenvía.
2. **Resumen automático.** Tras cada respuesta de un chat del proyecto, la cadena reescribe su
   resumen: qué se pidió, decidió y produjo, con los datos concretos (nombres, colores,
   estructuras), en un máximo de 8 líneas. Cuesta una petición por orden, y solo dentro de un
   proyecto. Si falla, se queda el anterior sin decir nada.
3. **Dos herramientas**, solo en un proyecto:
   - `leer_conversacion_proyecto`: lo pedido y lo respondido en otro chat, por su título. No
     incluye los resultados de herramientas, que pueden traer texto de páginas: son datos
     intermedios y abultan.
   - `anotar_en_proyecto`: apunta una decisión. Sin confirmación, a diferencia de `aprender`
     (D-038): no es "para siempre" ni para todo, solo para este proyecto, y se borra desde su
     editor.
4. **Ventana**:
   - "+ Proyecto" en lugar de "+ Carpeta";
   - en el menú de cada proyecto, "Proyecto: instrucciones y memoria", un editor con
     instrucciones, notas (con ✕) y las conversaciones con su resumen (se abren al pulsarlas),
     en el mismo hueco que Primeros pasos.

   Datos en `conversaciones/proyectos.json`, y cada resumen en su conversación. Renombrar o borrar
   la carpeta lleva consigo, o borra, sus datos.

**Descartado.**
- **Mandar las conversaciones enteras** a las demás: no caben en los límites gratuitos, y casi
  todo es ruido de herramientas. Resumen siempre, y lo completo bajo demanda.
- **Memoria semántica con embeddings** (`memory/`): para un proyecto de pocas conversaciones, los
  resúmenes caben enteros y no hay nada que buscar. Queda para la memoria entre proyectos.
- **El resumen solo al cerrar el chat**: la ventana no sabe cuándo se deja un chat, y el
  siguiente puede abrirse sin cerrar el anterior.

**Verificado.**
- Tests de las instrucciones, notas y resúmenes en el contexto, sin el propio chat; de leer otro
  chat sin lo leído de páginas; de renombrar y borrar; del proyecto en cualquier modo; y de punta
  a punta por el puente: un chat de diseño deja resumen y nota, y el siguiente los recibe.
- Un resumen real con la cadena del usuario conservó nombre, colores hexadecimales, tipografía y
  las cuatro pantallas.
- El editor, en la vista de demostración.

**Sin verificar**: un proyecto real de varios chats con modelos gratuitos, y cuánto aguanta la
cuota con el resumen por orden.

## D-043 — Memoria del agente: el perfil del usuario siempre, los recuerdos cuando vienen a cuento

**Contexto.** 15/10/2026. Pedido del usuario: empezar por la memoria, y un perfil que la IA lea
para saber quién es. Las piezas existían, pero solo para la voz (`chat.py`): `memory/` guarda y
busca por significado con embeddings, y `obsidian/usuario.md` refleja los hechos de "recuerda que
yo...". El agente de la ventana, que es donde se usa D.O.O.M a diario, no veía ninguna de las dos.
Empezaba cada conversación sin saber ni el nombre del usuario.

**Decisión.** Dos memorias distintas, porque se usan de forma distinta (`agent/memoria.py`).

1. **El perfil, en todas las órdenes.**
   - Va en `obsidian/usuario.md`: el mismo de la voz, que viaja con el repositorio entre equipos y
     se edita en Obsidian.
   - Tiene datos (nombre, cómo llamarle, a qué se dedica, dónde vive, idiomas, intereses y cómo
     quiere las respuestas) como propiedades de Obsidian, el bloque `---` de arriba. Debajo, los
     hechos sueltos, uno por línea con guion.
   - Se añade al final del prompt de cada orden, en cualquier modo, recortado a 2.500 caracteres.
   - Se edita en el panel **Perfil** de la ventana. El agente apunta hechos con
     `anotar_sobre_usuario`, **siempre con permiso**: va en todos los prompts y sube a GitHub.
2. **Los recuerdos, solo cuando vienen a cuento.**
   - Van en `memory.db` (`kind='fact'`), son de cada equipo y no se versionan.
   - Antes de cada orden se buscan los parecidos (`recall`, umbral 0,35, como la voz). Los que
     pasan entran en el prompt **de esa orden** y no se quedan en la conversación. El registro los
     enseña con ◈.
   - Tres herramientas: `recordar`, `buscar_en_memoria` (sin consulta, lista lo último) y
     `olvidar_recuerdo` (con permiso, enseñando cuál).
   - Necesitan fastembed (extra nuevo `memoria`, que ya venía en `voice`). Sin él, el perfil
     funciona igual y estas herramientas no se ofrecen.
3. **`recordar` pide permiso solo si en la misma orden se ha leído algo de fuera** (familias `web`,
   `ficheros`, `terminal`). Es lo que impide que una página se cuele como "algo que me dijo el
   usuario" y envenene todas las conversaciones siguientes. Sin nada leído, va solo: si no, cada
   "recuerda que..." sería un diálogo.
4. **Contraseñas, claves y datos bancarios no se guardan nunca, ni con permiso.** Se detectan
   claves con prefijo conocido, tarjetas, IBAN y frases como "la contraseña es...". El modelo
   recibe un error que le dice que lo guarde el usuario en un gestor de contraseñas.
5. **`usuario.md` manda.** Con dos sitios que editan el perfil, el fichero es la fuente de verdad:
   - `escribir_perfil` (voz) ya no lo sobrescribe desde la memoria: le **añade** lo nuevo y
     respeta los datos, el orden y lo borrado;
   - `sincronizar_perfil` olvida de la memoria lo que ya no está en el fichero, salvo si el fichero
     no existe;
   - "olvida eso" tras "recuerda que yo..." lo quita también del fichero;
   - la voz lee el perfil del fichero, así que también conoce los datos de la ventana.
6. **Varios hilos sin compartir conexión.** Cada operación abre su conexión a `memory.db`, porque la
   ventana consulta la memoria mientras el agente trabaja en su hilo. El modelo de embeddings se
   carga una vez, con cerrojo. Si hay recuerdos, se precarga en segundo plano; mientras carga, una
   orden va sin recuerdos en vez de esperar.

**Descartado.**
- **Un solo almacén para todo**:
  - el perfil en `memory.db` no se podría editar a mano ni viajaría entre equipos;
  - los recuerdos en el repositorio subirían a GitHub cada dato suelto;
  - y buscar el nombre del usuario por parecido falla justo cuando la orden no lo menciona.
- **El perfil en `data_dir()`**, como los proyectos: habría que rellenarlo en cada equipo. A cambio,
  el panel avisa de que viaja con el repositorio (privado) y no guarda secretos.
- **Extraer hechos automáticamente tras cada respuesta**, como el resumen de D-040: una petición
  más por orden con las cuotas gratuitas, y guardaría cosas sin que el usuario lo vea. Mejor que lo
  proponga el modelo, visible en el registro.
- **Confirmar siempre `recordar`**: más seguro, pero insoportable. El riesgo real está en lo leído
  de fuera, y ahí sí se pregunta.

**Verificado.**
- Tests (`test_memoria_agente.py`, `test_obsidian_vault.py`, `test_ventana.py`):
  - el perfil y los recuerdos en el prompt de cada orden, y no en la conversación;
  - la memoria en un modo que no la lista, y la orden que sigue si la memoria falla;
  - el permiso tras leer una página, y el rechazo de secretos con sus falsos positivos;
  - las propiedades de Obsidian que no son nuestras, la ida y vuelta, y el puente de la ventana;
  - la voz: "olvida eso" saca el hecho del fichero, y lee los datos del perfil.

  `conftest.py` aparta también el vault: ningún test toca el `usuario.md` real.
- Con el modelo real (paraphrase-multilingual-MiniLM-L12-v2):
  - 4 de 5 preguntas relacionadas recuperan su recuerdo en unos 30 ms;
  - las que no vienen a cuento no traen nada;
  - falló "¿puedo entrenar un modelo en el portátil?" frente a "el portátil HP no tiene GPU
    dedicada", por debajo del umbral. Para eso está `buscar_en_memoria`.
- De punta a punta con la cadena del usuario:
  - "me llamo Alejandro, llámame Alex" → pidió permiso y lo apuntó en el perfil;
  - "recuerda que el examen es el 12" → lo recordó sin preguntar;
  - en una conversación nueva respondió las dos cosas.

  Aun teniendo el recuerdo delante, el modelo hizo una búsqueda de más: es inofensivo.
- El panel Perfil, en la demostración.

**Sin verificar**:
- la ventana real con pywebview;
- la voz con un `usuario.md` editado desde la ventana en otro equipo y traído con `git pull`.
