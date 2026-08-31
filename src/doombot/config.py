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
    audio_input: str = ""
    """Fragmento del nombre del microfono, o cadena vacia para el del sistema.

    Es un nombre y no un indice a proposito: los indices de PortAudio se
    desplazan al enchufar o quitar un USB, asi que uno guardado aqui acaba
    apuntando a otro microfono. Ver ``voice.capture.Microphone``.
    """

    llm_backend: str = "ollama"
    """Que ``TextGenerator`` construye el orquestador: ``ollama`` o ``anthropic``.

    Ollama sigue siendo el que decide D-009: en la voz, la latencia local
    manda y el asistente tiene que funcionar sin conexion. Anthropic entra
    como segundo backend seleccionable para cuando pese mas la calidad de
    razonamiento que la latencia, a costa de mandar la conversacion fuera de
    la maquina.
    """
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

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
        audio_input=os.environ.get("DOOMBOT_AUDIO_INPUT", "").strip(),
        llm_backend=os.environ.get("DOOMBOT_LLM_BACKEND", "ollama").strip().lower(),
        anthropic_api_key=os.environ.get("DOOMBOT_ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.environ.get("DOOMBOT_ANTHROPIC_MODEL", "claude-sonnet-5").strip(),
    )
