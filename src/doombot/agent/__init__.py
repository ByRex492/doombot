"""Agente local: recibe una orden y la cumple solo, con herramientas (D-033).

    from doombot.agent import montar

    m = montar(narrar=lambda tipo, texto: print(texto), confirmar=lambda p: False)
    informe = m.agente.ejecutar("abre la calculadora")

A diferencia de ``actions.claude_code``, que delega en ``claude -p``, aqui el
bucle es propio y el cerebro es intercambiable: Ollama o Claude, ambos como
``ToolCaller`` (``backends/base.py``). Las herramientas cubren ficheros,
comandos, aplicaciones instaladas y un navegador propio.
"""

from doombot.agent.bucle import Agente, Informe
from doombot.agent.montaje import Montaje, montar

__all__ = ["Agente", "Informe", "Montaje", "montar"]
