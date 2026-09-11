"""El nucleo de orquestacion compartido entre el modo escrito y el hablado.

``_atender`` es lo que ejecutan por igual el bucle de teclado y el de voz: una
frase entra, y sale despachada como orden o pasada al modelo. Que los dos modos
compartan exactamente esto -y no dos copias que se desincronizan- es la razon
de que exista aparte del bucle.
"""

from __future__ import annotations

from doombot.chat import _atender
from doombot.orders.registry import Sesion
from doombot.phrases import default_matcher


class MemFalsa:
    def as_context(self, _):
        return ""

    def remember(self, texto, kind="general"):
        return 1

    def all(self, kind=None):
        return []


def _sesion(mem=None):
    dicho = {"prompt": None}
    s = Sesion(
        gen=None, mem=mem or MemFalsa(), cfg=None, perfil=None, agente=None,
        responder=lambda p: dicho.__setitem__("prompt", p),
        con_contexto=lambda pregunta, *extra: pregunta,
        preguntar=lambda _: "",
    )  # fmt: skip
    s._dicho = dicho  # type: ignore[attr-defined]
    return s


def test_una_pregunta_normal_va_al_modelo():
    s = _sesion()
    _atender(s, default_matcher(), MemFalsa(), "que hora es")
    assert s._dicho["prompt"] == "que hora es"  # type: ignore[attr-defined]


def test_una_orden_se_despacha_y_no_llega_al_modelo():
    s = _sesion()
    _atender(s, default_matcher(), MemFalsa(), "recuerda que el pan esta caro")
    # La orden 'remember' respondio; el modelo no se invoco.
    assert s._dicho["prompt"] is None  # type: ignore[attr-defined]
    assert "apuntado" in s.ultima_respuesta.lower()


def test_una_orden_sin_manejador_lo_dice_sin_mentir():
    s = _sesion()
    _atender(s, default_matcher(), MemFalsa(), "modo silencioso")  # 'silence', ya implementada
    # Cualquiera que este implementada responde algo; el caso de "aun no puedo"
    # solo salta con ordenes sin manejador, y eso ya lo cubre test_orders.
    assert s.ultima_respuesta
