"""Deteccion de hardware y seleccion de perfil.

El proyecto no sabe en que equipo corre. Mide la VRAM disponible y elige el
perfil de ``profiles.toml`` que le corresponde. Eso es lo que permite que el
mismo commit funcione en el sobremesa y en el portatil sin ramas ni variantes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from doombot.paths import PROFILES_FILE


@dataclass(frozen=True)
class EmbeddingConfig:
    """Modelo de embeddings. Global, no por perfil.

    A diferencia del modelo de lenguaje, este tiene que ser el mismo en todos
    los equipos: produce vectores que se almacenan y se comparan entre si, y
    dos modelos distintos generan espacios distintos. Ver el comentario de la
    seccion [embeddings] en profiles.toml.
    """

    model: str
    dimensions: int


@dataclass(frozen=True)
class Profile:
    """Un perfil resuelto, ya listo para pasar a los backends."""

    name: str
    description: str
    min_vram_mb: int

    llm_model: str
    llm_num_ctx: int
    llm_num_gpu: int
    llm_keep_alive: str

    stt_model: str
    stt_device: str
    stt_compute: str


def detect_vram_mb() -> int:
    """VRAM de la GPU mas grande, en MiB. Devuelve 0 si no hay ninguna usable.

    Usa ``nvidia-smi`` y no la API de Windows a proposito: ``Win32_VideoController``
    guarda ``AdapterRAM`` en un entero de 32 bits con signo, asi que informa mal
    en cuanto la tarjeta pasa de 4 GB â€”justo el caso que hay que distinguirâ€”.
    """
    exe = shutil.which("nvidia-smi")
    if exe is None:
        return 0
    try:
        salida = subprocess.run(
            [exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return 0

    valores = [int(x.strip()) for x in salida.splitlines() if x.strip().isdigit()]
    return max(valores, default=0)


def load_profiles(fichero: Path | None = None) -> dict[str, dict]:
    ruta = fichero or PROFILES_FILE
    with ruta.open("rb") as f:
        datos = tomllib.load(f)
    return datos["profiles"]


def select(vram_mb: int, perfiles: dict[str, dict]) -> str:
    """Nombre del perfil que corresponde a esa VRAM.

    Gana el de mayor ``min_vram_mb`` que no la supere, de modo que anadir un
    perfil intermedio no obliga a tocar esta funcion.
    """
    candidatos = [(d["min_vram_mb"], n) for n, d in perfiles.items() if d["min_vram_mb"] <= vram_mb]
    if not candidatos:
        raise RuntimeError(
            f"Ningun perfil admite {vram_mb} MiB de VRAM. "
            "Deberia haber uno con min_vram_mb = 0 en profiles.toml."
        )
    return max(candidatos)[1]


def current(fichero: Path | None = None) -> Profile:
    """Perfil activo. ``DOOMBOT_PROFILE`` lo fuerza; si no, se detecta."""
    perfiles = load_profiles(fichero)

    forzado = os.environ.get("DOOMBOT_PROFILE", "").strip()
    if forzado:
        if forzado not in perfiles:
            disponibles = ", ".join(sorted(perfiles))
            raise RuntimeError(f"DOOMBOT_PROFILE={forzado!r} no existe. Hay: {disponibles}.")
        nombre = forzado
    else:
        nombre = select(detect_vram_mb(), perfiles)

    d = perfiles[nombre]
    return Profile(
        name=nombre,
        description=d.get("description", ""),
        min_vram_mb=d["min_vram_mb"],
        llm_model=d["llm_model"],
        llm_num_ctx=d["llm_num_ctx"],
        llm_num_gpu=d.get("llm_num_gpu", 0),
        llm_keep_alive=d.get("llm_keep_alive", "5m"),
        stt_model=d["stt_model"],
        stt_device=d["stt_device"],
        stt_compute=d["stt_compute"],
    )


def embedding_config(fichero: Path | None = None) -> EmbeddingConfig:
    """Configuracion de embeddings, comun a todos los equipos."""
    ruta = fichero or PROFILES_FILE
    with ruta.open("rb") as f:
        datos = tomllib.load(f)
    d = datos["embeddings"]
    return EmbeddingConfig(model=d["model"], dimensions=d["dimensions"])
