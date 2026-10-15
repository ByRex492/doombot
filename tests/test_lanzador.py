"""El acceso directo de Linux, sin tocar el escritorio de quien pasa los tests."""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

from doombot.ventana import _icono
from doombot.ventana.lanzador import ICONO, con_doom, contenido_desktop


def test_el_desktop_apunta_al_python_del_venv_y_se_asocia_a_la_ventana():
    # PurePosixPath y no Path: el .desktop es de Linux, y en Windows Path pinta
    # las rutas con "\" aunque el test corra alli.
    p = PurePosixPath
    texto = contenido_desktop(
        p("/p/.venv/bin/python"), p("/p"), p("/p/ui/ventana/doom.svg"), p("/d/v.log")
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


def test_en_windows_la_ventana_lleva_un_ico_de_verdad(monkeypatch):
    # Con el .svg, WinForms revienta antes de abrir la ventana (System.Drawing.Icon).
    monkeypatch.setattr(sys, "platform", "win32")
    icono = Path(_icono())
    assert icono.suffix == ".ico"
    assert icono.read_bytes()[:4] == b"\x00\x00\x01\x00"


def test_fuera_de_windows_la_ventana_sigue_con_el_svg(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert _icono() == str(ICONO)
