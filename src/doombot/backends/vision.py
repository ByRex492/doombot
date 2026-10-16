"""Un modelo que ve: describe una imagen o responde preguntas sobre ella (D-047).

Habla el formato de imagenes de la API compatible con OpenAI (``image_url`` con
la imagen en base64), que entienden Gemini, Groq, NVIDIA y OpenRouter. Por
defecto se usa el primer Gemini de ``DOOMBOT_MODELOS``: ve bien y su capa
gratuita da de sobra para unas capturas al dia. ``DOOMBOT_VISION`` elige otro.

Va aparte de la cadena (D-034) a proposito: no todos sus modelos ven, y
mandar una imagen a uno que no ve devuelve un error o, peor, una respuesta
inventada.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from doombot.backends.base import BackendError

_TIMEOUT = httpx.Timeout(connect=5.0, read=40.0, write=30.0, pool=5.0)


class ModeloVision:
    """Un modelo con vision detras de una API compatible con OpenAI."""

    def __init__(
        self,
        modelo: str,
        *,
        base_url: str,
        api_key: str,
        proveedor: str = "",
        client: httpx.Client | None = None,
    ) -> None:
        self._modelo = modelo
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._clave = api_key
        self.model_name = f"{proveedor}/{modelo}" if proveedor else modelo
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    def mirar(self, imagen: bytes, pregunta: str, *, mime: str = "image/jpeg") -> str:
        datos = base64.b64encode(imagen).decode("ascii")
        cuerpo = {
            "model": self._modelo,
            "temperature": 0.2,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": pregunta},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{datos}"}},
                    ],
                }
            ],
        }
        try:
            r = self._client.post(
                self._url, json=cuerpo, headers={"Authorization": f"Bearer {self._clave}"}
            )
        except httpx.HTTPError as e:
            raise BackendError(f"No he podido hablar con {self.model_name}: {e}") from e
        if r.status_code == 429:
            raise BackendError(f"{self.model_name}: sin cuota por ahora; prueba en un rato.")
        if r.status_code >= 400:
            raise BackendError(f"{self.model_name} devolvio {r.status_code}: {r.text[:300]}")
        try:
            texto = r.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise BackendError(f"{self.model_name}: respuesta que no entiendo ({e})") from e
        return texto.strip()


def eleccion(cfg: Any) -> str:
    """El modelo de vision: ``DOOMBOT_VISION``, o el primer Gemini de la cadena."""
    elegido = (getattr(cfg, "vision", "") or "").strip()
    if elegido:
        return elegido
    return next((m for m in getattr(cfg, "modelos", ()) if m.startswith("gemini:")), "")


def construir_vision(cfg: Any) -> ModeloVision:
    """El modelo de vision de esta instalacion. ``ValueError`` con el motivo si no hay."""
    from doombot.backends.proveedores import PROVEEDORES, partir

    entrada = eleccion(cfg)
    if not entrada:
        raise ValueError(
            "Para ver hace falta un modelo con vision: pon un Gemini en DOOMBOT_MODELOS o "
            "DOOMBOT_VISION=proveedor:modelo en .env."
        )
    proveedor, modelo = partir(entrada)
    p = PROVEEDORES.get(proveedor)
    if p is None or not modelo:
        raise ValueError(
            f"DOOMBOT_VISION={entrada!r}: tiene que ser proveedor:modelo de una API compatible "
            f"con OpenAI ({', '.join(PROVEEDORES)})."
        )
    clave = cfg.clave(proveedor)
    if not clave:
        raise ValueError(f"Para ver con {entrada} falta DOOMBOT_{proveedor.upper()}_API_KEY.")
    return ModeloVision(modelo, base_url=p.base_url, api_key=clave, proveedor=proveedor)
