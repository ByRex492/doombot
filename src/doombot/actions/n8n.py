"""Dispara workflows de n8n por webhook, solo los que esten en la lista blanca.

D-030 (docs/decisiones.md): a diferencia de ``claude_code.py``, un webhook de
n8n no tiene un modo "plan" que proponga sin ejecutar -en cuanto llega la
peticion, el workflow corre de verdad-. Por eso la salvaguarda no es un nivel
de permiso, sino que el nombre dicho por voz tenga una entrada exacta en
``DOOMBOT_N8N_WORKFLOWS``: lo que no esta en esa lista no dispara nada, solo
avisa de cuales si lo estan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from doombot.backends.base import BackendError
from doombot.phrases.matcher import normalize

# Un workflow puede tardar lo que tarde n8n en ejecutarlo -no es una lectura,
# es la propia automatizacion corriendo-. Igual de generoso que el agente de
# acciones (D-014) y por el mismo motivo: una tarea asi ya se anuncia como
# "esto va a tardar", no como una respuesta inmediata.
_TIMEOUT = httpx.Timeout(connect=5.0, read=300.0, write=10.0, pool=5.0)


@dataclass(frozen=True)
class WorkflowResult:
    """Lo que devuelve disparar un workflow."""

    success: bool
    status_code: int
    output: str = ""


class N8nClient:
    """Dispara un workflow de n8n por su nombre, resuelto contra la lista blanca."""

    def __init__(
        self,
        *,
        base_url: str = "",
        workflows: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Normalizado igual que las ordenes de voz (mayusculas, tildes,
        # muletillas): el nombre llega desde Whisper, no escrito a mano.
        self._workflows = {normalize(k): v for k, v in (workflows or {}).items()}
        # Igual criterio que en los backends HTTP: el cliente se puede
        # inyectar, asi se prueba esta clase sin lanzar peticiones de verdad.
        self._client = client or httpx.Client(timeout=_TIMEOUT)

    @classmethod
    def from_config(cls, config: Any = None, **kwargs: Any) -> N8nClient:
        from doombot.config import settings

        cfg = config or settings()
        return cls(base_url=cfg.n8n_base_url, workflows=dict(cfg.n8n_workflows), **kwargs)

    def disponibles(self) -> list[str]:
        """Nombres configurados, para avisar cuando uno no se reconoce."""
        return sorted(self._workflows)

    def trigger(self, nombre: str) -> WorkflowResult:
        """Dispara el workflow que corresponda a ``nombre``. Bloquea hasta que responde."""
        ruta = self._workflows.get(normalize(nombre))
        if ruta is None:
            disponibles = ", ".join(self.disponibles()) or "(ninguno configurado)"
            raise BackendError(
                f"{nombre!r} no esta en la lista de flujos permitidos.\n"
                f"Disponibles: {disponibles}\n"
                "Anadelo a DOOMBOT_N8N_WORKFLOWS en .env."
            )
        if not self._base_url:
            raise BackendError("DOOMBOT_N8N_BASE_URL no esta configurado en .env.")

        url = f"{self._base_url}/{ruta.lstrip('/')}"
        try:
            r = self._client.post(url)
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise BackendError(
                f"No hay respuesta de n8n en {self._base_url}. "
                "Comprueba que este arrancado, o ajusta DOOMBOT_N8N_BASE_URL en .env."
            ) from e
        except httpx.HTTPStatusError as e:
            raise BackendError(
                f"n8n devolvio {e.response.status_code} para el flujo {nombre!r}. "
                "Comprueba que el webhook exista y este activo."
            ) from e
        except httpx.HTTPError as e:
            raise BackendError(f"Fallo hablando con n8n: {e}") from e

        return WorkflowResult(success=True, status_code=r.status_code, output=r.text[:500])

    def __repr__(self) -> str:
        return f"N8nClient(base_url={self._base_url!r}, workflows={sorted(self._workflows)})"
