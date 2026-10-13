"""Preferencias de la ventana: solo valores validos llegan al CSS de la ventana."""

from __future__ import annotations

from doombot.ventana import preferencias
from doombot.ventana.preferencias import DEFECTO, guardar, leer, limpiar


def test_lo_valido_se_conserva():
    datos = {
        "tema": "holograma",
        "c1": "#FFAE2B",
        "c2": "#ffd88a",
        "luz": 1.3,
        "fondo": 0.2,
        "velocidad": 0.5,
        "por_herramienta": False,
        "circuitos": False,
        "crt": False,
    }
    assert limpiar(datos) == {**datos, "c1": "#ffae2b"}


def test_lo_raro_vuelve_al_defecto_sin_romper():
    datos = {
        "tema": "inventado",
        "c1": "red; background: url(http://x)",  # no puede colarse CSS
        "c2": "#12345",
        "luz": True,  # un bool no es un brillo
        "fondo": "0.5",
        "velocidad": 99,
        "crt": "si",
        "otra": 1,
    }
    limpio = limpiar(datos)
    assert limpio["tema"] == "jarvis"
    assert limpio["c1"] == DEFECTO["c1"] and limpio["c2"] == DEFECTO["c2"]
    assert limpio["luz"] == DEFECTO["luz"] and limpio["fondo"] == DEFECTO["fondo"]
    assert limpio["velocidad"] == 2.0  # recortado a su maximo
    assert limpio["crt"] is True
    assert "otra" not in limpio


def test_guardar_y_leer(tmp_path):
    ruta = tmp_path / "ventana.json"
    guardar({"tema": "neon", "c1": "#ff2bd6", "luz": 0.4}, ruta)
    assert leer(ruta)["tema"] == "neon"
    assert leer(ruta)["luz"] == 0.4


def test_sin_fichero_o_roto_da_el_defecto(tmp_path):
    assert leer(tmp_path / "no-existe.json") == DEFECTO
    roto = tmp_path / "roto.json"
    roto.write_text("{no es json", encoding="utf-8")
    assert leer(roto) == DEFECTO


def test_vive_fuera_del_repositorio():
    from doombot.paths import PROJECT_ROOT

    assert PROJECT_ROOT not in preferencias.fichero().parents
