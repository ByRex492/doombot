"""Ordenes que delegan una accion real: en el agente de codigo, o en n8n."""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.backends.base import BackendError
from doombot.orders import Sesion, orden
from doombot.phrases.matcher import es_afirmacion

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


def _confirmado(s: Sesion, pregunta: str) -> bool:
    """Pide confirmacion antes de una accion real (D-031).

    Silencio, "no", o cualquier otra cosa que no sea una afirmacion clara se
    toma como negativa: ante la duda de si se entendio bien, no ejecutar es
    la opcion segura. Se avisa siempre del motivo, para que quien lo dijo
    sepa que paso y no se quede esperando una respuesta que ya se dio.
    """
    respuesta = s.preguntar(f"{pregunta} (di 'confirmo' o 'no')").strip()
    if es_afirmacion(respuesta):
        return True
    s.aviso(f"cancelado{f' ({respuesta!r} no es una confirmacion)' if respuesta else ''}.")
    return False


@orden("act")
def actuar(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que tarea quieres que ejecute?")
        return
    # "plan" ya es la salvaguarda: propone sin tocar nada (D-014), asi que
    # pedir confirmacion ahi encima seria un paso de mas sin nada real que
    # proteger. Los modos que si ejecutan son los que necesitan el freno.
    if s.cfg.agent_permission_mode != "plan" and not _confirmado(
        s, f"Voy a ejecutar en modo {s.cfg.agent_permission_mode}: {m.argument}."
    ):
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
    # Un webhook no tiene modo "plan" (D-030): a diferencia de "act", aqui se
    # confirma siempre, no solo en algunos modos.
    if not _confirmado(s, f"Voy a activar el flujo: {m.argument}."):
        return
    s.traza(f"disparando el flujo de n8n: {m.argument!r}")
    try:
        resultado = s.n8n.trigger(m.argument)
    except BackendError as e:
        s.aviso(str(e))
        return
    s.decir(f"[{'hecho' if resultado.success else 'fallo'}] flujo {m.argument!r} disparado")
