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
from doombot.files import listar_buzon
from doombot.identity import resumen, system_prompt
from doombot.memory import Memory
from doombot.obsidian import escribir_perfil, sincronizar_perfil
from doombot.orders import Sesion, despachar
from doombot.paths import VAULT_DIR, inbox_dir, memory_db
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
  lee el archivo <cual>    lee un fichero del buzon y responde sobre el
  lee lo ultimo que te deje   el mas reciente que hayas soltado ahi
  para / silencio          ordenes de control (aun sin voz que parar)

Cualquier otra cosa va al modelo. Ademas:

  /memoria                 lista todo lo guardado
  /borrar                  vacia la memoria
  /entrada                 lista los ficheros del buzon
  /obsidian                relee usuario.md por si lo editaste a mano
  /estado                  que sabe hacer esta instalacion
  /salir                   terminar
"""


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

    with Memory(embedder) as mem:
        # Una sola Sesion para toda la conversacion: los manejadores la
        # mutan (que se guardo lo ultimo, que se respondio) y el bucle no
        # necesita saber cuales de ellos lo hacen.
        sesion = Sesion(
            gen=gen,
            mem=mem,
            cfg=cfg,
            perfil=perfil,
            agente=agente,
            responder=lambda prompt: _responder(sesion, prompt),
            con_contexto=lambda pregunta, *extra: _con_contexto(mem, pregunta, *extra),
            preguntar=input,
        )

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
                sesion.ultimo_guardado = None
                continue
            if entrada == "/entrada":
                ficheros = listar_buzon()
                if not ficheros:
                    print(f"  (buzon vacio) deja ficheros en {inbox_dir()}")
                for f in ficheros:
                    print(f"  {f.name}  ({f.stat().st_size / 1024:.1f} kB)")
                continue
            if entrada == "/obsidian":
                n = sincronizar_perfil(mem)
                escribir_perfil(mem)
                print(f"  {n} lineas leidas de {VAULT_DIR / 'usuario.md'}")
                continue

            sesion.entrada = entrada

            # --- una orden? -------------------------------------------------
            orden = matcher.match(entrada)

            if orden:
                if not despachar(sesion, orden):
                    # La orden existe pero nadie la implementa todavia. Se dice
                    # tal cual: identity.py existe para que D.O.O.M no mienta
                    # sobre lo que sabe hacer, y callarlo aqui seria mentir.
                    sesion.traza(f"orden {orden.command} ({orden.how}, {orden.confidence})")
                    sesion.decir(f"[{orden.command}] entendido, pero aun no puedo hacerlo.")
                continue

            # --- no es una orden: memoria + modelo --------------------------
            contexto = mem.as_context(entrada)
            if contexto:
                for linea in contexto.splitlines()[1:]:
                    sesion.traza(f"contexto {linea.lstrip('- ')}")
            sesion.responder(sesion.con_contexto(entrada, contexto))


def _responder(sesion: Sesion, prompt: str) -> None:
    """Genera en streaming y guarda lo dicho.

    Se acumula ademas de imprimirse porque "repite" y la voz van a necesitar la
    ultima respuesta entera, y por streaming solo pasan trozos sueltos.
    """
    print("D.O.O.M> ", end="", flush=True)
    partes: list[str] = []
    try:
        for trozo in sesion.gen.stream(prompt, system=system_prompt()):
            partes.append(trozo)
            print(trozo, end="", flush=True)
        print()
    except BackendError as e:
        print(f"\n  {e}", file=sys.stderr)
    sesion.ultima_respuesta = "".join(partes).strip()
