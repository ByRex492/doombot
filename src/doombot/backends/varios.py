"""Varios modelos a la vez: para no depender de uno, y para contrastar (D-034).

Dos formas de combinarlos, para dos problemas distintos:

- ``Cadena``: uno responde y los demas esperan. Si el primero falla -sin
  conexion, clave mala, o se le acaba la cuota gratuita (429)-, responde el
  siguiente. Es lo que hace que un proveedor caido no pare a D.O.O.M. Cumple
  ``TextGenerator`` y ``ToolCaller``: el agente y el chat la usan como a un
  modelo cualquiera.
- ``Consejo``: todos responden a lo mismo, en paralelo, y un juez junta las
  respuestas diciendo en que discrepan. Es la comprobacion cruzada: un dato
  en el que coinciden tres familias de modelos distintas es mas fiable que el
  de una sola.

Un modelo que se queda sin cuota se "aparta" un rato (``espera_limite``) para
no gastar una peticion en el en cada paso del agente, pero sigue al final de
la fila por si es el unico que queda.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, TypeVar

from doombot.backends.base import (
    BackendError,
    EspecHerramienta,
    MensajeAgente,
    PasoModelo,
    Turno,
)
from doombot.backends.openai_compat import LimiteAlcanzado

T = TypeVar("T")


def etiqueta(g: Any) -> str:
    """``proveedor/modelo`` de cualquier generador, para mostrarlo."""
    if hasattr(g, "proveedor"):
        return str(g.model_name)
    tipo = type(g).__name__.removesuffix("Generator").lower()
    return f"{tipo}/{g.model_name}"


class Cadena:
    def __init__(
        self,
        generadores: Sequence[Any],
        *,
        avisar: Callable[[str], None] | None = None,
        espera_limite: float = 60.0,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        if not generadores:
            raise ValueError("Una cadena necesita al menos un modelo.")
        self.generadores = list(generadores)
        self.avisar = avisar
        self.ultimo: Any = None
        """El que respondio la ultima vez. El revisor del agente elige otro distinto."""
        self._espera = espera_limite
        self._reloj = reloj
        self._apartados: dict[int, float] = {}

    @property
    def model_name(self) -> str:
        return " → ".join(etiqueta(g) for g in self.generadores)

    def is_available(self) -> bool:
        return any(getattr(g, "is_available", lambda: True)() for g in self.generadores)

    # -- el contrato ---------------------------------------------------------
    def generate(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> str:
        return self._intentar(lambda g: g.generate(prompt, system=system, historial=historial))

    def paso(
        self,
        conversacion: Sequence[MensajeAgente],
        herramientas: Sequence[EspecHerramienta],
        *,
        system: str | None = None,
    ) -> PasoModelo:
        return self._intentar(lambda g: g.paso(conversacion, herramientas, system=system))

    def stream(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> Iterator[str]:
        """Se cambia de modelo solo antes del primer trozo.

        A mitad de respuesta ya no: el usuario ya ha leido u oido parte de una,
        y empalmar otra distinta detras daria un texto sin sentido.
        """
        fallos: list[str] = []
        for i, g in self._orden():
            trozos = g.stream(prompt, system=system, historial=historial)
            try:
                primero = next(trozos)
            except StopIteration:
                self._acierto(g, fallos)
                return
            except BackendError as e:
                self._fallo(i, g, e, fallos)
                continue
            self._acierto(g, fallos)
            yield primero
            yield from trozos
            return
        raise self._ninguno(fallos)

    # -- interno -------------------------------------------------------------
    def _orden(self) -> list[tuple[int, Any]]:
        ahora = self._reloj()
        libres = [
            (i, g) for i, g in enumerate(self.generadores) if self._apartados.get(i, 0) <= ahora
        ]
        apartados = [(i, g) for i, g in enumerate(self.generadores) if (i, g) not in libres]
        return libres + apartados

    def _intentar(self, llamada: Callable[[Any], T]) -> T:
        fallos: list[str] = []
        for i, g in self._orden():
            try:
                resultado = llamada(g)
            except BackendError as e:
                self._fallo(i, g, e, fallos)
                continue
            self._acierto(g, fallos)
            return resultado
        raise self._ninguno(fallos)

    def _fallo(self, i: int, g: Any, e: BackendError, fallos: list[str]) -> None:
        if isinstance(e, LimiteAlcanzado):
            self._apartados[i] = self._reloj() + self._espera
        fallos.append(str(e))
        if self.avisar is not None and len(self.generadores) > 1:
            self.avisar(f"{etiqueta(g)} no responde ({str(e).split(': ', 1)[-1]})")

    def _acierto(self, g: Any, fallos: list[str]) -> None:
        if fallos and self.avisar is not None:
            self.avisar(f"sigo con {etiqueta(g)}")
        self.ultimo = g

    @staticmethod
    def _ninguno(fallos: list[str]) -> BackendError:
        return BackendError("Ningun modelo ha respondido:\n  " + "\n  ".join(fallos))

    def __repr__(self) -> str:
        return f"Cadena({self.model_name})"


# -- el consejo -------------------------------------------------------------------
@dataclass(frozen=True)
class Opinion:
    modelo: str
    texto: str
    fallo: bool = False


@dataclass(frozen=True)
class Veredicto:
    opiniones: tuple[Opinion, ...]
    final: str


_JUEZ = (
    "Eres el verificador de D.O.O.M. Te doy una pregunta y las respuestas de varios modelos "
    "de IA distintos. Escribe la respuesta final, correcta y breve, en espanol. Si discrepan "
    "en algo que importa -un dato, una cifra, una conclusion-, dilo explicitamente: en que "
    "discrepan y cual parece correcto y por que. Si coinciden, dilo en una frase. No anadas "
    "datos que ninguno haya dado."
)


class Consejo:
    """Pregunta lo mismo a varios modelos y contrasta lo que dicen."""

    def __init__(self, generadores: Sequence[Any], *, juez: Any = None) -> None:
        if not generadores:
            raise ValueError("Un consejo necesita al menos un modelo.")
        self.generadores = list(generadores)
        # El juez por defecto es la cadena entera: si el primero no puede
        # juzgar, juzga el siguiente.
        self.juez = juez if juez is not None else Cadena(self.generadores)

    @property
    def model_name(self) -> str:
        return "consejo(" + ", ".join(etiqueta(g) for g in self.generadores) + ")"

    def consultar(self, pregunta: str, *, system: str | None = None) -> Veredicto:
        def opinar(g: Any) -> Opinion:
            try:
                return Opinion(etiqueta(g), g.generate(pregunta, system=system))
            except BackendError as e:
                return Opinion(etiqueta(g), str(e), fallo=True)

        with ThreadPoolExecutor(max_workers=min(len(self.generadores), 6)) as hilos:
            opiniones = tuple(hilos.map(opinar, self.generadores))

        validas = [o for o in opiniones if not o.fallo]
        if not validas:
            raise BackendError(
                "Ningun modelo del consejo ha respondido:\n  "
                + "\n  ".join(o.texto for o in opiniones)
            )
        if len(validas) == 1:
            unica = validas[0]
            return Veredicto(
                opiniones, f"{unica.texto}\n\n(Solo ha respondido {unica.modelo}: sin contraste.)"
            )

        partes = [f"Pregunta: {pregunta}"]
        partes += [f"Respuesta de {o.modelo}:\n{o.texto}" for o in validas]
        final = self.juez.generate("\n\n".join(partes), system=_JUEZ)
        return Veredicto(opiniones, final)

    # TextGenerator: el chat puede usar un consejo como si fuera un modelo.
    def generate(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> str:
        return self.consultar(prompt, system=system).final

    def stream(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> Iterator[str]:
        yield self.generate(prompt, system=system, historial=historial)
