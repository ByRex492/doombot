"""Los manejadores de la capa de acciones: `act` y `flow`, con su confirmacion.

D-031: un modo del agente que ejecuta de verdad, o cualquier disparo de n8n,
pide confirmacion antes de tocar nada. Estos tests prueban justo eso -que la
confirmacion decide si la accion real llega a lanzarse-, no el protocolo con
Claude Code o con n8n, que ya tienen sus propios tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from doombot.actions.claude_code import AgentResult
from doombot.actions.n8n import WorkflowResult
from doombot.actions.orders import actuar, flujo
from doombot.backends.base import BackendError
from doombot.orders.registry import Sesion
from doombot.phrases.matcher import Match


@dataclass
class CfgFalso:
    agent_permission_mode: str = "plan"


@dataclass
class AgenteFalso:
    llamadas: list[str] = field(default_factory=list)
    fallo: BackendError | None = None

    def run(self, tarea: str) -> AgentResult:
        self.llamadas.append(tarea)
        if self.fallo is not None:
            raise self.fallo
        return AgentResult(success=True, output="listo")


@dataclass
class N8nFalso:
    llamadas: list[str] = field(default_factory=list)
    fallo: BackendError | None = None

    def trigger(self, nombre: str) -> WorkflowResult:
        self.llamadas.append(nombre)
        if self.fallo is not None:
            raise self.fallo
        return WorkflowResult(success=True, status_code=200, output="ok")


def _sesion(*, permission_mode="plan", preguntar, agente=None, n8n=...):
    """``n8n=...`` (no ``None``) es aposta: n8n ausente es un caso a probar aparte."""
    avisos: list[str] = []
    s = Sesion(
        gen=None,
        mem=None,
        cfg=CfgFalso(agent_permission_mode=permission_mode),
        perfil=None,
        agente=agente if agente is not None else AgenteFalso(),
        n8n=N8nFalso() if n8n is ... else n8n,
        responder=lambda p: None,
        con_contexto=lambda p, *e: p,
        preguntar=preguntar,
    )
    s.aviso = avisos.append  # type: ignore[method-assign]
    s.avisos = avisos  # type: ignore[attr-defined]
    return s


def _no_deberia_preguntar(pregunta: str) -> str:
    raise AssertionError(f"no deberia haber pedido confirmacion: {pregunta!r}")


# -- act: la confirmacion depende del modo -------------------------------------
def test_modo_plan_no_pide_confirmacion():
    """plan ya es la salvaguarda (D-014): no hace falta preguntar encima."""
    agente = AgenteFalso()
    s = _sesion(permission_mode="plan", preguntar=_no_deberia_preguntar, agente=agente)
    actuar(s, Match("act", "ejecuta esto", 1.0, "exact", argument="arregla el bug"))
    assert agente.llamadas == ["arregla el bug"]
    assert "hecho" in s.ultima_respuesta


def test_modo_que_ejecuta_pide_confirmacion_y_no_actua_si_se_niega():
    agente = AgenteFalso()
    s = _sesion(permission_mode="acceptEdits", preguntar=lambda _: "no", agente=agente)
    actuar(s, Match("act", "ejecuta esto", 1.0, "exact", argument="borra logs"))
    assert agente.llamadas == []
    assert s.avisos and "cancelado" in s.avisos[0]


def test_modo_que_ejecuta_actua_si_se_confirma():
    agente = AgenteFalso()
    s = _sesion(permission_mode="acceptEdits", preguntar=lambda _: "confirmo", agente=agente)
    actuar(s, Match("act", "ejecuta esto", 1.0, "exact", argument="borra logs"))
    assert agente.llamadas == ["borra logs"]


def test_act_sin_argumento_no_pide_confirmacion_ni_ejecuta():
    agente = AgenteFalso()
    s = _sesion(permission_mode="acceptEdits", preguntar=_no_deberia_preguntar, agente=agente)
    actuar(s, Match("act", "ejecuta esto", 1.0, "exact", argument=""))
    assert agente.llamadas == []
    assert s.avisos and "que tarea" in s.avisos[0]


def test_fallo_del_agente_se_convierte_en_aviso():
    agente = AgenteFalso(fallo=BackendError("Ollama no responde"))
    s = _sesion(permission_mode="plan", preguntar=_no_deberia_preguntar, agente=agente)
    actuar(s, Match("act", "ejecuta esto", 1.0, "exact", argument="x"))
    assert s.avisos == ["Ollama no responde"]


# -- flow: siempre pide confirmacion, no tiene modo plan -----------------------
def test_flow_pide_confirmacion_aunque_el_modo_del_agente_sea_plan():
    """flow no depende de agent_permission_mode: es un riesgo distinto (D-030)."""
    n8n = N8nFalso()
    s = _sesion(permission_mode="plan", preguntar=lambda _: "no", n8n=n8n)
    flujo(s, Match("flow", "activa el flujo", 1.0, "exact", argument="riego"))
    assert n8n.llamadas == []
    assert s.avisos and "cancelado" in s.avisos[0]


def test_flow_dispara_si_se_confirma():
    n8n = N8nFalso()
    s = _sesion(preguntar=lambda _: "si", n8n=n8n)
    flujo(s, Match("flow", "activa el flujo", 1.0, "exact", argument="riego"))
    assert n8n.llamadas == ["riego"]
    assert "hecho" in s.ultima_respuesta


def test_flow_sin_n8n_configurado_avisa_sin_preguntar():
    s = _sesion(preguntar=_no_deberia_preguntar, n8n=None)
    flujo(s, Match("flow", "activa el flujo", 1.0, "exact", argument="riego"))
    assert s.avisos and "no esta configurado" in s.avisos[0]


def test_flow_sin_argumento_no_pide_confirmacion_ni_dispara():
    n8n = N8nFalso()
    s = _sesion(preguntar=_no_deberia_preguntar, n8n=n8n)
    flujo(s, Match("flow", "activa el flujo", 1.0, "exact", argument=""))
    assert n8n.llamadas == []
    assert s.avisos and "que flujo" in s.avisos[0]


def test_fallo_de_n8n_se_convierte_en_aviso():
    n8n = N8nFalso(fallo=BackendError("no esta en la lista de flujos permitidos"))
    s = _sesion(preguntar=lambda _: "si", n8n=n8n)
    flujo(s, Match("flow", "activa el flujo", 1.0, "exact", argument="riego"))
    assert s.avisos == ["no esta en la lista de flujos permitidos"]
