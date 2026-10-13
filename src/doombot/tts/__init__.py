"""Voz de D.O.O.M.: convierte texto en audio con Kokoro, bilingue es/en.

    from doombot.paths import models_dir
    from doombot.tts import KokoroSynthesizer

    voz = KokoroSynthesizer.from_models_dir(models_dir() / "kokoro")
    audio = voz.say("Hola, soy D.O.O.M.")

``KokoroSynthesizer`` se importa al pedirlo, no al cargar el paquete. El
registro de ordenes importa ``doombot.tts.orders`` en todo arranque, y eso
ejecuta este fichero: si aqui se importara ``synth`` -y con el ``kokoro_onnx``
y ``scipy``-, un equipo sin el extra ``voice-tts`` no podria despachar ni una
orden, tampoco en modo escrito. Si la capacidad de hablar esta disponible lo
decide ``doombot.identity`` mirando ``kokoro_onnx``, no este modulo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from doombot.tts.synth import KokoroSynthesizer

__all__ = ["KokoroSynthesizer"]


def __getattr__(nombre: str) -> Any:
    if nombre == "KokoroSynthesizer":
        from doombot.tts.synth import KokoroSynthesizer

        return KokoroSynthesizer
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
