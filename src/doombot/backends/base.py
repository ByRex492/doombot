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

from collections.abc import Iterator
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
