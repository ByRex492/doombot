# El HUD

`hud.html` es la interfaz de DOOM. Archivo único, sin dependencias de build.
Estilo cerrado: dirección **mínimo** (un solo anillo, sin marcas ni núcleo,
todo el peso en cómo respira y se engruesa) — ver `docs/decisiones.md` para
el resto de direcciones que se descartaron.

## Cómo abrirlo

Doble clic funciona para ver la animación, pero con dos limitaciones: el
micrófono (Chrome bloquea `getUserMedia` en `file://`) y el WebSocket del
transporte real (`ws://` desde `file://` también falla en algunos navegadores).
Para probarlo entero hay que servirlo:

```bash
py -3.12 -m http.server 8080 --bind 127.0.0.1 --directory C:\Users\migue\doombot-hud\ui\prototipo
```

Y entrar en `http://localhost:8080/hud.html`. Si además quieres ver el
transporte real funcionando sin el orquestador todavía montado, levanta
`ui/mock_servidor.py` en paralelo (ver `ui/README.md`).

## Controles

| Tecla | Acción |
|---|---|
| `1`–`5` | fuerza un estado |
| `espacio` (mantener) | ESCUCHANDO con amplitud del micrófono real |
| `Ctrl`+`Enter` | sintetiza el texto del panel |
| `D` | ciclo completo de conversación |
| `H` | oculta el panel de pruebas |

## Las tres mitades del archivo

**El HUD** (secciones 1, 2, 4-7) es lo que se queda. No decide nada: recibe
estado, amplitud y texto, y anima. El contrato es `window.DOOM`:

```js
DOOM.setState('escuchando')   // dormido | escuchando | pensando | hablando | error
DOOM.amplitude(0.63)          // 0..1, a 30-60 Hz
DOOM.caption('texto')         // subtítulo bajo el orbe
DOOM.reset()
```

**El transporte** (sección 3b) conecta ese contrato a un WebSocket real —
`ws://127.0.0.1:8765/hud`, contrato completo en D-022 (`docs/decisiones.md`).
Reintenta solo cada 1,5 s si no hay servidor, así que no rompe nada trabajar
sin el orquestador levantado.

**El banco de pruebas** (secciones 8 y 8b) se tira cuando el transporte esté
también en el lado Python. Hasta entonces sigue siendo el modo por defecto
si no hay servidor WS: existe para poder juzgar el ritmo con voz real antes
de tener Kokoro y Whisper conectados de verdad.

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
  la v1 va con ventana opaca sin marco (`ui/app.py`).
- El lado Python del transporte (el servidor WS de verdad, en el
  orquestador) no es cosa de `capa/hud` — pedido a integración, ver D-022.
