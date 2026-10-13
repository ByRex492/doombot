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


@orden("crosscheck")
def contrastar(s: Sesion, m: Match) -> None:
    """La misma pregunta a todos los modelos de DOOMBOT_MODELOS, y un juez que compara (D-034)."""
    from doombot.backends.base import BackendError
    from doombot.backends.proveedores import construir_todos
    from doombot.backends.varios import Consejo

    if not m.argument:
        s.aviso("¿que quieres que contraste?")
        return
    generadores, avisos = construir_todos(s.cfg)
    if len(generadores) < 2:
        s.aviso("Para contrastar hacen falta al menos dos modelos en DOOMBOT_MODELOS con su clave.")
        for aviso in avisos:
            s.traza(aviso)
        return
    s.traza(f"preguntando a {len(generadores)} modelos a la vez...")
    s.estado("pensando")
    try:
        veredicto = Consejo(generadores).consultar(s.con_contexto(m.argument))
    except BackendError as e:
        s.aviso(str(e))
        return
    for o in veredicto.opiniones:
        s.traza(f"{'fallo ' if o.fallo else ''}{o.modelo}: {' '.join(o.texto.split())[:160]}")
    s.decir(veredicto.final)
