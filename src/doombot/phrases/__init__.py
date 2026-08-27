"""Reconocimiento de ordenes habladas.

La capa refleja de D.O.O.M.: rapida, determinista y sin modelo de por medio.
Cuando el usuario dice "para", tiene que callar al instante y siempre.

    from doombot.phrases import default_matcher

    m = default_matcher()
    m.match("¡DOOM! Activa el modo silencioso.")   # -> Match(command='silence')
    m.match("recuerda que el pan esta caro")       # -> argument='el pan esta caro'
    m.match("que tiempo hace manana?")             # -> None, no es una orden

Devolver None es lo normal: casi todo lo que se dice no son ordenes, sino
cosas que hay que pasar al modelo.

Exportar estos nombres activa la capacidad correspondiente en
``doombot.identity``.
"""

from doombot.phrases.matcher import (
    BASICAS,
    UMBRAL_ERRATAS,
    Command,
    Match,
    PhraseMatcher,
    default_matcher,
    normalize,
    similarity,
)

__all__ = [
    "BASICAS",
    "UMBRAL_ERRATAS",
    "Command",
    "Match",
    "PhraseMatcher",
    "default_matcher",
    "normalize",
    "similarity",
]
