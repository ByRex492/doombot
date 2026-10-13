"""Catalogo de proveedores: de ``"groq:openai/gpt-oss-120b"`` a un generador (D-034).

Cada entrada de ``DOOMBOT_MODELOS`` es ``proveedor:modelo``. Se parte por el
PRIMER ``:`` -los nombres de modelo pueden llevar mas: ``qwen3:4b``,
``...:free``-. La clave de cada proveedor va en ``DOOMBOT_<PROVEEDOR>_API_KEY``.

Las capas gratuitas cambian a menudo (limites, modelos, condiciones). Lo que
hay aqui son las URLs, que son estables; que modelos usar y cuanto dejan
gastar se mira en el panel de cada uno. Ver D-034 para el estado medido a
13/10/2026.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from doombot.config import Settings


@dataclass(frozen=True)
class Proveedor:
    nombre: str
    base_url: str
    alta: str
    """Donde se crea la clave. Para decirselo al usuario cuando falte."""
    titulo: str = ""
    sugerido: str = ""
    """Modelo con el que se da de alta si el usuario no elige otro."""
    pasos: tuple[str, ...] = ()
    """Como conseguir la clave, para la pantalla de primeros pasos. Sin pasos, no sale ahi."""
    gratis: str = ""
    nota: str = ""


PROVEEDORES: dict[str, Proveedor] = {
    p.nombre: p
    for p in (
        Proveedor(
            "groq",
            "https://api.groq.com/openai/v1",
            "https://console.groq.com/keys",
            titulo="Groq",
            sugerido="openai/gpt-oss-120b",
            pasos=(
                "Abre la página y entra con tu cuenta de Google o de GitHub.",
                "En «API Keys», pulsa «Create API Key» y ponle un nombre (por ejemplo, doom).",
                "Copia la clave -empieza por gsk_ y solo se enseña una vez- y pégala aquí.",
            ),
            gratis="Unas 30 peticiones por minuto y 1.000 al día. Sin tarjeta.",
            nota="La más rápida. Empieza por esta.",
        ),
        Proveedor(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "https://aistudio.google.com/apikey",
            titulo="Gemini (Google)",
            sugerido="gemini-3.8-flash",
            pasos=(
                "Abre la página con tu cuenta de Google y acepta las condiciones de AI Studio.",
                "Pulsa «Create API key».",
                "Copia la clave -empieza por AIza- y pégala aquí.",
            ),
            gratis="Límites según el modelo; se ven en AI Studio. Sin tarjeta.",
            nota=(
                "Un segundo modelo de otra familia: activa la segunda opinión y «contrasta». "
                "En el plan gratuito, Google puede usar las peticiones para mejorar sus productos."
            ),
        ),
        Proveedor(
            "nvidia",
            "https://integrate.api.nvidia.com/v1",
            "https://build.nvidia.com",
            titulo="NVIDIA",
            sugerido="nvidia/nemotron-3-super-120b-a12b",
            pasos=(
                "Abre la página e inicia sesión; te pedirá unirte al programa de "
                "desarrolladores de NVIDIA, que es gratuito.",
                "Abre cualquier modelo y pulsa «Get API Key».",
                "Copia la clave -empieza por nvapi- y pégala aquí.",
            ),
            gratis="Unas 40 peticiones por minuto por modelo.",
            nota="Opcional: un tercer modelo para contrastar.",
        ),
        Proveedor(
            "openrouter",
            "https://openrouter.ai/api/v1",
            "https://openrouter.ai/keys",
            titulo="OpenRouter",
            sugerido="openai/gpt-oss-120b:free",
            pasos=(
                "Abre la página e inicia sesión.",
                "Pulsa «Create Key».",
                "Copia la clave -empieza por sk-or- y pégala aquí.",
            ),
            gratis="Solo 50 peticiones al día en los modelos gratuitos.",
            nota="De reserva: un agente gasta varias peticiones por orden.",
        ),
        Proveedor("mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys"),
        Proveedor("cerebras", "https://api.cerebras.ai/v1", "https://cloud.cerebras.ai"),
        Proveedor(
            "github",
            "https://models.github.ai/inference",
            "https://github.com/settings/tokens",
        ),
    )
}
# Estos dos no son "compatibles con OpenAI" para el proyecto: tienen backend
# propio, con sus particularidades ya resueltas.
_NATIVOS = ("ollama", "anthropic")


def partir(entrada: str) -> tuple[str, str]:
    proveedor, _, modelo = entrada.strip().partition(":")
    return proveedor.strip().lower(), modelo.strip()


def construir(entrada: str, cfg: Settings, **kwargs: Any) -> Any:
    """El generador de una entrada. Lanza ``ValueError`` si no se puede montar.

    El error dice exactamente que falta -proveedor desconocido, modelo vacio,
    clave ausente y donde sacarla-, porque es lo que el usuario va a leer.
    """
    proveedor, modelo = partir(entrada)
    if not modelo:
        raise ValueError(f"{entrada!r}: falta el modelo (formato proveedor:modelo).")

    if proveedor == "ollama":
        from doombot.backends.ollama import OllamaGenerator

        return OllamaGenerator(modelo, host=cfg.ollama_host, num_ctx=8192, **kwargs)
    if proveedor == "anthropic":
        from doombot.backends.anthropic import AnthropicGenerator

        return AnthropicGenerator(modelo, api_key=cfg.anthropic_api_key, **kwargs)

    p = PROVEEDORES.get(proveedor)
    if p is None:
        conocidos = ", ".join([*PROVEEDORES, *_NATIVOS])
        raise ValueError(f"{entrada!r}: proveedor desconocido. Conocidos: {conocidos}.")
    clave = cfg.clave(proveedor)
    if not clave:
        raise ValueError(
            f"{entrada!r}: falta DOOMBOT_{proveedor.upper()}_API_KEY en .env (se crea en {p.alta})."
        )
    from doombot.backends.openai_compat import OpenAICompatGenerator

    return OpenAICompatGenerator(
        modelo, base_url=p.base_url, api_key=clave, proveedor=proveedor, **kwargs
    )


def construir_todos(cfg: Settings) -> tuple[list[Any], list[str]]:
    """Los generadores de ``DOOMBOT_MODELOS`` que se pueden montar, y por que no los demas.

    Una entrada sin clave no impide arrancar: se avisa y se sigue con el resto.
    Es la idea de la cadena -no depender de uno-, aplicada tambien a la
    configuracion.
    """
    generadores, avisos = [], []
    for entrada in cfg.modelos:
        try:
            generadores.append(construir(entrada, cfg))
        except ValueError as e:
            avisos.append(str(e))
    return generadores, avisos
