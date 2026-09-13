"""Empaqueta el HUD como ejecutable de escritorio (`dist/DOOM.exe`).

Implementacion de D-016 (el HUD es una aplicacion de escritorio), no una
decision nueva: PyInstaller es la via mas directa para convertir `app.py`
en un `.exe` de doble clic sin instalar Python en la maquina destino.

    py -3.12 -m pip install pyinstaller
    py -3.12 ui/build.py

El resultado es un solo fichero (`--onefile`): mas lento a abrir (unos
segundos, mientras se descomprime a una carpeta temporal) pero mas facil
de repartir que una carpeta con decenas de ficheros sueltos. Si el arranque
molesta, `--onedir` en vez de `--onefile` lo deja instantaneo a cambio de
una carpeta `dist/DOOM/` completa.

`hud.html` viaja embebido (`--add-data`): el ejecutable no depende de que
la carpeta `prototipo/` exista al lado. `app.py` resuelve la ruta correcta
en los dos casos (`sys._MEIPASS` empaquetado, `__file__` en desarrollo).

Lo que NO empaqueta, a proposito: `mock_servidor.py` (herramienta de
prueba, no del producto) y el propio Python/pip -- WebView2 ya viene con
Windows 11, asi que no hace falta embeber un motor de navegador.
"""

from __future__ import annotations

import os
import pathlib

import PyInstaller.__main__

AQUI = pathlib.Path(__file__).parent
HTML = AQUI / "prototipo" / "hud.html"


def main() -> None:
    if not HTML.exists():
        raise SystemExit(f"No encuentro {HTML}")

    PyInstaller.__main__.run(
        [
            str(AQUI / "app.py"),
            "--name=DOOM",
            "--onefile",
            "--windowed",
            "--noconfirm",
            f"--add-data={HTML}{os.pathsep}prototipo",
            f"--distpath={AQUI / 'dist'}",
            f"--workpath={AQUI / 'build'}",
            f"--specpath={AQUI}",
        ]
    )


if __name__ == "__main__":
    main()
