"""Convierte el chorro de texto del modelo en voz, frase a frase, sin esperar.

Es la pieza que faltaba entre el sintetizador (D-021) y el bucle de
conversacion. El modelo genera tokens; el sintetizador quiere frases; los
altavoces quieren audio continuo. ``Speaker`` hace de puente entre los tres
en paralelo:

    tokens del LLM --> frases completas --> Audio --> Player (cola)

La clave es no esperar a que el modelo termine. Con 46 tok/s, una respuesta de
cien palabras tarda unos tres segundos en generarse: esperarla entera antes de
empezar a hablar son tres segundos de silencio. Trocear por frases y sintetizar
cada una en cuanto se cierra deja el primer sonido a un segundo escaso de
haber empezado a generar, y el resto va saliendo mientras el modelo sigue.

El troceo es incremental a proposito. La funcion ``_frases`` del sintetizador
parte un texto ya completo; aqui el texto llega a pedazos y hay que decidir en
cada pedazo si ya hay una frase cerrada, sin partir "D.O.O.M." por sus puntos.
"""

from __future__ import annotations

import queue
import re
import sys
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from doombot.backends.base import SpeechSynthesizer
from doombot.voice.eco import MonitorBargeIn, ReferenciaEco
from doombot.voice.eco import disponible as eco_disponible
from doombot.voice.player import Player

# Fin de frase: . ! ? o salto de linea, seguidos de espacio o de fin de
# texto. Esa condicion de "seguido de espacio" es la que protege sola las
# siglas: los puntos internos de "D.O.O.M." van pegados a la letra siguiente
# y no cuentan, y el ultimo si cierra la frase, que es lo correcto.
_FIN_FRASE = re.compile(r"[.!?…]+(?=\s|$)|\n+")
# Frases demasiado cortas se acumulan con la siguiente: sintetizar "Sí." solo
# suena entrecortado, y Kokoro tiene un coste fijo por llamada.
_MINIMO = 12


def partir_incremental(pendiente: str, *, cerrar: bool = False) -> tuple[list[str], str]:
    """Saca las frases completas de ``pendiente`` y devuelve lo que queda.

    ``cerrar=True`` fuerza a soltar el resto aunque no termine en puntuacion:
    es lo que se hace cuando el modelo ha dicho la ultima palabra.
    """
    frases: list[str] = []
    while True:
        m = _FIN_FRASE.search(pendiente)
        if m is None:
            break
        frase, pendiente = pendiente[: m.end()].strip(), pendiente[m.end() :]
        if not frase:
            continue
        if frases and len(frases[-1]) < _MINIMO:
            frases[-1] = f"{frases[-1]} {frase}"
        else:
            frases.append(frase)
    # Una frase corta al final se retiene en vez de soltarse: en streaming
    # "Hola." llega antes de saber que detras viene "Que tal estas?", y
    # soltarla sola es justo lo que se queria evitar. Al cerrar ya no hay
    # nada que esperar y sale tal cual.
    if not cerrar and frases and len(frases[-1]) < _MINIMO:
        pendiente = frases.pop() + pendiente
    if cerrar and pendiente.strip():
        frases.append(pendiente.strip())
        pendiente = ""
    return frases, pendiente


class Speaker:
    """Dice en voz alta lo que el modelo va generando."""

    def __init__(
        self,
        synth: SpeechSynthesizer,
        player: Player,
        *,
        on_sentence: Callable[[str], None] | None = None,
        silenciado: Callable[[], bool] = lambda: False,
    ) -> None:
        self._synth = synth
        self._player = player
        self._on_sentence = on_sentence
        self._silenciado = silenciado
        self._cancelar = threading.Event()
        # La sintesis va en su propio hilo. Sin esto, cada frase bloquearia al
        # consumidor del modelo medio segundo y el chorro de tokens se
        # atascaria justo mientras D.O.O.M habla. Con la cola, el modelo sigue
        # generando, Kokoro sintetiza y la tarjeta reproduce, los tres a la vez.
        self._frases: queue.Queue[str | None] = queue.Queue()
        # Cuantas frases hay entre la cola y el hilo. Un solo contador, y no
        # "cola vacia + hilo ocupado": entre sacar de la cola y marcar el hilo
        # como ocupado habia un hueco en el que wait() creia que no quedaba
        # nada. Se incrementa al encolar y se decrementa al terminar cada una.
        self._pendientes = 0
        self._lock = threading.Lock()
        self._hilo = threading.Thread(target=self._sintetizar, name="doom-tts", daemon=True)
        self._hilo.start()

    def speak_stream(
        self, trozos: Iterator[str], *, echo: Callable[[str], None] | None = None
    ) -> str:
        """Consume el chorro del modelo hablando por el camino. Devuelve el texto entero.

        ``echo`` recibe cada trozo tal cual llega, para seguir pintandolo por
        pantalla: hablar no sustituye al texto, lo acompana.
        """
        self._cancelar.clear()
        partes: list[str] = []
        pendiente = ""
        for trozo in trozos:
            if self._cancelar.is_set():
                break
            partes.append(trozo)
            if echo is not None:
                echo(trozo)
            pendiente += trozo
            frases, pendiente = partir_incremental(pendiente)
            for f in frases:
                self._decir(f)
        if not self._cancelar.is_set():
            frases, _ = partir_incremental(pendiente, cerrar=True)
            for f in frases:
                self._decir(f)
        return "".join(partes).strip()

    def say(self, texto: str) -> None:
        """Una frase o parrafo ya completo. Para "repite" y para avisos fijos."""
        self._cancelar.clear()
        frases, _ = partir_incremental(texto, cerrar=True)
        for f in frases:
            if self._cancelar.is_set():
                return
            self._decir(f)

    def stop(self) -> None:
        """Calla ya: deja de sintetizar y vacia lo que quedaba por sonar."""
        self._cancelar.set()
        with self._frases.mutex:
            descartadas = len(self._frases.queue)
            self._frases.queue.clear()
        with self._lock:
            self._pendientes -= descartadas
        self._player.stop()

    @property
    def is_speaking(self) -> bool:
        """True mientras quede algo por sintetizar o sonando de verdad.

        Lo necesita el barge-in (D-027): mientras esto sea True hay que seguir
        escuchando en paralelo, no esperar a ciegas a que termine.
        """
        return self._pendientes > 0 or self._player.is_playing

    def wait(self, timeout: float | None = None) -> bool:
        """Bloquea hasta que todo lo dicho haya sonado.

        Dos esperas encadenadas: que la cola de frases se vacie y el hilo de
        sintesis termine la que tenga entre manos, y despues que el reproductor
        agote su cola. Solo esperar al reproductor dejaria fuera lo que aun no
        se ha sintetizado.
        """
        limite = None if timeout is None else time.monotonic() + timeout
        while self._pendientes > 0:
            if limite is not None and time.monotonic() > limite:
                return False
            time.sleep(0.02)
        return self._player.wait(None if limite is None else max(0.0, limite - time.monotonic()))

    # -- interno -------------------------------------------------------------
    def _decir(self, frase: str) -> None:
        if self._silenciado():
            return
        with self._lock:
            self._pendientes += 1
        self._frases.put(frase)

    def _sintetizar(self) -> None:
        """El hilo de sintesis: saca frases de la cola y encola su audio."""
        while True:
            frase = self._frases.get()
            if frase is None:
                return
            try:
                if self._cancelar.is_set():
                    continue
                if self._on_sentence is not None:
                    self._on_sentence(frase)
                try:
                    audio = self._synth.say(frase)
                except Exception as e:  # noqa: BLE001 - un fallo de sintesis no tumba la conversacion
                    print(f"  (sin voz para esta frase: {e})")
                    continue
                if not self._cancelar.is_set():
                    self._player.play(audio)
            finally:
                with self._lock:
                    self._pendientes -= 1

    def close(self) -> None:
        self.stop()
        self._frases.put(None)
        self._player.close()


@dataclass
class Voz:
    """Lo que monta ``montar_voz``: quien habla y quien vigila que le hablen encima."""

    speaker: Speaker
    barge_in: MonitorBargeIn | None
    """None si falta `pyaec` o `webrtcvad` (D-027): "para" sigue funcionando,
    pero no el corte automatico al hablarle encima."""


def montar_voz(hud: Any | None = None) -> Voz | None:
    """Construye sintetizador + reproductor + Speaker, o None si no se puede.

    Todo opcional a proposito: un equipo sin `voice-tts`, o sin los ficheros
    de Kokoro, conversa por consola exactamente igual. Lo que no se hace es
    descargar 354 MB sin avisar al arrancar el chat: si faltan, se dice donde
    conseguirlos y se sigue sin voz.

    ``hud`` es el transporte hacia la interfaz (``hud_server.ServidorHUD``),
    si esta arrancado: recibe el nivel de audio a ~33 Hz, cada frase como
    subtitulo, y el paso a "dormido" cuando el reproductor se queda callado.
    """
    try:
        from doombot.tts import KokoroSynthesizer
        from doombot.tts.download import modelos_completos
        from doombot.tts.orders import silenciado
    except ImportError:
        return None

    from doombot.paths import models_dir

    carpeta = models_dir() / "kokoro"
    if not modelos_completos(carpeta):
        print(
            "  (sin voz: faltan los modelos de Kokoro en "
            f"{carpeta}; python -m doombot voz los descarga)",
            file=sys.stderr,
        )
        return None
    try:
        synth = KokoroSynthesizer.from_models_dir(carpeta)
    except Exception as e:  # noqa: BLE001 - lo que sea que falle, se sigue sin voz
        print(f"  (sin voz: {e})", file=sys.stderr)
        return None

    def nivel(v: float) -> None:
        if hud is not None:
            hud.set_amplitude(v)

    def callado() -> None:
        if hud is not None:
            hud.set_state("dormido")

    def frase(texto: str) -> None:
        if hud is not None:
            hud.set_caption(texto)

    # La referencia de eco (D-027) se conecta siempre que haya voz: cuesta
    # un hilo ocioso si nadie la usa, y sin ella el barge-in no tiene con que
    # cancelar el eco cuando mas adelante haga falta.
    referencia = ReferenciaEco()
    player = Player(
        synth.sample_rate,
        on_level=nivel,
        on_idle=callado,
        on_reference=referencia.agregar,
    )
    speaker = Speaker(synth, player, on_sentence=frase, silenciado=silenciado)

    barge_in = MonitorBargeIn(referencia) if eco_disponible() else None
    if barge_in is None:
        print(
            "  (barge-in automatico no disponible: instala pyaec y webrtcvad-wheels. "
            '"para" sigue funcionando)',
            file=sys.stderr,
        )
    return Voz(speaker, barge_in)
