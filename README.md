# jarvis-local

Asistente personal por voz que funciona **enteramente en local**: sin llamadas a la nube, sin
coste por uso y sin que el audio salga de la máquina.

Bilingüe (español e inglés), con activación por palabra clave, interfaz gráfica propia y
capacidad de controlar el PC para automatizar tareas reales.

> **Estado: en construcción.** Capa 1 (LLM) en curso. Este README se actualiza a medida que
> cada capa se valida. El porqué de cada decisión técnica está en [docs/decisiones.md](docs/decisiones.md).

---

## Arquitectura

El proyecto se construye por capas, validando cada una antes de pasar a la siguiente.

| Capa | Función | Herramienta | Estado |
|------|---------|-------------|--------|
| 1. Cerebro | Razonamiento y generación de respuestas | Ollama + modelo local | 🔨 En curso |
| 2. Oídos | Palabra de activación y voz a texto | openWakeWord + faster-whisper | ⬜ Pendiente |
| 3. Voz | Texto a voz | Kokoro TTS | ⬜ Pendiente |
| 4. Manos | Control del PC y las aplicaciones | Por decidir | ⬜ Pendiente |
| 5. Interfaz | HUD / ventana | Por decidir | ⬜ Pendiente |
| Orquestador | Une todas las capas | Python | 🔨 Crece con cada capa |

El orquestador **no se construye al final**: nace con la Capa 1 y se amplía cada vez que se
añade una pieza, de modo que en todo momento existe algo funcionando de extremo a extremo.
El razonamiento completo está en la decisión D-006.

---

## Requisitos

**Hardware de referencia** (el equipo donde se desarrolla):

- CPU AMD Ryzen 7 5800X · 32 GB RAM
- GPU NVIDIA RTX 5060 Ti, 16 GB VRAM (14,8 GiB utilizables para modelos)
- Windows 11

La GPU es el componente crítico: el LLM, Whisper y el TTS deben caber **simultáneamente** en
VRAM. Con menos de 12 GB habría que recortar el tamaño del modelo de lenguaje.

**Software:**

- [Python 3.12](https://www.python.org/downloads/) — no vale el 3.14, ver decisión D-001
- [Ollama](https://ollama.com/download) 0.33 o superior
- Git

---

## Instalación

```bash
git clone <url-del-repo> jarvis-local
cd jarvis-local
```

Crear el entorno virtual **con Python 3.12 explícitamente**. Si se omite la versión, Windows
usa el intérprete por defecto, que puede ser otro:

```bash
py -3.12 -m venv .venv
```

Activarlo. En PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Si PowerShell bloquea el script por política de ejecución, permitir los scripts locales para el
usuario actual (no requiere privilegios de administrador):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

Descargar los modelos de lenguaje (unos 13 GB en total):

```bash
ollama pull gemma4:12b
```

---

## Comprobar que la GPU se está usando

Es el fallo silencioso más habitual: Ollama funciona igualmente sobre CPU, pero unas veinte
veces más lento. Que el log detecte la GPU al arrancar **no garantiza** que la use durante la
inferencia.

La comprobación fiable es medir la VRAM ocupada mientras el modelo responde:

```bash
ollama ps
```

La columna `PROCESSOR` debe indicar `100% GPU`. Si aparece `CPU` o un reparto mixto, el modelo
no cabe entero en memoria y hay que bajar de tamaño o de cuantización.

---

## Extensiones de VSCode recomendadas

| Extensión | ID | Para qué |
|-----------|----|----------|
| Python | `ms-python.python` | Detecta intérpretes y entornos virtuales, ejecuta y depura |
| Pylance | `ms-python.vscode-pylance` | Autocompletado y comprobación de tipos en tiempo real |
| Ruff | `charliermarsh.ruff` | Linter y formateador en uno. Sustituye a flake8, black e isort |
| Even Better TOML | `tamasfe.even-better-toml` | Resalta los ficheros de configuración |
| Error Lens | `usernamehw.errorlens` | Muestra los errores en la propia línea. Opcional |

---

## Documentación

- [docs/decisiones.md](docs/decisiones.md) — qué se decidió, por qué, y qué se descartó
