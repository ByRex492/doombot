"""Modo interactivo: escribir a D.O.O.M. y ver como reacciona.

Junta por primera vez las cuatro capas en un bucle: reconoce ordenes, consulta
la memoria, genera con el modelo. Es lo que permite probar el sistema entero
sin escribir Python.

Muestra ademas por que hace lo que hace —que orden reconocio, que recuerdos
encontro y con que parecido—, porque probando importa mas entender la decision
que leer la respuesta. La voz llegara despues; de momento se escribe.
"""

from __future__ import annotations

import contextlib
import sys

from doombot import profiles
from doombot.actions.claude_code import ClaudeCodeAgent
from doombot.backends.anthropic import AnthropicGenerator
from doombot.backends.base import BackendError, TextGenerator
from doombot.backends.embeddings import FastEmbedder
from doombot.backends.ollama import OllamaGenerator
from doombot.config import Settings, settings
from doombot.identity import resumen, system_prompt
from doombot.memory import Memory
from doombot.obsidian import anotar_progreso, escribir_perfil, sincronizar_perfil
from doombot.paths import VAULT_DIR, memory_db
from doombot.phrases import default_matcher
from doombot.profiles import Profile


def _forzar_utf8() -> None:
    """Windows entrega la consola en cp1252, no en UTF-8.

    Sin esto, escribir "mi portátil" guardaba "mi portÃ¡til" en la memoria: la
    tilde se lee con una codificacion y se escribe con otra. Y no es un
    problema cosmetico, porque ese texto corrupto es el que se vectoriza y el
    que se recupera despues.

    Se reconfiguran los tres flujos con errors="replace" para que un caracter
    que la consola no sepa representar salga como un interrogante en vez de
    tumbar la sesion entera.
    """
    for flujo in (sys.stdin, sys.stdout, sys.stderr):
        # Un flujo redirigido o sin soporte se queda como esta: mejor seguir
        # con la codificacion que haya que no arrancar.
        with contextlib.suppress(AttributeError, OSError, ValueError):
            flujo.reconfigure(encoding="utf-8", errors="replace")


AYUDA = """
Escribe lo que quieras. Se reconocen ordenes:

  recuerda que <algo>      guarda un hecho en la memoria
  recuerda que yo <algo>   guarda un hecho SOBRE TI, siempre presente
  que sabes sobre <algo>   lo busca y responde con lo que encuentre
  olvida eso               borra el ultimo recuerdo guardado
  ejecuta esto <tarea>     delega una tarea real en el agente de acciones
  apunta el progreso <algo>  anade una nota al vault de Obsidian
  para / silencio          ordenes de control (aun sin voz que parar)

Cualquier otra cosa va al modelo. Ademas:

  /memoria                 lista todo lo guardado
  /borrar                  vacia la memoria
  /obsidian                relee usuario.md por si lo editaste a mano
  /estado                  que sabe hacer esta instalacion
  /salir                   terminar
"""


def _pintar_orden(m) -> None:
    print(f"  · orden {m.command} ({m.how}, {m.confidence})", file=sys.stderr)


def _contexto_usuario(mem: Memory) -> str:
    """Hechos guardados SOBRE el usuario, siempre presentes en el prompt.

    A diferencia de ``Memory.as_context()``, no se filtra por parecido con la
    pregunta: quien habla y que hace es relevante para cualquier conversacion,
    no solo para las que lo mencionan de pasada.
    """
    perfil = mem.all(kind="perfil")
    if not perfil:
        return ""
    lineas = [f"- {r.text}" for r in perfil]
    return "Lo que sabes del usuario, siempre relevante:\n" + "\n".join(lineas)


def _con_contexto(mem: Memory, pregunta: str, *extra: str) -> str:
    bloques = [b for b in (_contexto_usuario(mem), *extra) if b]
    if not bloques:
        return pregunta
    return "\n\n".join([*bloques, f"Pregunta: {pregunta}"])


def _generador(perfil: Profile, cfg: Settings) -> TextGenerator:
    """El TextGenerator que toca segun DOOMBOT_LLM_BACKEND.

    Ollama por defecto (D-009: latencia local, funciona sin conexion).
    Anthropic es el segundo backend, seleccionable sin tocar el resto del
    bucle porque ambos cumplen el mismo contrato.
    """
    if cfg.llm_backend == "anthropic":
        return AnthropicGenerator.from_config(cfg)
    return OllamaGenerator.from_profile(perfil, cfg)


def run() -> int:  # noqa: C901 - es un despachador, la longitud es la propia lista
    _forzar_utf8()

    try:
        perfil = profiles.current()
    except (RuntimeError, OSError) as e:
        print(f"No se pudo determinar el perfil: {e}", file=sys.stderr)
        return 1

    cfg = settings()
    gen = _generador(perfil, cfg)
    if not gen.is_available():
        if cfg.llm_backend == "anthropic":
            print("Falta DOOMBOT_ANTHROPIC_API_KEY en .env.", file=sys.stderr)
        else:
            print("Ollama no responde. Arrancalo y vuelve a intentarlo.", file=sys.stderr)
        return 1

    matcher = default_matcher()
    embedder = FastEmbedder.from_config()
    # Construirlo no lanza ningun proceso -eso solo pasa en .run()-, asi que
    # se crea siempre, se use o no en esta sesion.
    agente = ClaudeCodeAgent.from_config(cfg)

    print(f"D.O.O.M. · perfil {perfil.name} · {cfg.llm_backend}/{gen.model_name}")
    print(f"memoria en {memory_db()}")
    print("Escribe /ayuda para ver las ordenes, /salir para terminar.\n")

    ultimo_guardado: int | None = None

    with Memory(embedder) as mem:
        while True:
            try:
                # Se limpian tambien BOM y espacios invisibles: al pegar
                # texto desde otro sitio se cuelan, y "/estado﻿" no
                # coincidiria con ningun comando.
                entrada = input("tu> ").strip().strip("﻿​ ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not entrada:
                continue

            # --- comandos de la propia consola -----------------------------
            if entrada in ("/salir", "/exit", "/q"):
                return 0
            if entrada == "/ayuda":
                print(AYUDA)
                continue
            if entrada == "/estado":
                print(f"  {resumen()}")
                print(f"  {mem.count()} recuerdos guardados")
                continue
            if entrada == "/memoria":
                todos = mem.all()
                if not todos:
                    print("  (vacia)")
                for r in todos:
                    print(f"  [{r.id}] {r.text}")
                continue
            if entrada == "/borrar":
                print(f"  borrados {mem.clear()} recuerdos")
                ultimo_guardado = None
                continue
            if entrada == "/obsidian":
                n = sincronizar_perfil(mem)
                escribir_perfil(mem)
                print(f"  {n} lineas leidas de {VAULT_DIR / 'usuario.md'}")
                continue

            # --- una orden? -------------------------------------------------
            orden = matcher.match(entrada)

            if orden and orden.command == "remember":
                if not orden.argument:
                    print("  ¿que quieres que recuerde?")
                    continue
                _pintar_orden(orden)
                ultimo_guardado = mem.remember(orden.argument)
                print(f"D.O.O.M> Apuntado: {orden.argument}")
                continue

            if orden and orden.command == "recall":
                _pintar_orden(orden)
                encontrados = mem.recall(orden.argument)
                for r in encontrados:
                    print(f"  · recuerda ({r.similarity:.2f}) {r.text}", file=sys.stderr)
                if not encontrados:
                    print("D.O.O.M> No tengo nada guardado sobre eso.")
                    continue
                contexto = mem.as_context(orden.argument)
                _responder(gen, _con_contexto(mem, entrada, contexto))
                continue

            if orden and orden.command == "forget":
                _pintar_orden(orden)
                if ultimo_guardado is not None and mem.forget(ultimo_guardado):
                    print("D.O.O.M> Olvidado.")
                    ultimo_guardado = None
                else:
                    print("D.O.O.M> No hay nada reciente que olvidar.")
                continue

            if orden and orden.command == "identify":
                if not orden.argument:
                    print("  ¿que quieres que sepa de ti?")
                    continue
                _pintar_orden(orden)
                ultimo_guardado = mem.remember(orden.argument, kind="perfil")
                escribir_perfil(mem)
                print(f"D.O.O.M> Anotado sobre ti: {orden.argument}")
                continue

            if orden and orden.command == "progress":
                if not orden.argument:
                    print("  ¿que quieres anotar?")
                    continue
                _pintar_orden(orden)
                ruta = anotar_progreso(orden.argument)
                print(f"D.O.O.M> Anotado en {ruta.relative_to(VAULT_DIR.parent)}")
                continue

            if orden and orden.command == "act":
                if not orden.argument:
                    print("  ¿que tarea quieres que ejecute?")
                    continue
                _pintar_orden(orden)
                print(f"  · delegando en el agente ({cfg.agent_permission_mode}), puede tardar...")
                try:
                    resultado = agente.run(orden.argument)
                except BackendError as e:
                    print(f"  {e}", file=sys.stderr)
                    continue
                estado = "hecho" if resultado.success else "fallo"
                print(f"D.O.O.M> [{estado}] {resultado.output}")
                continue

            if orden:
                _pintar_orden(orden)
                print(f"D.O.O.M> [{orden.command}] entendido, pero aun no puedo hacerlo.")
                continue

            # --- no es una orden: memoria + modelo --------------------------
            contexto = mem.as_context(entrada)
            if contexto:
                for linea in contexto.splitlines()[1:]:
                    print(f"  · contexto {linea.lstrip('- ')}", file=sys.stderr)
            _responder(gen, _con_contexto(mem, entrada, contexto))


def _responder(gen: TextGenerator, prompt: str) -> None:
    print("D.O.O.M> ", end="", flush=True)
    try:
        for trozo in gen.stream(prompt, system=system_prompt()):
            print(trozo, end="", flush=True)
        print()
    except BackendError as e:
        print(f"\n  {e}", file=sys.stderr)
