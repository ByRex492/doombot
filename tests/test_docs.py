"""La documentacion tiene que seguir describiendo lo que hay.

Se desincroniza sola: se anade un modulo, se olvida documentarlo, y meses
despues la estructura escrita ya no se parece a la real. Le paso a identity.py,
que estuvo cuatro commits sin aparecer en ningun sitio pese a ser el modulo
que impide que D.O.O.M mienta sobre lo que sabe hacer.
"""

from __future__ import annotations

from doombot.paths import DOCS_DIR, PROJECT_ROOT

PAQUETE = PROJECT_ROOT / "src" / "doombot"

# Modulos que no hace falta anunciar: son mecanica de Python, no piezas del
# diseno que alguien tenga que entender para orientarse.
INTERNOS = {"__init__", "__main__"}


def _modulos() -> set[str]:
    """Modulos y subpaquetes de primer nivel del paquete."""
    nombres = {f.stem for f in PAQUETE.glob("*.py")} - INTERNOS
    nombres |= {d.name for d in PAQUETE.iterdir() if d.is_dir() and (d / "__init__.py").is_file()}
    return nombres


def test_el_paquete_anuncia_todos_sus_modulos():
    """El docstring de doombot/__init__.py es el indice del proyecto."""
    import doombot

    doc = doombot.__doc__ or ""
    faltan = sorted(m for m in _modulos() if m not in doc)
    assert not faltan, f"Sin mencionar en doombot/__init__.py: {faltan}"


def test_la_documentacion_describe_todos_los_modulos():
    doc = (DOCS_DIR / "estructura.md").read_text(encoding="utf-8")
    faltan = sorted(m for m in _modulos() if m not in doc)
    assert not faltan, f"Sin describir en docs/estructura.md: {faltan}"


def test_el_readme_existe_y_explica_como_empezar():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    for imprescindible in ("git clone", "python -m doombot", "pytest"):
        assert imprescindible in readme, f"El README no explica {imprescindible!r}"


def test_no_quedan_rutas_de_un_equipo_concreto_en_la_documentacion():
    """Salvo las del sobremesa, que se citan justamente como ejemplo ajeno."""
    for md in [*DOCS_DIR.glob("*.md"), PROJECT_ROOT / "README.md"]:
        texto = md.read_text(encoding="utf-8")
        assert "luism" not in texto, f"{md.name} lleva dentro el usuario del portatil"
