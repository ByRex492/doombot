# Prototipo del HUD

`hud.html` es la interfaz de DOOM. Archivo único, sin dependencias, sin red.

## Cómo abrirlo

Doble clic funciona para ver la animación. Pero el micrófono **no**: Chrome
bloquea `getUserMedia` en `file://`. Para probarlo entero hay que servirlo:

```bash
py -3.12 -m http.server 8080 --bind 127.0.0.1 --directory C:\Users\migue\jarvis-local\ui\prototipo
```

Y entrar en `http://localhost:8080/hud.html`.

## Controles

| Tecla | Acción |
|---|---|
| `1`–`5` | fuerza un estado |
| `espacio` (mantener) | ESCUCHANDO con amplitud del micrófono real |
| `Ctrl`+`Enter` | sintetiza el texto del panel |
| `D` | ciclo completo de conversación |
| `H` | oculta el panel de pruebas |

## Las dos mitades del archivo

**El HUD** (secciones 1–7) es lo que se queda. No decide nada: recibe estado,
amplitud y texto, y anima. El contrato es `window.DOOM`:

```js
DOOM.setState('escuchando')   // dormido | escuchando | pensando | hablando | error
DOOM.amplitude(0.63)          // 0..1, a 30-60 Hz
DOOM.caption('texto')         // subtítulo bajo el orbe
DOOM.reset()
```

**El banco de pruebas** (secciones 8 y 8b) se tira cuando exista el orquestador.
Existe para poder juzgar el ritmo con voz real antes de tener Kokoro y Whisper.

Usa `speechSynthesis`, el sintetizador del sistema. En Windows son las voces SAPI
instaladas, que corren en local; Chrome además ofrece voces "Google", que se
sintetizan en servidores remotos. El desplegable las marca `[local]` / `[nube]`
para que no se cuelen en un proyecto que quiere ser 100% offline.

Por lo mismo **no** se usa reconocimiento de voz del navegador: la Web Speech API
de Chrome envía el audio a Google. El micrófono se usa solo para medir amplitud,
que es un cálculo local.

## Medido en esta máquina

- 180 fps con 70 partículas, ventana 1568×699, RTX 5060 Ti.
- 3 voces SAPI locales disponibles de 8 (es/en). `Microsoft Helena` para español.
- Las voces SAPI **sí** emiten eventos `boundary` por palabra en Chrome. Aun así
  la envolvente del orbe no depende de ellos: lleva una base silábica continua y
  los `boundary` solo acentúan los picos. Si mañana una voz no los emite, el HUD
  sigue vivo.

## Pendiente

- La transparencia real de ventana en Windows con WebView2 no está resuelta;
  la v1 va con ventana opaca sin marco.
- El transporte definitivo será un WebSocket en `127.0.0.1`, no `evaluate_js`.
- El estilo artístico está sin cerrar: esto fija el comportamiento, no el aspecto.
