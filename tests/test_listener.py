"""El bucle de escucha, sin microfono ni modelos.

Todo va con dobles: un detector que se activa cuando se le dice, un microfono
que devuelve niveles guionizados y un transcriptor que responde fijo. La
validacion con voz real queda para el equipo que tiene microfono decente.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from doombot.voice.capture import Recording
from doombot.voice.listener import Heard, Listener, State
from doombot.voice.wake import Detection, PushToTalk, WakeDetector


class DetectorFalso:
    """Se activa tras N bloques. Cuenta los reset para detectar rebotes."""

    def __init__(self, tras: int = 2) -> None:
        self.tras = tras
        self.vistos = 0
        self.resets = 0

    def check(self, muestras):  # noqa: ARG002
        self.vistos += 1
        if self.vistos >= self.tras:
            self.vistos = 0
            return Detection(word="hey_jarvis", score=0.9)
        return None

    def reset(self) -> None:
        self.resets += 1

    @property
    def name(self) -> str:
        return "falso"


class FlujoFalso:
    def __init__(self, bloque: int) -> None:
        self.bloque = bloque

    def read(self, n):  # noqa: ARG002
        return np.zeros(self.bloque, dtype=np.float32), None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


class MicroFalso:
    def __init__(self, tmp_path: Path, *, mudo: bool = False) -> None:
        self.samplerate = 16_000
        self._tmp = tmp_path
        self._mudo = mudo
        self.grabaciones = 0

    def abrir_flujo(self, bloque):
        return FlujoFalso(bloque)

    def record_until_silence(self, **kwargs):  # noqa: ARG002
        self.grabaciones += 1
        f = self._tmp / f"g{self.grabaciones}.wav"
        f.write_bytes(b"RIFF")
        return Recording(path=f, duration=2.0, elapsed=2.1, peak=0.0 if self._mudo else 0.5)


class TranscriptorFalso:
    def __init__(self, texto: str = "hola doom") -> None:
        self.texto = texto
        self.llamadas = 0

    def transcribe(self, audio, *, language="es"):  # noqa: ARG002
        self.llamadas += 1
        return self.texto


@pytest.fixture
def listener(tmp_path):
    return Listener(MicroFalso(tmp_path), TranscriptorFalso(), DetectorFalso())


# -- contrato ---------------------------------------------------------------
def test_el_doble_cumple_el_contrato():
    assert isinstance(DetectorFalso(), WakeDetector)


def test_push_to_talk_cumple_el_contrato():
    assert isinstance(PushToTalk(lambda: False), WakeDetector)


# -- ciclo ------------------------------------------------------------------
def test_entrega_lo_transcrito(listener):
    oido = next(iter(listener.listen(veces=1)))
    assert isinstance(oido, Heard)
    assert oido.text == "hola doom"
    assert oido.detection.word == "hey_jarvis"


def test_no_transcribe_antes_de_la_activacion(tmp_path):
    """Whisper no se toca mientras se espera: es el punto del wake word."""
    stt = TranscriptorFalso()
    detector = DetectorFalso(tras=5)
    lis = Listener(MicroFalso(tmp_path), stt, detector)
    assert stt.llamadas == 0
    next(iter(lis.listen(veces=1)))
    assert stt.llamadas == 1


def test_reinicia_el_detector_tras_activar(tmp_path):
    """Sin reset, la ventana de contexto vuelve a disparar la misma palabra."""
    detector = DetectorFalso()
    lis = Listener(MicroFalso(tmp_path), TranscriptorFalso(), detector)
    list(lis.listen(veces=2))
    assert detector.resets == 2


def test_vuelve_a_dormir_entre_interacciones(tmp_path):
    estados = []
    lis = Listener(
        MicroFalso(tmp_path), TranscriptorFalso(), DetectorFalso(), on_state=estados.append
    )
    list(lis.listen(veces=2))
    assert estados.count(State.DORMIDO) == 2
    assert estados[0] == State.DORMIDO


def test_la_secuencia_de_estados(tmp_path):
    estados = []
    lis = Listener(
        MicroFalso(tmp_path), TranscriptorFalso(), DetectorFalso(), on_state=estados.append
    )
    list(lis.listen(veces=1))
    assert estados == [State.DORMIDO, State.ESCUCHANDO, State.TRANSCRIBIENDO]


def test_silencio_tras_activar_no_transcribe(tmp_path):
    """Decir la palabra y callarse no debe devolver una cadena vacia."""
    stt = TranscriptorFalso()
    lis = Listener(MicroFalso(tmp_path, mudo=True), stt, DetectorFalso())
    assert list(lis.listen(veces=1)) == []
    assert stt.llamadas == 0


def test_emite_nivel_mientras_espera(tmp_path):
    """Es el dato que hara respirar al orbe de la interfaz."""
    niveles = []
    lis = Listener(
        MicroFalso(tmp_path), TranscriptorFalso(), DetectorFalso(tras=3), on_level=niveles.append
    )
    list(lis.listen(veces=1))
    assert len(niveles) >= 3
    assert all(0.0 <= n <= 1.0 for n in niveles)


# -- push to talk ------------------------------------------------------------
def test_push_to_talk_dispara_al_pulsar(tmp_path):
    pulsaciones = iter([False, False, True])
    lis = Listener(
        MicroFalso(tmp_path), TranscriptorFalso(), PushToTalk(lambda: next(pulsaciones, False))
    )
    oido = next(iter(lis.listen(veces=1)))
    assert oido.detection.word == "manual"


def test_push_to_talk_no_dispara_solo(tmp_path):
    """Sin pulsar, el bucle no llega a grabar nunca."""
    lis = Listener(MicroFalso(tmp_path), TranscriptorFalso(), PushToTalk(lambda: False))
    assert list(lis.listen(veces=1, espera_ms=300)) == []


# -- utilidades --------------------------------------------------------------
def test_heard_detecta_texto_vacio():
    d = Detection(word="x", score=1.0)
    assert Heard(text="   ", detection=d, seconds=1.0, peak=0.5).vacio
    assert not Heard(text="hola", detection=d, seconds=1.0, peak=0.5).vacio


def test_la_conversion_a_int16_no_desborda():
    from doombot.voice.listener import _a_int16

    salida = _a_int16(np.array([2.0, -2.0, 0.0], dtype=np.float32))
    assert salida.dtype == np.int16
    assert salida.max() <= 32767
    assert salida.min() >= -32767
