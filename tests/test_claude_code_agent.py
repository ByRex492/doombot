"""El agente de acciones, probado sin lanzar procesos de verdad.

Mismo enfoque que test_ollama.py: un runner falso sustituye subprocess.run,
asi que estos tests corren en cualquier equipo sin necesitar el binario de
Claude Code instalado ni tocar el sistema de archivos real.

Los flags que se comprueban (-p, --output-format json, --permission-mode,
--allowedTools) y la forma del JSON (is_error, result, session_id,
duration_ms, total_cost_usd) estan verificados contra el binario real -ver
el modulo- y no inventados.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import pytest

from doombot.actions.claude_code import AgentResult, ClaudeCodeAgent
from doombot.backends.base import BackendError
from doombot.config import Settings


@dataclass
class ProcesoFalso:
    stdout: str
    stderr: str = ""
    returncode: int = 0


def runner_falso(handler):
    def runner(cmd, **kwargs):
        return handler(cmd, kwargs)

    return runner


# -- construccion -------------------------------------------------------------
def test_modo_de_permiso_invalido_falla_al_construir():
    with pytest.raises(ValueError, match="permission_mode"):
        ClaudeCodeAgent(permission_mode="lo-que-sea")


def test_modo_por_defecto_es_plan():
    """El valor seguro para algo disparado por voz: propone, no ejecuta."""
    agente = ClaudeCodeAgent()
    assert "plan" in repr(agente)


def test_from_config_traslada_los_ajustes():
    cfg = Settings(
        ollama_host="http://127.0.0.1:11434",
        log_level="INFO",
        agent_binary="/opt/claude/claude",
        agent_permission_mode="acceptEdits",
        agent_allowed_tools=("Read", "Edit"),
    )
    capturado = {}

    def handler(cmd, kwargs):
        capturado["cmd"] = cmd
        return ProcesoFalso(stdout=json.dumps({"result": "ok", "is_error": False}))

    agente = ClaudeCodeAgent.from_config(cfg, runner=runner_falso(handler))
    agente.run("haz algo")
    assert capturado["cmd"][0] == "/opt/claude/claude"
    assert "acceptEdits" in capturado["cmd"]
    assert "Read,Edit" in capturado["cmd"]


# -- construccion del comando --------------------------------------------------
def test_el_comando_lleva_los_flags_correctos():
    capturado = {}

    def handler(cmd, kwargs):
        capturado["cmd"] = cmd
        capturado["kwargs"] = kwargs
        return ProcesoFalso(stdout=json.dumps({"result": "ok", "is_error": False}))

    agente = ClaudeCodeAgent(runner=runner_falso(handler))
    agente.run("arregla el bug de X")

    cmd = capturado["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert "arregla el bug de X" in cmd
    assert "--output-format" in cmd and "json" in cmd
    assert "--permission-mode" in cmd and "plan" in cmd
    assert capturado["kwargs"]["capture_output"] is True
    assert capturado["kwargs"]["text"] is True


def test_sin_allowed_tools_no_manda_el_flag():
    capturado = {}

    def handler(cmd, kwargs):
        capturado["cmd"] = cmd
        return ProcesoFalso(stdout=json.dumps({"result": "ok", "is_error": False}))

    ClaudeCodeAgent(runner=runner_falso(handler)).run("x")
    assert "--allowedTools" not in capturado["cmd"]


# -- parseo del resultado -------------------------------------------------------
def test_resultado_exitoso_se_parsea():
    def handler(cmd, kwargs):
        return ProcesoFalso(
            stdout=json.dumps(
                {
                    "is_error": False,
                    "result": "listo",
                    "session_id": "abc-123",
                    "duration_ms": 842,
                    "total_cost_usd": 0.0231,
                }
            )
        )

    r = ClaudeCodeAgent(runner=runner_falso(handler)).run("haz algo")
    assert r == AgentResult(
        success=True,
        output="listo",
        session_id="abc-123",
        duration_ms=842,
        cost_usd=0.0231,
    )


def test_resultado_con_error_marca_success_false():
    def handler(cmd, kwargs):
        return ProcesoFalso(stdout=json.dumps({"is_error": True, "result": "Not logged in"}))

    r = ClaudeCodeAgent(runner=runner_falso(handler)).run("haz algo")
    assert r.success is False
    assert r.output == "Not logged in"


def test_json_invalido_da_un_error_legible():
    def handler(cmd, kwargs):
        return ProcesoFalso(stdout="esto no es json", stderr="algo fallo")

    with pytest.raises(BackendError, match="JSON"):
        ClaudeCodeAgent(runner=runner_falso(handler)).run("x")


# -- errores traducidos ----------------------------------------------------------
def test_binario_ausente_apunta_a_la_variable_de_entorno():
    def handler(cmd, kwargs):
        raise FileNotFoundError("no such file")

    with pytest.raises(BackendError, match="DOOMBOT_AGENT_BINARY"):
        ClaudeCodeAgent(runner=runner_falso(handler)).run("x")


def test_timeout_dice_que_tarea_se_cancelo():
    def handler(cmd, kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    with pytest.raises(BackendError, match="tardo mas"):
        ClaudeCodeAgent(runner=runner_falso(handler), timeout=1.0).run("tarea larga")


# -- contra el binario real -------------------------------------------------------
@pytest.mark.hardware
def test_contra_claude_code_real():
    """Se salta con: pytest -m 'not hardware'. Necesita `claude` autenticado."""
    r = ClaudeCodeAgent(permission_mode="plan").run("Responde solo con la palabra: listo")
    assert r.output
