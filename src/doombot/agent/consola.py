"""``python -m doombot agente``: el agente por escrito, al estilo de Claude Code.

Se escribe una orden, y el agente la cumple contando cada paso: lo que piensa
hacer, cada accion antes de hacerla y como salio. Lo irreversible se pregunta
en la propia consola. La conversacion se mantiene entre ordenes ("ahora
cierralo") hasta ``/nuevo``.
"""

from __future__ import annotations

import contextlib
import sys

from doombot.agent.montaje import Montaje, montar
from doombot.backends.base import BackendError
from doombot.phrases.matcher import es_afirmacion

AYUDA = (
    "Escribe lo que quieres que haga. /nuevo olvida lo anterior, /abiertas lista lo que he "
    "abierto, /salir termina. Ctrl+C corta la tarea en curso."
)

_FORMATO = {
    "comentario": "  · {}",
    "accion": "  → {}",
    "resultado": "    ✓ {}",
    "error": "    ✗ {}",
}


def narrar(tipo: str, texto: str) -> None:
    print(_FORMATO.get(tipo, "  {}").format(texto), flush=True)


def confirmar(pregunta: str) -> bool:
    try:
        respuesta = input(f"  ? {pregunta} ¿Confirmas? (s/N) ")
    except EOFError:
        return False
    return es_afirmacion(respuesta) or respuesta.strip().lower() in ("s", "y", "yes")


def _forzar_utf8() -> None:
    # Mismo motivo que en chat.py: la consola de Windows llega en cp1252.
    for flujo in (sys.stdin, sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError, ValueError):
            flujo.reconfigure(encoding="utf-8", errors="replace")


def _cabecera(m: Montaje) -> str:
    cerebro = m.agente.cerebro
    tipo = type(cerebro).__name__.removesuffix("Generator").lower()
    aviso = ""
    disponible = getattr(cerebro, "is_available", None)
    if disponible is not None and not disponible():
        aviso = (
            "\n  AVISO: el cerebro no responde (¿Ollama arrancado? ¿falta "
            "DOOMBOT_ANTHROPIC_API_KEY?). Ajusta DOOMBOT_AGENT_BRAIN en .env."
        )
    return (
        f"D.O.O.M agente · cerebro {tipo}/{cerebro.model_name} · "
        f"{len(m.agente.herramientas)} herramientas{aviso}"
    )


def run() -> int:
    _forzar_utf8()
    m = montar(narrar=narrar, confirmar=confirmar)
    print(_cabecera(m))
    print(AYUDA)
    try:
        while True:
            try:
                orden = input("\ndoom> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not orden:
                continue
            if orden in ("/salir", "/exit", "salir"):
                return 0
            if orden == "/nuevo":
                m.agente.olvidar()
                print("  (empiezo de cero)")
                continue
            if orden == "/abiertas":
                print("  " + (", ".join(m.abiertas()) or "nada todavia"))
                continue

            antes = len(m.abiertas())
            try:
                informe = m.agente.ejecutar(orden)
            except KeyboardInterrupt:
                print("\n  (tarea cortada)")
                continue
            except BackendError as e:
                print(f"\n  {e}", file=sys.stderr)
                continue
            print(f"D.O.O.M.: {informe.respuesta or '(sin respuesta)'}")
            nuevas = m.abiertas()[antes:]
            if nuevas:
                print(f"  (abierto en esta orden: {', '.join(nuevas)})")
    finally:
        m.cerrar()
