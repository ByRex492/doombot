"""El contrato del sintetizador, probado sin ningún sintetizador.

Se escribe antes que la implementación a propósito: la rama `capa/tts` necesita
saber qué forma tiene que cumplir para no bloquearse, y `capa/hud` necesita
saber de dónde va a salir el nivel que anima el orbe. El contrato es lo que
permite que ambas avancen sin verse.
"""

from __future__ import annotations

import math

from doombot.backends.base import Audio, SpeechSynthesizer


class SintetizadorDoble:
    """No hereda de nada. Eso es un Protocol."""

    def say(self, texto: str) -> Audio:
        return Audio([0.0] * 100, 24000)

    def stream(self, texto: str):
        yield self.say(texto)

    @property
    def voice_name(self) -> str:
        return "doble"

    @property
    def sample_rate(self) -> int:
        return 24000


def test_cumplir_el_contrato_no_exige_heredar():
    assert isinstance(SintetizadorDoble(), SpeechSynthesizer)


def test_al_que_le_falta_un_metodo_no_lo_cumple():
    class SinStream:
        def say(self, texto):
            return Audio([], 24000)

        voice_name = "x"
        sample_rate = 24000

    assert not isinstance(SinStream(), SpeechSynthesizer)


def test_la_duracion_sale_de_las_muestras_y_la_frecuencia():
    assert Audio([0.0] * 12000, 24000).duration == 0.5
    # Sin frecuencia no se divide entre cero: un audio vacio dura cero.
    assert Audio([], 0).duration == 0.0


def test_el_silencio_no_mueve_la_interfaz():
    assert Audio([0.0] * 1000, 24000).level() == 0.0
    assert Audio([], 24000).level() == 0.0


def test_el_nivel_crece_con_el_volumen_y_no_se_pasa_de_uno():
    """La interfaz espera 0-1: un valor por encima la romperia."""

    def tono(amplitud: float) -> Audio:
        return Audio(
            [math.sin(2 * math.pi * 220 * i / 24000) * amplitud for i in range(2400)], 24000
        )

    flojo, medio, fuerte = tono(0.05).level(), tono(0.2).level(), tono(0.9).level()
    assert 0.0 < flojo < medio <= fuerte <= 1.0
