"""Como quiere el usuario que se vea la ventana: colores, luz, fondo, velocidad (D-036).

Se guarda en ``data_dir()/ventana.json``: es estado local de este equipo, no
algo del proyecto, asi que no va al repositorio (ver ``paths.data_dir``).

Todo lo que llega de la ventana pasa por ``limpiar()``: solo las claves
conocidas, colores en ``#rrggbb`` y numeros dentro de su rango. Un valor raro
se cambia por el de defecto en vez de romper el dibujo -o de colar algo en el
CSS de la ventana, que es donde acaban estos valores-.
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
}
TEMAS = ("jarvis", "holograma", "neon", "matriz", "glaciar", "carmesi", "propio")
_RANGOS = {"luz": (0.0, 1.6), "fondo": (0.0, 1.0), "velocidad": (0.2, 2.0)}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def fichero() -> Path:
    from doombot.paths import data_dir

    return data_dir() / "ventana.json"


def limpiar(datos: Any) -> dict[str, Any]:
    limpio = dict(DEFECTO)
    if not isinstance(datos, dict):
        return limpio
    if datos.get("tema") in TEMAS:
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
    for clave in ("por_herramienta", "circuitos", "crt"):
        if isinstance(datos.get(clave), bool):
            limpio[clave] = datos[clave]
    return limpio


def leer(ruta: Path | None = None) -> dict[str, Any]:
    ruta = ruta or fichero()
    try:
        return limpiar(json.loads(ruta.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFECTO)


def guardar(datos: Any, ruta: Path | None = None) -> dict[str, Any]:
    limpio = limpiar(datos)
    ruta = ruta or fichero()
    ruta.write_text(json.dumps(limpio, indent=2), encoding="utf-8")
    return limpio
