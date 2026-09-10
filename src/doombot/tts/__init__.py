"""Voz de D.O.O.M.: convierte texto en audio con Kokoro, bilingue es/en.

    from doombot.paths import models_dir
    from doombot.tts import KokoroSynthesizer

    voz = KokoroSynthesizer.from_models_dir(models_dir() / "kokoro")
    audio = voz.say("Hola, soy D.O.O.M.")

Exportar ``KokoroSynthesizer`` activa ademas la capacidad de hablar en
``doombot.identity`` (ver la nota de sesion: ``identity.py`` hoy solo
comprueba el paquete ``voice``, hay que ampliarlo a ``tts``).
"""

from doombot.tts.synth import KokoroSynthesizer

__all__ = ["KokoroSynthesizer"]
