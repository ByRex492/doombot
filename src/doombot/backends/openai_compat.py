"""Generador sobre cualquier API compatible con la de OpenAI (D-034).

Casi todos los proveedores con capa gratuita hablan el mismo formato -Groq,
Gemini (su capa de compatibilidad), OpenRouter, NVIDIA NIM, Mistral,
Cerebras, GitHub Models-: ``POST {base}/chat/completions`` con ``messages`` y
``tools``. Una sola clase los cubre a todos; lo unico que cambia es la URL,
la clave y el modelo, que salen de ``backends/proveedores.py``.

Cumple ``TextGenerator`` y ``ToolCaller`` sin heredar de ellos, igual que
``OllamaGenerator`` y ``AnthropicGenerator``. Se habla en crudo con ``httpx``
por el mismo motivo que con Anthropic: la superficie es una llamada y su
version en streaming, y no merece un SDK como dependencia.
"""

from __future__ import annotations

import json
import re
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

_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
# Algunos modelos de razonamiento (qwen3, deepseek) devuelven su pensamiento
# dentro del texto. No es respuesta para el usuario.
_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.DOTALL)


class LimiteAlcanzado(BackendError):
    """El proveedor ha dicho que basta por ahora (HTTP 429).

    Tipo propio porque en una cadena de modelos no es un fallo del todo: el
    proveedor volvera a responder en un rato, y mientras tanto se salta.
    """


class OpenAICompatGenerator:
    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str = "",
        proveedor: str = "openai-compat",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self.proveedor = proveedor
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    # -- el contrato ---------------------------------------------------------
    @property
    def model_name(self) -> str:
        return f"{self.proveedor}/{self._model}"

    def generate(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> str:
        datos = self._post(self._cuerpo(self._mensajes(prompt, system, historial), stream=False))
        mensaje = (datos.get("choices") or [{}])[0].get("message", {})
        return _PENSAMIENTO.sub("", str(mensaje.get("content") or "")).strip()

    def stream(
        self, prompt: str, *, system: str | None = None, historial: Sequence[Turno] = ()
    ) -> Iterator[str]:
        cuerpo = self._cuerpo(self._mensajes(prompt, system, historial), stream=True)
        try:
            with self._client.stream("POST", self._url, json=cuerpo, headers=self._headers()) as r:
                if r.status_code >= 400:
                    r.read()
                    raise self._error_http(r)
                for linea in r.iter_lines():
                    if not linea.startswith("data: "):
                        continue
                    carga = linea[len("data: ") :].strip()
                    if carga == "[DONE]":
                        return
                    try:
                        evento = json.loads(carga)
                    except json.JSONDecodeError:
                        continue
                    delta = (evento.get("choices") or [{}])[0].get("delta", {})
                    if texto := delta.get("content"):
                        yield texto
        except httpx.HTTPError as e:
            raise self._error(e) from e

    def paso(
        self,
        conversacion: Sequence[MensajeAgente],
        herramientas: Sequence[EspecHerramienta],
        *,
        system: str | None = None,
    ) -> PasoModelo:
        mensajes: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
        for m in conversacion:
            if isinstance(m, str):
                mensajes.append({"role": "user", "content": m})
            elif isinstance(m, PasoModelo):
                mensaje: dict[str, Any] = {"role": "assistant", "content": m.texto or None}
                if m.llamadas:
                    mensaje["tool_calls"] = [
                        {
                            "id": ll.id,
                            "type": "function",
                            "function": {
                                "name": ll.nombre,
                                "arguments": json.dumps(ll.argumentos, ensure_ascii=False),
                            },
                        }
                        for ll in m.llamadas
                    ]
                mensajes.append(mensaje)
            elif isinstance(m, ResultadoHerramienta):
                mensajes.append({"role": "tool", "tool_call_id": m.id, "content": m.contenido})

        cuerpo = self._cuerpo(mensajes, stream=False, temperatura=0)
        if herramientas:
            cuerpo["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": h.nombre,
                        "description": h.descripcion,
                        "parameters": h.parametros,
                    },
                }
                for h in herramientas
            ]
        datos = self._post(cuerpo)
        mensaje_resp = (datos.get("choices") or [{}])[0].get("message", {})
        texto = _PENSAMIENTO.sub("", str(mensaje_resp.get("content") or "")).strip()

        llamadas = []
        for i, ll in enumerate(mensaje_resp.get("tool_calls") or []):
            funcion = ll.get("function", {})
            crudos = funcion.get("arguments") or "{}"
            try:
                argumentos = json.loads(crudos) if isinstance(crudos, str) else crudos
            except json.JSONDecodeError:
                argumentos = {}
            llamadas.append(
                LlamadaHerramienta(
                    id=str(ll.get("id") or f"llamada_{i}"),
                    nombre=str(funcion.get("name", "")),
                    argumentos=argumentos if isinstance(argumentos, dict) else {},
                )
            )
        return PasoModelo(texto=texto, llamadas=tuple(llamadas))

    # -- extras --------------------------------------------------------------
    def is_available(self) -> bool:
        """True si hay clave. Igual que en Anthropic: no se gasta cuota en comprobarlo."""
        return bool(self._api_key)

    # -- interno -------------------------------------------------------------
    @staticmethod
    def _mensajes(
        prompt: str, system: str | None, historial: Sequence[Turno]
    ) -> list[dict[str, Any]]:
        mensajes: list[dict[str, Any]] = [{"role": "system", "content": system}] if system else []
        mensajes.extend(historial)
        mensajes.append({"role": "user", "content": prompt})
        return mensajes

    def _cuerpo(
        self, mensajes: list[dict[str, Any]], *, stream: bool, temperatura: float | None = None
    ) -> dict[str, Any]:
        return {
            "model": self._model,
            "messages": mensajes,
            "stream": stream,
            "temperature": self._temperature if temperatura is None else temperatura,
            "max_tokens": self._max_tokens,
        }

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise BackendError(
                f"Falta la clave de {self.proveedor}. Ajusta "
                f"DOOMBOT_{self.proveedor.upper()}_API_KEY en .env."
            )
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    def _post(self, cuerpo: dict[str, Any]) -> dict[str, Any]:
        try:
            r = self._client.post(self._url, json=cuerpo, headers=self._headers())
        except httpx.HTTPError as e:
            raise self._error(e) from e
        if r.status_code >= 400:
            raise self._error_http(r)
        return r.json()

    def _error_http(self, r: httpx.Response) -> BackendError:
        try:
            cuerpo = r.json()
            detalle = cuerpo.get("error", {})
            detalle = detalle.get("message", "") if isinstance(detalle, dict) else str(detalle)
        except (json.JSONDecodeError, ValueError, AttributeError):
            detalle = r.text[:300]
        quien = self.model_name
        if r.status_code == 429:
            return LimiteAlcanzado(f"{quien}: limite de uso gratuito alcanzado por ahora.")
        if r.status_code in (401, 403):
            return BackendError(
                f"{quien}: clave rechazada. Revisa DOOMBOT_{self.proveedor.upper()}_API_KEY."
            )
        if r.status_code == 404:
            return BackendError(f"{quien}: ese modelo no existe en {self.proveedor}. {detalle}")
        return BackendError(f"{quien}: error {r.status_code}. {detalle}")

    def _error(self, e: httpx.HTTPError) -> BackendError:
        if isinstance(e, httpx.ConnectError):
            return BackendError(f"{self.model_name}: sin conexion con {self.proveedor}.")
        if isinstance(e, httpx.TimeoutException):
            return BackendError(f"{self.model_name}: tardo demasiado en responder.")
        return BackendError(f"{self.model_name}: {e}")

    def __repr__(self) -> str:
        return f"OpenAICompatGenerator({self.model_name!r})"
