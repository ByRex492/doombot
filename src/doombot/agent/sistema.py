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
from typing import TYPE_CHECKING, Any

from doombot.agent.herramientas import Herramienta, booleano, entero, texto

if TYPE_CHECKING:
    from doombot.agent.taller import Taller

_MAX_ENTRADAS = 200
_MAX_COINCIDENCIAS = 100
_MAX_CARPETAS = 20_000
_LINEAS_POR_LECTURA = 400
_TIMEOUT_COMANDO = 120.0
_TIMEOUT_TALLER = 600.0

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


def editar_fichero(ruta: str, buscar: str, reemplazar: str, todas: bool = False) -> str:
    """Cambia un trozo exacto de un fichero (D-045).

    Reescribir el fichero entero para cambiar tres lineas gasta en cada paso
    la cuota de tokens de los modelos gratuitos, y el modelo tiende a perder
    por el camino lo que no iba a tocar. Como el Edit de Claude Code: el trozo
    tiene que aparecer tal cual, y una sola vez salvo que se pidan todas.
    """
    fichero = _ruta(ruta)
    if not fichero.is_file():
        return f"Error: {fichero} no existe; para crearlo, escribir_fichero."
    if not buscar:
        return "Error: buscar no puede estar vacio."
    # newline="" conserva los saltos tal cual: sin eso, un fichero de Windows
    # se guardaria con saltos de Linux sin que nadie lo pidiera.
    with fichero.open(encoding="utf-8", errors="replace", newline="") as f:
        actual = f.read()
    n = actual.count(buscar)
    if n == 0 and "\r\n" in actual and "\r\n" not in buscar:
        # Fichero con saltos de Windows: el modelo siempre escribe \n.
        buscar, reemplazar = buscar.replace("\n", "\r\n"), reemplazar.replace("\n", "\r\n")
        n = actual.count(buscar)
    if n == 0:
        return (
            f"Error: no encuentro ese texto en {fichero.name}. Tiene que coincidir exacto, con "
            "espacios y sangria: lee el fichero y copialo tal cual."
        )
    if n > 1 and not todas:
        return (
            f"Error: ese texto aparece {n} veces en {fichero.name}. Anade lineas de alrededor "
            "para que sea unico, o pasa todas=true."
        )
    nuevo = actual.replace(buscar, reemplazar) if todas else actual.replace(buscar, reemplazar, 1)
    with fichero.open("w", encoding="utf-8", newline="") as f:
        f.write(nuevo)
    return f"Editado {fichero}: {n if todas else 1} cambio(s)."


_MAX_TEXTO = 80


def buscar_texto(buscar: str, carpeta: str = "~", patron: str = "") -> str:
    """Busca un texto dentro de los ficheros (como grep): donde se usa una funcion, un error."""
    raiz = _ruta(carpeta)
    if not raiz.is_dir():
        return f"Error: {raiz} no es una carpeta."
    if not buscar:
        return "Error: falta el texto a buscar."
    import fnmatch

    bajo = buscar.lower()
    halladas: list[str] = []
    for visitadas, (actual, carpetas, ficheros) in enumerate(os.walk(raiz), start=1):
        carpetas[:] = [c for c in carpetas if not c.startswith(".") and c not in _SIN_INTERES]
        for nombre in ficheros:
            if nombre.startswith(".") or (patron and not fnmatch.fnmatch(nombre, patron)):
                continue
            fichero = Path(actual) / nombre
            try:
                if fichero.stat().st_size > 1_000_000:
                    continue
                with fichero.open(encoding="utf-8", errors="strict") as f:
                    for n, linea in enumerate(f, start=1):
                        if bajo in linea.lower():
                            halladas.append(f"{fichero}:{n}: {linea.strip()[:160]}")
                            if len(halladas) >= _MAX_TEXTO:
                                break
            except (OSError, UnicodeDecodeError):
                continue  # binarios y lo que no se deja leer
            if len(halladas) >= _MAX_TEXTO:
                break
        if len(halladas) >= _MAX_TEXTO or visitadas >= _MAX_CARPETAS:
            break
    if not halladas:
        return f"«{buscar}» no aparece en {raiz}."
    return "\n".join(halladas)


_SIN_INTERES = frozenset({"node_modules", "__pycache__", "venv", "build", "dist", "target"})


def ejecutar_comando(
    comando: str,
    carpeta: str = "",
    *,
    runner: Callable[..., Any] = subprocess.run,
    timeout: float | None = None,
) -> str:
    limite = timeout or _TIMEOUT_COMANDO
    try:
        proceso = runner(
            comando,
            shell=True,
            cwd=str(_ruta(carpeta)) if carpeta else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=limite,
        )
    except subprocess.TimeoutExpired:
        return f"Error: el comando tardo mas de {limite:.0f}s y se corto."
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


def herramientas(taller: Taller | None = None) -> list[Herramienta]:
    """Las herramientas de ficheros y terminal. Con ``taller``, autonomia dentro de el (D-045).

    Dentro del taller no se pregunta lo que fuera si: sobrescribir, editar o
    ejecutar. A cambio, antes de tocar un proyecto se guarda su punto de
    control (``Taller.antes_de_tocar``), y deshacer vuelve atras.
    """

    def libre_ruta(a: dict[str, Any]) -> bool:
        ruta = str(a.get("ruta", ""))
        return taller is not None and taller.ruta_libre(ruta) and not es_sensible(ruta)

    def confirmar_escritura(a: dict[str, Any]) -> str | None:
        return None if libre_ruta(a) else _confirmar_escritura(a)

    def confirmar_edicion(a: dict[str, Any]) -> str | None:
        if libre_ruta(a):
            return None
        return f"Voy a CAMBIAR {_ruta(str(a.get('ruta', '')))}, que ya existe."

    def confirmar_comando(a: dict[str, Any]) -> str | None:
        if taller is not None and taller.comando_libre(
            str(a.get("comando", "")), str(a.get("carpeta", ""))
        ):
            return None
        return _confirmar_comando(a)

    def tocar(ruta: str) -> None:
        if taller is not None:
            taller.antes_de_tocar(ruta)

    def escribir(ruta: str, contenido: str) -> str:
        tocar(ruta)
        return escribir_fichero(ruta, contenido)

    def editar(ruta: str, buscar: str, reemplazar: str, todas: bool = False) -> str:
        tocar(ruta)
        return editar_fichero(ruta, buscar, reemplazar, todas)

    def ejecutar(comando: str, carpeta: str = "") -> str:
        en_taller = taller is not None and bool(carpeta) and taller.dentro(carpeta)
        if en_taller and not es_solo_lectura(comando):
            tocar(carpeta)
        # Compilar o instalar dependencias de un proyecto tarda mas que un comando suelto.
        return ejecutar_comando(comando, carpeta, timeout=_TIMEOUT_TALLER if en_taller else None)

    return [
        Herramienta(
            "listar_directorio",
            "Lista lo que hay en una carpeta. Las carpetas acaban en /.",
            listar_directorio,
            {"ruta": texto("Carpeta. Admite ~ para la carpeta personal. Por defecto ~.")},
            narrar=lambda a: f"Miro qué hay en {a.get('ruta') or '~'}",
            familia="ficheros",
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
            familia="ficheros",
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
            familia="ficheros",
        ),
        Herramienta(
            "buscar_texto",
            "Busca un texto dentro de los ficheros de una carpeta (como grep): donde se usa "
            "algo, de donde sale un error.",
            buscar_texto,
            {
                "buscar": texto("El texto a buscar (sin distinguir mayusculas)."),
                "carpeta": texto("Donde buscar. Por defecto ~."),
                "patron": texto("Solo ficheros con este nombre, ej. '*.py' (opcional)."),
            },
            requeridos=("buscar",),
            narrar=lambda a: f"Busco «{a.get('buscar')}» en {a.get('carpeta') or '~'}",
            familia="ficheros",
        ),
        Herramienta(
            "escribir_fichero",
            "Crea o sobrescribe un fichero de texto con el contenido dado.",
            escribir,
            {"ruta": texto("Ruta del fichero."), "contenido": texto("Texto completo.")},
            requeridos=("ruta", "contenido"),
            narrar=lambda a: f"Escribo {a.get('ruta')}",
            confirmar=confirmar_escritura,
            familia="ficheros",
        ),
        Herramienta(
            "editar_fichero",
            "Cambia un trozo de un fichero existente: buscar tiene que aparecer tal cual "
            "(con su sangria) y una sola vez, salvo todas=true.",
            editar,
            {
                "ruta": texto("Ruta del fichero."),
                "buscar": texto("El texto exacto que hay ahora."),
                "reemplazar": texto("Lo que va en su lugar."),
                "todas": booleano("Cambiar todas las apariciones."),
            },
            requeridos=("ruta", "buscar", "reemplazar"),
            narrar=lambda a: f"Edito {a.get('ruta')}",
            confirmar=confirmar_edicion,
            familia="ficheros",
        ),
        Herramienta(
            "ejecutar_comando",
            "Ejecuta un comando en la terminal del sistema y devuelve su salida. "
            f"Se corta a los {_TIMEOUT_COMANDO:.0f}s: no lo uses para abrir programas "
            "con ventana (para eso esta abrir_aplicacion).",
            ejecutar,
            {
                "comando": texto("El comando, tal cual se escribiria en la terminal."),
                "carpeta": texto("Carpeta desde la que ejecutarlo (opcional)."),
            },
            requeridos=("comando",),
            narrar=lambda a: f"Ejecuto: {a.get('comando')}",
            confirmar=confirmar_comando,
            familia="terminal",
        ),
    ]
