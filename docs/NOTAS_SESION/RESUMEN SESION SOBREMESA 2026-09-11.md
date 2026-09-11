# Resumen sesión sobremesa — 2026-09-11

Sesión de integración: cerrar lo que `capa/tts` dejó pedido en su nota del 10/09 y que no podía
tocar ella misma (`backends/base.py`, `pyproject.toml`, `identity.py`, `estructura.md` son de
integración). Commit `180dcaa`, ya en `origin/main`.

---

## Lo que se hizo

### 1. `_ESCALA_NIVEL`: de 3,0 a ojo a 13 medido

`capa/tts` midió el RMS real de Kokoro (ya procesado, el que sale de `say()`) en ventanas de
50 ms: mediana 0,035, p90 0,073, pico 0,11 — cuatro veces más bajo de lo que suponía el 3,0
provisional (que asumía RMS típico 0,15). Con ese número el orbe del HUD apenas se habría
movido mientras D.O.O.M hablaba. Con 13, la mediana queda en ~0,45 y el p90 cerca de 0,9, el
mismo criterio que ya proponía el comentario original pero con la cifra real.

Queda anotado en el propio código: el número vale para ventanas cortas (~50 ms, que es como el
orquestador va a trocear el audio para alimentar el HUD a 30-60 Hz). Sobre una frase entera el
promedio sale más bajo porque las pausas entre palabras cuentan.

### 2. Extra `voice-tts` en `pyproject.toml`

Solo `kokoro-onnx>=0.6` (trae `onnxruntime`, `phonemizer`, `espeakng-loader` como transitivas).
Sin `onnxruntime-gpu`: no hay ruta de GPU utilizable ahora mismo (pide `cublasLt64_13.dll` y el
paquete CUDA 13 en PyPI es un placeholder vacío — ver D-021), y el runtime normal pesa diez
veces menos.

### 3. `identity.py`: "escuchar" y "hablar", separadas

La nota de `capa/tts` pedía sumar una comprobación del paquete `tts` a la capacidad
"escuchar". Se optó por partirla en dos en vez de eso: la capacidad decía "escuchar por el
micrófono **y** responder en voz alta", y con `tts/` como paquete propio D.O.O.M habría
seguido afirmando que responde en voz alta por el mero hecho de tener micrófono — la clase de
mentira que este módulo existe para evitar. Ahora cada capacidad mira su propio paquete
(`voice` / `tts`).

### 4. `estructura.md` y `__init__.py` con el módulo `tts`

Los dos tests de `test_docs.py` que estaban en rojo en `capa/tts` (por ser ficheros de
integración) pasan ahora.

---

## Verificado

Suite completa tras la fusión: **291 pasan, 1 omitida, 1 falla** — la que falla es la conocida,
el binario `claude` sin instalar en esta máquina (Capa 4, pendiente desde el 01/09). D-021
(la decisión de `capa/tts`) ya estaba documentada por esa rama antes de fusionar; no hizo falta
tocarla.

---

## Estado de las ramas paralelas

| Rama | Estado |
|---|---|
| `capa/tts` | Fusionada a `main`. Pendiente de confirmar por escucha: `ef_dora` vs `em_alex` como voz por defecto (seis muestras mandadas por chat, ver nota del 10/09). |
| `capa/hud` | En marcha, sin fusionar. Cerrando el estilo artístico (cuatro direcciones visuales en prototipo, aún sin elegir) antes de abordar el transporte WebSocket. |

---

## Pendiente, heredado de sesiones anteriores

Sin cambios hoy: elegir micrófono real (`DOOMBOT_AUDIO_INPUT`), `OLLAMA_MAX_LOADED_MODELS=1`,
instalar el CLI `claude`, confirmar la voz de Kokoro. Ver la nota del 10/09 para el resto
(continuidad de conversación, `repeat`, PDF/ofimática, n8n, enrutador velocidad/calidad,
arrastrar-y-soltar).
