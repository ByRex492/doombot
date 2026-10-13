"""La aplicacion de escritorio de D.O.O.M: un planeta, el registro del agente y un chat (D-035).

    python -m doombot ventana

Una ventana propia -pywebview: WebView2 en Windows, WebKitGTK en Linux-, sin
navegador a la vista. Por dentro dibuja ``ui/ventana/doom.html``; el agente
corre en el mismo proceso y se hablan por ``puente.Puente``.
"""

from __future__ import annotations

import contextlib
import os
import sys
from collections.abc import Callable
from typing import Any

from doombot.paths import UI_DIR
from doombot.ventana.lanzador import CLASE_VENTANA, ICONO
from doombot.ventana.puente import Puente

HTML = UI_DIR / "ventana" / "doom.html"

__all__ = ["HTML", "Puente", "abrir"]


def abrir(*, montar: Callable[..., Any] | None = None, depurar: bool = False) -> int:
    """Abre la ventana y no vuelve hasta que se cierra.

    ``montar`` sustituye a ``agent.montaje.montar``: es la costura para abrir
    la ventana con un cerebro de prueba, sin modelo de verdad.
    """
    # Antes de que arranque GTK: asi la ventana se llama "doombot" para el
    # escritorio (WM_CLASS) y el dock la asocia al icono del lanzador, en vez
    # de mostrar un "__main__.py" generico al lado.
    if sys.platform.startswith("linux"):
        with contextlib.suppress(Exception):
            from gi.repository import GLib

            GLib.set_prgname(CLASE_VENTANA)
            GLib.set_application_name("D.O.O.M")
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
        width=1280,
        height=880,
        min_size=(600, 640),
        background_color="#020409",
    )
    puente._conectar(ventana)
    ventana.events.closed += puente._cerrar
    try:
        webview.start(debug=depurar, icon=str(ICONO) if ICONO.is_file() else None)
    except KeyboardInterrupt:
        # Ctrl+C en la terminal desde la que se abrio: es "cierra", no un fallo.
        print("\nD.O.O.M cerrado.", file=sys.stderr)
    finally:
        puente._cerrar()
    # Cerrar la ventana es cerrar el programa. Los hilos del agente no son
    # demonio: una peticion a un modelo a medias retendria el proceso hasta su
    # tiempo maximo -un minuto- sin ventana ni forma de verlo. Ya se ha
    # cerrado lo que habia que cerrar; el resto se termina aqui.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
