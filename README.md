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

Para trabajar también la parte de voz: `pip install -e ".[dev,voice]"`.

Requiere **Python 3.12** exacto. Ni 3.13 ni 3.14: el stack de audio e IA no
publica wheels para esas versiones.

## Cómo evita atarse a un equipo

Hay tres reglas, y las tres están cubiertas por tests:

| Regla | Dónde vive | Qué la comprueba |
|---|---|---|
| Ninguna ruta absoluta en el código | `paths.py` deriva todas las rutas | `test_sin_rutas_absolutas_escritas_a_mano` |
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
| `TextGenerator` | `generate`, `stream`, `model_name` | `OllamaGenerator` |
| `Transcriber` | `transcribe` | `WhisperTranscriber` |
| `Embedder` | `embed`, `dimensions` | pendiente |

Son `Protocol`, no clases base: una implementación no hereda ni importa nada,
le basta con tener los métodos. `OllamaGenerator` sirve igual para el Ollama
local que para el del sobremesa por red — solo cambia `DOOMBOT_OLLAMA_HOST`.

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

La similitud se calcula en Python, sin dependencias binarias por equipo. Tiene
un techo medido: una búsqueda cuesta ~76 ms fijos de vectorizar la pregunta más
unos 62 ms por cada mil recuerdos guardados. Con el presupuesto de ~200 ms que
necesita la voz, el límite práctico ronda los **1.500 recuerdos**; a partir de
ahí tocará `sqlite-vec` o numpy.

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
