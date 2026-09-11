# Resumen sesión capa/hud — 2026-09-11

Encargo cerrado del todo: estilo artístico elegido y transporte WebSocket implementado y
probado. Rama `capa/hud`, carpeta `C:\Users\migue\doombot-hud`. Detalle de la decisión de
arquitectura (contrato completo del transporte) en **D-022**, `docs/decisiones.md`.

---

## Tarea 1 — cerrar el estilo artístico

Cuatro direcciones montadas como prototipos que corrían de verdad (nunca descripciones):
**instrumento** (líneas finas, marcas, arcos orbitales — lo más JARVIS), **materia** (masa
líquida rellena, filamentos, brasas), **cristal** (gema facetada, vértices fijos, destello) y
**mínimo** (un solo anillo, sin núcleo ni marcas, todo el peso en el movimiento). El usuario
las abrió y eligió **mínimo** a la primera.

Cerrado: `ui/prototipo/hud.html` lleva ahora el dibujo de esa dirección. Los otros tres
prototipos y la carpeta `ui/prototipo/estilos/` de comparación, borrados — cumplieron su
función y ya no hacía falta mantenerlos vivos. El contrato `window.DOOM` y los `ESTADOS`
(números de cada uno de los cinco estados) no cambiaron en ningún momento: la elección de
estilo fue solo sobre `dibujar()`.

## Tarea 2 — el transporte WebSocket

`ws://127.0.0.1:8765/hud`, JSON de una línea por evento, mapeado 1:1 al contrato `window.DOOM`
ya existente (`state`, `amplitude`, `caption`, `reset`). Contrato completo, con la tabla de
frecuencias y el porqué de cada decisión, en D-022 — esta nota no lo repite.

Lo nuevo en el repositorio:

- **`ui/prototipo/hud.html`**, sección 3b: el cliente WS. Reconecta solo cada 1,5 s si no hay
  servidor; en cuanto conecta, sale del banco de pruebas (oculta el panel, deja de usar las
  fuentes simuladas) sin que nadie tenga que tocar nada a mano.
- **`ui/app.py`**: el lanzador de escritorio, ventana `pywebview` sin marco. Sin `js_api` ni
  `evaluate_js` — toda la comunicación va por el WebSocket, que es justo lo que evita el
  bloqueo del hilo de audio que tenía `evaluate_js` a 60 Hz.
- **`ui/mock_servidor.py`**: servidor de prueba con `websockets`, **no el definitivo** —
  existe para probar el cliente contra un servidor real sin esperar a que el orquestador
  tenga el suyo. Mismo papel que el banco de pruebas de voz del propio `hud.html`.
- **`ui/README.md`**: cómo probar cada pieza.

**Verificado, no solo escrito.** Instalé `pywebview` y `websockets` en el `.venv` de este
worktree (no en `pyproject.toml`, que es de integración) y comprobé:

1. `hud.html` servido por `http://` + `mock_servidor.py` en paralelo: conecta, reacciona a los
   cuatro tipos de mensaje, y si se mata el servidor y se levanta de nuevo, reconecta solo sin
   recargar la página.
2. `ui/app.py` abre la ventana sin lanzar ninguna excepción.

---

## Lo que pide a integración

No puedo tocar `pyproject.toml`, `chat.py`, `config.py`, `paths.py` ni `backends/base.py`. Ya
lo pedí por el canal directo entre sesiones (queda igual documentado aquí por si esa sesión ya
no está viva cuando se lea esto):

1. **`pywebview` y `websockets`** en `pyproject.toml` — probablemente un extra propio (tipo
   `hud`), siguiendo el patrón de `voice-cuda` / `voice-tts`.
2. **Que el orquestador abra el servidor WS** con el contrato de D-022, en un módulo suyo (no
   en `chat.py` directamente — ver D-020, las órdenes no viven ahí). Tiene que empujar
   `Audio.level()` (ya en escala 0-1, D-021) a 30-60 Hz mientras suena micrófono o TTS.

## Pendiente, heredado del encargo original

La transparencia real de ventana en Windows sigue sin solución (WebView2 no la soporta,
`LWA_COLORKEY` da un recorte binario que destroza el resplandor). `ui/app.py` va con ventana
opaca sin marco, tal y como preveía el encargo. No es una decisión nueva — queda anotado en
D-022 y en `ui/prototipo/README.md` por si aparece algo mejor más adelante.

---

## Estado de la capa

| Pieza | Estado |
|---|---|
| Estilo visual | **Cerrado.** Dirección mínimo, elegida por el usuario mirando prototipos reales |
| Contrato `window.DOOM` | Sin cambios desde el primer prototipo |
| Transporte (lado HUD) | **Hecho y probado** contra un servidor de prueba |
| Transporte (lado orquestador) | Pendiente de integración — pedido, no bloqueante para cerrar esta rama |
| Ventana de escritorio | `ui/app.py` abre y carga el HUD; transparencia real sin resolver |
