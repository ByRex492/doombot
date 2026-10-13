"""Todas las rutas del proyecto, derivadas en tiempo de ejecucion.

Ningun otro modulo construye rutas por su cuenta. La regla existe porque una
sola ruta absoluta escrita a mano ata el proyecto al equipo donde se escribio,
y el fallo no aparece hasta que alguien lo abre en otro sitio.

Hay dos raices y no conviene mezclarlas:

- ``PROJECT_ROOT`` es el repositorio. Se versiona, es identico en todas las
  maquinas y es de solo lectura en la practica.
- ``data_dir()`` es donde vive el estado local (memoria, registros, modelos
  descargados). Cambia de sitio en cada equipo, no se versiona, y de ahi que
  se resuelva por el sistema operativo en vez de fijarse aqui.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# paths.py esta en src/doombot/, asi que la raiz esta dos niveles arriba.
# Se calcula desde __file__ y no desde el directorio de trabajo: invocar el
# proyecto desde otra carpeta no debe cambiar donde cree que estan las cosas.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

PROFILES_FILE: Path = PROJECT_ROOT / "profiles.toml"
ENV_FILE: Path = PROJECT_ROOT / ".env"
ENV_EXAMPLE: Path = PROJECT_ROOT / ".env.example"
DOCS_DIR: Path = PROJECT_ROOT / "docs"
SKILLS_DIR: Path = PROJECT_ROOT / "skills"
"""Las skills de D.O.O.M que se versionan (D-038). Las personales, en ``data_dir()/skills``."""
UI_DIR: Path = PROJECT_ROOT / "ui"
"""Interfaces: el HUD (``ui/prototipo``) y la ventana de la aplicacion (``ui/ventana``)."""

VAULT_DIR: Path = PROJECT_ROOT / "obsidian"
"""El vault de Obsidian del proyecto: se versiona, igual que ``DOCS_DIR``.

A diferencia de ``data_dir()``, esto NO es estado privado -no lleva nada que
se haya dicho en voz alta, solo hechos que el usuario ha decidido escribir o
confirmar-, asi que vive dentro del repositorio a proposito: es lo que
permite que el sobremesa y el resto de equipos vean el mismo vault con
`git pull`, sin exportar ni copiar nada a mano.
"""

_APP_NAME = "doombot"


def data_dir() -> Path:
    """Carpeta de datos locales. Se crea si no existe.

    Orden de preferencia:

    1. ``DOOMBOT_DATA_DIR``, por si conviene ponerla en otro disco.
    2. La carpeta que marca el sistema operativo para datos de aplicacion.
    3. ``~/.local/share`` como ultimo recurso.

    Deliberadamente NO cae en ``PROJECT_ROOT / "data"``: la base de datos de
    la memoria acabaria dentro del repositorio, y bastaria un ``git add -A``
    distraido para subir a GitHub todo lo que el asistente haya escuchado.
    """
    override = os.environ.get("DOOMBOT_DATA_DIR", "").strip()
    if override:
        return _ensure(Path(override).expanduser())

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME")
        root = Path(base) if base else Path.home() / ".local" / "share"

    return _ensure(root / _APP_NAME)


def memory_db() -> Path:
    """Fichero SQLite con la memoria de D.O.O.M."""
    return data_dir() / "memory.db"


def log_dir() -> Path:
    return _ensure(data_dir() / "logs")


def models_dir() -> Path:
    """Modelos descargados (voz, embeddings). Pesan cientos de MB."""
    return _ensure(data_dir() / "models")


def inbox_dir() -> Path:
    """El buzon: ficheros que se le dejan a D.O.O.M para que los lea.

    Vive bajo ``data_dir()`` y no en el repositorio, por la misma razon que la
    memoria: aqui acaban documentos del usuario -facturas, contratos, apuntes-
    y un ``git add -A`` distraido los subiria a GitHub.

    Es la respuesta al problema de darle un fichero sin usar las manos para
    describirlo: se suelta aqui una vez, y despues se le pide de palabra.
    """
    return _ensure(data_dir() / "entrada")


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p
