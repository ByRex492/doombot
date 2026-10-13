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

import difflib
import json
import re
import time
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

# Un modelo gratuito que tarda mas de un minuto suele estar saturado: mejor
# pasar al siguiente de la cadena que dejar al usuario esperando.
_TIMEOUT = httpx.Timeout(connect=5.0, read=40.0, write=30.0, pool=5.0)
# Algunos modelos de razonamiento (qwen3, deepseek) devuelven su pensamiento
# dentro del texto. No es respuesta para el usuario.
_PENSAMIENTO = re.compile(r"<think>.*?</think>", re.DOTALL)


# Valor que Google documenta para llamadas a herramientas que no genero Gemini.
_FIRMA_AJENA = "skip_thought_signature_validator"
# Si el proveedor pide esperar menos que esto, se espera y se reintenta una vez
# en vez de dar el modelo por agotado: el limite gratuito de Groq es por minuto.
_ESPERA_MAXIMA = 12.0


class LlamadaInvalida(BackendError):
    """El proveedor rechazo una llamada a una herramienta que no se le ofrecio.

    Groq valida las llamadas en el servidor: si el modelo se inventa un nombre
    ("clickar" por "clicar") devuelve un 400 en vez de pasarnos la llamada para
    que el bucle le diga que no existe. ``nombre`` es lo que intento llamar.
    """

    def __init__(self, mensaje: str, nombre: str) -> None:
        super().__init__(mensaje)
        self.nombre = nombre


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
        # Inyectable para que los tests no esperen de verdad.
        self._dormir = time.sleep

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
                    mensaje["tool_calls"] = self._llamadas_salientes(m.llamadas)
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
        try:
            datos = self._post(cuerpo)
        except LlamadaInvalida as e:
            # Una vez mas, diciendole que herramientas hay de verdad y cual
            # queria seguramente. Si vuelve a fallar, el error sigue su camino.
            nombres = [h.nombre for h in herramientas]
            parecida = difflib.get_close_matches(e.nombre, nombres, n=1, cutoff=0.6)
            pista = f" ¿Querias decir «{parecida[0]}»?" if parecida else ""
            aviso = (
                f"(Aviso del sistema) La herramienta «{e.nombre}» no existe.{pista} Usa solo "
                f"estas, con su nombre exacto: {', '.join(nombres)}."
            )
            cuerpo["messages"] = [*cuerpo["messages"], {"role": "user", "content": aviso}]
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
                    extra={"extra_content": ll["extra_content"]} if ll.get("extra_content") else {},
                )
            )
        return PasoModelo(texto=texto, llamadas=tuple(llamadas))

    def _llamadas_salientes(self, llamadas: Sequence[LlamadaHerramienta]) -> list[dict[str, Any]]:
        """Las llamadas de un turno anterior, en formato OpenAI, con su firma si la hay.

        Gemini 3 firma su razonamiento en ``extra_content.google.thought_signature``
        y exige recibirlo de vuelta; sin firma responde 400 y rechaza la
        conversacion entera. Las llamadas que no hizo Gemini -las de otro modelo
        de la cadena- no tienen firma: para esas Google documenta un valor de
        relleno que salta la comprobacion, a costa de que Gemini no recuerde ese
        razonamiento (que de todos modos no era suyo).
        """
        firmadas = any("extra_content" in ll.extra for ll in llamadas)
        salida = []
        for ll in llamadas:
            item: dict[str, Any] = {
                "id": ll.id,
                "type": "function",
                "function": {
                    "name": ll.nombre,
                    "arguments": json.dumps(ll.argumentos, ensure_ascii=False),
                },
            }
            if "extra_content" in ll.extra:
                item["extra_content"] = ll.extra["extra_content"]
            elif self.proveedor == "gemini" and not firmadas:
                item["extra_content"] = {"google": {"thought_signature": _FIRMA_AJENA}}
            salida.append(item)
        return salida

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

    def _post(self, cuerpo: dict[str, Any], *, reintento: bool = True) -> dict[str, Any]:
        try:
            r = self._client.post(self._url, json=cuerpo, headers=self._headers())
        except httpx.HTTPError as e:
            raise self._error(e) from e
        if r.status_code == 429 and reintento:
            espera = _segundos(r.headers.get("retry-after"))
            if espera is not None and espera <= _ESPERA_MAXIMA:
                self._dormir(espera + 0.5)
                return self._post(cuerpo, reintento=False)
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
        if r.status_code == 503:
            # "Demasiada demanda": pasajero, como el 429. Que la cadena lo aparte un rato.
            return LimiteAlcanzado(f"{quien}: saturado ahora mismo, prueba en un momento.")
        if r.status_code == 400 and "tool call validation failed" in detalle.lower():
            nombre = re.search(r"call tool '([^']+)'", detalle)
            return LlamadaInvalida(
                f"{quien}: pidio una herramienta que no existe. {detalle}",
                nombre.group(1) if nombre else "",
            )
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
            # Pasajero, como un 429: la cadena lo aparta un rato en vez de volver
            # a esperarlo un minuto entero en el paso siguiente.
            return LimiteAlcanzado(f"{self.model_name}: tardo demasiado en responder.")
        return BackendError(f"{self.model_name}: {e}")

    def __repr__(self) -> str:
        return f"OpenAICompatGenerator({self.model_name!r})"


def _segundos(cabecera: str | None) -> float | None:
    """``Retry-After`` en segundos, o None si no viene o no es un numero."""
    try:
        return max(0.0, float(cabecera)) if cabecera is not None else None
    except ValueError:
        return None
