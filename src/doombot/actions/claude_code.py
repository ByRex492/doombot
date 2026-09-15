"""Ejecuta tareas reales delegando en Claude Code, en modo no interactivo.

Es la capa de acciones (D-014): en vez de escribir un ejecutor de
herramientas propio, se reutiliza el agente que ya construye este proyecto,
invocado con ``claude -p`` -su modo "print", pensado para automatizacion- en
vez de una sesion interactiva.

Los flags que se usan (``-p``, ``--output-format``, ``--permission-mode``,
``--allowedTools``) y la forma del JSON de salida (``result``, ``is_error``,
``session_id``, ``duration_ms``, ``total_cost_usd``) estan verificados contra
el binario real, no supuestos: ``claude --help`` y una invocacion de prueba.

**El modo por defecto es ``plan``, y es una decision deliberada.** Una orden
de voz que dispare la ejecucion de codigo de verdad -editar ficheros, correr
comandos- es un riesgo real y dificil de deshacer si el reconocimiento de voz
se equivoca. ``plan`` hace que el agente proponga lo que haria sin tocar
nada; pasar a un modo que ejecuta (``acceptEdits``, ``bypassPermissions``) es
algo que quien instala D.O.O.M tiene que elegir explicitamente en su ``.env``,
no algo que este modulo decida por el.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doombot.backends.base import BackendError

if TYPE_CHECKING:
    from collections.abc import Callable

# Ejecutar codigo de verdad puede tardar: instalar dependencias, correr
# tests, generar varios ficheros. 300s es generoso a proposito; para la voz,
# una tarea asi ya se anuncia como "esto va a tardar", no como una respuesta
# inmediata.
_TIMEOUT_DEFECTO = 300.0

_MODOS_VALIDOS = ("acceptEdits", "auto", "bypassPermissions", "manual", "dontAsk", "plan")


@dataclass(frozen=True)
class AgentResult:
    """Lo que devuelve una tarea delegada en el agente."""

    success: bool
    output: str
    session_id: str = ""
    duration_ms: int = 0
    cost_usd: float = 0.0


class ClaudeCodeAgent:
    """Delega una tarea en un `claude -p` no interactivo y parsea su JSON."""

    def __init__(
        self,
        *,
        binary: str = "claude",
        cwd: Path | None = None,
        permission_mode: str = "plan",
        allowed_tools: list[str] | None = None,
        timeout: float = _TIMEOUT_DEFECTO,
        runner: Callable[..., Any] | None = None,
        resolver: Callable[[str], str | None] | None = None,
    ) -> None:
        if permission_mode not in _MODOS_VALIDOS:
            raise ValueError(
                f"permission_mode={permission_mode!r} no es valido. "
                f"Opciones: {', '.join(_MODOS_VALIDOS)}."
            )
        # CreateProcess (lo que usa subprocess.run sin shell=True en Windows) no
        # prueba las extensiones de PATHEXT como hace cmd.exe: "claude" no
        # resuelve a "claude.cmd" aunque este en el PATH y funcione desde una
        # consola interactiva. shutil.which() si conoce PATHEXT, asi que
        # resolvemos aqui, una vez, y pasamos el nombre ya completo a
        # subprocess.run. Si no encuentra nada -ruta absoluta ya dada, binario
        # ausente de verdad- se deja tal cual: run() lo intenta igual y traduce
        # el FileNotFoundError a un mensaje legible.
        self._resolver = resolver or shutil.which
        self._binary = self._resolver(binary) or binary
        self._cwd = cwd
        self._permission_mode = permission_mode
        self._allowed_tools = allowed_tools
        self._timeout = timeout
        # Igual criterio que en los backends HTTP: el runner se puede
        # inyectar, asi se prueba esta clase sin lanzar procesos de verdad.
        self._runner = runner or subprocess.run

    @classmethod
    def from_config(cls, config: Any = None, **kwargs: Any) -> ClaudeCodeAgent:
        from doombot.config import settings

        cfg = config or settings()
        return cls(
            binary=cfg.agent_binary or "claude",
            permission_mode=cfg.agent_permission_mode,
            allowed_tools=list(cfg.agent_allowed_tools) or None,
            **kwargs,
        )

    # -- lo que hace de verdad -------------------------------------------------
    def run(self, task: str) -> AgentResult:
        """Ejecuta ``task`` y espera a que termine. Bloquea."""
        cmd = [
            self._binary,
            "-p",
            task,
            "--output-format",
            "json",
            "--permission-mode",
            self._permission_mode,
        ]
        if self._allowed_tools:
            cmd += ["--allowedTools", ",".join(self._allowed_tools)]

        try:
            proceso = self._runner(
                cmd,
                cwd=self._cwd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as e:
            raise BackendError(
                f"No se encuentra el binario {self._binary!r} de Claude Code.\n"
                "Ajusta DOOMBOT_AGENT_BINARY en .env con la ruta completa."
            ) from e
        except subprocess.TimeoutExpired as e:
            raise BackendError(
                f"La tarea tardo mas de {self._timeout:.0f}s y se cancelo: {task!r}"
            ) from e

        return self._parsear(proceso, task)

    # -- interno ----------------------------------------------------------------
    def _parsear(self, proceso: Any, task: str) -> AgentResult:
        try:
            datos = json.loads(proceso.stdout)
        except json.JSONDecodeError as e:
            raise BackendError(
                f"Claude Code no devolvio JSON valido para la tarea {task!r}.\n"
                f"Salida: {proceso.stdout[:500]!r}\n"
                f"Error: {proceso.stderr[:500]!r}"
            ) from e

        return AgentResult(
            success=not datos.get("is_error", proceso.returncode != 0),
            output=str(datos.get("result", "")),
            session_id=str(datos.get("session_id", "")),
            duration_ms=int(datos.get("duration_ms", 0)),
            cost_usd=float(datos.get("total_cost_usd", 0.0)),
        )

    def __repr__(self) -> str:
        return f"ClaudeCodeAgent(permission_mode={self._permission_mode!r}, cwd={self._cwd!r})"
