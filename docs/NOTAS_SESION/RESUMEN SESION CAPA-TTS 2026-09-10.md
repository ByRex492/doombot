# Resumen sesión capa/tts — 2026-09-10

Sintetizador de voz con Kokoro, en `C:\Users\migue\doombot-tts`, rama `capa/tts`. El encargo
era medir en esta máquina (latencia, consumo, calidad en español) y construir el sintetizador
cumpliendo `SpeechSynthesizer`. Detalle completo y justificación de cada número en **D-021**
(`docs/decisiones.md`); esta nota es el resumen para quien fusione.

---

## Lo que se hizo

### 1. `kokoro-onnx` en CPU, fp32 — todo medido, nada supuesto

- **CPU, no GPU.** `onnxruntime-gpu` pide `cublasLt64_13.dll` (CUDA 13/cuDNN 9 para esta
  Blackwell sm_120) y no hay wheel real en PyPI todavía —`nvidia-cublas-cu13` es un placeholder
  en `0.0.1`—. Instalar el CUDA Toolkit completo es la misma opción que D-018 ya descartó.
  En CPU el `RTF` ya va en 0,44–0,56: sobra margen, y deja la GPU entera para `gemma4:12b`.
- **fp32, no los cuantizados.** Contraintuitivo y por eso quedó medido: en esta CPU (Zen 3, sin
  aceleración fp16 nativa) fp16 va MÁS LENTO que fp32, e int8 cae en kernels sin optimizar y es
  **ocho veces más lento** (RTF 4,3). El fichero más pequeño no era el más rápido.
- **Streaming propio, por frase.** El troceo interno de `kokoro-onnx` es por lotes de hasta 510
  fonemas, no por frase: un párrafo típico de D.O.O.M. (3-4 frases) cabe en un solo lote y no
  entrega nada hasta tenerlo entero —igual que `say()`, sin beneficio—. `stream()` trocea por
  frase y sintetiza la siguiente en un hilo mientras entrega la actual: **TTFA 0,40 s frente a
  4,23 s** de `say()` en el mismo párrafo, mismo coste total.
- **Cadencia y pausas** por los parámetros nativos de Kokoro (`speed=0.85`,
  `sentence_pause=0.4`, `clause_pause=0.15`), no por estirar el audio después: Kokoro ya calcula
  la duración del fonema antes de vocalizar.
- **Post-procesado sutil**, en `tts/dsp.py`: pasa-altos a 150 Hz (corte de graves) y una cola de
  reverberación sintética (RT60 0,3 s, mezcla 15%) para sala pequeña. Con `scipy`, que ya estaba
  por Whisper — sin dependencia nueva.

### 2. Los ficheros del modelo no vienen por pip

A diferencia de Whisper o los embeddings, `kokoro-onnx` no descarga solo. `tts/download.py`
(`asegurar_modelos`) trae `kokoro-v1.0.onnx` + `voices-v1.0.bin` (354 MB) a
`paths.models_dir() / "kokoro"` la primera vez que hacen falta. No descarga fp16 ni int8: no se
usan.

### 3. Órdenes y tests

`silence` / `speak` en `tts/orders.py`: marcan un interruptor de módulo (`silenciado()`) que el
futuro bucle de voz tendrá que consultar antes de reproducir —hoy `chat.py` solo imprime por
consola, no hay audio real que cortar todavía—. `tests/test_kokoro.py` (con un doble de Kokoro,
sin cargar el modelo real salvo en el test `@pytest.mark.hardware`) y `tests/test_tts_download.py`
(sin red). `pytest -m "not hardware"` en verde salvo dos tests de sincronía de documentación
—ver más abajo, son de integración—.

---

## Escucha pendiente de confirmar

Mandadas por chat seis muestras: `ef_dora` vs `em_alex` (las dos voces españolas candidatas),
seco vs con el post-procesado, y las muestras finales es/en con la cadencia ya aplicada.
`ef_dora` queda como valor por defecto en el código a falta de esa confirmación —si el usuario
prefiere `em_alex`, o quiere afinar la mezcla de reverberación, es cambiar una constante en
`tts/synth.py` (`VOZ_ES`, `reverberacion`).

---

## Lo que integración espera recibir (tocan ficheros que `capa/tts` no puede editar)

1. **`_ESCALA_NIVEL` en `backends/base.py`.** Medido con audio real de Kokoro (procesado, el que
   de verdad sale de `say()`): RMS por ventana de 50 ms, mediana ≈0,035, p90 ≈0,07-0,073, pico
   puntual ≈0,11. Con la fórmula actual (`RMS × escala`, tope en 1.0), **`_ESCALA_NIVEL ≈ 13`**
   deja la mediana en ~0,45 y el p90 cerca de 0,9 sin saturar todo el rato — el mismo criterio
   que ya proponía el comentario, con el número real en vez de a ojo (la estimación de 3,0
   asumía un RMS típico de 0,15; el real es cuatro veces más bajo).
2. **Extra `voice-tts` en `pyproject.toml`.** Solo `kokoro-onnx>=0.6` — trae `onnxruntime`,
   `phonemizer`, `espeakng-loader` como transitivas. **No** `onnxruntime-gpu`: no hay ruta de GPU
   utilizable ahora mismo (ver D-021), y el paquete normal es diez veces más ligero.
3. **`identity.py` solo comprueba el paquete `voice` para la capacidad "escuchar".** Con
   `tts/` como paquete propio (según la tabla de capas de `CLAUDE.md`), la línea de
   `_tiene_contenido("voice")` no ve el sintetizador. Hace falta sumar `_tiene_contenido("tts")`
   a esa capacidad (o partirla en "escuchar" / "hablar", ahora que son paquetes distintos).
4. **`doombot/__init__.py` y `docs/estructura.md` sin el módulo `tts`.** `tests/test_docs.py`
   lo detecta solo — son las dos únicas pruebas en rojo en esta rama, y es su trabajo señalarlo:
   ambos ficheros son de integración.

---

## Instalado en esta máquina, fuera del repositorio

`espeak-ng` por `winget` (de refuerzo: `kokoro-onnx` trae el suyo empaquetado vía
`espeakng-loader` y no llegó a hacer falta), y `kokoro-v1.0.onnx` / `kokoro-v1.0.fp16.onnx` /
`kokoro-v1.0.int8.onnx` / `voices-v1.0.bin` en `models_dir()/kokoro` (los tres modelos, para
poder medir los tres; solo fp32 lo usa el código).
