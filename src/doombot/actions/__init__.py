"""Capa de acciones: D.O.O.M ejecutando tareas reales, no solo respondiendo.

D-014 (docs/decisiones.md) decidio adoptar un estandar de skills en vez de
inventar uno propio cuando llegara esta capa. ``claude_code.py`` va un paso
antes de eso: delega la ejecucion en el propio Claude Code -el agente que
construye este proyecto- en modo no interactivo, en vez de escribir un
ejecutor de herramientas desde cero.

Exportar estos nombres activa la capacidad "actuar" en ``doombot.identity``,
que hasta ahora declaraba -con razon- que D.O.O.M no podia tocar nada.
"""

from doombot.actions.claude_code import AgentResult, ClaudeCodeAgent

__all__ = ["AgentResult", "ClaudeCodeAgent"]
