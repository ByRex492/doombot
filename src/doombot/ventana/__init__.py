"""La aplicacion de escritorio de D.O.O.M: un planeta, el registro del agente y un chat (D-035).

    python -m doombot ventana

Una ventana propia -pywebview: WebView2 en Windows, WebKitGTK en Linux-, sin
navegador a la vista. Por dentro dibuja ``ui/ventana/doom.html``; el agente
corre en el mismo proceso y se hablan por ``puente.Puente``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from doombot.paths import UI_DIR
from doombot.ventana.puente import Puente

HTML = UI_DIR / "ventana" / "doom.html"

__all__ = ["HTML", "Puente", "abrir"]


def abrir(*, montar: Callable[..., Any] | None = None, depurar: bool = False) -> int:
    """Abre la ventana y no vuelve hasta que se cierra.

    ``montar`` sustituye a ``agent.montaje.montar``: es la costura para abrir
    la ventana con un cerebro de prueba, sin modelo de verdad.
    """
    try:
        import webview
    except ImportError:
        print(
            'La ventana necesita pywebview: pip install -e ".[hud]"\n'
            "En Linux ademas el GTK del sistema (ver README, 'La aplicacion').",
            file=sys.stderr,
        )
        return 1

    puente = Puente(montar)
    ventana = webview.create_window(
        "D.O.O.M",
        url=HTML.as_uri(),
        js_api=puente,
        width=980,
        height=940,
        min_size=(560, 640),
        background_color="#05070C",
    )
    puente._conectar(ventana)
    ventana.events.closed += puente._cerrar
    webview.start(debug=depurar)
    return 0
