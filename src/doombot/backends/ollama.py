"""Generador de texto sobre Ollama.

Cumple ``TextGenerator`` sin heredar de el: los contratos son ``Protocol``, y
basta con tener los metodos. Por eso este modulo no importa ``base``, y podria
vivir en otro paquete sin que nada cambiara.

La misma clase sirve para el Ollama local y para el del sobremesa por red: lo
unico que cambia es ``host``, que sale de la configuracion. No hay dos
implementaciones ni una rama que las distinga.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from doombot.backends.base import BackendError
from doombot.config import Settings, settings
from doombot.profiles import Profile

# La conexion se resuelve rapido o no se resuelve: si Ollama no esta escuchando
# conviene fallar en segundos, no dejar la voz colgada. La lectura, en cambio,
# tarda lo que tarde el modelo en generar, y en CPU eso puede irse a minutos.
_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)

# D-008: siempre /api/chat, nunca /api/generate.
#
# No es una preferencia de estilo. Medido en el sobremesa, /api/generate con
# gemma4:12b agotaba el limite de tokens devolviendo una respuesta VACIA
# (done_reason: length, 250 tokens generados, 0 caracteres). La causa es que
# /api/generate recibe el prompt en crudo, mientras que /api/chat aplica la
# plantilla de conversacion propia de cada modelo.
#
# El fallo no aparece con todos los modelos —en el portatil, llama3.2:3b
# respondia bien por /api/generate—, y por eso estuvo semanas sin detectarse:
# el codigo funcionaba en una maquina y devolvia el vacio en la otra.
#
# Ademas es el unico endpoint con historial de conversacion y tool calling,
# ambos necesarios en las capas siguientes.
RUTA_CHAT = "/api/chat"


class OllamaGenerator:
    """Genera texto contra un servidor Ollama."""

    def __init__(
        self,
        model: str,
        *,
        host: str = "http://127.0.0.1:11434",
        num_ctx: int = 4096,
        num_gpu: int = 0,
        keep_alive: str = "5m",
        temperature: float = 0.7,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._host = host.rstrip("/")
        self._keep_alive = keep_alive

        # Solo se mandan las opciones que se apartan del criterio de Ollama.
        # num_gpu = 0 significa "decide tu", y enviarlo explicitamente le
        # diria justo lo contrario: cero capas en GPU, todo a CPU.
        self._options: dict[str, Any] = {"num_ctx": num_ctx, "temperature": temperature}
        if num_gpu:
            self._options["num_gpu"] = num_gpu

        # El cliente se puede inyectar. Es lo que permite probar esta clase
        # entera sin un Ollama delante, en cualquier equipo y en cualquier CI.
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    # -- construccion desde el perfil activo ---------------------------------
    @classmethod
    def from_profile(
        cls,
        profile: Profile,
        config: Settings | None = None,
        **kwargs: Any,
    ) -> OllamaGenerator:
        """Arma el generador con lo que diga el perfil y la configuracion.

        Aqui se juntan las tres piezas por primera vez, y ninguna conoce a las
        otras: ``profiles`` mide el hardware, ``config`` sabe donde escucha
        Ollama, y esta clase sabe hablar el protocolo. El unico sitio del
        proyecto donde se relacionan es este metodo.
        """
        cfg = config or settings()
        return cls(
            model=profile.llm_model,
            host=cfg.ollama_host,
            num_ctx=profile.llm_num_ctx,
            num_gpu=profile.llm_num_gpu,
            keep_alive=profile.llm_keep_alive,
            **kwargs,
        )

    # -- el contrato ---------------------------------------------------------
    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Respuesta completa. Bloquea hasta que el modelo termina."""
        datos = self._post(RUTA_CHAT, self._cuerpo(prompt, system, stream=False))
        return str(datos.get("message", {}).get("content", "")).strip()

    def stream(self, prompt: str, *, system: str | None = None) -> Iterator[str]:
        """Respuesta por fragmentos, segun los va produciendo el modelo.

        Lo necesita la voz. Con 29 tok/s, una respuesta de cien palabras tarda
        unos cinco segundos: esperarla entera son cinco segundos de silencio
        antes de empezar a hablar. Con streaming se sintetiza la primera frase
        mientras se genera el resto.
        """
        cuerpo = self._cuerpo(prompt, system, stream=True)
        url = f"{self._host}{RUTA_CHAT}"
        try:
            with self._client.stream("POST", url, json=cuerpo) as r:
                r.raise_for_status()
                for linea in r.iter_lines():
                    if not linea:
                        continue
                    try:
                        trozo = json.loads(linea)
                    except json.JSONDecodeError:
                        continue
                    if texto := trozo.get("message", {}).get("content"):
                        yield texto
                    if trozo.get("done"):
                        return
        except httpx.HTTPError as e:
            raise self._error(e) from e

    # -- extras utiles fuera del contrato ------------------------------------
    def is_available(self) -> bool:
        """True si el servidor responde. No lanza: sirve para diagnosticar."""
        try:
            r = self._client.get(f"{self._host}/api/tags", timeout=5.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def installed_models(self) -> list[str]:
        datos = self._get("/api/tags")
        return sorted(m["name"] for m in datos.get("models", []))

    # -- interno -------------------------------------------------------------
    def _cuerpo(self, prompt: str, system: str | None, *, stream: bool) -> dict[str, Any]:
        """Cuerpo para /api/chat: mensajes con rol, no un prompt en crudo.

        El rol de sistema va como un mensaje mas, el primero de la lista. Es la
        forma que espera este endpoint, y la que permite anadir historial de
        conversacion mas adelante sin cambiar nada de esta estructura.
        """
        mensajes: list[dict[str, str]] = []
        if system:
            mensajes.append({"role": "system", "content": system})
        mensajes.append({"role": "user", "content": prompt})

        return {
            "model": self._model,
            "messages": mensajes,
            "stream": stream,
            "options": self._options,
            "keep_alive": self._keep_alive,
        }

    def _post(self, ruta: str, cuerpo: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._client.post(f"{self._host}{ruta}", json=cuerpo)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise self._error(e) from e

    def _get(self, ruta: str) -> dict[str, Any]:
        try:
            r = self._client.get(f"{self._host}{ruta}")
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise self._error(e) from e

    def _error(self, e: httpx.HTTPError) -> BackendError:
        """Traduce el fallo de red a algo que se le pueda decir al usuario.

        Un ``ConnectError`` pelado no ayuda a nadie. Las dos causas reales son
        que Ollama no este arrancado o que el modelo no este descargado, y
        ambas tienen arreglo en un comando.
        """
        if isinstance(e, httpx.ConnectError):
            return BackendError(
                f"No hay respuesta de Ollama en {self._host}. "
                "Comprueba que este arrancado, o ajusta DOOMBOT_OLLAMA_HOST en .env."
            )
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
            return BackendError(
                f"El modelo {self._model!r} no esta en {self._host}. "
                f"Descargalo con: ollama pull {self._model}"
            )
        if isinstance(e, httpx.ReadTimeout):
            return BackendError(
                f"{self._model} tardo demasiado en responder. "
                "Con el modelo repartido entre CPU y GPU esto es esperable: "
                "comprueba con 'ollama ps' que PROCESSOR diga 100% GPU."
            )
        return BackendError(f"Fallo hablando con Ollama en {self._host}: {e}")

    def __repr__(self) -> str:
        return f"OllamaGenerator(model={self._model!r}, host={self._host!r})"
