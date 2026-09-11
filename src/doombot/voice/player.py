"""Reproduce el audio que devuelve el sintetizador, y se deja interrumpir.

El sintetizador produce ``Audio`` y no sabe nada de altavoces (D-021). Esta es
la otra mitad: una cola de trozos que un hilo de audio va vaciando por el
dispositivo de salida. Separarlo asi es lo que hace posible dos cosas que un
``play()`` bloqueante no da:

- **Cortar a media frase.** ``stop()`` vacia la cola y el siguiente bloque que
  pida la tarjeta sale en silencio. Es el mecanismo del *barge-in*: cuando el
  usuario interrumpa, D.O.O.M se calla en el acto, no al terminar la frase.
- **Medir el nivel mientras suena.** Cada bloque que sale por la tarjeta se
  mide y se avisa. Es lo que anima la interfaz cuando quien habla es D.O.O.M,
  en la misma escala 0-1 que el microfono (``Audio.level()``).

El tamano de bloque es de 30 ms a proposito: ``_ESCALA_NIVEL`` esta medida en
ventanas de 50 ms (D-021) y a esa escala 30 ms da practicamente lo mismo, pero
avisa 33 veces por segundo, dentro de los 30-60 Hz que espera el HUD.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

import numpy as np

from doombot.backends.base import Audio

BLOQUE_MS = 30


class Player:
    """Cola de ``Audio`` que suena en segundo plano por el dispositivo por defecto."""

    def __init__(
        self,
        sample_rate: int,
        *,
        on_level: Callable[[float], None] | None = None,
        on_idle: Callable[[], None] | None = None,
        device: int | str | None = None,
    ) -> None:
        self._sr = sample_rate
        self._on_level = on_level
        self._on_idle = on_idle
        self._device = device
        self._cola: queue.Queue[np.ndarray | None] = queue.Queue()
        self._resto = np.zeros(0, dtype=np.float32)  # lo que sobro del ultimo trozo
        self._sonando = False
        self._stream = None
        self._lock = threading.Lock()

    # -- uso -----------------------------------------------------------------
    def play(self, audio: Audio) -> None:
        """Encola un trozo. Vuelve al instante; suena cuando le toque."""
        if audio.sample_rate != self._sr:
            raise ValueError(f"Audio a {audio.sample_rate} Hz en un reproductor de {self._sr} Hz")
        self._asegurar_stream()
        self._cola.put(np.asarray(audio.samples, dtype=np.float32))

    def stop(self) -> None:
        """Corta ya. Lo que quedaba por sonar se descarta."""
        with self._cola.mutex:
            self._cola.queue.clear()
        with self._lock:
            self._resto = np.zeros(0, dtype=np.float32)
        # El callback vera la cola vacia en el siguiente bloque y sacara
        # silencio: no hace falta tocar el stream, que sigue abierto por si
        # llega mas audio.

    def wait(self, timeout: float | None = None) -> bool:
        """Bloquea hasta que se vacie todo. True si termino, False si expiro."""
        fin = threading.Event()
        self._cola.put(None)  # centinela: cuando el callback lo saque, ya sono todo
        self._centinela = fin
        return fin.wait(timeout)

    @property
    def is_playing(self) -> bool:
        return self._sonando

    def close(self) -> None:
        self.stop()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    # -- interno -------------------------------------------------------------
    def _asegurar_stream(self) -> None:
        if self._stream is not None:
            return
        import sounddevice as sd

        self._centinela: threading.Event | None = None
        self._stream = sd.OutputStream(
            samplerate=self._sr,
            channels=1,
            dtype="float32",
            blocksize=int(self._sr * BLOQUE_MS / 1000),
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, salida: np.ndarray, frames: int, _tiempo, _estado) -> None:
        """Lo llama la tarjeta de sonido cada bloque. No puede bloquear."""
        with self._lock:
            trozo = self._resto
            while len(trozo) < frames:
                try:
                    siguiente = self._cola.get_nowait()
                except queue.Empty:
                    break
                if siguiente is None:  # centinela de wait()
                    if self._centinela is not None:
                        self._centinela.set()
                    continue
                trozo = np.concatenate([trozo, siguiente])
            bloque, self._resto = trozo[:frames], trozo[frames:]

        n = len(bloque)
        salida[:n, 0] = bloque
        salida[n:, 0] = 0.0

        sonando = n > 0
        if sonando != self._sonando:
            self._sonando = sonando
            if not sonando and self._on_idle is not None:
                self._on_idle()
        if self._on_level is not None:
            self._on_level(Audio(bloque, self._sr).level() if sonando else 0.0)
