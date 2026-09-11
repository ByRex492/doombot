# Interfaz (HUD)

| Fichero | Qué es |
|---|---|
| `prototipo/hud.html` | La interfaz. Un solo fichero HTML: dibujo, contrato `window.DOOM` y cliente WebSocket. |
| `app.py` | Lanzador de escritorio: ventana `pywebview` sin marco que carga `hud.html`. |
| `mock_servidor.py` | Servidor WS de prueba, **no el definitivo** — para probar el transporte sin el orquestador. |

## Probar la ventana de escritorio

Requiere `pywebview` (pedido a integración en `pyproject.toml`, ver D-022 en
`docs/decisiones.md`; mientras tanto, para probar en local: `py -3.12 -m pip
install pywebview`):

```bash
py -3.12 ui/app.py
```

Abre `hud.html` directo por `file://` dentro de la ventana: sin microfono real
ni WebSocket (ambos los bloquea el navegador embebido en `file://`), pero
sirve para comprobar tamaño, marco y color de fondo de la ventana.

## Probar el transporte completo (WebSocket real, sin orquestador)

Dos procesos en paralelo. Uno sirve `hud.html` por `http://` (para que el
micrófono y el WebSocket funcionen):

```bash
py -3.12 -m http.server 8080 --bind 127.0.0.1 --directory ui/prototipo
```

Y el otro manda el mismo ciclo que el banco de pruebas (`D` en `hud.html`),
pero de verdad por WebSocket, con `websockets` (`py -3.12 -m pip install
websockets` si hace falta):

```bash
py -3.12 ui/mock_servidor.py
```

Entra en `http://localhost:8080/hud.html`: en cuanto el WebSocket conecta, el
HUD sale del banco de pruebas (oculta el panel, `fuente = 'ext'`) y sigue el
ciclo que manda `mock_servidor.py`. Mata el servidor y el cliente reintenta
solo cada 1,5 s — se puede reiniciar sin recargar la página.

## Qué falta para que esto sea el HUD real

Nada más de este lado. Lo que falta es del orquestador (`main`, no
`capa/hud`): abrir el mismo servidor WS con el contrato de D-022 y empujar
`Audio.level()` (D-021) a 30-60 Hz mientras suena micrófono o TTS.
