"""Transcripcion en la nube, con Whisper en Groq (D-046).

Cumple ``Transcriber``, igual que ``WhisperTranscriber``. Existe para los
equipos donde Whisper local no compensa o no esta: el portatil sin GPU, o un
equipo sin el extra ``voice``. Groq sirve ``whisper-large-v3-turbo`` gratis
con la misma clave que ya se usa para el chat, y tarda menos de un segundo
en lo que una frase dicha.

Lo que cuesta: **el audio sale del equipo**. Por eso no es la opcion por
defecto donde hay Whisper local (``DOOMBOT_STT=auto``), y la ventana dice
cual se esta usando.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from doombot.backends.base import BackendError

_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MODELO = "whisper-large-v3-turbo"
_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)


class TranscriptorNube:
    """Whisper en Groq. ``model_name`` para que la ventana pueda decir cual es."""

    def __init__(
        self,
        clave: str,
        *,
        modelo: str = _MODELO,
        url: str = _URL,
        client: httpx.Client | None = None,
    ) -> None:
        if not clave:
            raise BackendError("Falta DOOMBOT_GROQ_API_KEY para transcribir en la nube.")
        self._clave = clave
        self.model_name = f"groq/{modelo}"
        self._modelo = modelo
        self._url = url
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    def transcribe(self, audio: Path, *, language: str = "es") -> str:
        try:
            with Path(audio).open("rb") as f:
                r = self._client.post(
                    self._url,
                    headers={"Authorization": f"Bearer {self._clave}"},
                    files={"file": (Path(audio).name, f, "audio/wav")},
                    data={"model": self._modelo, "language": language, "response_format": "text"},
                )
        except httpx.HTTPError as e:
            raise BackendError(f"No he podido transcribir en Groq: {e}") from e
        if r.status_code == 429:
            raise BackendError("Groq: sin cuota de transcripcion por ahora; prueba en un rato.")
        if r.status_code >= 400:
            raise BackendError(f"Groq devolvio {r.status_code} al transcribir: {r.text[:200]}")
        return r.text.strip()
