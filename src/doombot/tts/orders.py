"""Ordenes que atiende la voz: silenciar y reanudar la salida hablada.

``silence`` y ``speak`` estaban declaradas en ``phrases/matcher.py`` sin
manejador -D-020 lo dejaba localizado ahi, respondiendo "entendido, pero aun
no puedo hacerlo"-. Aqui pasan a marcar un estado real.

Lo que NO hacen todavia: cortar audio a media frase. Eso pide que exista el
bucle de voz que reproduce lo que devuelve ``SpeechSynthesizer`` -hoy
``chat.py`` solo imprime por consola, no hay nada que silenciar de verdad-.
Mientras tanto, ``silenciado()`` es el interruptor que ese bucle, cuando
exista, tiene que consultar antes de reproducir. Verlo en la nota de sesion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match

# Un solo interruptor de proceso. La sesion de voz es una sola conversacion
# a la vez -no hay dos usuarios hablandole a D.O.O.M. en paralelo-, asi que no
# hace falta guardar esto en la ``Sesion`` (que integracion no deja tocar
# desde aqui) ni en ningun sitio persistente: silenciar es para esta
# conversacion, no una preferencia que sobreviva a reiniciar.
_silenciado = False


def silenciado() -> bool:
    """True si la salida hablada esta desactivada ahora mismo."""
    return _silenciado


@orden("silence")
def silenciar(s: Sesion, m: Match) -> None:
    global _silenciado
    _silenciado = True
    s.decir("Modo silencioso. No hablo hasta que me digas 'modo normal'.")


@orden("speak")
def hablar(s: Sesion, m: Match) -> None:
    global _silenciado
    _silenciado = False
    s.decir("Vuelvo a hablar.")
