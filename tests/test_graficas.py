"""Graficas (D-037): matematicas en ejes y estadistica con los calculos hechos aqui."""

from __future__ import annotations

import pytest

from doombot.agent.graficas import Graficas, limpiar_estadistica, limpiar_grafica
from doombot.agent.montaje import montar
from doombot.backends.base import PasoModelo


# -- matematicas en ejes ------------------------------------------------------------------
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


def test_lo_malo_de_una_grafica_se_descarta():
    g = limpiar_grafica(
        {
            "x": [5, 1],
            "vectores": [{"a": [1, 1]}, {"a": "nada"}, {"a": [1e13, 0]}],
            "funciones": [{"f": "__import__('os')"}, {"f": "alert(1)"}, {"f": "sin(x)"}],
        }
    )
    assert g["x"] == [-10.0, 10.0]
    assert len(g["vectores"]) == 1
    assert g["funciones"] == [{"f": "sin(x)", "nombre": ""}]


def test_una_grafica_vacia_es_un_error():
    with pytest.raises(ValueError, match="nada que dibujar"):
        limpiar_grafica({"x": [0, 1]})


# -- estadistica --------------------------------------------------------------------------
def test_barras_con_su_resumen():
    e = limpiar_estadistica(
        {
            "tipo": "barras",
            "eje_y": "ventas",
            "categorias": ["ene", "feb", "mar"],
            "series": [{"nombre": "2024", "valores": [10, 30, 20]}],
        }
    )
    assert e["series"] == [{"nombre": "2024", "valores": [10.0, 30.0, 20.0]}]
    assert "total 60" in e["resumen"] and "media 20" in e["resumen"]
    assert "maximo 30 (feb)" in e["resumen"] and "minimo 10 (ene)" in e["resumen"]


def test_un_valor_por_categoria_o_se_explica_el_error():
    with pytest.raises(ValueError, match="tiene 2 valores y hay 3 categorias"):
        limpiar_estadistica(
            {
                "tipo": "lineas",
                "categorias": ["a", "b", "c"],
                "series": [{"nombre": "s", "valores": [1, 2]}],
            }
        )


def test_sectores_calcula_los_porcentajes():
    e = limpiar_estadistica(
        {"tipo": "sectores", "categorias": ["si", "no", "ns"], "valores": [50, 30, 20]}
    )
    assert e["porcentajes"] == [50.0, 30.0, 20.0]
    assert "si: 50 (50%)" in e["resumen"]
    with pytest.raises(ValueError, match="positivos"):
        limpiar_estadistica({"tipo": "sectores", "categorias": ["a"], "valores": [-1]})


def test_histograma_con_intervalos_y_estadisticos_exactos():
    e = limpiar_estadistica({"tipo": "histograma", "datos": list(range(1, 11)), "intervalos": 5})
    assert [i["n"] for i in e["intervalos"]] == [2, 2, 2, 2, 2]
    assert e["intervalos"][0]["desde"] == 1.0 and e["intervalos"][-1]["hasta"] == 10.0
    assert e["media"] == 5.5 and e["mediana"] == 5.5
    assert "desviacion tipica 3.02765" in e["resumen"]


def test_histograma_elige_los_intervalos_si_no_se_dicen():
    e = limpiar_estadistica({"tipo": "histograma", "datos": [1.5] * 50 + [2.5] * 50})
    assert 5 <= len(e["intervalos"]) <= 30
    assert sum(i["n"] for i in e["intervalos"]) == 100


def test_dispersion_con_regresion_exacta():
    puntos = [[x, 2 * x + 1] for x in range(10)]
    e = limpiar_estadistica(
        {
            "tipo": "dispersion",
            "series": [{"nombre": "medidas", "puntos": puntos}],
            "regresion": True,
        }
    )
    assert e["series"][0]["regresion"] == {"pendiente": 2.0, "ordenada": 1.0, "r": 1.0}
    assert "y = 2·x + 1" in e["resumen"]


@pytest.mark.parametrize(
    "malo",
    [
        {"tipo": "tarta"},
        {"tipo": "barras", "series": [{"valores": [1]}]},
        {"tipo": "histograma", "datos": [1]},
        {"tipo": "dispersion", "series": []},
        {"tipo": "barras", "categorias": ["a"], "series": [{"valores": [True]}]},
        "no es json",
    ],
)
def test_lo_que_no_vale_se_rechaza_con_motivo(malo):
    with pytest.raises(ValueError):
        limpiar_estadistica(malo)


# -- la herramienta -------------------------------------------------------------------------
def test_la_herramienta_pinta_y_devuelve_los_calculos_al_modelo():
    pintado = []
    g = Graficas(pintado.append)
    respuesta = g.mostrar(
        "Notas", estadistica={"tipo": "histograma", "datos": [5, 6, 7, 8, 9], "intervalos": 2}
    )
    assert "media 7" in respuesta and "usalos" in respuesta
    assert pintado[0]["titulo"] == "Notas"
    assert "resumen" not in pintado[0]["estadistica"]  # el texto es para el modelo, no para pintar

    g.mostrar("Vectores", grafica={"vectores": [{"a": [1, 2]}]})
    assert pintado[1]["grafica"]["vectores"]
    assert g.mostrar("Nada").startswith("Error")


def test_solo_hay_herramienta_de_graficas_si_hay_pantalla():
    class Cerebro:
        model_name = "c"

        def paso(self, *a, **k):
            return PasoModelo("fin")

    sin = montar(narrar=lambda *a: None, confirmar=lambda p: False, cerebro_=Cerebro())
    con = montar(
        narrar=lambda *a: None, confirmar=lambda p: False, cerebro_=Cerebro(), pantalla=print
    )
    assert "mostrar_grafica" not in sin.agente.herramientas
    assert con.agente.herramientas["mostrar_grafica"].familia == "visual"
    assert "mostrar_grafica" in con.agente.system
