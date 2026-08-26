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
Medido en el portátil con `small` en CPU: **RTF 0,28**, cuatro veces más
rápido que tiempo real.

## Memoria

Guarda cosas y las recupera **por significado, no por palabras**:

```python
from doombot.backends.embeddings import FastEmbedder
from doombot.memory import Memory

with Memory(FastEmbedder.from_config()) as m:
    m.remember("El portatil lleva una GTX 1050 con 3 GB de VRAM")
    m.recall("cuanta memoria grafica tengo?")   # lo encuentra
```

Ninguna palabra de la pregunta aparece en el recuerdo. Es lo que hace el
`Embedder`: compara vectores, no texto.

Vive en SQLite dentro de la carpeta de datos del usuario, **fuera del
repositorio** — `python -m doombot` dice dónde. La similitud se calcula en
Python: con unos miles de recuerdos cuesta milisegundos, y evita una
dependencia binaria por equipo.

El umbral por defecto es **0,35**, medido: los aciertos claros puntúan entre
0,51 y 0,67 y el ruido se queda bajo 0,26. Por debajo de ese umbral no se
devuelve nada, y es deliberado — **es preferible no recordar nada que recordar
algo que no viene a cuento**, porque un modelo pequeño construye sobre el
contexto que le des aunque no responda a la pregunta.

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
