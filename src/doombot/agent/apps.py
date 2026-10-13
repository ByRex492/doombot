"""Reconocer, abrir y cerrar las aplicaciones instaladas.

Cada sistema guarda su lista de aplicaciones en un sitio distinto, pero todos
la guardan: no hace falta adivinar ejecutables.

- **Linux**: ficheros ``.desktop`` (lo que ve el menu del escritorio), con
  nombre, nombre generico ("Navegador web") y palabras clave.
- **Windows**: los accesos directos ``.lnk`` del menu Inicio.
- **macOS**: los paquetes ``.app`` de ``/Applications``.

Buscar por nombre generico y palabras clave es lo que permite que "abre el
navegador" encuentre Firefox sin que el modelo sepa como se llama.

Abrir no se confirma (se deshace cerrando). Cerrar si: puede perder trabajo
sin guardar (D-033).
"""

from __future__ import annotations

import csv
import difflib
import io
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from doombot.agent.herramientas import Herramienta, texto
from doombot.phrases.matcher import normalize


@dataclass(frozen=True)
class App:
    nombre: str
    ident: str
    """Lo que identifica la app para lanzarla: id del .desktop, ruta del .lnk o del .app."""
    ruta: Path
    generico: str = ""
    palabras: tuple[str, ...] = ()
    categorias: tuple[str, ...] = ()
    """``Categories`` del .desktop (``WebBrowser``, ``FileManager``...): no dependen del idioma."""
    exec_: str = ""

    def describir(self) -> str:
        extra = f" — {self.generico}" if self.generico else ""
        return f"{self.nombre}{extra}"


# -- descubrimiento -------------------------------------------------------------
def _dirs_linux() -> list[Path]:
    casa = Path.home()
    datos = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    # El orden importa: la carpeta del usuario va primero y gana sobre la del
    # sistema, como hace el propio escritorio.
    return [
        Path(os.environ.get("XDG_DATA_HOME") or casa / ".local/share") / "applications",
        *(Path(d) / "applications" for d in datos.split(":") if d),
        Path("/var/lib/snapd/desktop/applications"),
        casa / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
    ]


def _leer_desktop(fichero: Path) -> App | None:
    """Lee la seccion [Desktop Entry]. Devuelve None si no es una app visible."""
    try:
        lineas = fichero.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    campos: dict[str, str] = {}
    en_entrada = False
    for linea in lineas:
        linea = linea.strip()
        if linea.startswith("["):
            en_entrada = linea == "[Desktop Entry]"
            continue
        if en_entrada and "=" in linea and not linea.startswith("#"):
            clave, _, valor = linea.partition("=")
            campos.setdefault(clave.strip(), valor.strip())

    if campos.get("Type", "Application") != "Application":
        return None
    if campos.get("NoDisplay", "").lower() == "true" or campos.get("Hidden", "").lower() == "true":
        return None
    nombre = campos.get("Name[es]") or campos.get("Name")
    if not nombre:
        return None
    palabras = campos.get("Keywords[es]", "") + ";" + campos.get("Keywords", "")
    return App(
        nombre=nombre,
        ident=fichero.stem,
        ruta=fichero,
        generico=campos.get("GenericName[es]") or campos.get("GenericName", ""),
        palabras=tuple(p.strip() for p in palabras.split(";") if p.strip()),
        categorias=tuple(c for c in campos.get("Categories", "").split(";") if c),
        exec_=campos.get("Exec", ""),
    )


def _apps_linux(dirs: Iterable[Path]) -> list[App]:
    vistas: dict[str, App | None] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for fichero in sorted(d.rglob("*.desktop")):
            # El primero gana, aunque sea para ocultarla: un .desktop del usuario
            # con NoDisplay=true esconde la app del sistema, igual que en el menu.
            if fichero.stem not in vistas:
                vistas[fichero.stem] = _leer_desktop(fichero)
    return [a for a in vistas.values() if a is not None]


def _apps_windows(dirs: Iterable[Path]) -> list[App]:
    apps: dict[str, App] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for lnk in sorted(d.rglob("*.lnk")):
            nombre = lnk.stem
            bajo = nombre.lower()
            if "uninstall" in bajo or "desinstal" in bajo:
                continue
            apps.setdefault(bajo, App(nombre=nombre, ident=str(lnk), ruta=lnk))
    return list(apps.values())


def _apps_mac(dirs: Iterable[Path]) -> list[App]:
    apps: dict[str, App] = {}
    for d in dirs:
        if not d.is_dir():
            continue
        for app in sorted([*d.glob("*.app"), *d.glob("*/*.app")]):
            apps.setdefault(app.stem.lower(), App(nombre=app.stem, ident=str(app), ruta=app))
    return list(apps.values())


def descubrir(plataforma: str = sys.platform, dirs: Iterable[Path] | None = None) -> list[App]:
    if plataforma == "win32":
        programas = "Microsoft/Windows/Start Menu/Programs"
        defecto = [
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / programas,
            Path(os.environ.get("APPDATA", "")) / programas,
        ]
        apps = _apps_windows(dirs if dirs is not None else defecto)
    elif plataforma == "darwin":
        defecto = [
            Path("/Applications"),
            Path("/System/Applications"),
            Path.home() / "Applications",
        ]
        apps = _apps_mac(dirs if dirs is not None else defecto)
    else:
        apps = _apps_linux(dirs if dirs is not None else _dirs_linux())
    return sorted(apps, key=lambda a: a.nombre.lower())


# Lo que se pide en espanol -"el navegador", "algo para musica"- hacia las
# categorias estandar de freedesktop. GNOME traduce los nombres con gettext, no
# en el .desktop: sin esto, "navegador" no encontraba Firefox ("Web Browser") ni
# "archivos" encontraba Nautilus ("Files"). Las categorias, en cambio, estan
# siempre y en ingles.
_CATEGORIAS = {
    "navegador": ("webbrowser",),
    "navegador web": ("webbrowser",),
    "internet": ("webbrowser",),
    "editor": ("texteditor",),
    "editor de texto": ("texteditor",),
    "bloc de notas": ("texteditor",),
    "archivos": ("filemanager",),
    "ficheros": ("filemanager",),
    "explorador": ("filemanager",),
    "explorador de archivos": ("filemanager",),
    "musica": ("audio", "music"),
    "reproductor": ("player",),
    "video": ("video",),
    "videos": ("video",),
    "fotos": ("photography", "viewer"),
    "imagenes": ("graphics", "viewer"),
    "correo": ("email",),
    "email": ("email",),
    "terminal": ("terminalemulator",),
    "consola": ("terminalemulator",),
    "configuracion": ("settings",),
    "ajustes": ("settings",),
    "calculadora": ("calculator",),
    "ofimatica": ("office",),
    "hoja de calculo": ("spreadsheet",),
    "chat": ("chat", "instantmessaging"),
    "juegos": ("game",),
}


def buscar(apps: Iterable[App], consulta: str, limite: int = 5) -> list[App]:
    """Las apps que mejor encajan con ``consulta``, de mejor a peor.

    Por nombre primero, despues por nombre generico y palabras clave, y por
    ultimo por parecido aproximado -para "fire fox" o "visual studio"-.
    """
    q = normalize(consulta)
    for articulo in ("el ", "la ", "los ", "las ", "un ", "una ", "algo para ", "el de "):
        q = q.removeprefix(articulo)
    if not q:
        return []
    categorias_pedidas = set(_CATEGORIAS.get(q, ()))
    puntuadas: list[tuple[float, App]] = []
    for app in apps:
        nombre = normalize(app.nombre)
        extras = normalize(" ".join((app.generico, app.ident, *app.palabras)))
        categorias = {c.lower() for c in app.categorias}
        if nombre == q:
            puntos = 100.0
        elif nombre.startswith(q):
            puntos = 80.0
        elif nombre in categorias_pedidas:
            # La app se llama como la categoria: "Settings" para "configuracion".
            puntos = 70.0
        elif q in nombre:
            puntos = 60.0
        elif categorias_pedidas & categorias:
            puntos = 50.0
        elif q in extras.split() or (len(q) > 3 and q in extras):
            puntos = 40.0
        else:
            puntos = difflib.SequenceMatcher(None, q, nombre).ratio() * 50
            if puntos < 30:
                continue
        puntuadas.append((puntos, app))
    puntuadas.sort(key=lambda t: (-t[0], t[1].nombre.lower()))
    return [a for _, a in puntuadas[:limite]]


# -- lanzar y cerrar ------------------------------------------------------------
def _sin_codigos(exec_: str) -> list[str]:
    """``Exec`` de un .desktop sin los %f, %U... que rellena el escritorio."""
    import shlex

    return [p for p in shlex.split(exec_) if not (len(p) == 2 and p.startswith("%"))]


def orden_lanzar(app: App, argumentos: list[str], plataforma: str = sys.platform) -> list[str]:
    """El comando que abre ``app``. Separado para poder probarlo sin abrir nada."""
    if plataforma == "darwin":
        return ["open", "-a", app.ident, *(["--args", *argumentos] if argumentos else [])]
    if shutil.which("gtk-launch"):
        return ["gtk-launch", app.ident, *argumentos]
    if not argumentos and shutil.which("gio"):
        return ["gio", "launch", str(app.ruta)]
    return [*_sin_codigos(app.exec_), *argumentos]


@dataclass
class Aplicaciones:
    """Estado de las herramientas de apps: el catalogo y lo que ha abierto el agente."""

    plataforma: str = sys.platform
    lanzador: Callable[..., Any] | None = None
    ejecutor: Callable[..., Any] = subprocess.run
    abiertas: list[str] = field(default_factory=list)
    _catalogo: list[App] | None = None

    @property
    def catalogo(self) -> list[App]:
        if self._catalogo is None:
            self._catalogo = descubrir(self.plataforma)
        return self._catalogo

    def listar(self, filtro: str = "") -> str:
        apps = buscar(self.catalogo, filtro, limite=40) if filtro else self.catalogo
        if not apps:
            return f"No encuentro ninguna aplicacion para {filtro!r}."
        cabecera = f"{len(apps)} aplicaciones" + (f" para {filtro!r}" if filtro else "")
        return cabecera + ":\n" + "\n".join(a.describir() for a in apps)

    def abrir(self, nombre: str, argumento: str = "") -> str:
        candidatas = buscar(self.catalogo, nombre)
        if not candidatas:
            return (
                f"Error: no encuentro ninguna aplicacion instalada que se parezca a {nombre!r}. "
                "Usa listar_aplicaciones para ver cuales hay."
            )
        app = candidatas[0]
        argumentos = [argumento] if argumento else []
        if self.plataforma == "win32":
            # os.startfile abre el .lnk como lo haria el menu Inicio, sin consola.
            lanzar = self.lanzador or os.startfile  # type: ignore[attr-defined]
            if argumentos:
                lanzar(app.ident, arguments=" ".join(argumentos))
            else:
                lanzar(app.ident)
        else:
            lanzar = self.lanzador or subprocess.Popen
            lanzar(
                orden_lanzar(app, argumentos, self.plataforma),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        self.abiertas.append(app.nombre)
        otras = [a.nombre for a in candidatas[1:3]]
        nota = f" (otras parecidas: {', '.join(otras)})" if otras else ""
        return f"Abierta {app.nombre}{nota}."

    def ventanas(self) -> str:
        if self.plataforma == "win32":
            r = self.ejecutor(
                ["tasklist", "/v", "/fo", "csv", "/nh"], capture_output=True, text=True
            )
            filas = [f for f in csv.reader(io.StringIO(r.stdout)) if len(f) >= 9]
            lineas = [f"{f[0]} (pid {f[1]}): {f[8]}" for f in filas if f[8] not in ("N/A", "")]
        elif self.plataforma == "darwin":
            guion = (
                'tell application "System Events" to get name of '
                "(processes where background only is false)"
            )
            r = self.ejecutor(["osascript", "-e", guion], capture_output=True, text=True)
            lineas = [n.strip() for n in r.stdout.split(",") if n.strip()]
        else:
            if not shutil.which("wmctrl"):
                return (
                    "Error: para ver las ventanas abiertas hace falta wmctrl "
                    "(sudo apt install wmctrl). En Wayland no funciona."
                )
            r = self.ejecutor(["wmctrl", "-l"], capture_output=True, text=True)
            # "0x0120000a  0 equipo Titulo de la ventana": el titulo es el resto.
            lineas = [
                ln.split(None, 3)[3] for ln in r.stdout.splitlines() if len(ln.split(None, 3)) == 4
            ]
        if not lineas:
            return "No veo ninguna ventana abierta."
        return "Ventanas abiertas:\n" + "\n".join(lineas)

    def cerrar(self, nombre: str) -> str:
        if self.plataforma == "win32":
            r = self.ejecutor(
                ["taskkill", "/IM", nombre if nombre.lower().endswith(".exe") else f"{nombre}.exe"],
                capture_output=True,
                text=True,
            )
        elif self.plataforma == "darwin":
            r = self.ejecutor(
                ["osascript", "-e", f'quit app "{nombre}"'], capture_output=True, text=True
            )
        else:
            if not shutil.which("wmctrl"):
                return "Error: para cerrar ventanas hace falta wmctrl (sudo apt install wmctrl)."
            # -c cierra la ventana como el boton de la X: la app puede pedir
            # guardar. No se mata ningun proceso. Si el titulo no coincide, se
            # prueba con el nombre de la app que encaje: se pide "calculadora"
            # y la ventana se titula "Calculator" (GNOME en ingles).
            for titulo in dict.fromkeys(
                [nombre, *(a.nombre for a in buscar(self.catalogo, nombre, 1))]
            ):
                r = self.ejecutor(["wmctrl", "-c", titulo], capture_output=True, text=True)
                if r.returncode == 0:
                    return f"Pedido el cierre de la ventana {titulo!r}."
            return (
                f"Error: no hay ninguna ventana cuyo titulo contenga {nombre!r}. "
                "Mira los titulos con ventanas_abiertas."
            )
        if r.returncode != 0:
            return f"Error: no he podido cerrar {nombre!r}: {(r.stderr or r.stdout).strip()}"
        return f"Pedido el cierre de {nombre!r}."

    def herramientas(self) -> list[Herramienta]:
        return [
            Herramienta(
                "listar_aplicaciones",
                "Lista las aplicaciones instaladas. Con filtro, las que mejor encajan "
                "(por nombre o por tipo: 'navegador', 'editor de texto', 'musica').",
                self.listar,
                {"filtro": texto("Nombre o tipo de aplicacion. Vacio = todas.")},
                narrar=lambda a: (
                    f"Busco aplicaciones de «{a['filtro']}»"
                    if a.get("filtro")
                    else "Repaso las aplicaciones instaladas"
                ),
                familia="apps",
            ),
            Herramienta(
                "abrir_aplicacion",
                "Abre una aplicacion instalada por su nombre o tipo. Opcionalmente "
                "con un fichero o direccion para abrir en ella.",
                self.abrir,
                {
                    "nombre": texto("Nombre de la aplicacion, ej. 'Firefox' o 'calculadora'."),
                    "argumento": texto("Fichero o URL que abrir con ella (opcional)."),
                },
                requeridos=("nombre",),
                narrar=lambda a: (
                    f"Abro {a.get('nombre')}"
                    + (f" con {a['argumento']}" if a.get("argumento") else "")
                ),
                familia="apps",
            ),
            Herramienta(
                "ventanas_abiertas",
                "Lista las ventanas o aplicaciones abiertas ahora mismo.",
                self.ventanas,
                narrar=lambda a: "Miro qué ventanas hay abiertas",
                familia="apps",
            ),
            Herramienta(
                "cerrar_aplicacion",
                "Cierra una aplicacion como el boton de cerrar. En Linux, por parte del "
                "titulo de su ventana; en Windows, por nombre de proceso.",
                self.cerrar,
                {"nombre": texto("Parte del titulo de la ventana, o nombre del proceso.")},
                requeridos=("nombre",),
                narrar=lambda a: f"Cierro {a.get('nombre')}",
                confirmar=lambda a: (
                    f"Voy a cerrar {a.get('nombre')!r} (si hay algo sin guardar, se puede perder)."
                ),
                familia="apps",
            ),
        ]
