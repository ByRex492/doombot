"""Configuracion local, leida de .env y del entorno.

Todo lo que puede cambiar de un equipo a otro entra por aqui. Si un modulo
necesita saber algo del equipo, lo pide a este modulo en vez de mirarlo el.

El parser de .env es propio y son treinta lineas. Evita una dependencia mas
en un proyecto que ya arrastra un stack de audio pesado, y el formato que
necesitamos —clave=valor y comentarios— no da para mas.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from doombot.paths import ENV_FILE


def load_env(fichero: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Vuelca .env en ``os.environ``. Sin fichero, no hace nada.

    Por defecto NO pisa variables ya definidas: lo que venga del entorno real
    manda sobre el fichero, que es lo que permite forzar un valor puntual en
    una ejecucion sin editar nada.
    """
    ruta = fichero or ENV_FILE
    if not ruta.is_file():
        return {}

    leidas: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        leidas[clave] = valor
        if override or clave not in os.environ:
            os.environ[clave] = valor
    return leidas


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    log_level: str

    @property
    def is_remote_ollama(self) -> bool:
        """True si apuntamos al Ollama de otra maquina.

        Lo consulta la capa de voz: contra un Ollama remoto la latencia de red
        se suma a la de generacion, y merece la pena avisar en el arranque en
        vez de dejar que parezca que el modelo va lento.
        """
        return not any(x in self.ollama_host for x in ("127.0.0.1", "localhost", "::1"))


@lru_cache(maxsize=1)
def settings() -> Settings:
    load_env()
    return Settings(
        ollama_host=os.environ.get("DOOMBOT_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        log_level=os.environ.get("DOOMBOT_LOG_LEVEL", "INFO").upper(),
    )
