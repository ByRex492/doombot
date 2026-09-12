"""El registro en sí: la ``Sesion``, el decorador y el despachador."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from doombot.actions.claude_code import ClaudeCodeAgent
    from doombot.backends.base import TextGenerator
    from doombot.config import Settings
    from doombot.hud_server import ServidorHUD
    from doombot.memory import Memory
    from doombot.phrases.matcher import Match
    from doombot.profiles import Profile
    from doombot.voice.speaker import Speaker


@dataclass
class Sesion:
    """El estado vivo de una conversación, lo que un manejador puede necesitar.

    Es mutable a propósito: ``ultimo_guardado`` y ``ultima_respuesta`` cambian
    de un turno a otro y varias órdenes los comparten -"olvida eso" necesita
    saber qué guardó "recuerda que"-. Antes eran variables locales del bucle;
    sacarlas aquí es lo que permite que los manejadores vivan fuera de él.
    """

    gen: TextGenerator
    mem: Memory
    cfg: Settings
    perfil: Profile
    agente: ClaudeCodeAgent

    # Cómo responder. Se inyecta en vez de importarse para que un manejador no
    # dependa de que la salida sea una consola: cuando exista la voz, cambia
    # esto y no los manejadores.
    responder: Callable[[str], None]
    con_contexto: Callable[..., str]
    preguntar: Callable[[str], str]

    # La voz y la interfaz son opcionales: D.O.O.M funciona por consola sin
    # ninguna de las dos. Quien las tenga las usa; quien no, las ve a None.
    speaker: Speaker | None = None
    hud: ServidorHUD | None = None

    entrada: str = ""  # lo que se escribió tal cual, sin recortar la orden
    ultimo_guardado: int | None = None
    ultima_respuesta: str = ""

    # Turnos previos con el modelo -no con las órdenes, que se resuelven aquí
    # sin pasar por él- (D-026). Se guarda entero; quien construya el cuerpo
    # de la petición recorta lo que quepa en el contexto del perfil activo.
    historial: list[dict[str, str]] = field(default_factory=list)

    def traza(self, texto: str) -> None:
        """Explicación de por qué hace lo que hace. Va a stderr, no es respuesta."""
        print(f"  · {texto}", file=sys.stderr)

    def aviso(self, texto: str) -> None:
        print(f"  {texto}", file=sys.stderr)

    def decir(self, texto: str) -> None:
        """Una respuesta corta y fija, sin pasar por el modelo.

        Se imprime siempre y, si hay voz, se dice tambien. Hablar no sustituye
        al texto: lo acompana, y asi la consola sigue sirviendo para leer lo
        que se dijo.
        """
        self.ultima_respuesta = texto
        print(f"D.O.O.M> {texto}")
        if self.speaker is not None:
            self.speaker.say(texto)

    def estado(self, nombre: str) -> None:
        """Cambio de estado hacia la interfaz. Sin HUD conectado no cuesta nada."""
        if self.hud is not None:
            self.hud.set_state(nombre)


Handler = Callable[["Sesion", "Match"], None]

_REGISTRO: dict[str, Handler] = {}
_CARGADO = False


def orden(nombre: str) -> Callable[[Handler], Handler]:
    """Decorador que asocia un manejador al nombre de una orden.

    El nombre tiene que coincidir con el de un ``Command`` de
    ``phrases.matcher``; un test lo comprueba, porque registrar un manejador
    para una orden que nadie puede pronunciar es código muerto silencioso.
    """

    def envolver(f: Handler) -> Handler:
        if nombre in _REGISTRO:
            otro = _REGISTRO[nombre]
            raise ValueError(
                f"La orden {nombre!r} ya la maneja {otro.__module__}.{otro.__qualname__}. "
                "Dos capas se la disputan: hay que decidir de quién es."
            )
        _REGISTRO[nombre] = f
        return f

    return envolver


def cargar(*, forzar: bool = False) -> None:
    """Importa el módulo ``orders`` de cada subpaquete de ``doombot``.

    Importar es lo que ejecuta los decoradores y llena el registro. Se hace por
    descubrimiento y no con una lista escrita: una lista sería otro fichero
    común que toda capa nueva tendría que editar, que es justo lo que este
    módulo existe para evitar.
    """
    global _CARGADO
    if _CARGADO and not forzar:
        return

    import doombot

    for info in pkgutil.iter_modules(doombot.__path__):
        if not info.ispkg or info.name == "orders":
            continue
        try:
            importlib.import_module(f"doombot.{info.name}.orders")
        except ModuleNotFoundError as e:
            # Un subpaquete sin ordenes es lo normal (backends, phrases). Pero
            # si el fallo viene de DENTRO de su orders.py, callarlo dejaria la
            # orden sin registrar y sin avisar: se distingue por el nombre.
            if e.name != f"doombot.{info.name}.orders":
                raise
    _CARGADO = True


def registradas() -> dict[str, Handler]:
    """Copia del registro. Para diagnosticar y para los tests."""
    cargar()
    return dict(_REGISTRO)


def despachar(sesion: Sesion, match: Match) -> bool:
    """Atiende la orden si alguien la reclamó. Devuelve si lo hizo.

    Un ``False`` no es un error: significa que la orden está definida pero
    todavía no la implementa nadie -``stop``, ``silence`` y ``speak`` están
    así hasta que exista la voz-. Quien llama decide qué decir en ese caso.
    """
    cargar()
    handler = _REGISTRO.get(match.command)
    if handler is None:
        return False
    sesion.traza(f"orden {match.command} ({match.how}, {match.confidence})")
    handler(sesion, match)
    return True
