"""Lee y escribe en el vault de Obsidian del proyecto.

El vault vive en ``paths.VAULT_DIR``, dentro del repositorio, a proposito:
ver el docstring de esa constante. Nada aqui habla con la app de Obsidian en
si -no hace falta: un vault es solo una carpeta de ficheros Markdown-, asi
que estas funciones no tienen ninguna dependencia mas alla de la libreria
estandar y ``Memory``.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from doombot.paths import VAULT_DIR

if TYPE_CHECKING:
    from doombot.memory import Memory

_CABECERA_PERFIL = (
    "# Usuario\n\n"
    "<!-- Generado por D.O.O.M a partir de lo que le cuentas -orden 'recuerda\n"
    "     que yo...'-. Puedes editar esto a mano: con /obsidian (o al arrancar)\n"
    "     se aprende igual que si lo hubieras dicho por voz o texto. -->\n\n"
)


def perfil_path(vault_dir: Path | None = None) -> Path:
    """Donde vive el perfil legible del usuario."""
    return (vault_dir or VAULT_DIR) / "usuario.md"


def progreso_path(fecha: date, vault_dir: Path | None = None) -> Path:
    """Donde vive la nota de progreso de un dia concreto."""
    return (vault_dir or VAULT_DIR) / "progreso" / f"{fecha:%Y-%m-%d}.md"


# -- D.O.O.M -> vault -----------------------------------------------------------
def escribir_perfil(mem: Memory, vault_dir: Path | None = None) -> Path:
    """Vuelca a Markdown lo que D.O.O.M sabe del usuario (``kind='perfil'``).

    Sobrescribe el fichero entero: es un espejo de la memoria, no un diario
    que se acumula, asi que no tiene sentido conservar una linea que ya no
    esta en ``Memory`` -por ejemplo, tras un ``olvida eso``-.
    """
    hechos = mem.all(kind="perfil")
    ruta = perfil_path(vault_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cuerpo = "".join(f"- {h.text}\n" for h in hechos)
    ruta.write_text(_CABECERA_PERFIL + cuerpo, encoding="utf-8")
    return ruta


def anotar_progreso(
    texto: str,
    *,
    ahora: datetime | None = None,
    vault_dir: Path | None = None,
) -> Path:
    """Anade una linea a la nota de progreso de hoy, bajo Mañana o Tarde.

    Un fichero por dia y no uno solo que crece sin fin: asi cada sesion de
    trabajo -aqui, en el portatil, en el sobremesa- deja un rastro que se
    puede repasar sin desplazarse por meses de historial.
    """
    ahora = ahora or datetime.now()
    turno = _turno(ahora)
    ruta = progreso_path(ahora.date(), vault_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    linea = f"- {ahora:%H:%M} — {texto.strip()}\n"
    cabecera_turno = f"## {turno}\n"

    if not ruta.is_file():
        ruta.write_text(f"# {ahora:%Y-%m-%d}\n\n{cabecera_turno}\n{linea}", encoding="utf-8")
        return ruta

    lineas = ruta.read_text(encoding="utf-8").splitlines(keepends=True)
    if cabecera_turno in lineas:
        # Se inserta al final de ESE turno: justo antes de la siguiente
        # cabecera de turno, o al final del fichero si es la ultima.
        i = lineas.index(cabecera_turno) + 1
        while i < len(lineas) and not lineas[i].startswith("## "):
            i += 1
        lineas.insert(i, linea)
    else:
        if lineas and not lineas[-1].endswith("\n"):
            lineas[-1] += "\n"
        lineas += ["\n", cabecera_turno, "\n", linea]

    ruta.write_text("".join(lineas), encoding="utf-8")
    return ruta


def _turno(ahora: datetime) -> str:
    """Mañana antes de las 14:00, Tarde despues. Corte simple y suficiente."""
    return "Mañana" if ahora.hour < 14 else "Tarde"


# -- vault -> D.O.O.M -----------------------------------------------------------
def sincronizar_perfil(mem: Memory, vault_dir: Path | None = None) -> int:
    """Aprende lo que el usuario haya escrito a mano en ``usuario.md``.

    Cada linea que empieza por "- " se guarda como un hecho ``kind='perfil'``,
    igual que si se hubiera dicho "recuerda que yo ...". ``Memory.remember``
    ya evita duplicados, asi que sincronizar varias veces seguidas no repite
    nada.
    """
    ruta = perfil_path(vault_dir)
    if not ruta.is_file():
        return 0

    hechos = [
        linea.strip()[2:].strip()
        for linea in ruta.read_text(encoding="utf-8").splitlines()
        if linea.strip().startswith("- ")
    ]
    hechos = [h for h in hechos if h]
    if not hechos:
        return 0

    mem.remember_many(hechos, kind="perfil")
    return len(hechos)
