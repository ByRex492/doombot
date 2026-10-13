"""Acceso directo a la aplicacion: en el menu y en el dock, sin terminal (D-035).

    python -m doombot lanzador

Escribe un ``.desktop`` en la carpeta de aplicaciones del usuario (no del
sistema: no hace falta sudo y se borra con un fichero) y lo fija en el dock de
GNOME. El ``.desktop`` apunta al Python del ``.venv`` con el que se ejecuta
esta orden, asi que hay que lanzarla con ese mismo Python.

La ventana se llama ``doombot`` para el escritorio (``WM_CLASS``, ver
``ventana.abrir``) y el ``.desktop`` lo declara en ``StartupWMClass``: es lo
que hace que el dock reconozca la ventana como la de este icono en vez de
mostrar otro generico al lado.

Solo Linux por ahora. En Windows el equivalente es un acceso directo en el
menu Inicio; queda pendiente (ver la nota de sesion).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

from doombot.paths import PROJECT_ROOT, UI_DIR, data_dir

NOMBRE = "doombot.desktop"
ICONO = UI_DIR / "ventana" / "doom.svg"
CLASE_VENTANA = "doombot"


def contenido_desktop(python: Path, proyecto: Path, icono: Path, registro: Path) -> str:
    """El ``.desktop``. La salida va a un registro: lanzado desde el menu no hay terminal."""
    orden = f"exec '{python}' -m doombot ventana >>'{registro}' 2>&1"
    return "\n".join(
        [
            "[Desktop Entry]",
            "Type=Application",
            "Name=D.O.O.M",
            "GenericName=Asistente local",
            "Comment=Asistente con agente: aplicaciones, navegador, ficheros y graficas",
            f'Exec=sh -c "{orden}"',
            f"Path={proyecto}",
            f"Icon={icono}",
            "Terminal=false",
            "Categories=Utility;",
            "Keywords=doom;asistente;agente;jarvis;",
            f"StartupWMClass={CLASE_VENTANA}",
            "StartupNotify=true",
            "",
        ]
    )


def con_doom(favoritos: str) -> str | None:
    """La lista de favoritos de GNOME con D.O.O.M al final, o None si ya estaba."""
    try:
        lista = ast.literal_eval(favoritos.strip().removeprefix("@as "))
    except (ValueError, SyntaxError):
        lista = []
    if not isinstance(lista, list):
        lista = []
    if NOMBRE in lista:
        return None
    return str([*lista, NOMBRE])


def instalar(*, fijar_en_dock: bool = True) -> list[str]:
    """Instala el acceso y devuelve lo que ha hecho, linea a linea."""
    if not sys.platform.startswith("linux"):
        return ["El acceso directo automatico solo esta hecho para Linux por ahora."]
    hecho = []
    carpeta = (
        Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "applications"
    )
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / NOMBRE
    registro = data_dir() / "ventana.log"
    destino.write_text(
        contenido_desktop(Path(sys.executable), PROJECT_ROOT, ICONO, registro), encoding="utf-8"
    )
    hecho.append(f"Acceso creado: {destino}")
    hecho.append(f"Lo que escriba la aplicacion queda en {registro}")
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(carpeta)], capture_output=True, check=False)

    if fijar_en_dock and shutil.which("gsettings"):
        actual = subprocess.run(
            ["gsettings", "get", "org.gnome.shell", "favorite-apps"],
            capture_output=True,
            text=True,
            check=False,
        )
        nueva = con_doom(actual.stdout) if actual.returncode == 0 else None
        if actual.returncode != 0:
            hecho.append("No he podido leer el dock (¿no es GNOME?): fijalo a mano desde el menu.")
        elif nueva is None:
            hecho.append("Ya estaba fijado en el dock.")
        else:
            subprocess.run(
                ["gsettings", "set", "org.gnome.shell", "favorite-apps", nueva], check=False
            )
            hecho.append("Fijado en el dock, al final.")
    return hecho
