"""Historial de conversaciones por carpetas (D-038), en carpetas temporales."""

from __future__ import annotations

import pytest

from doombot.backends.base import LlamadaHerramienta, PasoModelo, ResultadoHerramienta
from doombot.ventana.historial import Historial, deserializar, serializar, titulo_de


def test_el_estado_del_agente_va_y_vuelve_igual():
    conversacion = [
        "abre la calculadora",
        PasoModelo(
            "La abro.",
            (
                LlamadaHerramienta(
                    "c1", "abrir_aplicacion", {"nombre": "calc"}, {"extra_content": {"g": 1}}
                ),
            ),
        ),
        ResultadoHerramienta("c1", "abrir_aplicacion", "Abierta."),
        PasoModelo("Hecho."),
    ]
    vuelta = deserializar(serializar(conversacion))
    assert vuelta == conversacion
    assert vuelta[1].llamadas[0].extra == {
        "extra_content": {"g": 1}
    }  # la firma de Gemini sobrevive


def test_titulo_de_la_primera_orden():
    assert titulo_de("  abre   firefox ") == "abre firefox"
    assert len(titulo_de("x" * 200)) == 48


def test_guardar_listar_renombrar_mover_y_borrar(tmp_path):
    h = Historial(tmp_path)
    a = h.nueva("primera conversacion", carpeta="Trabajo", modo="programacion")
    b = h.nueva("segunda")
    h.guardar(a)
    h.guardar(b)

    lista = h.lista()
    assert {c["titulo"] for c in lista} == {"primera conversacion", "segunda"}
    assert h.carpetas() == ["Trabajo"]

    assert h.renombrar(a["id"], "Refactor del parser")
    assert h.mover(b["id"], "Estudios")
    assert h.leer(a["id"])["titulo"] == "Refactor del parser"
    assert h.carpetas() == ["Estudios", "Trabajo"]

    assert h.borrar(a["id"])
    assert h.leer(a["id"]) is None
    assert [c["id"] for c in h.lista()] == [b["id"]]


def test_las_carpetas_vacias_existen_y_borrar_una_no_borra_su_contenido(tmp_path):
    h = Historial(tmp_path)
    h.crear_carpeta("Ideas")
    assert h.carpetas() == ["Ideas"]

    c = h.nueva("algo", carpeta="Ideas")
    h.guardar(c)
    h.renombrar_carpeta("Ideas", "Proyectos")
    assert h.leer(c["id"])["carpeta"] == "Proyectos"

    h.borrar_carpeta("Proyectos")
    assert h.carpetas() == []
    assert h.leer(c["id"])["carpeta"] == ""  # la conversacion sigue, sin carpeta


@pytest.mark.parametrize("malo", ["../../etc/passwd", "carpetas", "20261013-113520-zzzzzz", ""])
def test_un_identificador_raro_no_sale_de_la_carpeta(tmp_path, malo):
    h = Historial(tmp_path)
    with pytest.raises(ValueError):
        h.borrar(malo)
    assert h.leer(malo) is None
