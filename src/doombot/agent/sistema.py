"""Herramientas del sistema: ficheros y comandos.

Acceso a todo el equipo, no a una carpeta de trabajo: es lo que se pidio
(D-033). La proteccion no es encerrar al agente sino preguntar antes de lo
que no se deshace -sobrescribir un fichero, o cualquier comando que no este
en la lista corta de los que solo leen-.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from doombot.agent.herramientas import Herramienta, entero, texto

_MAX_ENTRADAS = 200
_MAX_COINCIDENCIAS = 100
_MAX_CARPETAS = 20_000
_LINEAS_POR_LECTURA = 400
_TIMEOUT_COMANDO = 120.0

# Programas que solo miran. Un comando con alguno de estos -y sin nada que
# redirija o encadene otra cosa- se ejecuta sin preguntar. Todo lo demas,
# incluido lo que no se reconoce, se confirma: ante la duda, preguntar.
_SOLO_LECTURA = frozenset({
    "ls", "dir", "pwd", "cat", "head", "tail", "wc", "grep", "rg", "find", "tree",
    "which", "where", "whoami", "hostname", "uname", "date", "uptime", "df", "du",
    "free", "ps", "tasklist", "echo", "type", "file", "stat", "lsblk", "lscpu",
    "nproc", "ip", "ifconfig", "ipconfig", "systeminfo", "wmctrl", "xdg-mime",
    "sort", "uniq", "cut",
})  # fmt: skip
_GIT_SOLO_LECTURA = frozenset({"status", "log", "diff", "show"})
_FIND_PELIGROSOS = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint"})
# Una tuberia entre programas de solo lectura sigue siendo solo lectura; una
# redireccion, una sustitucion o un segundo comando encadenado, no.
_METACARACTERES = re.compile(r"[;&<>`$(){}\n]|\|\|")


# Ficheros cuyo contenido no debe llegar al modelo sin que el usuario lo vea:
# claves, credenciales, perfiles de navegador. Leerlos es "solo lectura", pero
# con el navegador propio el agente puede mandar lo leido a cualquier web, y
# una pagina maliciosa podria pedirselo. Por eso se confirman (D-033).
_CARPETAS_SENSIBLES = frozenset({
    ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker", ".password-store",
    "keyrings", ".mozilla", "google-chrome", "chromium", "bravesoftware",
    "user data", "navegador-agente",
})  # fmt: skip
_FICHERO_SENSIBLE = re.compile(
    r"(^\.env(\..*)?$|^id_(rsa|dsa|ecdsa|ed25519)|\.(pem|key|p12|pfx|kdbx|keychain)$|"
    r"credential|secret|(^|[._-])tokens?([._-]|$)|password|contrasena|\.netrc$|\.pgpass$)",
    re.IGNORECASE,
)


# Escribir aqui hace que algo se ejecute solo mas adelante -al abrir una
# terminal, al iniciar sesion-: crear el fichero ya es irreversible en la
# practica, aunque no existiera antes.
_ARRANQUE = re.compile(
    r"(^|/)\.(bashrc|bash_profile|zshrc|profile|zprofile)$|(^|/)(autostart|startup)(/|$)|crontab",
    re.IGNORECASE,
)


def es_sensible(ruta: str) -> bool:
    partes = [p.lower() for p in _ruta(ruta).parts]
    if any(p in _CARPETAS_SENSIBLES for p in partes[:-1]):
        return True
    return bool(partes) and bool(_FICHERO_SENSIBLE.search(partes[-1]))


def es_solo_lectura(comando: str) -> bool:
    if _METACARACTERES.search(comando):
        return False
    for segmento in comando.split("|"):
        try:
            partes = shlex.split(segmento, posix=sys.platform != "win32")
        except ValueError:
            return False
        if not partes:
            return False
        programa = Path(partes[0]).name.lower().removesuffix(".exe")
        if any(es_sensible(a) for a in partes[1:] if not a.startswith("-")):
            return False
        if programa == "git":
            if len(partes) < 2 or partes[1] not in _GIT_SOLO_LECTURA:
                return False
        elif programa == "find":
            if _FIND_PELIGROSOS & set(partes):
                return False
        elif programa not in _SOLO_LECTURA:
            return False
    return True


def _ruta(ruta: str) -> Path:
    return Path(os.path.expandvars(ruta or "~")).expanduser()


# -- las funciones ----------------------------------------------------------------
def listar_directorio(ruta: str = "~") -> str:
    carpeta = _ruta(ruta)
    if not carpeta.is_dir():
        return f"Error: {carpeta} no es una carpeta."
    entradas = sorted(carpeta.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    lineas = [f"{p.name}/" if p.is_dir() else p.name for p in entradas[:_MAX_ENTRADAS]]
    extra = len(entradas) - len(lineas)
    pie = f"\n[... y {extra} entradas mas]" if extra > 0 else ""
    return f"{carpeta}:\n" + "\n".join(lineas) + pie


def leer_fichero(ruta: str, desde_linea: int = 1) -> str:
    fichero = _ruta(ruta)
    if not fichero.is_file():
        return f"Error: {fichero} no existe o no es un fichero."
    try:
        lineas = fichero.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return f"Error: no se puede leer {fichero}: {e}"
    inicio = max(1, int(desde_linea))
    trozo = lineas[inicio - 1 : inicio - 1 + _LINEAS_POR_LECTURA]
    fin = inicio + len(trozo) - 1
    cabecera = f"{fichero} (lineas {inicio}-{fin} de {len(lineas)})"
    if fin < len(lineas):
        cabecera += f"; para seguir, desde_linea={fin + 1}"
    return cabecera + ":\n" + "\n".join(trozo)


def buscar_ficheros(patron: str, carpeta: str = "~") -> str:
    """Busca por nombre (comodines tipo ``*.pdf``), sin entrar en carpetas ocultas."""
    raiz = _ruta(carpeta)
    if not raiz.is_dir():
        return f"Error: {raiz} no es una carpeta."
    import fnmatch

    patron_bajo = patron.lower()
    if not any(c in patron_bajo for c in "*?["):
        patron_bajo = f"*{patron_bajo}*"
    halladas: list[str] = []
    for visitadas, (actual, carpetas, ficheros) in enumerate(os.walk(raiz), start=1):
        carpetas[:] = [c for c in carpetas if not c.startswith(".") and c != "node_modules"]
        for nombre in ficheros + carpetas:
            if fnmatch.fnmatch(nombre.lower(), patron_bajo):
                halladas.append(str(Path(actual) / nombre))
        if len(halladas) >= _MAX_COINCIDENCIAS or visitadas >= _MAX_CARPETAS:
            break
    if not halladas:
        return f"Nada que coincida con {patron!r} en {raiz}."
    return "\n".join(halladas[:_MAX_COINCIDENCIAS])


def escribir_fichero(ruta: str, contenido: str) -> str:
    fichero = _ruta(ruta)
    fichero.parent.mkdir(parents=True, exist_ok=True)
    fichero.write_text(contenido, encoding="utf-8")
    return f"Escrito {fichero} ({len(contenido)} caracteres)."


def ejecutar_comando(
    comando: str, carpeta: str = "", *, runner: Callable[..., Any] = subprocess.run
) -> str:
    try:
        proceso = runner(
            comando,
            shell=True,
            cwd=str(_ruta(carpeta)) if carpeta else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_COMANDO,
        )
    except subprocess.TimeoutExpired:
        return f"Error: el comando tardo mas de {_TIMEOUT_COMANDO:.0f}s y se corto."
    salida = (proceso.stdout or "") + (proceso.stderr or "")
    estado = "" if proceso.returncode == 0 else f"Error: codigo de salida {proceso.returncode}\n"
    return estado + (salida.strip() or "(sin salida)")


# -- confirmaciones -----------------------------------------------------------------
def _confirmar_lectura(args: dict[str, Any]) -> str | None:
    ruta = str(args.get("ruta", ""))
    if es_sensible(ruta):
        return f"Voy a leer {_ruta(ruta)}, que parece contener claves o credenciales."
    return None


def _confirmar_escritura(args: dict[str, Any]) -> str | None:
    ruta = str(args.get("ruta", ""))
    fichero = _ruta(ruta)
    if fichero.exists():
        return f"Voy a SOBRESCRIBIR {fichero}, que ya existe."
    if es_sensible(ruta) or _ARRANQUE.search(fichero.as_posix()):
        return f"Voy a crear {fichero}, en un sitio delicado (claves o arranque automatico)."
    return None


def _confirmar_comando(args: dict[str, Any]) -> str | None:
    comando = str(args.get("comando", ""))
    if es_solo_lectura(comando):
        return None
    return f"Voy a ejecutar en tu equipo: {comando}"


def herramientas() -> list[Herramienta]:
    return [
        Herramienta(
            "listar_directorio",
            "Lista lo que hay en una carpeta. Las carpetas acaban en /.",
            listar_directorio,
            {"ruta": texto("Carpeta. Admite ~ para la carpeta personal. Por defecto ~.")},
            narrar=lambda a: f"Miro qué hay en {a.get('ruta') or '~'}",
        ),
        Herramienta(
            "leer_fichero",
            f"Lee un fichero de texto, {_LINEAS_POR_LECTURA} lineas cada vez.",
            leer_fichero,
            {
                "ruta": texto("Ruta del fichero."),
                "desde_linea": entero("Primera linea a leer, empezando en 1."),
            },
            requeridos=("ruta",),
            narrar=lambda a: f"Leo {a.get('ruta')}",
            confirmar=_confirmar_lectura,
        ),
        Herramienta(
            "buscar_ficheros",
            "Busca ficheros o carpetas por nombre, con comodines (ej. *.pdf).",
            buscar_ficheros,
            {
                "patron": texto("Nombre o patron, ej. 'factura' o '*.pdf'."),
                "carpeta": texto("Donde buscar. Por defecto ~."),
            },
            requeridos=("patron",),
            narrar=lambda a: f"Busco «{a.get('patron')}» en {a.get('carpeta') or '~'}",
        ),
        Herramienta(
            "escribir_fichero",
            "Crea o sobrescribe un fichero de texto con el contenido dado.",
            escribir_fichero,
            {"ruta": texto("Ruta del fichero."), "contenido": texto("Texto completo.")},
            requeridos=("ruta", "contenido"),
            narrar=lambda a: f"Escribo {a.get('ruta')}",
            confirmar=_confirmar_escritura,
        ),
        Herramienta(
            "ejecutar_comando",
            "Ejecuta un comando en la terminal del sistema y devuelve su salida. "
            f"Se corta a los {_TIMEOUT_COMANDO:.0f}s: no lo uses para abrir programas "
            "con ventana (para eso esta abrir_aplicacion).",
            ejecutar_comando,
            {
                "comando": texto("El comando, tal cual se escribiria en la terminal."),
                "carpeta": texto("Carpeta desde la que ejecutarlo (opcional)."),
            },
            requeridos=("comando",),
            narrar=lambda a: f"Ejecuto: {a.get('comando')}",
            confirmar=_confirmar_comando,
        ),
    ]
