"""Contratos de los backends.

D.O.O.M habla con estas interfaces y nunca con una implementacion concreta.
Es lo que permite que el portatil use un modelo pequeno en local, el sobremesa
uno grande, y que el portatil pueda apuntar por red al sobremesa sin que
cambie una linea de la logica.

Son ``Protocol`` y no clases base: una implementacion no tiene que heredar de
nada ni importar este modulo, basta con que tenga los metodos. Asi el contrato
no arrastra dependencias hacia quien lo cumple.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TextGenerator(Protocol):
    """Genera texto a partir de un prompt."""

    def generate(self, prompt: str, *, system: str | None = None) -> str: ...

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        """Genera por fragmentos.

        Lo necesita la voz: esperar a la respuesta entera antes de empezar a
        hablar anade un silencio proporcional a su longitud. Con streaming se
        sintetiza la primera frase mientras se genera el resto.
        """
        ...

    @property
    def model_name(self) -> str: ...


@runtime_checkable
class Transcriber(Protocol):
    """Convierte audio en texto."""

    def transcribe(self, audio: Path, *, language: str = "es") -> str: ...


# Cuanto se amplifica el RMS para llevarlo al 0-1 que espera la interfaz.
#
# PROVISIONAL, puesto a ojo: el valor eficaz de la voz es bastante mas bajo que
# su pico, asi que sin amplificar el orbe apenas se moveria. Con 3, un RMS de
# 0,15 -tipico al hablar- da 0,45, y los picos llegan arriba sin saturar todo el
# rato. Hay que medirlo con audio real de Kokoro y corregirlo aqui; es un numero
# suelto justamente para que eso sea cambiar una linea.
_ESCALA_NIVEL = 3.0


@dataclass(frozen=True)
class Audio:
    """Un trozo de sonido ya sintetizado, todavia sin reproducir.

    Se devuelven las muestras y no un fichero WAV a proposito. Escribir a disco
    para volver a leerlo anade latencia justo donde mas se nota -el primer
    sonido de una respuesta- y ademas impide lo que viene despues: medir el
    nivel para animar la interfaz, y cortar a mitad de frase cuando el usuario
    interrumpa.

    ``samples`` son valores entre -1 y 1. Un ``numpy.ndarray`` sirve, y es lo
    que devolveran las implementaciones reales; el contrato no lo exige para no
    arrastrar numpy hasta la capa de contratos.
    """

    samples: Sequence[float]
    sample_rate: int

    @property
    def duration(self) -> float:
        """Segundos de sonido."""
        return len(self.samples) / self.sample_rate if self.sample_rate else 0.0

    def level(self) -> float:
        """Nivel entre 0 y 1, para animar la interfaz mientras habla.

        La interfaz no decide nada: recibe estado y nivel, y anima. Este es el
        lado que produce ese numero cuando quien habla es D.O.O.M; cuando habla
        el usuario sale del microfono. Que ambos den la misma escala es lo que
        permite que el HUD no sepa cual de los dos esta sonando.
        """
        if not len(self.samples):
            return 0.0
        cuadrados = sum(float(s) * float(s) for s in self.samples)
        return min(1.0, (cuadrados / len(self.samples)) ** 0.5 * _ESCALA_NIVEL)


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Convierte texto en voz.

    El contrato tiene dos formas de pedir lo mismo, y no sobra ninguna:

    - ``say`` devuelve la frase entera. Es lo simple, y vale para respuestas
      cortas y para medir.
    - ``stream`` va devolviendo trozos segun estan listos. Es lo que permite
      empezar a hablar en torno a un segundo en vez de esperar a sintetizar
      toda la respuesta, que con un parrafo largo son varios segundos de
      silencio incomodo.

    Quien reproduce el sonido no es esto. Un sintetizador produce audio; sacarlo
    por los altavoces, encolarlo o cortarlo a media frase es de la capa de voz.
    Separarlo es lo que hara posible interrumpir a D.O.O.M mientras habla sin
    tocar el motor de sintesis.
    """

    def say(self, texto: str) -> Audio: ...

    def stream(self, texto: str) -> Iterator[Audio]:
        """Trozos de audio segun se generan, en orden."""
        ...

    @property
    def voice_name(self) -> str:
        """Que voz concreta esta usando. Para diagnosticar y para el arranque."""
        ...

    @property
    def sample_rate(self) -> int: ...


@runtime_checkable
class Embedder(Protocol):
    """Convierte texto en vectores, para la memoria."""

    def embed(self, textos: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int:
        """Longitud de los vectores.

        La memoria la guarda junto a los datos: cambiar de modelo de embeddings
        invalida los vectores almacenados, y hay que poder detectarlo en vez de
        comparar vectores de dimensiones distintas.
        """
        ...


class BackendError(RuntimeError):
    """Fallo al hablar con un backend.

    Que sea un tipo propio permite a la capa de voz distinguir 'Ollama no
    responde' —que se le puede decir al usuario en voz alta— de un error de
    programacion, que no.
    """
