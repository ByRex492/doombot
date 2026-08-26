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
