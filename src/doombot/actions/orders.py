"""Ordenes que delegan una accion real: en el agente de codigo, o en n8n."""

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


@orden("flow")
def flujo(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que flujo quieres activar?")
        return
    if s.n8n is None:
        s.aviso("n8n no esta configurado (falta DOOMBOT_N8N_BASE_URL en .env).")
        return
    s.traza(f"disparando el flujo de n8n: {m.argument!r}")
    try:
        resultado = s.n8n.trigger(m.argument)
    except BackendError as e:
        s.aviso(str(e))
        return
    s.decir(f"[{'hecho' if resultado.success else 'fallo'}] flujo {m.argument!r} disparado")
