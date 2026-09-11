"""El registro de órdenes.

Estos tests protegen lo que hace posible trabajar en varias capas a la vez: que
cada una declare sus órdenes sin editar un fichero común, y que el registro
avise cuando dos se pisan en vez de que gane la última importada.
"""

from __future__ import annotations

import pytest

from doombot.orders import despachar, orden, registradas
from doombot.orders.registry import _REGISTRO, Sesion
from doombot.phrases.matcher import BASICAS, Match


@pytest.fixture
def sesion():
    """Una Sesion con las dependencias falsas: no hace falta ni Ollama ni memoria."""
    dichas: list[str] = []
    s = Sesion(
        gen=None,
        mem=None,
        cfg=None,
        perfil=None,
        agente=None,
        responder=lambda p: dichas.append(p),
        con_contexto=lambda pregunta, *extra: pregunta,
        preguntar=lambda _: "",
    )
    s.dichas = dichas  # type: ignore[attr-defined]
    return s


def test_toda_orden_registrada_se_puede_pronunciar():
    """Registrar un manejador para una orden que no existe es codigo muerto.

    Y silencioso: nadie lo llamaria nunca, porque el matcher no puede producir
    ese nombre. Con capas trabajando en paralelo es un error facil -se decide
    un nombre en una rama y otro en la otra-, asi que se comprueba.
    """
    pronunciables = {c.name for c in BASICAS}
    huerfanas = sorted(set(registradas()) - pronunciables)
    assert not huerfanas, f"Manejadores sin orden que los dispare: {huerfanas}"


def test_dos_capas_no_pueden_reclamar_la_misma_orden():
    """Que gane la ultima importada seria un fallo invisible y no determinista.

    El orden de importacion depende del recorrido de pkgutil, asi que el
    sintoma cambiaria de un equipo a otro. Mejor romper al arrancar.
    """

    @orden("_prueba_duplicada")
    def primero(s, m):
        pass

    try:
        with pytest.raises(ValueError, match="ya la maneja"):

            @orden("_prueba_duplicada")
            def segundo(s, m):
                pass

    finally:
        _REGISTRO.pop("_prueba_duplicada", None)


def test_una_orden_sin_manejador_no_es_un_error(sesion):
    """Una orden definida pero que nadie implementa todavia.

    despachar devuelve False y quien llama decide que decir. Devolver False no
    puede confundirse con un fallo: es el estado normal de una orden que espera
    a que exista su capa. (Antes el ejemplo era `stop`; desde D-023 ya tiene
    manejador, y este test lo detecto: por eso ahora se usa un nombre ficticio.)
    """
    assert despachar(sesion, Match("_sin_manejador", "x", 1.0, "exact")) is False


def test_el_despacho_llega_al_manejador_de_su_capa(sesion, monkeypatch):
    """Recorrido completo: un Match entra y sale ejecutado el manejador."""
    llamado = []

    monkeypatch.setitem(_REGISTRO, "_prueba_ok", lambda s, m: llamado.append(m.argument))
    assert despachar(sesion, Match("_prueba_ok", "x", 1.0, "exact", argument="hola")) is True
    assert llamado == ["hola"]


def test_decir_guarda_la_ultima_respuesta(sesion, capsys):
    """La necesitan "repite" y la voz, que aun no existen pero ya la piden."""
    sesion.decir("dos grados")
    assert sesion.ultima_respuesta == "dos grados"
    assert "D.O.O.M> dos grados" in capsys.readouterr().out


def test_las_capas_declaran_sus_ordenes_donde_viven():
    """Cada manejador vive en su paquete, no en un fichero central.

    Es la propiedad que hace que dos sesiones trabajando en capas distintas no
    editen las mismas lineas. Si alguien vuelve a centralizarlos, este test lo
    dice.
    """
    donde = {n: h.__module__ for n, h in registradas().items()}
    assert donde["remember"].startswith("doombot.memory")
    assert donde["progress"].startswith("doombot.obsidian")
    assert donde["read_file"].startswith("doombot.files")
    assert donde["act"].startswith("doombot.actions")
