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

# Un turno anterior de la conversacion: {"role": "user"|"assistant", "content": texto}.
# El mismo formato que ya monta Ollama en su lista `messages` y que Anthropic
# usa en la suya -no es un tipo propio del proyecto, es el que hablan las dos
# APIs-, asi que ninguno de los dos backends tiene que traducir nada.
Turno = dict[str, str]


@runtime_checkable
class TextGenerator(Protocol):
    """Genera texto a partir de un prompt."""

    def generate(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> str: ...

    def stream(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> Iterator[str]:
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
# MEDIDO con audio real de Kokoro ya procesado -el que sale de say()-, en
# ventanas de 50 ms: RMS mediano 0,035, p90 0,073, pico puntual 0,11. Con 13 la
# mediana queda en 0,45 y el p90 cerca de 0,9, que es el criterio buscado:
# movimiento amplio sin saturar todo el rato.
#
# El 3,0 anterior estaba puesto a ojo y erraba por un factor de cuatro: suponia
# un RMS tipico de 0,15, y el real es 0,035. Con aquel numero el orbe se habria
# quedado casi quieto mientras D.O.O.M hablaba (ver D-021).
#
# OJO con la ventana: la cifra vale para trozos cortos, del orden de 50 ms, que
# es como los va a trocear el orquestador para alimentar la interfaz a 30-60 Hz.
# Aplicado a una frase entera el resultado sale mas bajo, porque las pausas
# entre palabras entran en el promedio.
_ESCALA_NIVEL = 13.0


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
        # Vectorizado si es un ndarray: esto se llama desde el callback de la
        # tarjeta de sonido 33 veces por segundo, y un bucle de Python ahi
        # es justo lo que no conviene. La lista pura queda para los tests.
        try:
            import numpy as np

            if isinstance(self.samples, np.ndarray):
                rms = float(np.sqrt(np.mean(self.samples.astype(np.float64) ** 2)))
                return min(1.0, rms * _ESCALA_NIVEL)
        except ImportError:
            pass
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


# -- llamada a herramientas (D-033) ---------------------------------------------
# Tipos neutros para el agente: ni el formato de Ollama ni el de Anthropic. El
# bucle del agente (``doombot.agent``) solo conoce estos, y cada backend
# traduce a su API al construir la peticion. Es lo que deja cambiar de cerebro
# con una variable de .env, como ya pasa con ``TextGenerator``.


@dataclass(frozen=True)
class EspecHerramienta:
    """Lo que el modelo ve de una herramienta: nombre, para que sirve, argumentos.

    ``parametros`` es un JSON Schema de tipo ``object``: es lo que piden las
    dos APIs, Ollama dentro de ``function.parameters`` y Anthropic como
    ``input_schema``.
    """

    nombre: str
    descripcion: str
    parametros: dict


@dataclass(frozen=True)
class LlamadaHerramienta:
    """Una herramienta que el modelo pide ejecutar."""

    id: str
    nombre: str
    argumentos: dict


@dataclass(frozen=True)
class PasoModelo:
    """Un turno del modelo: lo que dice y las herramientas que pide.

    Sin ``llamadas``, el modelo ha terminado y ``texto`` es su respuesta final.
    Con ellas, ``texto`` es el comentario que acompana a la accion -lo que el
    agente va contando de lo que hace-, y puede venir vacio.
    """

    texto: str
    llamadas: tuple[LlamadaHerramienta, ...] = ()


@dataclass(frozen=True)
class ResultadoHerramienta:
    """Lo que devolvio una herramienta, para devolverselo al modelo."""

    id: str
    nombre: str
    contenido: str


# Una conversacion de agente: texto del usuario, pasos del modelo y resultados
# de herramientas, en orden.
MensajeAgente = str | PasoModelo | ResultadoHerramienta


@runtime_checkable
class ToolCaller(Protocol):
    """Un modelo que puede pedir herramientas, no solo responder texto."""

    def paso(
        self,
        conversacion: Sequence[MensajeAgente],
        herramientas: Sequence[EspecHerramienta],
        *,
        system: str | None = None,
    ) -> PasoModelo: ...

    @property
    def model_name(self) -> str: ...


class BackendError(RuntimeError):
    """Fallo al hablar con un backend.

    Que sea un tipo propio permite a la capa de voz distinguir 'Ollama no
    responde' —que se le puede decir al usuario en voz alta— de un error de
    programacion, que no.
    """
