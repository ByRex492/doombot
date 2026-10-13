"""El acceso directo de Linux, sin tocar el escritorio de quien pasa los tests."""

from __future__ import annotations

from pathlib import Path

from doombot.ventana.lanzador import ICONO, con_doom, contenido_desktop


def test_el_desktop_apunta_al_python_del_venv_y_se_asocia_a_la_ventana():
    texto = contenido_desktop(
        Path("/p/.venv/bin/python"), Path("/p"), Path("/p/ui/ventana/doom.svg"), Path("/d/v.log")
    )
    assert "Exec=sh -c \"exec '/p/.venv/bin/python' -m doombot ventana >>'/d/v.log' 2>&1\"" in texto
    assert "Path=/p" in texto and "Icon=/p/ui/ventana/doom.svg" in texto
    assert "StartupWMClass=doombot" in texto and "Terminal=false" in texto


def test_se_añade_al_final_del_dock_una_sola_vez():
    actual = "['org.gnome.Nautilus.desktop', 'firefox.desktop']\n"
    assert (
        con_doom(actual) == "['org.gnome.Nautilus.desktop', 'firefox.desktop', 'doombot.desktop']"
    )
    assert con_doom("['doombot.desktop']") is None
    assert con_doom("@as []") == "['doombot.desktop']"
    assert con_doom("basura") == "['doombot.desktop']"


def test_el_icono_existe_y_es_un_svg():
    assert ICONO.is_file()
    assert ICONO.read_text(encoding="utf-8").lstrip().startswith("<svg")
