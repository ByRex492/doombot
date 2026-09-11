"""Lanzador de escritorio del HUD.

Ventana pywebview sin marco que carga hud.html. No lleva js_api ni usa
evaluate_js para nada del dibujo: toda la comunicacion con el orquestador
va por el WebSocket que abre el propio hud.html (ver D-022 en
docs/decisiones.md). Este fichero solo pone la ventana.

La transparencia real de ventana en Windows no esta resuelta (WebView2 no
la soporta, y LWA_COLORKEY da un recorte binario que destroza el
resplandor) -- ver D-016 y D-022. La v1 va opaca, sin marco.

Requiere `pywebview`, que capa/hud no puede anadir a pyproject.toml (es
fichero de integracion): pedido por nota de sesion y por el canal directo
entre sesiones. Para probar en local mientras tanto:

    py -3.12 -m pip install pywebview
    py -3.12 ui/app.py
"""

from __future__ import annotations

import pathlib

import webview

HTML = pathlib.Path(__file__).parent / "prototipo" / "hud.html"


def main() -> None:
    webview.create_window(
        "D.O.O.M",
        url=HTML.resolve().as_uri(),
        width=720,
        height=780,
        frameless=True,
        easy_drag=True,
        background_color="#04070b",
    )
    webview.start()


if __name__ == "__main__":
    main()
