"""Procesos que se quedan en marcha: el juego que se prueba, el servidor de desarrollo (D-045).

``ejecutar_comando`` espera a que el comando acabe, y un juego o un servidor
no acaban: se cortarian a los dos minutos sin que el agente viera nada. Aqui
se lanzan aparte, su salida se va guardando (las ultimas lineas) y el agente
la lee cuando quiere: "lanza el juego, juega tu un poco, mira los errores".

Todos mueren al cerrar D.O.O.M: un servidor huerfano ocupando un puerto es
justo el tipo de sorpresa que no se quiere.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MAX_PROCESOS = 6
_LINEAS = 400
_ESPERA_ARRANQUE = 2.0


@dataclass
class _Proceso:
    nombre: str
    comando: str
    carpeta: str
    popen: subprocess.Popen
    lineas: deque[str] = field(default_factory=lambda: deque(maxlen=_LINEAS))
    inicio: float = field(default_factory=time.monotonic)

    @property
    def vivo(self) -> bool:
        return self.popen.poll() is None

    def estado(self) -> str:
        if self.vivo:
            return f"en marcha desde hace {time.monotonic() - self.inicio:.0f}s"
        return f"terminado con codigo {self.popen.returncode}"


class Procesos:
    """Los procesos lanzados en esta sesion, por nombre."""

    def __init__(self, *, popen: Callable[..., Any] = subprocess.Popen) -> None:
        self._popen = popen
        self._procesos: dict[str, _Proceso] = {}
        self._lock = threading.Lock()

    def lanzar(self, nombre: str, comando: str, carpeta: str = "") -> str:
        if not comando.strip():
            return "Error: falta el comando."
        nombre = (nombre or comando.split()[0]).strip()[:40]
        with self._lock:
            previo = self._procesos.get(nombre)
            if previo is not None and previo.vivo:
                return f"Error: ya hay un proceso «{nombre}» en marcha; paralo o usa otro nombre."
            if sum(p.vivo for p in self._procesos.values()) >= _MAX_PROCESOS:
                return f"Error: ya hay {_MAX_PROCESOS} procesos en marcha; para alguno antes."
        cwd = str(Path(os.path.expandvars(carpeta)).expanduser()) if carpeta else None
        opciones: dict[str, Any] = {}
        if sys.platform == "win32":
            opciones["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            opciones["start_new_session"] = True  # para matar a sus hijos con el
        try:
            p = self._popen(
                comando,
                shell=True,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **opciones,
            )
        except OSError as e:
            return f"Error: no se pudo lanzar: {e}"
        proceso = _Proceso(nombre, comando, carpeta, p)
        with self._lock:
            self._procesos[nombre] = proceso
        threading.Thread(target=self._leer, args=(proceso,), daemon=True).start()
        # Lo que sale en los primeros segundos suele ser lo importante: el
        # puerto del servidor, o el error que lo tumba nada mas arrancar.
        fin = time.monotonic() + _ESPERA_ARRANQUE
        while time.monotonic() < fin and proceso.vivo:
            time.sleep(0.1)
        return f"Lanzado «{nombre}» ({proceso.estado()}).\n" + self._cola(proceso, 30)

    def ver(self, nombre: str, lineas: int = 60) -> str:
        proceso = self._procesos.get((nombre or "").strip())
        if proceso is None:
            return f"Error: no hay ningun proceso «{nombre}». Hay: {self._nombres()}."
        return f"«{proceso.nombre}» {proceso.estado()}.\n" + self._cola(proceso, lineas)

    def parar(self, nombre: str) -> str:
        proceso = self._procesos.get((nombre or "").strip())
        if proceso is None:
            return f"Error: no hay ningun proceso «{nombre}». Hay: {self._nombres()}."
        if proceso.vivo:
            _matar(proceso.popen)
        return f"Parado «{proceso.nombre}»."

    def listar(self) -> str:
        if not self._procesos:
            return "No hay procesos lanzados en esta sesion."
        return "\n".join(
            f"- {p.nombre}: {p.estado()} · {p.comando}" for p in self._procesos.values()
        )

    def cerrar(self) -> None:
        for p in list(self._procesos.values()):
            if p.vivo:
                with contextlib.suppress(Exception):
                    _matar(p.popen)

    def herramienta_funcion(
        self, accion: str, nombre: str = "", comando: str = "", carpeta: str = ""
    ) -> str:
        accion = (accion or "").strip().lower()
        if accion == "lanzar":
            return self.lanzar(nombre, comando, carpeta)
        if accion == "ver":
            return self.ver(nombre)
        if accion == "parar":
            return self.parar(nombre)
        if accion == "listar":
            return self.listar()
        return "Error: accion debe ser lanzar, ver, parar o listar."

    # -- interno --------------------------------------------------------------
    def _nombres(self) -> str:
        return ", ".join(self._procesos) or "ninguno"

    @staticmethod
    def _cola(proceso: _Proceso, n: int) -> str:
        ultimas = list(proceso.lineas)[-n:]
        return "\n".join(ultimas) if ultimas else "(sin salida todavia)"

    @staticmethod
    def _leer(proceso: _Proceso) -> None:
        salida = proceso.popen.stdout
        if salida is None:
            return
        with contextlib.suppress(Exception):
            for linea in salida:
                proceso.lineas.append(linea.rstrip("\n"))


def _matar(popen: Any) -> None:
    """Termina el proceso y sus hijos: un ``npm run dev`` deja otro node debajo."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(popen.pid)],
            capture_output=True,
            check=False,
        )
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(popen.pid, signal.SIGTERM)
    try:
        popen.wait(timeout=3)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(popen.pid, signal.SIGKILL)
