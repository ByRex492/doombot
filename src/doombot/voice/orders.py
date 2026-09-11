"""Ordenes de control de la voz: parar y repetir.

Las dos estaban declaradas desde el principio y respondian "entendido, pero
aun no puedo hacerlo". `stop` no tenia nada que parar hasta que existio el
reproductor; `repeat` estaba mal clasificada como orden de voz -por escrito
tiene el mismo sentido- y solo necesitaba que la Sesion guardara la ultima
respuesta, que desde D-020 lo hace.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("stop")
def parar(s: Sesion, m: Match) -> None:
    """Calla en el acto. Es el barge-in a mano; el automatico llegara con el eco."""
    if s.speaker is not None:
        s.speaker.stop()
    # Sin voz que parar, la orden sigue teniendo sentido como "dejalo": no
    # hay nada que hacer, pero no se contesta con un "no puedo".
    s.traza("parado")


@orden("repeat")
def repetir(s: Sesion, m: Match) -> None:
    if not s.ultima_respuesta:
        s.decir("No he dicho nada todavia.")
        return
    # decir() la vuelve a guardar como ultima respuesta, asi que "repite" dos
    # veces seguidas repite lo mismo, que es lo que uno espera.
    s.decir(s.ultima_respuesta)
