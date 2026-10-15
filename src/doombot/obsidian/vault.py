"""Lee y escribe en el vault de Obsidian del proyecto.

El vault vive en ``paths.VAULT_DIR``, dentro del repositorio, a proposito:
ver el docstring de esa constante. Nada aqui habla con la app de Obsidian en
si -no hace falta: un vault es solo una carpeta de ficheros Markdown-, asi
que estas funciones no tienen ninguna dependencia mas alla de la libreria
estandar y ``Memory``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from doombot.paths import VAULT_DIR

if TYPE_CHECKING:
    from doombot.memory import Memory

_CABECERA_PERFIL = (
    "# Usuario\n\n"
    "<!-- Lo que D.O.O.M sabe de ti: lo lee en cada conversacion. Se edita en la\n"
    "     ventana (Perfil), con la orden 'recuerda que yo...' o aqui a mano.\n"
    "     Las propiedades de arriba son tus datos; cada linea con guion, un hecho.\n"
    "     Este fichero manda: lo que borres aqui, D.O.O.M lo olvida. -->\n\n"
)

# Los datos del perfil (D-043), en el orden en que se piden. Van como
# propiedades de Obsidian (el bloque ``---`` de arriba del fichero): se ven y
# se editan como tales en la app, y no se confunden con los hechos sueltos.
CAMPOS_PERFIL: tuple[str, ...] = (
    "nombre", "llamame", "dedicacion", "ubicacion", "idiomas", "intereses", "estilo",
)  # fmt: skip


@dataclass
class Perfil:
    """Quien es el usuario: sus datos, los hechos sueltos y lo que no es nuestro."""

    campos: dict[str, str] = field(default_factory=dict)
    hechos: list[str] = field(default_factory=list)
    otras: list[str] = field(default_factory=list)
    """Lineas de propiedades que no son de D.O.O.M (``tags``, por ejemplo): se conservan."""


def perfil_path(vault_dir: Path | None = None) -> Path:
    """Donde vive el perfil legible del usuario."""
    return (vault_dir or VAULT_DIR) / "usuario.md"


def progreso_path(fecha: date, vault_dir: Path | None = None) -> Path:
    """Donde vive la nota de progreso de un dia concreto."""
    return (vault_dir or VAULT_DIR) / "progreso" / f"{fecha:%Y-%m-%d}.md"


# -- el perfil (D-043) -----------------------------------------------------------
def leer_perfil(vault_dir: Path | None = None) -> Perfil:
    """El perfil tal como esta en ``usuario.md``. Vacio si no existe."""
    ruta = perfil_path(vault_dir)
    if not ruta.is_file():
        return Perfil()
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    perfil = Perfil()
    cuerpo = lineas
    if lineas and lineas[0].strip() == "---" and "---" in (x.strip() for x in lineas[1:]):
        fin = next(i for i, x in enumerate(lineas[1:], 1) if x.strip() == "---")
        for linea in lineas[1:fin]:
            clave, _, valor = linea.partition(":")
            if clave.strip() in CAMPOS_PERFIL and not linea.startswith((" ", "\t")):
                perfil.campos[clave.strip()] = _valor(valor.strip())
            elif linea.strip():
                perfil.otras.append(linea)
        cuerpo = lineas[fin + 1 :]
    perfil.hechos = [
        h for x in cuerpo if x.strip().startswith("- ") and (h := x.strip()[2:].strip())
    ]
    return perfil


def _valor(crudo: str) -> str:
    """El valor de una propiedad: entre comillas (como se escribe aqui) o a pelo (Obsidian)."""
    if crudo.startswith('"'):
        try:
            return str(json.loads(crudo))
        except ValueError:
            pass
    return crudo.strip("'\"")


def guardar_perfil(perfil: Perfil, vault_dir: Path | None = None) -> Path:
    """Escribe el perfil entero. Los valores van en JSON: una comilla o un salto no lo rompen."""
    ruta = perfil_path(vault_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    propiedades = [
        f"{c}: {json.dumps(v, ensure_ascii=False)}"
        for c in CAMPOS_PERFIL
        if (v := perfil.campos.get(c, "").strip())
    ] + perfil.otras
    arriba = "---\n" + "\n".join(propiedades) + "\n---\n" if propiedades else ""
    cuerpo = "".join(f"- {h}\n" for h in perfil.hechos)
    ruta.write_text(arriba + _CABECERA_PERFIL + cuerpo, encoding="utf-8")
    return ruta


def anotar_hecho(hecho: str, vault_dir: Path | None = None) -> str:
    """Anade un hecho al perfil, si no estaba. Devuelve el hecho tal como queda."""
    hecho = " ".join(hecho.split()).removeprefix("- ").strip()
    if not hecho:
        raise ValueError("No hay nada que anotar.")
    perfil = leer_perfil(vault_dir)
    if hecho not in perfil.hechos:
        perfil.hechos.append(hecho)
        guardar_perfil(perfil, vault_dir)
    return hecho


def quitar_hecho(hecho: str | int, vault_dir: Path | None = None) -> str:
    """Quita un hecho del perfil, por su posicion o por su texto. Devuelve el quitado."""
    perfil = leer_perfil(vault_dir)
    if isinstance(hecho, int):
        if not 0 <= hecho < len(perfil.hechos):
            raise ValueError("Ese dato ya no esta en el perfil.")
        quitado = perfil.hechos.pop(hecho)
    elif hecho in perfil.hechos:
        quitado = hecho
        perfil.hechos.remove(hecho)
    else:
        raise ValueError("Ese dato ya no esta en el perfil.")
    guardar_perfil(perfil, vault_dir)
    return quitado


def perfil_para_prompt(perfil: Perfil, *, limite: int = 2500) -> str:
    """El perfil, listo para el prompt. Vacio si no hay nada."""
    c = {k: " ".join(v.split()) for k, v in perfil.campos.items() if v.strip()}
    lineas = []
    if c.get("nombre"):
        llamale = f"; llamale {c['llamame']}" if "llamame" in c else ""
        lineas.append(f"- Se llama {c['nombre']}{llamale}")
    elif c.get("llamame"):
        lineas.append(f"- Llamale {c['llamame']}")
    for clave, frase in (
        ("dedicacion", "Se dedica a"), ("ubicacion", "Vive en"), ("idiomas", "Idiomas"),
        ("intereses", "Le interesa"),
    ):  # fmt: skip
        if c.get(clave):
            lineas.append(f"- {frase}: {c[clave]}")
    lineas += [f"- {h}" for h in perfil.hechos]
    bloques = []
    if lineas:
        bloques.append(
            "Quien es el usuario (su perfil: tenlo en cuenta siempre, sin recitarlo):\n"
            + "\n".join(lineas)
        )
    if c.get("estilo"):
        bloques.append(f"Como quiere que le respondas: {c['estilo']}")
    texto = "\n".join(bloques)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


# -- D.O.O.M -> vault -----------------------------------------------------------
def escribir_perfil(mem: Memory, vault_dir: Path | None = None) -> Path:
    """Anade al perfil lo que la voz ha aprendido del usuario (``kind='perfil'``).

    Antes era un espejo de la memoria que sobrescribia el fichero. Desde que el
    perfil se edita tambien en la ventana (D-043), el fichero es quien manda: se
    le anaden los hechos nuevos de la memoria y se respeta todo lo demas -sus
    datos, el orden, y lo que el usuario haya borrado o escrito a mano-.
    """
    perfil = leer_perfil(vault_dir)
    nuevos = [h.text for h in reversed(mem.all(kind="perfil")) if h.text not in perfil.hechos]
    perfil.hechos += nuevos
    return guardar_perfil(perfil, vault_dir)


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
    """Pone la memoria al dia con ``usuario.md``: aprende lo nuevo y olvida lo borrado.

    Cada linea que empieza por "- " se guarda como un hecho ``kind='perfil'``,
    igual que si se hubiera dicho "recuerda que yo ...". ``Memory.remember``
    ya evita duplicados, asi que sincronizar varias veces seguidas no repite
    nada. Lo que ya no esta en el fichero se olvida: el fichero manda (D-043),
    y sin esto un dato borrado en la ventana volveria en la siguiente escritura.
    Sin fichero no se olvida nada: que falte no es lo mismo que este vacio.
    """
    if not perfil_path(vault_dir).is_file():
        return 0

    hechos = leer_perfil(vault_dir).hechos
    if hechos:
        mem.remember_many(hechos, kind="perfil")
    quedan = set(hechos)
    for r in mem.all(kind="perfil"):
        if r.text not in quedan:
            mem.forget(r.id)
    return len(hechos)
