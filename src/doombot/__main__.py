"""Punto de entrada. Sin argumentos, informa del equipo donde esta corriendo.

    python -m doombot
    doombot            (tras instalar con pip install -e .)

Este diagnostico es lo primero que conviene ejecutar al sentarse en una
maquina distinta: dice que perfil ha elegido y por que, que es la pregunta
que surge cuando el asistente se comporta distinto de lo esperado.
"""

from __future__ import annotations

import sys

from doombot import __version__, profiles
from doombot.config import settings
from doombot.paths import PROJECT_ROOT, data_dir


def main() -> int:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
