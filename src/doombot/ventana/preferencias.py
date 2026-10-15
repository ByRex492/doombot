"""Como quiere el usuario que se vea la ventana: colores, luz, fondo, velocidad (D-036).

Se guarda en ``data_dir()/ventana.json``: es estado local de este equipo, no
algo del proyecto, asi que no va al repositorio (ver ``paths.data_dir``).

Todo lo que llega de la ventana pasa por ``limpiar()``: solo las claves
conocidas, colores en ``#rrggbb`` y numeros dentro de su rango. Un valor raro
se cambia por el de defecto en vez de romper el dibujo -o de colar algo en el
CSS de la ventana, que es donde acaban estos valores-.

Ademas de los temas fijos, el usuario guarda sus propios perfiles de color
(``perfiles``: id, nombre y los dos colores). El tema activo puede ser uno de
ellos; entonces sus colores son los que se pintan.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFECTO: dict[str, Any] = {
    "tema": "jarvis",
    "c1": "#29d3ff",
    "c2": "#8ff3ff",
    "luz": 1.0,
    "fondo": 0.6,
    "velocidad": 1.0,
    "por_herramienta": True,
    "circuitos": True,
    "crt": True,
    # La voz (D-046): leer en voz alta tambien lo escrito, y arrancar escuchando.
    "voz_siempre": False,
    "manos_libres": False,
    "perfiles": [],
}
TEMAS = ("jarvis", "holograma", "neon", "matriz", "glaciar", "carmesi", "propio")
_RANGOS = {"luz": (0.0, 1.6), "fondo": (0.0, 1.0), "velocidad": (0.2, 2.0)}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_PERFILES = 24
_ID_PERFIL = re.compile(r"^perfil-[a-z0-9]{1,16}$")
_LARGO_NOMBRE = 32


def _perfiles(datos: Any) -> list[dict[str, str]]:
    """Los perfiles de color, validados uno a uno.

    Uno con algo roto se descarta entero en vez de corregirse: un perfil a
    medias no es el que se guardo. El nombre solo se pinta como texto, pero
    igualmente se queda sin caracteres de control y con un largo razonable.
    """
    if not isinstance(datos, list):
        return []
    perfiles: list[dict[str, str]] = []
    vistos: set[str] = set()
    for p in datos:
        if not isinstance(p, dict):
            continue
        ident, nombre = p.get("id"), p.get("nombre")
        if not isinstance(ident, str) or not _ID_PERFIL.match(ident) or ident in vistos:
            continue
        if not isinstance(nombre, str):
            continue
        nombre = " ".join("".join(c if c.isprintable() else " " for c in nombre).split())
        if not nombre:
            continue
        colores = [p.get("c1"), p.get("c2")]
        if not all(isinstance(c, str) and _COLOR.match(c) for c in colores):
            continue
        vistos.add(ident)
        perfiles.append(
            {
                "id": ident,
                "nombre": nombre[:_LARGO_NOMBRE],
                "c1": colores[0].lower(),
                "c2": colores[1].lower(),
            }
        )
        if len(perfiles) == MAX_PERFILES:
            break
    return perfiles


def fichero() -> Path:
    from doombot.paths import data_dir

    return data_dir() / "ventana.json"


def limpiar(datos: Any) -> dict[str, Any]:
    # La lista nueva cada vez: dict(DEFECTO) compartiria la de DEFECTO.
    limpio = {**DEFECTO, "perfiles": []}
    if not isinstance(datos, dict):
        return limpio
    limpio["perfiles"] = _perfiles(datos.get("perfiles"))
    propios = {p["id"]: p for p in limpio["perfiles"]}
    if datos.get("tema") in TEMAS or datos.get("tema") in propios:
        limpio["tema"] = datos["tema"]
    for clave in ("c1", "c2"):
        valor = datos.get(clave)
        if isinstance(valor, str) and _COLOR.match(valor):
            limpio[clave] = valor.lower()
    for clave, (minimo, maximo) in _RANGOS.items():
        valor = datos.get(clave)
        # bool es int en Python: True no es un brillo valido.
        if isinstance(valor, int | float) and not isinstance(valor, bool):
            limpio[clave] = round(min(maximo, max(minimo, float(valor))), 3)
    for clave in ("por_herramienta", "circuitos", "crt", "voz_siempre", "manos_libres"):
        if isinstance(datos.get(clave), bool):
            limpio[clave] = datos[clave]
    # Con un perfil propio activo mandan sus colores: la ventana pinta c1 y c2,
    # y asi los dos no pueden separarse.
    if limpio["tema"] in propios:
        limpio["c1"] = propios[limpio["tema"]]["c1"]
        limpio["c2"] = propios[limpio["tema"]]["c2"]
    return limpio


def leer(ruta: Path | None = None) -> dict[str, Any]:
    ruta = ruta or fichero()
    try:
        return limpiar(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return limpiar(None)


def guardar(datos: Any, ruta: Path | None = None) -> dict[str, Any]:
    limpio = limpiar(datos)
    ruta = ruta or fichero()
    ruta.write_text(json.dumps(limpio, indent=2), encoding="utf-8")
    return limpio
