"""El taller (D-045): donde D.O.O.M trabaja los proyectos de codigo con autonomia total.

Fuera del taller el agente pregunta antes de lo irreversible (D-033). Dentro
no: crea, edita, borra, ejecuta e instala lo que el proyecto necesite sin
pedir permiso, porque programar a base de "¿puedo escribir este fichero?" no
se aguanta. Lo que lo hace seguro no es preguntar, sino poder volver atras:

- **Punto de control antes de cada orden.** La primera vez que una orden va a
  tocar un proyecto, se guarda su estado en un repositorio git *en la sombra*
  (``data_dir()/taller``), aparte del git del propio proyecto: no ensucia su
  historial ni sus ramas, y funciona tambien en carpetas sin git.
- **Deshacer.** Devuelve el proyecto al ultimo punto de control distinto del
  estado actual; antes guarda el actual, asi que deshacer tambien se deshace.
- **Lo que sale del taller se sigue preguntando**: un comando con ``sudo``,
  que instala algo en el sistema, publica (``git push``), se conecta a otra
  maquina o nombra una ruta de fuera del taller.

Limite honesto: un programa escrito en el taller y ejecutado ahi puede hacer
lo que quiera en el equipo, y eso no se puede detectar mirando el comando.
La proteccion ahi es que lo que lee de fuera son datos y no ordenes (D-033).

Y un **diario** por proyecto (``.doom/diario.md``): que se pidio, que se hizo y
que ficheros cambiaron, sin gastar peticiones -es la respuesta del propio
agente-. Es lo que permite "¿en que nos quedamos con el juego?".
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from doombot.agent.herramientas import Herramienta, recortar, texto
from doombot.agent.procesos import Procesos

# Lo que no se guarda en los puntos de control: se regenera solo (dependencias,
# compilados, caches de motores de juego) y pesaria gigas.
_EXCLUIR = (
    "node_modules/", ".venv/", "venv/", "__pycache__/", ".pytest_cache/", ".godot/",
    ".import/", "Library/", "Temp/", "Obj/", "obj/", "Logs/", "build/", "dist/", "target/",
    ".gradle/", ".idea/", ".vs/", ".doom/", "*.log", ".DS_Store",
)  # fmt: skip

# Lo que sale del taller aunque se ejecute dentro: se pregunta siempre.
_SALE = re.compile(
    r"\b(sudo|su|doas|pkexec|runas)\b"
    r"|\b(apt|apt-get|dnf|yum|pacman|zypper|snap|flatpak|winget|choco|scoop|brew)\s"
    r"|\b(systemctl|launchctl|reboot|shutdown|poweroff|halt|fdisk|parted|diskpart)\b|\bmkfs"
    r"|\bgit\s+push\b|\b(npm|pnpm|yarn|bun)\s+publish\b|\b(twine|cargo|gem)\s+(upload|publish|push)"
    r"|\bdocker\s+push\b|\b(ssh|scp|sftp|rsync|ftp)\b"
    r"|\b(curl|wget|iwr|irm)\b[^|\n]*\|\s*(sh|bash|zsh|iex|python3?|pwsh|powershell)\b"
    r"|\b(reg|regedit)\s+(add|delete|import)\b|Set-ExecutionPolicy|\bcrontab\b|\bschtasks\b"
    r"|\b(npm|pnpm|yarn)\s+(i|install|add)\b[^\n]*\s(-g|--global)\b|\byarn\s+global\b"
    r"|\$\(|`|\$\{",
    re.IGNORECASE,
)
# pip fuera de un entorno virtual instala en el Python del sistema (o en el de D.O.O.M).
_PIP = re.compile(r"\b(pip3?|python3?\s+-m\s+pip)\s+install\b", re.IGNORECASE)
_VENV = re.compile(
    r"(\.venv|venv|env)[/\\](bin|Scripts)[/\\]|\b(uv|poetry|pipenv)\s", re.IGNORECASE
)
# Rutas escritas en el comando (tambien dentro de comillas o de "python -c").
_RUTA = re.compile(
    r"""(?:^|[\s'"=(,])(~[^\s'";|&)]*|/(?!/)[^\s'";|&)]*|[A-Za-z]:[\\/][^\s'";|&)]*"""
    r"""|\$HOME[^\s'";|&)]*|%[A-Za-z_]+%[^\s'";|&)]*|\.\.[\\/][^\s'";|&)]*|\.\.(?=[\s'";|&)]|$))"""
)
_INOFENSIVAS = {"/dev/null", "/dev/stdout", "/dev/stderr", "nul"}


def _expandir(ruta: str) -> Path:
    return Path(os.path.expandvars(ruta or "~")).expanduser()


def _slug(texto_: str) -> str:
    limpio = re.sub(r"[^\w.-]+", "-", texto_.strip(), flags=re.UNICODE).strip("-.")
    return limpio[:60] or "proyecto"


class Taller:
    """Las carpetas del taller, sus puntos de control y su diario."""

    def __init__(
        self,
        raices: list[Path],
        *,
        datos: Path | None = None,
        git: str | None = "git",
        run: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.raices = [_expandir(str(r)) for r in raices] or [Path.home() / "taller"]
        self._datos = datos
        self._git = git
        self._run = run
        self.procesos = Procesos()
        self._orden = ""
        self._tocados: dict[Path, str] = {}
        """Proyectos tocados en la orden en curso -> su punto de control."""
        self.avisar: Callable[[str], None] = lambda _texto: None

    @property
    def raiz(self) -> Path:
        """Donde se crean los proyectos nuevos."""
        return self.raices[0]

    @property
    def autonomo(self) -> bool:
        """Sin git no hay deshacer, y sin deshacer no hay autonomia: se pregunta como fuera."""
        return bool(self._git)

    # -- donde esta cada cosa ---------------------------------------------------
    def dentro(self, ruta: str | Path) -> bool:
        p = self._absoluta(ruta)
        return any(p == r or p.is_relative_to(r) for r in self.raices)

    def proyecto_de(self, ruta: str | Path) -> Path | None:
        """El proyecto al que pertenece una ruta: la carpeta de primer nivel del taller."""
        p = self._absoluta(ruta)
        for r in self.raices:
            if p != r and p.is_relative_to(r):
                return r / p.relative_to(r).parts[0]
        return None

    @staticmethod
    def _absoluta(ruta: str | Path, base: Path | None = None) -> Path:
        p = _expandir(str(ruta))
        if not p.is_absolute():
            p = (base or Path.cwd()) / p
        return Path(os.path.normpath(p))

    # -- autonomia ----------------------------------------------------------------
    def ruta_libre(self, ruta: str) -> bool:
        """Escribir aqui no se pregunta: esta en un proyecto del taller."""
        return self.autonomo and self.proyecto_de(ruta) is not None

    def comando_libre(self, comando: str, carpeta: str) -> bool:
        """Un comando que se ejecuta en el taller y no sale de el."""
        if not self.autonomo or not carpeta or not self.dentro(carpeta):
            return False
        if _SALE.search(comando) or (_PIP.search(comando) and not _VENV.search(comando)):
            return False
        base = self._absoluta(carpeta)
        temporal = Path(tempfile.gettempdir()).resolve()
        for m in _RUTA.finditer(comando):
            crudo = m.group(1).rstrip(".,:")
            if crudo.lower() in _INOFENSIVAS:
                continue
            p = self._absoluta(crudo, base)
            if p.is_relative_to(temporal) or self.dentro(p):
                continue
            return False
        return True

    # -- puntos de control --------------------------------------------------------
    def nueva_orden(self, tarea: str) -> None:
        self._orden = recortar(tarea, 80)
        self._tocados = {}

    def antes_de_tocar(self, ruta: str | Path) -> None:
        """Guarda el estado del proyecto de ``ruta`` la primera vez que una orden lo toca."""
        if not self.autonomo:
            return
        proyecto = self.proyecto_de(ruta)
        if proyecto is None or proyecto in self._tocados:
            return
        proyecto.mkdir(parents=True, exist_ok=True)
        try:
            punto = self._punto(proyecto, f"antes de «{self._orden or 'una orden'}»")
        except (OSError, subprocess.SubprocessError, RuntimeError) as e:
            self.avisar(f"sin punto de control en {proyecto.name}: {recortar(str(e), 120)}")
            punto = ""
        self._tocados[proyecto] = punto
        self._guardar_estado(activo=str(proyecto))

    def _sombra(self, proyecto: Path) -> Path:
        huella = hashlib.sha1(str(proyecto).encode()).hexdigest()[:8]
        from doombot.paths import data_dir

        base = self._datos or data_dir() / "taller"
        return base / f"{_slug(proyecto.name)}-{huella}.git"

    def _g(self, proyecto: Path, *args: str, comprobar: bool = True) -> str:
        sombra = self._sombra(proyecto)
        orden = [
            self._git or "git",
            f"--git-dir={sombra}",
            f"--work-tree={proyecto}",
            "-c", "core.autocrlf=false", "-c", "core.quotepath=off",
            "-c", "commit.gpgsign=false", "-c", f"core.hooksPath={sombra / 'hooks'}",
            "-c", "user.name=D.O.O.M", "-c", "user.email=doom@localhost",
            *args,
        ]  # fmt: skip
        r = self._run(orden, capture_output=True, text=True, encoding="utf-8", timeout=120)
        if comprobar and r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout or "git fallo").strip())
        return r.stdout or ""

    def _preparar_sombra(self, proyecto: Path) -> None:
        sombra = self._sombra(proyecto)
        if (sombra / "HEAD").is_file():
            return
        sombra.parent.mkdir(parents=True, exist_ok=True)
        self._g(proyecto, "init", "-q")
        (sombra / "info").mkdir(exist_ok=True)
        (sombra / "info" / "exclude").write_text("\n".join(_EXCLUIR) + "\n", encoding="utf-8")

    def _punto(self, proyecto: Path, mensaje: str) -> str:
        """Guarda el estado actual si ha cambiado. Devuelve el commit del punto."""
        self._preparar_sombra(proyecto)
        self._g(proyecto, "add", "-A")
        hay_cabeza = self._g(proyecto, "rev-parse", "-q", "--verify", "HEAD", comprobar=False)
        if hay_cabeza.strip():
            sin_cambios = self._run(
                [self._git or "git", f"--git-dir={self._sombra(proyecto)}",
                 f"--work-tree={proyecto}", "diff", "--cached", "--quiet", "HEAD"],
                capture_output=True, timeout=120,
            ).returncode == 0  # fmt: skip
            if sin_cambios:
                return hay_cabeza.strip()
        self._g(proyecto, "commit", "-q", "--allow-empty", "-m", mensaje)
        return self._g(proyecto, "rev-parse", "HEAD").strip()

    def cambios(self, proyecto: str = "") -> str:
        p = self._elegir(proyecto)
        if isinstance(p, str):
            return p
        if not (self._sombra(p) / "HEAD").is_file():
            return f"No hay puntos de control de {p.name} todavia: no he tocado nada ahi."
        base = self._tocados.get(p) or "HEAD"
        self._g(p, "add", "-A")
        resumen = self._g(p, "diff", "--cached", "--stat", base).strip()
        if not resumen:
            return f"Sin cambios en {p.name} desde el ultimo punto de control."
        detalle = self._g(p, "diff", "--cached", base)
        return f"Cambios en {p.name}:\n{resumen}\n\n{recortar_lineas(detalle, 120)}"

    def deshacer(self, proyecto: str = "") -> str:
        p = self._elegir(proyecto)
        if isinstance(p, str):
            return p
        if not (self._sombra(p) / "HEAD").is_file():
            return f"No hay puntos de control de {p.name}: no hay nada que deshacer."
        self._g(p, "add", "-A")
        actual = self._g(p, "write-tree").strip()
        destino = self._destino(p, actual)
        if destino is None:
            return f"No hay nada que deshacer en {p.name}: esta como en su primer punto de control."
        commit, mensaje = destino
        # Lo de ahora tambien se guarda: deshacer se puede deshacer.
        self._g(p, "commit", "-q", "--allow-empty", "-m", "deshacer: estado antes de deshacer")
        self._g(p, "read-tree", "-u", "--reset", commit)
        self._tocados.pop(p, None)
        return f"Devuelto {p.name} al estado {mensaje}."

    def _destino(self, p: Path, actual: str) -> tuple[str, str] | None:
        for linea in self._g(p, "log", "--format=%H%x09%T%x09%s").splitlines():
            commit, arbol, mensaje = (linea.split("\t", 2) + ["", ""])[:3]
            if mensaje.startswith("deshacer:") or arbol == actual:
                continue
            return commit, mensaje
        return None

    def destino_deshacer(self, proyecto: str = "") -> str:
        """Lo que deshacer devolveria, para la pregunta de confirmacion."""
        p = self._elegir(proyecto)
        if isinstance(p, str):
            return "el proyecto activo"
        return f"{p.name} al estado de antes de la ultima orden que lo cambio"

    def _elegir(self, proyecto: str) -> Path | str:
        """El proyecto por nombre (o parte de el), o el activo si no se dice."""
        if proyecto.strip():
            nombre = proyecto.strip().lower()
            candidatos = [p for p in self._proyectos() if p.name.lower() == nombre]
            candidatos = candidatos or [p for p in self._proyectos() if nombre in p.name.lower()]
            if len(candidatos) == 1:
                return candidatos[0]
            if not candidatos and self.proyecto_de(proyecto):
                return self.proyecto_de(proyecto)  # type: ignore[return-value]
            nombres = ", ".join(p.name for p in candidatos or self._proyectos()) or "ninguno"
            return f"Error: ¿que proyecto? {'Varios encajan' if candidatos else 'Hay'}: {nombres}."
        activo = self._estado().get("activo")
        if activo and Path(activo).is_dir():
            return Path(activo)
        return "Error: no se en que proyecto estamos; dime cual."

    # -- proyectos y diario -------------------------------------------------------
    def _proyectos(self) -> list[Path]:
        hallados = []
        for r in self.raices:
            if r.is_dir():
                hallados += [p for p in r.iterdir() if p.is_dir() and not p.name.startswith(".")]
        return sorted(hallados, key=_actividad, reverse=True)

    def crear(self, nombre: str, descripcion: str = "") -> str:
        carpeta = self.raiz / _slug(nombre)
        if carpeta.exists():
            return f"Error: ya existe {carpeta}. Elige otro nombre o trabaja en ese."
        carpeta.mkdir(parents=True)
        titulo = " ".join(nombre.split()) or carpeta.name
        (carpeta / "README.md").write_text(
            f"# {titulo}\n\n{descripcion.strip()}\n", encoding="utf-8"
        )
        if self._git:
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                self._run([self._git, "init", "-q", str(carpeta)], capture_output=True, timeout=30)
        self._guardar_estado(activo=str(carpeta))
        self._anotar(carpeta, f"Proyecto creado. {descripcion.strip()}".strip())
        return f"Creado {carpeta} (con README.md y git). Es el proyecto activo."

    def terminar_orden(self, tarea: str, respuesta: str) -> None:
        """Apunta en el diario de cada proyecto tocado que se pidio y que se hizo."""
        for proyecto, punto in self._tocados.items():
            ficheros = ""
            if punto:
                with contextlib.suppress(OSError, subprocess.SubprocessError, RuntimeError):
                    self._g(proyecto, "add", "-A")
                    ficheros = self._g(proyecto, "diff", "--cached", "--stat", punto).strip()
                    ficheros = ", ".join(
                        x.split("|")[0].strip() for x in ficheros.splitlines()[:-1]
                    )[:300]
            entrada = f"**Pedido:** {recortar(tarea, 200)}\n**Hecho:** {recortar(respuesta, 600)}"
            if ficheros:
                entrada += f"\n**Ficheros:** {ficheros}"
            with contextlib.suppress(OSError):
                self._anotar(proyecto, entrada)

    def _anotar(self, proyecto: Path, entrada: str) -> None:
        diario = proyecto / ".doom" / "diario.md"
        diario.parent.mkdir(parents=True, exist_ok=True)
        if not diario.exists():
            diario.write_text(f"# Diario de {proyecto.name}\n", encoding="utf-8")
        with diario.open("a", encoding="utf-8") as f:
            f.write(f"\n## {datetime.now():%d/%m/%Y %H:%M}\n{entrada}\n")

    @staticmethod
    def ultimas(proyecto: Path, n: int = 3) -> list[str]:
        diario = proyecto / ".doom" / "diario.md"
        if not diario.is_file():
            return []
        bloques = diario.read_text(encoding="utf-8").split("\n## ")[1:]
        return [b.strip() for b in bloques[-n:]]

    def contexto(self) -> str:
        """Lo que el agente sabe del taller en cada orden: los proyectos y en que se estaba."""
        proyectos = self._proyectos()
        lineas = [f"Tu taller ({self.raiz}){'' if proyectos else ': vacio todavia'}."]
        for p in proyectos[:12]:
            ultima = self.ultimas(p, 1)
            cuando = f" · ultima vez {ultima[0].split(chr(10))[0]}" if ultima else ""
            lineas.append(f"- {p.name}: {_descripcion(p)}{cuando}")
        activo = self._estado().get("activo")
        if activo and Path(activo).is_dir():
            ultimas = self.ultimas(Path(activo), 2)
            lineas.append(f"Proyecto activo: {Path(activo).name} ({activo}).")
            if ultimas:
                lineas.append("Lo ultimo de su diario:\n" + "\n".join(f"[{u}]" for u in ultimas))
        return recortar_lineas("\n".join(lineas), 40, 2500)

    # -- estado -------------------------------------------------------------------
    def _fichero_estado(self) -> Path:
        from doombot.paths import data_dir

        return (self._datos or data_dir() / "taller") / "estado.json"

    def _estado(self) -> dict[str, Any]:
        with contextlib.suppress(OSError, ValueError):
            return json.loads(self._fichero_estado().read_text(encoding="utf-8"))
        return {}

    def _guardar_estado(self, **cambios: Any) -> None:
        f = self._fichero_estado()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({**self._estado(), **cambios}, ensure_ascii=False), "utf-8")

    def info(self) -> dict[str, Any]:
        return {
            "raiz": str(self.raiz),
            "autonomo": self.autonomo,
            "proyectos": [p.name for p in self._proyectos()],
            "activo": Path(self._estado().get("activo") or "").name,
        }

    # -- herramientas ---------------------------------------------------------------
    def herramientas(self) -> list[Herramienta]:
        def permiso_proceso(a: dict[str, Any]) -> str | None:
            if str(a.get("accion", "")).lower() != "lanzar":
                return None
            if self.comando_libre(str(a.get("comando", "")), str(a.get("carpeta", ""))):
                return None
            return f"Voy a dejar en marcha en tu equipo: {a.get('comando')}"

        def proceso(accion: str, nombre: str = "", comando: str = "", carpeta: str = "") -> str:
            if str(accion).lower() == "lanzar" and carpeta:
                self.antes_de_tocar(carpeta)
            return self.procesos.herramienta_funcion(accion, nombre, comando, carpeta)

        return [
            Herramienta(
                "crear_proyecto",
                "Crea un proyecto nuevo en el taller (carpeta con README y git) y lo deja "
                "como activo.",
                self.crear,
                {
                    "nombre": texto("Nombre corto, ej. 'juego-naves'."),
                    "descripcion": texto("Que es, en una frase."),
                },
                requeridos=("nombre",),
                narrar=lambda a: f"Creo el proyecto {a.get('nombre')}",
                familia="ficheros",
            ),
            Herramienta(
                "ver_cambios",
                "Que ha cambiado en un proyecto del taller desde el punto de control de esta "
                "orden (o el ultimo).",
                self.cambios,
                {"proyecto": texto("Nombre del proyecto. Vacio: el activo.")},
                narrar=lambda a: f"Miro los cambios de {a.get('proyecto') or 'este proyecto'}",
                familia="ficheros",
            ),
            Herramienta(
                "deshacer_cambios",
                "Devuelve un proyecto del taller al estado de antes de la ultima orden que lo "
                "cambio. Solo si el usuario lo pide.",
                self.deshacer,
                {"proyecto": texto("Nombre del proyecto. Vacio: el activo.")},
                narrar=lambda a: (
                    f"Deshago los últimos cambios de {a.get('proyecto') or 'este proyecto'}"
                ),
                confirmar=lambda a: (
                    f"Voy a devolver {self.destino_deshacer(str(a.get('proyecto', '')))}. "
                    "Lo de ahora queda guardado por si te arrepientes."
                ),
                familia="ficheros",
            ),
            Herramienta(
                "proceso",
                "Procesos que se quedan abiertos (un juego, un servidor): accion=lanzar (con "
                "comando y carpeta), ver (sus ultimas lineas de salida), parar o listar.",
                proceso,
                {
                    "accion": texto("lanzar, ver, parar o listar."),
                    "nombre": texto("Nombre corto para referirse a el, ej. 'juego'."),
                    "comando": texto("Al lanzar: el comando."),
                    "carpeta": texto("Al lanzar: carpeta desde la que se ejecuta."),
                },
                requeridos=("accion",),
                narrar=lambda a: (
                    f"Lanzo {a.get('nombre') or a.get('comando')}"
                    if str(a.get("accion", "")).lower() == "lanzar"
                    else f"{str(a.get('accion', '')).capitalize()} proceso {a.get('nombre', '')}"
                ),
                confirmar=permiso_proceso,
                familia="terminal",
            ),
        ]


def _actividad(p: Path) -> float:
    diario = p / ".doom" / "diario.md"
    with contextlib.suppress(OSError):
        return diario.stat().st_mtime if diario.exists() else p.stat().st_mtime
    return 0.0


def _descripcion(p: Path) -> str:
    readme = p / "README.md"
    with contextlib.suppress(OSError):
        for linea in readme.read_text(encoding="utf-8").splitlines():
            if linea.strip() and not linea.startswith("#"):
                return recortar(linea, 90)
    return "(sin descripcion)"


def recortar_lineas(t: str, max_lineas: int, max_chars: int = 6000) -> str:
    lineas = t.splitlines()
    if len(lineas) > max_lineas:
        lineas = [*lineas[:max_lineas], f"[... {len(lineas) - max_lineas} lineas mas]"]
    salida = "\n".join(lineas)
    return salida if len(salida) <= max_chars else salida[: max_chars - 1] + "…"


def crear_taller(cfg: Any = None) -> Taller:
    """El taller de esta instalacion, de ``DOOMBOT_TALLER`` (por defecto ``~/taller``)."""
    from doombot.config import settings

    cfg = cfg or settings()
    raices = [Path(r) for r in getattr(cfg, "taller", ())] or [RAIZ_POR_DEFECTO]
    return Taller(raices, git=shutil.which("git"))


RAIZ_POR_DEFECTO = Path("~/taller")
