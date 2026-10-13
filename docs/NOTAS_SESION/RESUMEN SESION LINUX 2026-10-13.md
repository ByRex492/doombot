# Resumen sesión Linux — 2026-10-13

Sesión desde el portátil Linux (Ubuntu, GNOME en X11, sin GPU: perfil `cpu_only`), con Claude
Code. Sin `.venv` propio, sin Ollama y sin clave de Anthropic: todo se verificó con un entorno
virtual temporal y dobles de prueba, salvo lo que se dice expresamente.

**Dos ramas, ninguna fusionada a `main`** (fusionar desde el sobremesa, como pide CLAUDE.md):

| Rama | Qué | Depende de |
|---|---|---|
| `tarea/extras-opcionales` | Arreglo: sin el extra `voice-tts`, las órdenes reventaban | `main` |
| `tarea/agente-local` | Agente local nuevo (D-033) | la anterior (la incluye) |

Fusionar solo `tarea/agente-local` mete las dos.

## 1. El arreglo (`tarea/extras-opcionales`)

El registro de órdenes importa `doombot.tts.orders` en todo arranque; eso ejecutaba
`tts/__init__.py`, que importaba `synth` -y con él `kokoro_onnx` y, vía `dsp.py`, `scipy`-. En un
equipo sin `voice-tts` la primera orden reventaba, también en modo escrito. En el sobremesa no se
nota porque allí está todo instalado.

- `tts/__init__.py` importa `KokoroSynthesizer` al pedirlo; `MODELO_ONNX`/`VOCES_BIN` pasan a
  `tts/download.py`.
- `identity.py`: "hablar" mira `kokoro_onnx` con `find_spec`.
- `test_kokoro`, `test_hud_server` se saltan sin su extra; `test_micro_por_fragmento` pasa
  `opener` (sondeaba el micro real, como los dos arreglados en b823d99).

**Comprobar en el sobremesa:** que con `voice-tts` instalado el diagnóstico sigue diciendo
"hablar" (sin "(no)").

**Visto y no tocado:** `tts/dsp.py` importa `scipy`, pero `scipy` solo está declarado en el extra
`voice-aec`, no en `voice-tts`. Un equipo con solo `voice-tts` no podría hablar. Decidir en
integración si `voice-tts` lo pide también.

## 2. El agente local (`tarea/agente-local`, D-033)

Pedido: un agente que reciba órdenes escritas y actúe solo, contando lo que hace y qué abre, con
acceso a todo el equipo, aplicaciones y un navegador que controle. Decidido con el usuario:
**cerebro intercambiable** (Ollama o Claude), **autónomo salvo lo irreversible**, **navegador
propio** aparte del suyo. Todo el porqué en D-033.

```
python -m doombot agente          # consola propia, al estilo Claude Code
agente <orden>                    # la misma pieza desde python -m doombot chat
```

Archivos tocados fuera de `agent/` (integración, revisar al fusionar): `backends/base.py`
(contrato `ToolCaller` y tipos neutros), `backends/ollama.py` y `backends/anthropic.py` (método
`paso()`), `config.py` (`DOOMBOT_AGENT_BRAIN`, `DOOMBOT_AGENT_MODEL`), `phrases/matcher.py`
(orden `agent`), `__main__.py`, `identity.py`, `pyproject.toml` (extra `agent-web`).

**Número de decisión:** se usó **D-033**. Si el sobremesa ha escrito otra D-033 entretanto,
renumerar esta al fusionar.

### Verificado aquí
- 408 tests sin hardware en verde, `ruff` limpio.
- Contra el escritorio real: descubre 55 aplicaciones; "navegador", "archivos", "configuración",
  "calculadora" encuentran la correcta (hizo falta usar las categorías del `.desktop`: GNOME
  traduce los nombres con gettext).
- Un cerebro de guion abrió la Calculadora, vio su ventana con `wmctrl`, pidió confirmación y la
  cerró. De punta a punta, con las herramientas reales.
- La consola arranca sin modelo y avisa de que el cerebro no responde, sin romperse.

### Sin verificar
- **Ningún modelo real ha llevado el bucle.** Ni Ollama ni Claude. El formato de `tool_calls` de
  Ollama y el de `tool_use` de Anthropic están hechos según sus APIs y probados con transportes
  falsos, no contra el servidor real.
- ~~El navegador propio no se ha lanzado~~ — lanzado después, ver sección 3.
- Windows: el descubrimiento por `.lnk`, `os.startfile` y `tasklist`/`taskkill` están escritos y
  con test de descubrimiento, pero no se han ejecutado en Windows.

## 3. Varios modelos gratuitos (D-034) y navegador probado de verdad

Mismo día, misma rama `tarea/agente-local`. Pedido: modelos gratuitos, varios, para contrastar
y no depender de uno.

- `backends/openai_compat.py`: una clase para todos los proveedores con API tipo OpenAI
  (Groq, Gemini, NVIDIA, OpenRouter, Mistral, Cerebras, GitHub). Catálogo en
  `backends/proveedores.py`, lista en `DOOMBOT_MODELOS=proveedor:modelo,...`.
- `backends/varios.py`: `Cadena` (si uno falla o se queda sin cuota, el siguiente) y `Consejo`
  (todos a la vez y un juez que compara). Backend `varios` en chat y agente; `/contrasta` y
  "contrasta ..." para el consejo.
- `agent/revision.py`: segunda opinión de otro modelo antes de lo irreversible.
- Integración tocada además: `chat.py` (`_generador` acepta `varios`), `config.py`
  (`modelos`, `claves`, `agent_revisor`), `phrases/matcher.py` (orden `crosscheck`).

**Navegador propio, ya probado en real**: en este portátil hay `.venv` del proyecto (Python
3.12, `.[dev,agent-web]`) y Chromium de Playwright (658 MB en `~/.cache/ms-playwright`, más de
lo que estimé: trae también el *headless shell* y ffmpeg). Cargó example.com, leyó su texto,
pulsó un enlace y volvió atrás.

**`.env` creado en este portátil** (no se versiona) con `varios` en chat y agente. Faltan las
claves: el usuario las crea (Groq, Google AI Studio, NVIDIA) y las pega.

**Sin verificar**: ningún proveedor real, ni los IDs exactos de Gemini y NVIDIA en sus capas
gratuitas.

## 4. La aplicación: planeta, registro y chat (D-035)

Pedido: una interfaz propia "como Claude Code", sin abrir un HTML en el navegador; una esfera
como un planeta que reaccione, y un chat debajo que diga lo que piensa y qué abre.

- `python -m doombot ventana`: ventana pywebview con `ui/ventana/doom.html` (planeta WebGL +
  registro + caja de texto). El agente en el mismo proceso, por `src/doombot/ventana/puente.py`.
- El planeta cambia de modo según la `familia` de cada herramienta (`web`, `apps`, `ficheros`,
  `terminal`), y además: pensando, esperando permiso (naranja), respondiendo, error.
- Agente: `Herramienta.familia`, `Agente.observar` (eventos para interfaces) y `Agente.parar()`.
- Integración tocada además: `paths.py` (`UI_DIR`), `__main__.py` (`ventana`).
- `doom.html#demo` simula una orden completa sin agente: sirve para diseñar.

**En este portátil**: extra `hud` instalado en `.venv`, y `gi`/`cairo` del sistema enlazados
dentro del `.venv` (ver README, "La aplicación"). Ventana real probada con un cerebro de guion:
abrió la Calculadora con las herramientas reales y lo contó en el registro.

**Sin verificar**: con modelo real, en Windows (WebView2) y como ejecutable. Y la voz: el planeta
aún no reacciona al micrófono ni a Kokoro como el HUD; juntar los dos es lo siguiente.

## Qué hacer primero en el sobremesa

1. Fusionar `tarea/agente-local` (`git merge --no-ff`), revisar los ficheros de integración de
   arriba, `pytest -m "not hardware"`.
2. `pip install -e ".[agent-web]"` y `python -m playwright install chromium`. Copiar las claves
   gratuitas del `.env` del portátil y añadir `ollama:gemma4:12b` al final de `DOOMBOT_MODELOS`.
3. Probar `python -m doombot agente` con `gemma4:12b` (`DOOMBOT_AGENT_BRAIN=ollama`) y, si hay
   clave, con Claude (`DOOMBOT_AGENT_BRAIN=anthropic`), con órdenes como:
   - "abre el bloc de notas" / "abre el explorador de archivos en Descargas"
   - "busca en la web el tiempo en Madrid y dime qué temperatura hace" (navegador propio)
   - "ábreme youtube" (navegador del usuario)
   - "qué ventanas tengo abiertas" / "cierra la calculadora" (debe preguntar)
   - "borra la carpeta X" (debe preguntar; contestar no y ver que no insiste)
   Anotar cuántas resuelve cada cerebro: eso decide el valor por defecto de `DOOMBOT_AGENT_BRAIN`.
4. En Windows: comprobar que "abre la calculadora" encuentra el acceso del menú Inicio.
5. `python -m doombot ventana` en Windows: que abre con WebView2, que el planeta se ve (WebGL) y
   que el navegador propio funciona desde la ventana (Playwright en el hilo del agente).

## Ideas que quedan para después
- El agente por voz: la orden `agente` ya pasa por `Sesion.decir`/`preguntar`, falta oírlo.
- Que el HUD muestre los pasos del agente (otro tipo de evento en D-022).
- Control del escritorio por capturas (necesita modelo con visión; descartado por ahora en D-033).
