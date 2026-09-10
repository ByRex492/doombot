"""Órdenes que escriben en el vault."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.obsidian import anotar_progreso
from doombot.orders import Sesion, orden
from doombot.paths import VAULT_DIR

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("progress")
def progreso(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que quieres anotar?")
        return
    ruta = anotar_progreso(m.argument)
    s.decir(f"Anotado en {ruta.relative_to(VAULT_DIR.parent)}")
