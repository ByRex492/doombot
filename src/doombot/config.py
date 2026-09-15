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

    agent_binary: str = "claude"
    agent_permission_mode: str = "plan"
    """Modo por defecto del agente de acciones (``actions.claude_code``).

    "plan" propone sin ejecutar. Es el valor seguro para una orden que llega
    por voz: solo se pasa a un modo que ejecuta de verdad si quien instala
    D.O.O.M lo decide explicitamente en su .env, nunca por defecto.
    """
    agent_allowed_tools: tuple[str, ...] = ()
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

    n8n_base_url: str = ""
    """Raiz del servidor de n8n, ej. ``http://127.0.0.1:5678``. Vacio = sin n8n."""
    n8n_workflows: tuple[tuple[str, str], ...] = ()
    """Lista blanca: nombre hablado -> ruta del webhook (D-030).

    Tupla de pares y no ``dict`` por el mismo motivo que ``agent_allowed_tools``:
    ``Settings`` es ``frozen`` y un campo mutable rompe esa garantia. Un
    webhook de n8n no tiene modo "plan" -ejecuta en cuanto llega la peticion-,
    asi que a diferencia del agente de acciones aqui no hay nivel de permiso
    que suavice la ejecucion: la unica salvaguarda es que el nombre hablado
    tenga una entrada aqui.
    """

    @property
    def is_remote_ollama(self) -> bool:
        """True si apuntamos al Ollama de otra maquina.

        Lo consulta la capa de voz: contra un Ollama remoto la latencia de red
        se suma a la de generacion, y merece la pena avisar en el arranque en
        vez de dejar que parezca que el modelo va lento.
        """
        return not any(x in self.ollama_host for x in ("127.0.0.1", "localhost", "::1"))


def _parse_n8n_workflows(raw: str) -> tuple[tuple[str, str], ...]:
    """``"backup:webhook/x,riego:webhook/y"`` -> ``(("backup","webhook/x"), ...)``.

    Un par mal formado -sin ``:``, o con el nombre o la ruta vacios- se
    descarta en vez de fallar: un error de sintaxis en ``.env`` no debe
    impedir arrancar D.O.O.M, solo dejar ese workflow fuera de la lista.
    """
    pares = []
    for trozo in raw.split(","):
        nombre, _, ruta = trozo.strip().partition(":")
        nombre, ruta = nombre.strip(), ruta.strip()
        if nombre and ruta:
            pares.append((nombre, ruta))
    return tuple(pares)


@lru_cache(maxsize=1)
def settings() -> Settings:
    load_env()
    tools = os.environ.get("DOOMBOT_AGENT_ALLOWED_TOOLS", "").strip()
    return Settings(
        ollama_host=os.environ.get("DOOMBOT_OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
        log_level=os.environ.get("DOOMBOT_LOG_LEVEL", "INFO").upper(),
        audio_input=os.environ.get("DOOMBOT_AUDIO_INPUT", "").strip(),
        agent_binary=os.environ.get("DOOMBOT_AGENT_BINARY", "claude").strip(),
        agent_permission_mode=os.environ.get("DOOMBOT_AGENT_PERMISSION_MODE", "plan").strip(),
        agent_allowed_tools=tuple(t.strip() for t in tools.split(",") if t.strip()),
        llm_backend=os.environ.get("DOOMBOT_LLM_BACKEND", "ollama").strip().lower(),
        anthropic_api_key=os.environ.get("DOOMBOT_ANTHROPIC_API_KEY", "").strip(),
        anthropic_model=os.environ.get("DOOMBOT_ANTHROPIC_MODEL", "claude-sonnet-5").strip(),
        n8n_base_url=os.environ.get("DOOMBOT_N8N_BASE_URL", "").strip().rstrip("/"),
        n8n_workflows=_parse_n8n_workflows(os.environ.get("DOOMBOT_N8N_WORKFLOWS", "").strip()),
    )
