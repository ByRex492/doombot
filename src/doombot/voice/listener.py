"""El bucle de escucha: une lo que hasta ahora estaba suelto.

El microfono grababa y Whisper transcribia, pero nadie los conectaba. Aqui esta
la maquina de estados que convierte las dos piezas en un asistente que se puede
gobernar hablando:

    DORMIDO --palabra de activacion--> ESCUCHANDO --silencio--> TRANSCRIBIENDO
       ^                                                              |
       +--------------------------------------------------------------+

Dos decisiones que conviene entender:

**El bucle no decide que hacer con el texto.** Devuelve lo transcrito y vuelve a
dormir. Quien llama decide si es una orden, una pregunta o ruido. Asi la capa de
voz no depende del cerebro y se puede probar sin el.

**Los cambios de estado se emiten, no se imprimen.** Es lo que consumira el HUD
de la Capa 5, junto al chorro de amplitud: la interfaz solo escucha y anima. Sin
esa separacion, rehacer la interfaz obligaria a tocar el audio.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from doombot.voice.capture import BLOQUE_MS, BLOQUE_SEGUNDOS, Microphone
from doombot.voice.wake import Detection, WakeWord

if TYPE_CHECKING:
    from collections.abc import Callable

    from doombot.backends.base import Transcriber
    from doombot.voice.wake import WakeDetector


class State(StrEnum):
    """Los estados que atraviesa una interaccion."""

    DORMIDO = "dormido"
    ESCUCHANDO = "escuchando"
    TRANSCRIBIENDO = "transcribiendo"
    ERROR = "error"


@dataclass(frozen=True)
class Heard:
    """Lo que se oyo en una interaccion completa."""

    text: str
    detection: Detection
    seconds: float
    peak: float

    @property
    def vacio(self) -> bool:
        return not self.text.strip()


class Listener:
    """Escucha en segundo plano y entrega lo que se dice tras la activacion."""

    def __init__(
        self,
        microphone: Microphone,
        transcriber: Transcriber,
        detector: WakeDetector | None = None,
        *,
        on_state: Callable[[State], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        silence_ms: int = 1_200,
        max_ms: int = 30_000,
        wait_ms: int = 10_000,
    ) -> None:
        self._mic = microphone
        self._stt = transcriber
        self._detector = detector if detector is not None else WakeWord()
        self._on_state = on_state
        self._on_level = on_level
        self._silence_ms = silence_ms
        self._max_ms = max_ms
        self._wait_ms = wait_ms
        self._state = State.DORMIDO
        # Para apagar la escucha desde otro hilo (la ventana, D-046): se mira en
        # cada bloque mientras se espera la activacion, y listen() termina.
        self.parar = threading.Event()

    @property
    def state(self) -> State:
        return self._state

    def _cambiar(self, estado: State) -> None:
        self._state = estado
        if self._on_state is not None:
            self._on_state(estado)

    # -- el bucle ------------------------------------------------------------
    def listen(self, *, veces: int | None = None, espera_ms: int | None = None) -> Iterator[Heard]:
        """Escucha indefinidamente, entregando cada interaccion completa.

        ``veces`` limita cuantas interacciones se atienden antes de terminar.
        Sin el, el bucle no acaba nunca: es lo que se quiere en uso real.

        ``espera_ms`` acota cuanto se aguarda una activacion que no llega. Por
        defecto no hay limite —un asistente espera lo que haga falta—, pero sin
        esa salida un detector que nunca dispara cuelga el proceso, que es
        exactamente lo que hace un push-to-talk que nadie pulsa.
        """
        atendidas = 0
        while (veces is None or atendidas < veces) and not self.parar.is_set():
            deteccion = self._esperar_activacion(espera_ms)
            if deteccion is None:
                return
            oido = self._atender(deteccion)
            if oido is not None:
                yield oido
            atendidas += 1

    def _esperar_activacion(self, espera_ms: int | None = None) -> Detection | None:
        """Bloquea hasta oir la palabra de activacion.

        Aqui es donde D.O.O.M pasa la mayor parte del tiempo, y por eso solo
        corre el detector barato: Whisper no se toca hasta que hay activacion.
        """
        self._cambiar(State.DORMIDO)
        bloque = int(self._mic.samplerate * BLOQUE_SEGUNDOS)
        tope = None if espera_ms is None else max(1, espera_ms // BLOQUE_MS)
        leidos = 0
        try:
            with self._mic.abrir_flujo(bloque) as flujo:
                while (tope is None or leidos < tope) and not self.parar.is_set():
                    leidos += 1
                    datos, _ = flujo.read(bloque)
                    muestras = _a_int16(datos)
                    if self._on_level is not None:
                        self._on_level(_nivel(datos))
                    deteccion = self._detector.check(muestras)
                    if deteccion is not None:
                        self._detector.reset()
                        return deteccion
        except KeyboardInterrupt:
            return None
        return None

    def _atender(self, deteccion: Detection) -> Heard | None:
        """Graba hasta el silencio y transcribe."""
        self._cambiar(State.ESCUCHANDO)
        grabacion = self._mic.record_until_silence(
            max_ms=self._max_ms,
            silence_ms=self._silence_ms,
            wait_ms=self._wait_ms,
            on_level=self._on_level,
        )
        with grabacion:
            if grabacion.parece_mudo:
                # No es un error: alguien dijo la palabra y luego no hablo.
                # Volver a dormir es mas util que devolver una cadena vacia.
                return None
            self._cambiar(State.TRANSCRIBIENDO)
            texto = self._stt.transcribe(grabacion.path)
            return Heard(
                text=texto,
                detection=deteccion,
                seconds=grabacion.duration,
                peak=grabacion.peak,
            )


def _a_int16(datos: Any) -> Any:
    """De float32 en [-1, 1] a int16, que es lo que espera openWakeWord."""
    import numpy as np

    muestras = np.asarray(datos, dtype=np.float32).reshape(-1)
    return (np.clip(muestras, -1.0, 1.0) * 32767).astype(np.int16)


def _nivel(datos: Any) -> float:
    """Nivel RMS del bloque, para alimentar la animacion de la interfaz."""
    import numpy as np

    muestras = np.asarray(datos, dtype=np.float32).reshape(-1)
    if not muestras.size:
        return 0.0
    return min(1.0, float(np.sqrt(np.mean(muestras**2))) * 4.0)
