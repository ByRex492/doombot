# Resumen sesión sobremesa — 2026-09-11

Primera fusión real del trabajo en paralelo: **`capa/tts` entregó y está en `main`**. La
infraestructura montada ayer (registro de órdenes, contrato por adelantado, worktrees) hizo lo
que prometía: la rama llegó sin tocar un solo fichero de integración y se fusionó sin conflicto.

Todo en `main` y subido: `origin/main` = `4794395`. Las tres ramas en el mismo commit.

---

## Lo que se hizo

### 1. `capa/tts` revisada y fusionada (`f1a693e`)

Antes de fusionar, tres comprobaciones:

- **Zona.** 892 líneas nuevas, todas en `src/doombot/tts/`, sus dos ficheros de tests y sus
  docs. Cero invasiones. El parte automático (`scripts/estado-capas.ps1`) lo confirmó.
- **Decisión y nota.** D-021 escrita con su número reservado, nota de sesión propia
  (`RESUMEN SESION CAPA-TTS 2026-09-10.md`).
- **La cifra que pedían cambiar.** No se aplicó a ciegas: RMS por ventanas de 50 ms, mediana
  0,035, p90 0,073. Con factor 13 → 0,45 y 0,95. La aritmética cuadra con el criterio que ya
  estaba escrito en el comentario.

**Lo que trae**, en dos hallazgos que conviene leer en D-021 antes de tocar el sintetizador:

- **Los modelos cuantizados son más lentos, no más rápidos.** int8 da RTF 4,26 frente a 0,44
  del fp32: diez veces peor. Este Zen 3 no acelera fp16 nativamente y el int8 de ONNX cae en
  kernels sin optimizar. Sin medir se habría enviado el int8 por ser el fichero más pequeño.
- **El streaming de `kokoro-onnx` no sirve para lo que promete.** Reparte por lotes de fonemas,
  no por frase, y un párrafo entero cabe en un lote: no entrega nada hasta tenerlo todo. Se
  escribió el troceo por frase aparte. Primer audio en **0,40 s** en vez de 4,23 s, mismo coste
  total.

GPU descartada para esto, y no por VRAM: `onnxruntime-gpu` pide `cublasLt64_13.dll` y el
paquete de CUDA 13 en PyPI es un *placeholder* vacío. En CPU va sobrado y deja la GPU libre para
el LLM.

### 2. Las tres peticiones de integración, aplicadas (`180dcaa`)

Lo que la rama no podía tocar y pidió por su nota:

| Petición | Qué se hizo |
|---|---|
| `_ESCALA_NIVEL` en `backends/base.py` | 3,0 → **13**. Mi estimación a ojo erraba por un factor de cuatro |
| Extra `voice-tts` en `pyproject.toml` | `kokoro-onnx>=0.6`, sin `onnxruntime-gpu` |
| `identity.py` | Pedían sumar `tts` a "escuchar". **Se partió en dos** en su lugar |

La tercera merece explicación. La capacidad "escuchar" decía *"escuchar por el micrófono y
responder en voz alta"*: una sola entrada para dos cosas que ahora viven en paquetes distintos.
Sumando `tts` sin más, D.O.O.M habría seguido diciendo que responde en voz alta por el mero
hecho de tener micrófono. Eso es justo la mentira que `identity.py` existe para evitar. Ahora
son `escuchar` (mira `voice/`) y `hablar` (mira `tts/`), y D.O.O.M dice:

```
conversar, transcribir, recordar, escuchar, hablar, actuar, consultar (no)
```

Sobre `_ESCALA_NIVEL` se dejó un aviso que no venía en la petición: **la cifra vale para trozos
cortos, del orden de 50 ms**, que es como los va a trocear el orquestador para alimentar la
interfaz a 30-60 Hz. Sobre una frase entera sale más baja, porque las pausas entran en el
promedio.

**Suite completa tras la fusión: 293 tests, 291 pasan, 1 omitido, 1 falla** — el binario
`claude`, que sigue sin estar instalado. No es regresión.

### 3. Canal directo entre sesiones

Descubierto de paso: las sesiones de Claude Code de esta máquina se ven entre sí y pueden
mandarse mensajes. Las dos ramas se identificaron al primer intento y confirmaron que pedirán
por ahí lo que no puedan tocar. Es lo que permitió que la petición de `capa/tts` llegara y se
aplicara en la misma mañana, sin esperar a leer su nota.

| Sesión | Rama |
|---|---|
| `doombot-70` | `capa/tts` |
| `doombot-eb` | `capa/hud` |

**No sustituye a las notas ni al `push`.** El canal existe mientras las sesiones estén vivas;
si se cierra una, lo único que queda es lo que haya en el repositorio.

---

## Estado de las ramas

| Rama | Estado |
|---|---|
| `capa/tts` | **Entregada y fusionada.** Su rama ya no tiene nada que `main` no tenga. Se puede cerrar la sesión |
| `capa/hud` | Trabajando en `ui/prototipo/estilos/`, sin commitear todavía. Base al día en `4794395` |
| `main` | Kokoro integrado, `voice-tts` instalable, identity partida |

---

## Lo que viene, y de quién es

### De `capa/hud` (en marcha)

Cerrar el estilo artístico y entregar el transporte por WebSocket con su formato de eventos.
Lo que pedirá a integración, previsiblemente: la dependencia de `pywebview` y del servidor
WebSocket en `pyproject.toml`.

### De integración (`main`), cuando HUD entregue

Esto es lo que queda del TTS y **no es de la rama de TTS sino del orquestador**:

1. **Conectar `stream()` a `chat.py`** para que las respuestas salgan por los altavoces y no
   solo por pantalla. La `Sesion` ya inyecta `responder` precisamente para esto: cambia ahí, no
   en los manejadores.
2. **Trocear el audio en ventanas de ~50 ms** y empujar `Audio.level()` al HUD a 30-60 Hz.
3. **`repeat`**, que sigue sin implementar y ahora es trivial: `Sesion.ultima_respuesta` ya
   existe. Y `stop`, que con voz de verdad por fin tiene algo que parar.

### Sin cambios desde el 01/09

Elegir micrófono (`DOOMBOT_AUDIO_INPUT`), `OLLAMA_MAX_LOADED_MODELS=1`, el binario `claude`,
las pruebas de micrófono (pospuestas por decisión del usuario), continuidad de conversación,
PDF en el buzón, n8n, el enrutador Ollama/Claude.

---

## Estado por capas

| Capa | Código | ¿Funciona? |
|---|---|---|
| 1 · Cerebro (LLM) | completo | **Sí** |
| 2 · Oídos (micro + wake word + Whisper) | completo | **Sí**. Sin probar con voz real |
| 3 · Memoria | completo | **Sí** |
| 4 · Acciones (Claude Code) | completo | **No**: falta el binario `claude` |
| 5 · Voz (TTS) | **completo, en `main`** | **Sí**, medido. Falta conectarlo al orquestador |
| 5 · Interfaz (HUD) | en `capa/hud` | prototipo funcionando, estilo en marcha |
| Obsidian | completo | **Sí** |
| Ficheros | completo | **Sí** |
