"""La orden "agente": el agente local desde el chat (y, mas adelante, la voz).

``python -m doombot agente`` es la forma principal de usarlo -una consola solo
para el-. Esta orden es la misma pieza desde ``python -m doombot chat``:
"agente abre la calculadora". El agente se monta la primera vez y se reutiliza,
para que conserve la conversacion y su navegador entre una orden y otra.
"""

from __future__ import annotations

import atexit
from typing import TYPE_CHECKING

from doombot.agent.montaje import Montaje, montar
from doombot.backends.base import BackendError
from doombot.orders import Sesion, orden
from doombot.phrases.matcher import es_afirmacion

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match

_montaje: Montaje | None = None


def _narrador(s: Sesion):
    def narrar(tipo: str, texto: str) -> None:
        # Lo que va a hacer se dice -con voz, si la hay-; el resto es traza.
        if tipo == "accion":
            s.decir(texto)
        else:
            s.traza(texto)

    return narrar


def _confirmador(s: Sesion):
    def confirmar(pregunta: str) -> bool:
        respuesta = s.preguntar(f"{pregunta} (di 'confirmo' o 'no')").strip()
        return es_afirmacion(respuesta)

    return confirmar


@orden("agent")
def agente(s: Sesion, m: Match) -> None:
    global _montaje
    if not m.argument:
        s.aviso("¿que quieres que haga?")
        return
    if _montaje is None:
        try:
            from doombot.agent.memoria import crear_memoria

            _montaje = montar(
                narrar=_narrador(s),
                confirmar=_confirmador(s),
                cfg=s.cfg,
                perfil=s.perfil,
                memoria=crear_memoria(),
            )
        except ValueError as e:
            s.aviso(str(e))
            return
        atexit.register(_montaje.cerrar)
    # Se reasignan en cada orden: la sesion es la que esta hablando ahora.
    _montaje.agente.narrar = _narrador(s)
    _montaje.agente.confirmar = _confirmador(s)
    s.estado("pensando")
    try:
        informe = _montaje.agente.ejecutar(m.argument)
    except BackendError as e:
        s.aviso(str(e))
        return
    s.decir(informe.respuesta or "hecho")
