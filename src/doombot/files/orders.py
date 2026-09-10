"""Orden que lee un fichero del buzón y responde sobre él."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.backends.base import BackendError
from doombot.files import como_contexto, leer, resolver
from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("read_file")
def leer_fichero(s: Sesion, m: Match) -> None:
    try:
        doc = leer(resolver(m.argument))
    except BackendError as e:
        s.aviso(str(e))
        return
    s.traza(f"leido {doc.resumen}")
    # Se pregunta qué hacer con él: sin eso, "lee el contrato" no dice nada
    # sobre la tarea y el modelo se la inventa.
    pregunta = s.preguntar("  ¿que quieres saber de el? ").strip()
    s.responder(
        s.con_contexto(
            pregunta or "Resume este fichero en cinco lineas.",
            como_contexto(doc),
        )
    )
