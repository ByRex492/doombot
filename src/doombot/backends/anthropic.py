"""Generador de texto sobre la API de Claude (Anthropic).

Cumple ``TextGenerator`` igual que ``OllamaGenerator``: mismo contrato, sin
heredar de el. Es el segundo backend, no un sustituto del primero: D-009
elige el modelo local por latencia y porque D.O.O.M tiene que funcionar sin
conexion (ver ``docs/decisiones.md``). Este backend entra para lo que pese
mas la calidad de razonamiento que la latencia, a costa de mandar la
conversacion fuera de la maquina.

Se habla en crudo con la API REST via ``httpx``, igual que con Ollama, en vez
de anadir el SDK oficial de Anthropic como dependencia: la superficie que se
usa es una llamada y su version en streaming, y ``httpx`` ya es dependencia
base del proyecto.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from typing import Any

import httpx

from doombot.backends.base import (
    BackendError,
    EspecHerramienta,
    LlamadaHerramienta,
    MensajeAgente,
    PasoModelo,
    ResultadoHerramienta,
    Turno,
)
from doombot.config import Settings, settings

_BASE_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

# Igual que en Ollama: conectar falla rapido si algo va mal, pero un modelo
# grande razonando puede tardar minutos en terminar de generar.
_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=30.0, pool=5.0)


class AnthropicGenerator:
    """Genera texto contra la API de mensajes de Anthropic."""

    def __init__(
        self,
        model: str = "claude-sonnet-5",
        *,
        api_key: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._temperature = temperature
        # Igual que en OllamaGenerator: el cliente se puede inyectar, asi se
        # prueba esta clase entera sin clave ni red de por medio.
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    @classmethod
    def from_config(cls, config: Settings | None = None, **kwargs: Any) -> AnthropicGenerator:
        cfg = config or settings()
        return cls(model=cfg.anthropic_model, api_key=cfg.anthropic_api_key, **kwargs)

    # -- el contrato ---------------------------------------------------------
    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> str:
        """Respuesta completa. Bloquea hasta que el modelo termina."""
        datos = self._post(self._cuerpo(prompt, system, historial, stream=False))
        bloques = datos.get("content", [])
        return "".join(b.get("text", "") for b in bloques if b.get("type") == "text").strip()

    def stream(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> Iterator[str]:
        """Respuesta por fragmentos, via server-sent events.

        Igual motivo que en Ollama: sintetizar la primera frase mientras se
        genera el resto evita que la voz espere la respuesta entera.
        """
        self._exigir_clave()
        cuerpo = self._cuerpo(prompt, system, historial, stream=True)
        try:
            with self._client.stream("POST", _BASE_URL, json=cuerpo, headers=self._headers()) as r:
                if r.status_code >= 400:
                    r.read()
                    raise self._error_http(r)
                for linea in r.iter_lines():
                    if not linea.startswith("data: "):
                        continue
                    try:
                        evento = json.loads(linea[len("data: ") :])
                    except json.JSONDecodeError:
                        continue
                    tipo = evento.get("type")
                    if tipo == "content_block_delta":
                        delta = evento.get("delta", {})
                        if delta.get("type") == "text_delta" and (texto := delta.get("text")):
                            yield texto
                    elif tipo == "message_stop":
                        return
        except httpx.HTTPError as e:
            raise self._error(e) from e

    # -- llamada a herramientas (D-033) ---------------------------------------
    def paso(
        self,
        conversacion: Sequence[MensajeAgente],
        herramientas: Sequence[EspecHerramienta],
        *,
        system: str | None = None,
    ) -> PasoModelo:
        """Un turno del agente: el modelo responde o pide herramientas.

        Mismo contrato que ``OllamaGenerator.paso``. La diferencia de formato
        queda aqui dentro: Anthropic devuelve bloques ``tool_use`` con su
        ``id``, y espera los resultados como bloques ``tool_result`` dentro de
        un mensaje del usuario, no como un rol propio.
        """
        mensajes: list[dict[str, Any]] = []

        def anadir(rol: str, bloque: dict[str, Any]) -> None:
            # La API exige alternar roles: varios resultados seguidos, o un
            # resultado seguido de una tarea nueva, van en el mismo mensaje.
            if mensajes and mensajes[-1]["role"] == rol:
                mensajes[-1]["content"].append(bloque)
            else:
                mensajes.append({"role": rol, "content": [bloque]})

        for m in conversacion:
            if isinstance(m, str):
                anadir("user", {"type": "text", "text": m})
            elif isinstance(m, PasoModelo):
                if m.texto or not m.llamadas:
                    anadir("assistant", {"type": "text", "text": m.texto or "(sin texto)"})
                for ll in m.llamadas:
                    anadir(
                        "assistant",
                        {
                            "type": "tool_use",
                            "id": ll.id,
                            "name": ll.nombre,
                            "input": ll.argumentos,
                        },
                    )
            elif isinstance(m, ResultadoHerramienta):
                anadir(
                    "user",
                    {"type": "tool_result", "tool_use_id": m.id, "content": m.contenido},
                )

        cuerpo: dict[str, Any] = {
            "model": self._model,
            # Escribir un fichero entero cabe en un solo turno: 1024 se queda
            # corto para eso, aunque sobre para una respuesta hablada.
            "max_tokens": max(self._max_tokens, 4096),
            "temperature": 0,
            "messages": mensajes,
            "tools": [
                {"name": h.nombre, "description": h.descripcion, "input_schema": h.parametros}
                for h in herramientas
            ],
        }
        if system:
            cuerpo["system"] = system

        datos = self._post(cuerpo)
        textos = []
        llamadas = []
        for b in datos.get("content", []):
            if b.get("type") == "text":
                textos.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                llamadas.append(
                    LlamadaHerramienta(
                        id=str(b.get("id", "")),
                        nombre=str(b.get("name", "")),
                        argumentos=b.get("input") or {},
                    )
                )
        return PasoModelo(texto="".join(textos).strip(), llamadas=tuple(llamadas))

    # -- extras utiles fuera del contrato ------------------------------------
    def is_available(self) -> bool:
        """True si hay una clave configurada.

        A diferencia de ``OllamaGenerator.is_available``, no comprueba la red:
        no hay un endpoint barato de salud en la API de Anthropic, y
        preguntarle con una peticion de verdad consumiria cuota solo para
        diagnosticar.
        """
        return bool(self._api_key)

    # -- interno -------------------------------------------------------------
    def _cuerpo(
        self, prompt: str, system: str | None, historial: Sequence[Turno], *, stream: bool
    ) -> dict[str, Any]:
        # A diferencia de Ollama, el sistema no es un mensaje mas: va en su
        # propio campo (D-026). Los turnos anteriores si son mensajes, con el
        # mismo formato role/content que ya usa esta API.
        cuerpo: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": [*historial, {"role": "user", "content": prompt}],
            "stream": stream,
        }
        if system:
            cuerpo["system"] = system
        return cuerpo

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    def _exigir_clave(self) -> None:
        if not self._api_key:
            raise BackendError(
                "Falta la clave de la API de Anthropic.\n"
                "Ajusta DOOMBOT_ANTHROPIC_API_KEY en .env.\n"
                "Se crea en https://console.anthropic.com/settings/keys"
            )

    def _post(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        self._exigir_clave()
        try:
            r = self._client.post(_BASE_URL, json=cuerpo, headers=self._headers())
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise self._error_http(e.response) from e
        except httpx.HTTPError as e:
            raise self._error(e) from e

    def _error_http(self, response: httpx.Response) -> BackendError:
        """Traduce un codigo de estado de la API a algo accionable."""
        try:
            detalle = response.json().get("error", {}).get("message", "")
        except (json.JSONDecodeError, ValueError):
            detalle = response.text

        codigo = response.status_code
        if codigo == 401:
            return BackendError(
                "La clave de la API de Anthropic no es valida.\n"
                "Comprueba DOOMBOT_ANTHROPIC_API_KEY en .env."
            )
        if codigo == 404:
            return BackendError(
                f"El modelo {self._model!r} no existe o tu cuenta no tiene acceso.\n"
                "Comprueba DOOMBOT_ANTHROPIC_MODEL en .env."
            )
        if codigo == 429:
            return BackendError(
                "Limite de peticiones alcanzado en la API de Anthropic. Espera un momento."
            )
        if codigo == 529:
            return BackendError(
                "La API de Anthropic esta sobrecargada. Reintenta en unos segundos."
            )
        return BackendError(f"Fallo hablando con la API de Anthropic ({codigo}): {detalle}")

    def _error(self, e: httpx.HTTPError) -> BackendError:
        if isinstance(e, httpx.ConnectError):
            return BackendError(
                "No hay respuesta de la API de Anthropic. Comprueba tu conexion a internet."
            )
        if isinstance(e, httpx.ReadTimeout):
            return BackendError(f"{self._model} tardo demasiado en responder.")
        return BackendError(f"Fallo hablando con la API de Anthropic: {e}")

    def __repr__(self) -> str:
        return f"AnthropicGenerator(model={self._model!r})"
