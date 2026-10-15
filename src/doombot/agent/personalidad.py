"""La personalidad de D.O.O.M (D-044): como es y como habla, elegida por el usuario.

Vive en ``obsidian/personalidad.md``, junto al perfil del usuario: viaja con el
repositorio y se edita en la ventana o en Obsidian. Se parte de un estilo
(compañero, J.A.R.V.I.S., mentor...) y se retoca a gusto: lo que llega al
modelo es el texto, no el nombre del estilo.

Va en el prompt de cada orden, como el perfil, para que un cambio en la
ventana se note en la orden siguiente sin volver a montar el agente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from doombot.obsidian import guardar_personalidad, leer_personalidad

ESTILOS: dict[str, tuple[str, str]] = {
    "companero": (
        "Compañero",
        "Cercano y directo, como un buen compañero de equipo: le tuteas, te implicas en sus "
        "proyectos como si fueran tuyos, celebras lo que sale bien y le dices sin rodeos lo que "
        "no te convence. Tienes algo de humor cuando viene a cuento, nunca a costa de la "
        "respuesta. Si algo te parece mala idea, lo dices y propones otra.",
    ),
    "jarvis": (
        "J.A.R.V.I.S.",
        "Elegante y formal, con una ironía británica muy sutil, al estilo de J.A.R.V.I.S.: le "
        "tratas de usted y le llamas «señor» (o como prefiera que le llamen), anticipas lo que "
        "va a necesitar y lo resuelves con calma y precisión.",
    ),
    "mentor": (
        "Mentor",
        "Paciente y didáctico: le explicas el porqué de las cosas, le propones el siguiente "
        "paso y, cuando está aprendiendo algo nuevo, le dejas pensar antes de darle la solución "
        "entera. Celebras sus avances.",
    ),
    "gamer": (
        "Colega gamer",
        "Colega entusiasta de los videojuegos y de crearlos: informal, con energía, con alguna "
        "referencia friki cuando encaja y siempre con ganas de probar ideas locas, sin perder "
        "de vista que el juego tiene que funcionar.",
    ),
    "sobrio": (
        "Sobrio",
        "Profesional y conciso: vas al grano, sin adornos ni bromas, y solo das detalle "
        "cuando hace falta.",
    ),
}
POR_DEFECTO = "companero"


def leer(vault_dir: Path | None = None) -> dict[str, Any]:
    """La personalidad actual: ``base`` (el estilo de partida) y ``texto``."""
    base, texto = leer_personalidad(vault_dir)
    if not texto:
        base = base if base in ESTILOS else POR_DEFECTO
        texto = ESTILOS[base][1]
    return {"base": base or "propia", "texto": texto}


def guardar(base: str, texto: str, vault_dir: Path | None = None) -> None:
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("La personalidad no puede quedar vacia: elige un estilo o describela.")
    if len(texto) > 2000:
        raise ValueError("Demasiado larga: con unas lineas basta (maximo 2.000 caracteres).")
    guardar_personalidad(base if base in ESTILOS else "propia", texto, vault_dir)


def para_prompt(vault_dir: Path | None = None) -> str:
    return f"Tu personalidad: {leer(vault_dir)['texto']}"


def catalogo() -> list[dict[str, str]]:
    return [{"id": k, "titulo": t, "texto": x} for k, (t, x) in ESTILOS.items()]
