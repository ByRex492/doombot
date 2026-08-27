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
from doombot.backends.base import BackendError
from doombot.backends.embeddings import FastEmbedder
from doombot.backends.ollama import OllamaGenerator
from doombot.identity import resumen, system_prompt
from doombot.memory import Memory
from doombot.paths import memory_db
from doombot.phrases import default_matcher


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
  que sabes sobre <algo>   lo busca y responde con lo que encuentre
  olvida eso               borra el ultimo recuerdo guardado
  para / silencio          ordenes de control (aun sin voz que parar)

Cualquier otra cosa va al modelo. Ademas:

  /memoria                 lista todo lo guardado
  /borrar                  vacia la memoria
  /estado                  que sabe hacer esta instalacion
  /salir                   terminar
"""


def _pintar_orden(m) -> None:
    print(f"  · orden {m.command} ({m.how}, {m.confidence})", file=sys.stderr)


def run() -> int:  # noqa: C901 - es un despachador, la longitud es la propia lista
    _forzar_utf8()

    try:
        perfil = profiles.current()
    except (RuntimeError, OSError) as e:
        print(f"No se pudo determinar el perfil: {e}", file=sys.stderr)
        return 1

    gen = OllamaGenerator.from_profile(perfil)
    if not gen.is_available():
        print("Ollama no responde. Arrancalo y vuelve a intentarlo.", file=sys.stderr)
        return 1

    matcher = default_matcher()
    embedder = FastEmbedder.from_config()

    print(f"D.O.O.M. · perfil {perfil.name} · {perfil.llm_model}")
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
                _responder(gen, f"{contexto}\n\nPregunta: {entrada}")
                continue

            if orden and orden.command == "forget":
                _pintar_orden(orden)
                if ultimo_guardado is not None and mem.forget(ultimo_guardado):
                    print("D.O.O.M> Olvidado.")
                    ultimo_guardado = None
                else:
                    print("D.O.O.M> No hay nada reciente que olvidar.")
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
            prompt = f"{contexto}\n\nPregunta: {entrada}" if contexto else entrada
            _responder(gen, prompt)


def _responder(gen: OllamaGenerator, prompt: str) -> None:
    print("D.O.O.M> ", end="", flush=True)
    try:
        for trozo in gen.stream(prompt, system=system_prompt()):
            print(trozo, end="", flush=True)
        print()
    except BackendError as e:
        print(f"\n  {e}", file=sys.stderr)
