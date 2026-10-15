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
    "Escribe lo que quieres que haga. /contrasta <pregunta> se la hace a todos los modelos y "
    "compara, /nuevo olvida lo anterior, /abiertas lista lo que he abierto, /salir termina. "
    "Ctrl+C corta la tarea en curso."
)

_FORMATO = {
    "comentario": "  · {}",
    "accion": "  → {}",
    "resultado": "    ✓ {}",
    "error": "    ✗ {}",
    "aviso": "    ↻ {}",
    "memoria": "  ◈ me acuerdo de: {}",
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
    from doombot.backends.varios import Cadena, etiqueta

    cerebro = m.agente.cerebro
    nombre = cerebro.model_name if isinstance(cerebro, Cadena) else etiqueta(cerebro)
    lineas = [f"D.O.O.M agente · {len(m.agente.herramientas)} herramientas · cerebro {nombre}"]
    if m.agente.revisar is not None:
        lineas.append("  segunda opinion de otro modelo antes de lo irreversible: activada")
    lineas += [f"  sin usar: {a}" for a in m.avisos]
    disponible = getattr(cerebro, "is_available", None)
    if disponible is not None and not disponible():
        lineas.append(
            "  AVISO: el cerebro no responde (¿Ollama arrancado? ¿falta una clave?). "
            "Ajusta DOOMBOT_AGENT_BRAIN y DOOMBOT_MODELOS en .env."
        )
    return "\n".join(lineas)


def _contrastar(pregunta: str) -> None:
    """``/contrasta``: la misma pregunta a todos los modelos, y un juez que compara."""
    from doombot.backends.proveedores import construir_todos
    from doombot.backends.varios import Consejo
    from doombot.config import settings

    generadores, _ = construir_todos(settings())
    if len(generadores) < 2:
        print("  Para contrastar hacen falta al menos dos modelos en DOOMBOT_MODELOS con su clave.")
        return
    print(f"  Preguntando a {len(generadores)} modelos a la vez...")
    veredicto = Consejo(generadores).consultar(pregunta)
    for o in veredicto.opiniones:
        marca = "✗" if o.fallo else "·"
        print(f"  {marca} {o.modelo}: {' '.join(o.texto.split())[:200]}")
    print(f"D.O.O.M.: {veredicto.final}")


def run() -> int:
    _forzar_utf8()
    try:
        from doombot.agent.memoria import crear_memoria
        from doombot.agent.taller import crear_taller

        m = montar(
            narrar=narrar, confirmar=confirmar, memoria=crear_memoria(), taller=crear_taller()
        )
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
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
            if orden.startswith("/contrasta"):
                pregunta = orden.removeprefix("/contrasta").strip()
                if not pregunta:
                    print("  Uso: /contrasta <pregunta>")
                    continue
                try:
                    _contrastar(pregunta)
                except BackendError as e:
                    print(f"  {e}", file=sys.stderr)
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
