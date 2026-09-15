"""Orden manual para enrutar una pregunta puntual a Claude (D-032).

No es un enrutador automatico: sigue sin haber criterio de cuando escalar de
Ollama a Claude (D-009 lo dejo abierto, la sesion del 31/08 lo anoto como
pendiente sin decidir). Esta orden no resuelve esa pregunta -la deja donde
estaba-, solo evita seguir sin nada mientras se decide: quien habla elige, una
vez, cuando le importa mas la calidad de razonamiento que la latencia.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.backends.anthropic import AnthropicGenerator
from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("ask_claude")
def preguntar_claude(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que le pregunto a Claude?")
        return
    s.traza("enrutando esta pregunta a Claude, no al backend por defecto...")
    # Cambio de sesion.gen solo para este turno: _responder ya sabe generar en
    # streaming, hablar si hay voz, y guardar el turno en el historial -no hay
    # nada de eso que reescribir aqui, solo prestarle el generador que toca.
    # Si falta DOOMBOT_ANTHROPIC_API_KEY, AnthropicGenerator.stream() lo dice
    # con un BackendError que _responder ya sabe mostrar y no propagar.
    original = s.gen
    s.gen = AnthropicGenerator.from_config(s.cfg)
    try:
        s.responder(s.con_contexto(m.argument))
    finally:
        s.gen = original
