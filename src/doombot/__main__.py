"""Punto de entrada.

    python -m doombot            diagnostico del equipo
    python -m doombot chat       modo interactivo, con memoria y ordenes
    python -m doombot "pregunta" se la lanza al modelo del perfil activo

El diagnostico es lo primero que conviene ejecutar al sentarse en una maquina
distinta: dice que perfil ha elegido y por que, que es la pregunta que surge
cuando el asistente se comporta distinto de lo esperado.
"""

from __future__ import annotations

import sys

from doombot import __version__, profiles
from doombot.backends.base import BackendError
from doombot.backends.ollama import OllamaGenerator
from doombot.config import settings
from doombot.identity import resumen, system_prompt
from doombot.paths import PROJECT_ROOT, data_dir

# El prompt se construye a partir de lo que esta instalacion sabe hacer de
# verdad. Ver doombot/identity.py: con uno fijo, el modelo afirmaba haber
# abierto programas y prometia recordar cosas sin haber memoria alguna.
SYSTEM = system_prompt()


def diagnostico() -> int:
    cfg = settings()

    try:
        perfil = profiles.current()
    except (RuntimeError, OSError) as e:
        print(f"No se pudo determinar el perfil: {e}", file=sys.stderr)
        return 1

    vram = profiles.detect_vram_mb()

    print(f"D.O.O.M {__version__}")
    print(f"  proyecto   {PROJECT_ROOT}")
    print(f"  datos      {data_dir()}")
    print()
    print(f"  VRAM       {vram} MiB" if vram else "  VRAM       sin GPU detectada")
    print(f"  perfil     {perfil.name}  ({perfil.description})")
    print()
    print(
        f"  modelo     {perfil.llm_model}  ctx={perfil.llm_num_ctx}  num_gpu={perfil.llm_num_gpu}"
    )
    print(f"  voz        {perfil.stt_model}  {perfil.stt_device}/{perfil.stt_compute}")
    print(f"  ollama     {cfg.ollama_host}{'  (remoto)' if cfg.is_remote_ollama else ''}")

    gen = OllamaGenerator.from_profile(perfil, cfg)
    if gen.is_available():
        instalados = gen.installed_models()
        tiene = any(m.split(":")[0] == perfil.llm_model.split(":")[0] for m in instalados)
        print(f"  estado     responde, {len(instalados)} modelos instalados")
        if not tiene:
            print(f"             falta {perfil.llm_model}: ollama pull {perfil.llm_model}")
    else:
        print("  estado     sin respuesta (¿Ollama arrancado?)")

    print()
    print(f"  sabe hacer {resumen()}")
    return 0


def preguntar(texto: str) -> int:
    """Lanza una pregunta al modelo del perfil activo, en streaming.

    Se usa ``stream`` y no ``generate`` para ver salir el texto segun se
    genera: es la misma via que usara la voz, y sirve para notar de inmediato
    si el modelo se ha quedado repartido entre CPU y GPU.
    """
    try:
        gen = OllamaGenerator.from_profile(profiles.current())
        for trozo in gen.stream(texto, system=SYSTEM):
            print(trozo, end="", flush=True)
        print()
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as e:
        print(f"{e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("chat", "-i", "--interactivo"):
        from doombot.chat import run

        return run()
    if args:
        return preguntar(" ".join(args))
    return diagnostico()


if __name__ == "__main__":
    raise SystemExit(main())
