"""La orden que enruta manualmente una pregunta a Claude (D-032).

No prueba la conversacion con la API -eso ya lo cubre test_anthropic.py-, solo
que la orden presta ``sesion.gen`` durante un turno y lo devuelve tal cual
estaba despues, pase lo que pase.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from doombot.backends.anthropic import AnthropicGenerator
from doombot.backends.orders import preguntar_claude
from doombot.orders import Sesion
from doombot.phrases.matcher import Match


@dataclass
class CfgFalso:
    anthropic_api_key: str = "clave-de-prueba"
    anthropic_model: str = "claude-sonnet-5"


@dataclass
class GenFalso:
    """El backend "por defecto" antes y despues del turno prestado a Claude."""

    nombre: str = "ollama-falso"


def _sesion(*, gen_original=None):
    gen_original = gen_original if gen_original is not None else GenFalso()
    llamadas: list[tuple[object, str]] = []
    avisos: list[str] = []
    s = Sesion(
        gen=gen_original,
        mem=None,
        cfg=CfgFalso(),
        perfil=None,
        agente=None,
        responder=lambda p: llamadas.append((s.gen, p)),
        con_contexto=lambda pregunta, *extra: f"con-contexto:{pregunta}",
        preguntar=lambda _: "",
    )
    s.aviso = avisos.append  # type: ignore[method-assign]
    s.llamadas = llamadas  # type: ignore[attr-defined]
    s.avisos = avisos  # type: ignore[attr-defined]
    return s


def _match(argumento: str) -> Match:
    return Match("ask_claude", "pregunta a claude", 1.0, "exact", argument=argumento)


def test_presta_un_anthropicgenerator_solo_durante_el_turno():
    s = _sesion()
    preguntar_claude(s, _match("¿que hora es en Tokio?"))

    assert len(s.llamadas) == 1
    gen_usado, prompt = s.llamadas[0]
    assert isinstance(gen_usado, AnthropicGenerator)
    assert prompt == "con-contexto:¿que hora es en Tokio?"


def test_el_backend_original_vuelve_despues():
    original = GenFalso()
    s = _sesion(gen_original=original)
    preguntar_claude(s, _match("hola"))
    assert s.gen is original


def test_el_backend_original_vuelve_incluso_si_responder_falla():
    """Un fallo dentro de responder() no debe dejar Claude puesto para el resto."""
    original = GenFalso()
    s = _sesion(gen_original=original)
    s.responder = lambda p: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        preguntar_claude(s, _match("hola"))
    assert s.gen is original


def test_sin_argumento_no_toca_el_backend_ni_pregunta_nada():
    original = GenFalso()
    s = _sesion(gen_original=original)
    preguntar_claude(s, _match(""))

    assert s.gen is original
    assert s.llamadas == []
    assert s.avisos and "que le pregunto" in s.avisos[0]
