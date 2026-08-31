"""El system prompt tiene que decir la verdad sobre lo que hay instalado.

No es una cuestion de trato. Con un prompt fijo, llama3.2:3b contestaba "Abri
el navegador" a una orden que no puede ejecutar, y "Te recordare comprar pan"
sin existir memoria alguna. Eso impide desarrollar: si el asistente promete
recordar tanto con memoria como sin ella, al construir la memoria no hay forma
de saber si funciona.
"""

from __future__ import annotations

from doombot import identity


def test_siempre_sabe_conversar():
    caps = {c.name: c for c in identity.capabilities()}
    assert caps["conversar"].available


def test_actuar_se_activa_en_cuanto_actions_expone_algo():
    """Igual que memory/: en cuanto el paquete expone algo, se declara solo."""
    from doombot import actions

    publico = [x for x in dir(actions) if not x.startswith("_")]
    caps = {c.name: c for c in identity.capabilities()}
    assert caps["actuar"].available == bool(publico)


def test_no_dice_recordar_sin_memoria():
    """En cuanto memory/ exponga algo, esta capacidad se activa sola."""
    from doombot import memory

    publico = [x for x in dir(memory) if not x.startswith("_")]
    caps = {c.name: c for c in identity.capabilities()}
    assert caps["recordar"].available == bool(publico)


def test_el_prompt_declara_lo_que_no_puede():
    p = identity.system_prompt()
    assert "Limitaciones" in p
    # "consultar" (acceso a internet) sigue sin implementar; a diferencia de
    # "actuar", no se activa sola con ningun paquete existente.
    assert "acceso a internet" in p


def test_el_prompt_prohibe_fingir():
    """La instruccion que corrige el fallo observado en la auditoria."""
    p = identity.system_prompt().lower()
    assert "nunca afirmes haber hecho algo" in p


def test_el_prompt_lleva_el_nombre_y_el_idioma():
    p = identity.system_prompt()
    assert identity.NOMBRE in p
    assert "espanol" in p.lower() or "español" in p.lower()


def test_el_prompt_se_adapta_a_lo_instalado(monkeypatch):
    """Al implementar una capa, el prompt deja de negarla sin tocarlo."""
    real = identity.capabilities

    def con_memoria():
        return [
            identity.Capability("recordar", True, "guardar cosas", "no guardas nada")
            if c.name == "recordar"
            else c
            for c in real()
        ]

    monkeypatch.setattr(identity, "capabilities", con_memoria)
    p = identity.system_prompt()
    assert "guardar cosas" in p
    assert "no guardas nada" not in p


def test_el_entrypoint_usa_el_prompt_construido():
    from doombot.__main__ import SYSTEM

    assert identity.system_prompt() == SYSTEM


def test_resumen_nombra_todas_las_capacidades():
    r = identity.resumen()
    for c in identity.capabilities():
        assert c.name in r


def test_el_prompt_prohibe_inventar_datos():
    """ "No puedo hacer eso" y "no se eso" son distintas: hacen falta las dos.

    Con solo la primera, ante "donde esta alojado el codigo?" el modelo
    respondia inventando carpetas concretas del disco.
    """
    p = identity.system_prompt().lower()
    assert "si no sabes algo, dilo" in p
    assert "no inventes datos concretos" in p
