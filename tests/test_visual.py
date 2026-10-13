"""Visuales (D-037): el filtro de SVG, la validacion de graficas y la herramienta."""

from __future__ import annotations

import pytest

from doombot.agent.montaje import montar
from doombot.agent.visual import Visual, limpiar_grafica, limpiar_svg
from doombot.backends.base import PasoModelo

CABALLO = """```svg
<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" fill="none" stroke="currentColor">
  <defs><marker id="m" markerWidth="4" markerHeight="4"><path d="M0 0 L4 2 L0 4z"/></marker></defs>
  <path d="M110 150 C120 120 220 115 270 130" stroke-width="3" marker-end="url(#m)"/>
  <circle cx="322" cy="72" r="2.5" fill="currentColor"/>
  <text x="10" y="20">Caballo <tspan font-weight="bold">simple</tspan> fin</text>
</svg>
```"""


# -- el filtro de SVG -------------------------------------------------------------
def test_un_dibujo_normal_pasa_entero():
    limpio = limpiar_svg(CABALLO)
    assert 'viewBox="0 0 400 300"' in limpio  # deducido de width/height
    assert "width=" not in limpio.split(">")[0]  # el tamaño lo pone la ventana
    assert 'marker-end="url(#m)"' in limpio and "markerWidth" in limpio
    assert "<circle" in limpio and "Caballo" in limpio and "simple" in limpio and "fin" in limpio


@pytest.mark.parametrize(
    "malo",
    [
        '<svg><script>alert(1)</script><rect width="1" height="1"/></svg>',
        '<svg onload="pywebview.api.parar()"><rect/></svg>',
        '<svg><a href="javascript:alert(1)"><rect/></a></svg>',
        '<svg xmlns:x="http://www.w3.org/1999/xlink"><image x:href="http://x/y.png"/></svg>',
        '<svg><foreignObject><div xmlns="http://www.w3.org/1999/xhtml">hola</div></foreignObject></svg>',
        '<svg><rect fill="url(http://malo/x)" style="background:url(http://x)"/></svg>',
        '<svg><style>@import url(http://x);</style><rect onclick="x()"/></svg>',
    ],
)
def test_nada_que_ejecute_o_cargue_algo_sobrevive(malo):
    limpio = limpiar_svg(malo).lower()
    for prohibido in ("script", "onload", "onclick", "href", "javascript", "foreignobject",
                      "image", "http://malo", "style", "@import"):  # fmt: skip
        assert prohibido not in limpio


@pytest.mark.parametrize(
    "malo",
    [
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg>&a;</svg>',  # billion laughs
        '<!DOCTYPE svg SYSTEM "file:///etc/passwd"><svg/>',  # XXE
        "<html><body/></html>",
        "no es xml",
        "",
    ],
)
def test_lo_que_no_es_un_svg_limpio_se_rechaza(malo):
    with pytest.raises(ValueError):
        limpiar_svg(malo)


# -- graficas -----------------------------------------------------------------------
def test_una_grafica_de_vectores():
    g = limpiar_grafica(
        {
            "x": [-1, 5],
            "y": [-1, 4],
            "vectores": [{"a": [3, 2], "nombre": "u"}, {"de": [3, 2], "a": [4, 4], "nombre": "v"}],
            "funciones": [{"f": "x**2 - 1", "nombre": "f"}],
            "inventado": 1,
        }
    )
    assert g["vectores"][0] == {"de": [0.0, 0.0], "a": [3.0, 2.0], "nombre": "u"}
    assert g["funciones"] == [{"f": "x^2 - 1", "nombre": "f"}]
    assert "inventado" not in g


def test_acepta_la_grafica_como_texto_json():
    assert limpiar_grafica('{"puntos": [{"en": [1, 2]}]}')["puntos"][0]["en"] == [1.0, 2.0]


def test_lo_malo_de_una_grafica_se_descarta():
    g = limpiar_grafica(
        {
            "x": [5, 1],  # al reves: se queda el de defecto
            "vectores": [{"a": [1, 1]}, {"a": "nada"}, {"a": [1e9, 0]}],
            "funciones": [{"f": "__import__('os')"}, {"f": "alert(1)"}, {"f": "sin(x)"}],
        }
    )
    assert g["x"] == [-10.0, 10.0]
    assert len(g["vectores"]) == 1
    assert g["funciones"] == [{"f": "sin(x)", "nombre": ""}]


def test_una_grafica_vacia_es_un_error():
    with pytest.raises(ValueError, match="nada que dibujar"):
        limpiar_grafica({"x": [0, 1]})


# -- la herramienta -------------------------------------------------------------------
def test_la_herramienta_pinta_lo_limpio_y_se_lo_dice_al_modelo():
    pintado = []
    v = Visual(pintado.append)
    respuesta = v.mostrar("Vectores", grafica={"vectores": [{"a": [1, 2]}]})
    assert "Mostrado" in respuesta
    assert pintado[0]["titulo"] == "Vectores" and pintado[0]["grafica"]["vectores"]

    v.mostrar("Caballo", svg='<svg viewBox="0 0 10 10"><script>x</script><rect/></svg>')
    assert "script" not in pintado[1]["svg"]
    assert v.mostrar("Nada").startswith("Error")


def test_solo_hay_herramienta_visual_si_hay_pantalla():
    class Cerebro:
        model_name = "c"

        def paso(self, *a, **k):
            return PasoModelo("fin")

    sin = montar(narrar=lambda *a: None, confirmar=lambda p: False, cerebro_=Cerebro())
    con = montar(
        narrar=lambda *a: None, confirmar=lambda p: False, cerebro_=Cerebro(), pantalla=print
    )
    assert "mostrar_visual" not in sin.agente.herramientas
    assert "mostrar_visual" in con.agente.herramientas
    assert con.agente.herramientas["mostrar_visual"].familia == "visual"
