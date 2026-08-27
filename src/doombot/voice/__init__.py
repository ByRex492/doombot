"""Captura de audio, palabra de activacion y bucle de escucha.

    from doombot.voice import Listener, Microphone, WakeWord

    escucha = Listener(Microphone.from_settings(), transcriptor)
    for oido in escucha.listen():
        print(oido.text)

La sintesis de voz llegara en la Capa 3. Por ahora D.O.O.M oye pero no habla.
"""

from doombot.voice.capture import Microphone, Recording, listar_microfonos
from doombot.voice.listener import Heard, Listener, State
from doombot.voice.wake import Detection, PushToTalk, WakeDetector, WakeWord

__all__ = [
    "Detection",
    "Heard",
    "Listener",
    "Microphone",
    "PushToTalk",
    "Recording",
    "State",
    "WakeDetector",
    "WakeWord",
    "listar_microfonos",
]
