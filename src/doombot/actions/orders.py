"""Orden que delega una tarea real en el agente de acciones."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.backends.base import BackendError
from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("act")
def actuar(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que tarea quieres que ejecute?")
        return
    s.traza(f"delegando en el agente ({s.cfg.agent_permission_mode}), puede tardar...")
    try:
        resultado = s.agente.run(m.argument)
    except BackendError as e:
        s.aviso(str(e))
        return
    s.decir(f"[{'hecho' if resultado.success else 'fallo'}] {resultado.output}")
