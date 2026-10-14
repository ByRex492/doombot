# D.O.O.M

Asistente de voz local. Se desarrolla desde dos equipos, y el proyecto está
construido para no notar en cuál de los dos está corriendo.

## Empezar en una máquina nueva

```powershell
git clone https://github.com/ByRex492/doombot.git
cd doombot
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -m doombot
```

Ese último comando dice qué perfil ha elegido y por qué. Es lo primero que
conviene ejecutar al sentarse en un equipo distinto.

Para hablar con el modelo del perfil activo:

```powershell
python -m doombot "¿qué hora es un buen momento para hacer commit?"
```

### El lanzador: `doom`

Para no depender de acordarse de activar el entorno:

```powershell
.\doom            # diagnóstico
.\doom escuchar tecla
.\doom "que hora es"
```

`doom.cmd` y `doom.ps1` llaman al Python del `.venv` directamente. Es la forma
recomendada de usarlo.

### El entorno virtual tiene que estar activo

`doombot` se instala **dentro del `.venv`**, no en el Python del sistema. Si
sale esto:

```
No module named doombot
```

es que el terminal está usando el Python global. Actívalo, una vez por
terminal:

```powershell
.\.venv\Scripts\Activate.ps1
```

Se nota porque el prompt pasa a empezar por `(.venv)`. Si PowerShell lo
bloquea con *running scripts is disabled*:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

En los terminales que abre VSCode se activa solo. Y para lanzarlo sin activar
nada:

```powershell
.\.venv\Scripts\python.exe -m doombot "hola"
```

Ojo con el nombre: la carpeta del portátil es `doombot-local`, pero el módulo
de Python es `doombot`. `python -m doombot`, siempre.

Para trabajar también la parte de voz: `pip install -e ".[dev,voice]"`. Los
extras se combinan según lo que necesites (ver `pyproject.toml`):

| Extra | Trae | Para |
|---|---|---|
| `voice` | Whisper, wake word, embeddings, micrófono | Oír y transcribir (Capa 2) |
| `voice-cuda` | Librerías CUDA de Whisper | Transcribir en GPU NVIDIA |
| `voice-tts` | `kokoro-onnx` | Hablar en voz alta (D-021) |
| `voice-aec` | Cancelación de eco + VAD | Barge-in: cortar a D.O.O.M hablándole encima (D-027) |
| `hud` | `pywebview`, `websockets` | La ventana del HUD (D-016, D-022) |
| `agent-web` | `playwright` | El navegador propio del agente (D-033); después, `python -m playwright install chromium` |

Requiere **Python 3.12** exacto. Ni 3.13 ni 3.14: el stack de audio e IA no
publica wheels para esas versiones.

## Cómo evita atarse a un equipo

Hay tres reglas, y las tres están cubiertas por tests:

| Regla | Dónde vive | Qué la comprueba |
|---|---|---|
| Ninguna ruta absoluta en el código | `paths.py` deriva todas las rutas | `test_sin_rutas_absolutas` |
| El hardware se detecta, no se escribe | `profiles.py` + `profiles.toml` | `test_seleccion_por_vram` |
| Lo local no se versiona | `.env` (plantilla en `.env.example`) | `test_env_no_esta_versionado` |

Los datos que genera D.O.O.M —memoria, registros, modelos— viven **fuera del
repositorio**, en la carpeta de datos del usuario. `python -m doombot` dice
dónde.

## Perfiles

`profiles.toml` guarda las combinaciones de modelo y voz medidas en cada tipo
de máquina. Se elige por VRAM disponible, no por nombre de equipo: un hostname
cambia y una tarjeta se sustituye.

| Perfil | VRAM | Modelo | Voz |
|---|---|---|---|
| `workstation` | ≥ 8 GB | `gemma4:12b` | `small` en CUDA |
| `laptop` | ≥ 2 GB | `llama3.2:3b`, `num_gpu 99` | `small` en CPU |
| `cpu_only` | sin GPU | `qwen3:1.7b` | `base` en CPU |

Para forzar uno en pruebas: `DOOMBOT_PROFILE=workstation` en `.env`.

## Estructura

Ver [docs/estructura.md](docs/estructura.md) para qué hace cada carpeta y por
qué está donde está.

## Backends

La lógica habla con los contratos de `backends/base.py`, nunca con un motor
concreto:

| Contrato | Qué promete | Implementación |
|---|---|---|
| `TextGenerator` | `generate`, `stream`, `model_name` | `OllamaGenerator`, `AnthropicGenerator` |
| `Transcriber` | `transcribe` | `WhisperTranscriber` |
| `Embedder` | `embed`, `dimensions` | `FastEmbedder` |
| `WakeDetector` | `check`, `reset`, `name` | `WakeWord`, `PushToTalk` |

Son `Protocol`, no clases base: una implementación no hereda ni importa nada,
le basta con tener los métodos. `OllamaGenerator` sirve igual para el Ollama
local que para el del sobremesa por red — solo cambia `DOOMBOT_OLLAMA_HOST`.

**Dos `TextGenerator`, seleccionables con `DOOMBOT_LLM_BACKEND`.** Ollama es
el que corre por defecto (D-009: latencia local, funciona sin conexión).
`AnthropicGenerator` habla con la API de Claude por `httpx` crudo, sin el SDK,
y pesa más la calidad de razonamiento a costa de mandar la conversación fuera
del equipo. También se puede pedir puntualmente sin cambiar el backend por
defecto — ver "pregunta a Claude" en Órdenes.

`WhisperTranscriber` necesita el extra `voice`. Carga el modelo de forma
perezosa, así que construirlo para leer su configuración no cuesta la carga.

Medido en el portátil con `small` en CPU: **RTF entre 0,28 y 0,59** según el
estado del equipo — siempre por debajo de 1, que es la condición para que la
voz no se acumule. Hay un coste fijo por llamada de unos 4 segundos, así que
las frases muy cortas dan RTF alto sin que eso indique un problema.

## Memoria

Guarda cosas y las recupera **por significado, no por palabras**:

```python
from doombot.backends.embeddings import FastEmbedder
from doombot.memory import Memory

with Memory(FastEmbedder.from_config()) as m:
    m.remember("El portatil lleva una GTX 1050 con 3 GB de VRAM")
    m.recall("cuanta memoria grafica tengo?")  # lo encuentra
```

Ninguna palabra de la pregunta aparece en el recuerdo. Es lo que hace el
`Embedder`: compara vectores, no texto.

Vive en SQLite dentro de la carpeta de datos del usuario, **fuera del
repositorio** — `python -m doombot` dice dónde. Cada recuerdo ocupa unos 2 KB.

Una búsqueda cuesta ~76 ms fijos de vectorizar la pregunta más el recorrido de
los vectores. Con el presupuesto de ~200 ms que necesita la voz, el límite
práctico ronda los **1.500 recuerdos** en Python puro, y sube a unos **6.000**
con el núcleo nativo de `native/doomkit` compilado, que va 4x más rápido.
Es opcional: ver [native/README.md](native/README.md).

El umbral por defecto es **0,35**, medido: los aciertos claros puntúan entre
0,51 y 0,67 y el ruido se queda bajo 0,26. Por debajo de ese umbral no se
devuelve nada, y es deliberado — **es preferible no recordar nada que recordar
algo que no viene a cuento**, porque un modelo pequeño construye sobre el
contexto que le des aunque no responda a la pregunta.

## Órdenes

La capa refleja: rápida, determinista y **sin modelo de por medio**. Cuando
dices "para", D.O.O.M tiene que callar al instante — no pasar la frase por un
3B a 29 tok/s y esperar a ver qué opina.

```python
from doombot.phrases import default_matcher

m = default_matcher()
m.match("¡DOOM! Activa el modo silencioso.")  # Match(command='silence')
m.match("recuerda que el pan esta caro")  # argument='el pan esta caro'
m.match("que tiempo hace mañana?")  # None — no es una orden
```

Devolver `None` es lo normal: casi nada de lo que se dice son órdenes, sino
cosas que pasar al modelo.

Lo que llega no es texto limpio, sino lo que devuelve Whisper, así que todo
pasa por `normalize` (minúsculas, sin tildes ni signos, incluidos `¡` y `¿`) y
la búsqueda admite tres grados: exacta, contenida en una frase más larga, y
tolerante a erratas del dictado. Verificado dictando las diez órdenes por
micrófono: **10/10**, incluyendo casos donde Whisper transcribió "¡Dum!" por
"Doom" y se comió una letra.

Mil reconocimientos tardan menos de un segundo.

Cada capa declara las suyas en su propio `orders.py` (D-020): `chat.py` no es
el cuello de botella por el que pasa toda orden nueva. Además de las básicas
de arriba:

| Orden | Qué hace | Capa |
|---|---|---|
| `recuerda que yo <algo>` | Guarda un hecho SOBRE el usuario, siempre presente en el prompt | `memory` |
| `ejecuta esto: <tarea>` | Delega una tarea real en Claude Code (`claude -p`, modo `plan` por defecto) | `actions` |
| `activa el flujo: <nombre>` | Dispara un *workflow* de n8n de la lista blanca (D-030) | `actions` |
| `pregunta a claude: <algo>` | Manda esta pregunta a Claude, sin cambiar el backend por defecto (D-032) | `backends` |
| `apunta el progreso: <algo>` | Añade una nota al vault de Obsidian del día | `obsidian` |
| `lee el archivo <cuál>` | Lee un fichero del buzón (`data_dir()/buzon`) y responde sobre él | `files` |

**`ejecuta esto` y `activa el flujo` piden confirmación hablada antes de
tocar nada de verdad** (D-031) — salvo `ejecuta esto` en modo `plan`, donde ya
no hay nada real que confirmar porque el agente solo propone. Silencio o
cualquier respuesta que no sea una afirmación clara ("sí", "confirmo",
"adelante"...) se toma como negativa.

## Voz

D.O.O.M escucha y, con `voice-tts` instalado, también habla. El bucle manos
libres cierra las dos mitades:

    DORMIDO --activación--> ESCUCHANDO --silencio--> TRANSCRIBIENDO --> LLM --> HABLANDO --> DORMIDO

```powershell
.\doom voz               # manos libres: activación -> escucha -> LLM -> voz
.\doom voz tecla          # igual, disparado con una pulsación en vez de la palabra
.\doom voz-descargar      # trae los modelos de Kokoro la primera vez
.\doom escuchar           # solo la mitad de oír, sin responder en voz
.\doom escuchar tecla     # se dispara con una pulsación
.\doom micro              # lista los micrófonos
.\doom micro probar 12    # graba con un dispositivo concreto
```

La palabra de activación (`openWakeWord`, modelo `hey_jarvis`) está siempre
despierta porque es barata: solo busca un patrón acústico. Dejar a Whisper
transcribiendo en continuo costaría entre el 28% y el 59% de un núcleo, y
además transcribiría todo lo que se hable en la habitación.

`PushToTalk` cumple el mismo contrato y sirve para depurar sin depender de que
el detector te oiga.

**La síntesis** (`tts/synth.py`) usa Kokoro por ONNX Runtime en CPU, con
troceo por frase propio (D-021): la primera frase se sintetiza mientras el
LLM sigue generando el resto, así la voz no espera la respuesta entera.

**Barge-in real** (D-027, extra `voice-aec`): hablarle encima a D.O.O.M lo
corta al instante — cancelación de eco (`pyaec`) + detector de voz
(`webrtcvad`), sin necesitar la palabra de activación de nuevo. Sin ese extra,
"para" (D-023) sigue siendo la forma de cortarlo.

## Interfaz (HUD)

Extra `hud`. Una ventana de escritorio (`pywebview`) con un orbe que refleja
el estado del turno — escuchando, pensando, hablando — servida por
`hud_server.py` vía WebSocket (D-016, D-022). Es opcional en los dos sentidos:
sin el extra instalado no se intenta arrancar, y si el puerto está ocupado
D.O.O.M sigue igual sin ella.

## Acciones

D.O.O.M puede tocar el mundo real, de dos formas con riesgos distintos (ver
`docs/estructura.md`):

- **`actions/claude_code.py`** delega tareas de código -editar ficheros,
  ejecutar comandos- en `claude -p`, sin interfaz. Modo `plan` por defecto:
  propone sin ejecutar nada; pasar a uno que ejecuta de verdad
  (`DOOMBOT_AGENT_PERMISSION_MODE=acceptEdits` o `bypassPermissions`) es una
  decisión explícita en `.env`, nunca el valor de fábrica (D-014).
- **`actions/n8n.py`** dispara *workflows* de n8n por webhook (D-030). D.O.O.M
  siempre inicia, n8n nunca — no hay servidor nuevo escuchando entradas
  ajenas. Un webhook no tiene modo `plan`, así que la salvaguarda es una lista
  blanca en `.env` (`DOOMBOT_N8N_WORKFLOWS`): un nombre que no esté ahí no
  dispara nada.

Ambas piden confirmación hablada antes de ejecutar de verdad (D-031, ver
Órdenes arriba).

### El agente local

```
python -m doombot agente
```

Una consola al estilo de Claude Code: escribes lo que quieres y D.O.O.M lo
hace solo, contando cada paso (D-033). Así se ve (ejemplo):

```
doom> abre el navegador y busca el tiempo en Madrid
  · Abro tu navegador con la búsqueda.
  → Abro el tiempo en Madrid en tu navegador
    ✓ Abierta https://duckduckgo.com/?q=el+tiempo+en+Madrid en el navegador del usuario.
D.O.O.M.: Te he abierto la búsqueda del tiempo en Madrid.
```

Reconoce las aplicaciones instaladas (por nombre o por tipo: "el navegador",
"algo para música"), las abre y las cierra; abre páginas en tu navegador o las
lee y maneja en uno propio, aparte del tuyo (extra `agent-web`); lee, busca y
escribe ficheros; ejecuta comandos. **Pregunta antes de lo irreversible**:
sobrescribir, cerrar una aplicación, cualquier comando que no sea de solo
lectura, pulsar "comprar"/"enviar"/"aceptar", o leer ficheros con claves.

El cerebro es intercambiable (`DOOMBOT_AGENT_BRAIN=ollama|anthropic`). Con
Ollama todo se queda en el equipo, pero un modelo pequeño elige mal las
herramientas; con Claude decide mucho mejor, a cambio de que la conversación
-y lo que el agente lee- salga de la máquina. `/nuevo` olvida lo anterior,
`/abiertas` lista lo que ha abierto, Ctrl+C corta la tarea. Desde
`python -m doombot chat` es la orden `agente <lo que sea>`.

### La aplicación

```
python -m doombot ventana
```

D.O.O.M en su propia ventana, como cualquier programa, con aspecto de HUD
(D-036): en el centro un núcleo holográfico que reacciona -cambia de color y
de gesto según use el navegador, aplicaciones, ficheros o la terminal, y se
pone ámbar cuando espera tu permiso-; a los lados, los paneles SISTEMA y
ACTIVIDAD unidos a él por circuitos; debajo, lo que piensa, lo que abre y lo
que hace, paso a paso, y la línea de órdenes. En **Personalizar** se elige
tema (Jarvis, Holograma, Neón, Matriz, Glaciar, Carmesí) o colores propios,
brillo, rejilla, velocidad y efectos; se guarda en este equipo. Las confirmaciones son botones, con la segunda opinión del otro
modelo debajo. Mientras trabaja, el botón de enviar pasa a ser **Parar**.

Antes de darte una respuesta que se apoya en páginas o ficheros, otro modelo
de la lista la repasa: comprueba los datos contra lo consultado y las fuentes
(D-039, `DOOMBOT_AGENT_REFINAR`). Para leer páginas usa Jina Reader, que no
necesita clave ni abre el navegador; con `DOOMBOT_JINA_API_KEY`, gratuita,
puede leer más por minuto.

**Primeros pasos.** Si no hay ningún modelo configurado, la ventana empieza
por ahí (y después está siempre en la cabecera): cómo conseguir cada clave
gratuita, un enlace a la página, una caja para pegarla y los botones
**Guardar** -la escribe en `.env`, que queda legible solo por ti- y
**Probar** -una petición mínima para ver que responde-. También dice si está
el navegador propio del agente y si hay un Ollama local.

Las claves son de tu cuenta, no del equipo: la misma vale en cualquier
ordenador, pero `.env` no se sube a GitHub, así que en cada equipo se pegan
de nuevo.

**Gráficas.** Si le pides que represente datos, estadísticas, funciones o
vectores ("represéntame u=(4,1) y v=(1,3)", "haz un histograma de estas
notas", "compara las ventas de 2025 y 2026 en barras"), el núcleo se aparta y
aparece la gráfica: ejes, barras, líneas, sectores, histograma o dispersión
con recta de regresión. Las medias, porcentajes y demás los calcula D.O.O.M
con exactitud, no el modelo. **Ampliar** ocupa también el registro y
**Núcleo** vuelve (D-037).

**Modos y conversaciones.** Junto a la línea de órdenes se elige el modo: *Global* (todo, con
los expertos a mano) o una skill -Diseño, Investigación, Programación, Ciencias-, cada una con
sus instrucciones, sus herramientas y sus modelos. Cuando le dices algo como "recuerda que
prefiero…", lo apunta (tras confirmarlo) y lo tiene en cuenta en ese modo y en el global; en el
mismo selector se ve lo aprendido y se puede olvidar. Las skills son carpetas en `skills/`
(formato agentskills.io): una nueva es una carpeta nueva. A la izquierda, en *Conversaciones*,
el historial por carpetas: se retoma cualquier conversación donde se dejó, con su modo.

**Icono en el menú y en el dock (Linux):**

```bash
.venv/bin/python -m doombot lanzador
```

Crea `~/.local/share/applications/doombot.desktop` con el icono del núcleo
y lo fija al final del dock; desde ahí se abre sin terminal, y lo que escriba
la aplicación va a `ventana.log` en la carpeta de datos. `--sin-dock` no lo
fija. Para quitarlo, basta con borrar ese fichero.

Necesita el extra `hud` (`pywebview`). En Linux usa el GTK y el WebKit del
sistema; como el `.venv` no ve los paquetes del sistema, se enlazan una vez:

```bash
ln -s /usr/lib/python3/dist-packages/gi .venv/lib/python3.12/site-packages/
ln -s /usr/lib/python3/dist-packages/cairo .venv/lib/python3.12/site-packages/
```

En Windows no hace falta nada: usa WebView2, que ya trae el sistema.

### Varios modelos gratuitos

Para no depender de un solo modelo ni de un solo proveedor (D-034):

```
DOOMBOT_AGENT_BRAIN=varios
DOOMBOT_MODELOS=groq:openai/gpt-oss-120b,gemini:gemini-3.8-flash,nvidia:nvidia/nemotron-3-super-120b-a12b
DOOMBOT_GROQ_API_KEY=...
```

- **En cadena**: responde el primero; si falla o se le acaba la cuota gratuita, el siguiente.
- **En consejo**: `/contrasta <pregunta>` (o `contrasta ...` en el chat) pregunta a todos a la
  vez y un juez dice en qué coinciden y en qué no.
- **Segunda opinión**: antes de algo irreversible, otro modelo distinto del que lo propuso dice
  si encaja con lo que pediste; lo ves junto a la pregunta de confirmación.

Las claves son gratuitas y sin tarjeta (ver `.env.example`). Ojo: con proveedores en la nube, lo
que el agente lee sale del equipo.

## Desarrollo

```powershell
pytest                      # todo
pytest -m "not hardware"    # solo lo que no necesita Ollama ni GPU
ruff check .
ruff format .
```

Los tests marcados `hardware` necesitan un Ollama arrancado. El resto corre en
cualquier equipo: los backends aceptan un cliente HTTP por parámetro, así que
se prueban con uno falso.
