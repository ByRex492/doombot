# Interfaz (HUD)

| Fichero | Qué es |
|---|---|
| `prototipo/hud.html` | La interfaz cerrada (estilo mínimo). Un solo fichero: dibujo, contrato `window.DOOM` y cliente WebSocket. |
| `prototipo/cyberpunk.html` | Dirección visual alternativa, en revisión — mismo motor, distinto dibujo. Ver el mensaje del usuario que la pidió antes de tocarla. |
| `app.py` | Lanzador de escritorio: ventana `pywebview` sin marco que carga `hud.html`. Ruta a prueba de empaquetado (`sys._MEIPASS` si está congelado). |
| `build.py` | Empaqueta `app.py` en `dist/DOOM.exe` con PyInstaller, `hud.html` embebido. |
| `mock_servidor.py` | Servidor WS de prueba, **no el definitivo** — para probar el transporte sin el orquestador. |

`pywebview` y `websockets` ya están en `pyproject.toml` (extra `hud`,
añadido por integración) — instala el proyecto con `pip install -e .[hud]`
y no hace falta instalar nada suelto para lo de abajo.

## El ejecutable

```bash
py -3.12 -m pip install pyinstaller
py -3.12 ui/build.py
```

Genera `dist/DOOM.exe`: un solo fichero, sin Python instalado en la máquina
destino (WebView2 ya viene con Windows 11). `hud.html` viaja embebido dentro
del `.exe` — comprobado quitando de en medio `prototipo/hud.html` y
arrancando igual. `dist/` y `build/` no se versionan (`.gitignore`); se
regeneran con el comando de arriba en cualquier máquina.

`--onefile` tarda un par de segundos en abrir la primera vez (se
descomprime a una carpeta temporal). Si eso molesta más que pesar una
carpeta en vez de un solo fichero, cambiar `--onefile` por `--onedir` en
`build.py` dado un arranque instantáneo a cambio de repartir `dist/DOOM/`
entera en vez de un `.exe` suelto.

## Probar la ventana de escritorio sin empaquetar

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

## Estado

El transporte real ya existe del lado del orquestador —
`src/doombot/hud_server.py` en `main`, mismo contrato de D-022, verificado
de punta a punta contra este cliente—. `app.py`/`build.py` abren la
ventana; el propio `chat.py` es quien tiene que arrancarla (o el usuario,
a mano, con `dist/DOOM.exe`) y hablarle por el WebSocket.
