"""Barge-in real: interrumpir a D.O.O.M hablandole encima (D-027).

Sin esto, escuchar mientras suena el altavoz haria que D.O.O.M se oyera a si
mismo y se interrumpiera solo -el eco acustico de su propia voz entra por el
microfono igual que la voz real del usuario-. La cancelacion de eco (AEC)
resta del microfono una copia de lo que se envio al altavoz, dejando sobre
todo lo que dice el usuario encima.

Tres piezas, en orden:

- ``ReferenciaEco``: lo que de verdad sono por los altavoces (lo alimenta
  ``Player.on_reference``), remuestreado de los 24 kHz de Kokoro a los 16 kHz
  del microfono y guardado en un anillo corto.
- ``pyaec.Aec``: el filtro adaptativo que resta esa referencia del bloque que
  llega del microfono. Verificado con una senal sintetica antes de conectarlo
  a nada real: ~15x de atenuacion sobre un eco puro (ver D-027).
- ``webrtcvad``: sobre la senal ya sin eco, decide si lo que queda es voz de
  verdad. Varios bloques seguidos, no uno, para no disparar con un carraspeo
  o un resto de eco mal cancelado.

Todo opcional en cadena, como el resto de la voz (D-021, D-024): sin `pyaec`
o `webrtcvad` instalados, el barge-in automatico no existe y "para" sigue
siendo la unica forma de cortar a D.O.O.M.
"""

from __future__ import annotations

import queue
import threading
from collections import deque

import numpy as np

try:
    from pyaec import Aec
except ImportError:  # pragma: no cover - el extra `voice` es opcional
    Aec = None  # type: ignore[assignment, misc]

try:
    import webrtcvad
except ImportError:  # pragma: no cover - el extra `voice` es opcional
    webrtcvad = None  # type: ignore[assignment]

SAMPLE_RATE = 16_000
"""El del microfono (ver voice/capture.py), no el de Kokoro."""

_TASA_KOKORO = 24_000

# webrtcvad solo admite bloques de 10, 20 o 30 ms.
BLOQUE_MS = 20
MUESTRAS_BLOQUE = SAMPLE_RATE * BLOQUE_MS // 1000  # 320

# Bloques de voz seguidos, tras cancelar el eco, para dar el barge-in por
# real. Uno solo dispara con un carraspeo o un resto de eco mal cancelado;
# tres bloques (60 ms) es donde deja de saltar solo, a ojo -medirlo con
# barge-in real, en una sala con eco de verdad, queda pendiente (ver la nota
# de sesion)-.
BLOQUES_PARA_DISPARAR = 3

# Cuanta referencia se conserva. De sobra para el desajuste entre "lo que se
# mando a la tarjeta" y "lo que el microfono oye de vuelta" -decimas de
# segundo como mucho-, sin dejar crecer el anillo sin limite en una respuesta
# larga.
_SEGUNDOS_REFERENCIA = 2.0


def disponible() -> bool:
    """False si falta `pyaec` o `webrtcvad` (extra `voice` incompleto)."""
    return Aec is not None and webrtcvad is not None


class ReferenciaEco:
    """Lo ultimo que sono por los altavoces, ya a la tasa del microfono.

    ``agregar`` la llama el callback de audio de ``Player`` -no puede
    bloquear ni cargarse con nada pesado-, asi que solo encola; el
    remuestreo de verdad ocurre en un hilo propio. ``tomar`` la llama el
    hilo que lee el microfono, a su propio ritmo.
    """

    def __init__(self) -> None:
        self._entrada: queue.Queue[np.ndarray | None] = queue.Queue()
        self._buffer: deque[int] = deque(maxlen=int(SAMPLE_RATE * _SEGUNDOS_REFERENCIA))
        self._lock = threading.Lock()
        self._hilo = threading.Thread(target=self._procesar, name="doom-eco", daemon=True)
        self._hilo.start()

    def agregar(self, bloque: np.ndarray) -> None:
        """``bloque``: float32 a 24 kHz, tal cual lo mando ``Player`` a la tarjeta."""
        if len(bloque):
            self._entrada.put(bloque)

    def tomar(self, n: int) -> list[int]:
        """Los ``n`` enteros mas recientes, int16. Ceros por delante si aun no hay tantos."""
        with self._lock:
            ultimos = list(self._buffer)[-n:]
        if len(ultimos) < n:
            ultimos = [0] * (n - len(ultimos)) + ultimos
        return ultimos

    def vaciar(self) -> None:
        """Al empezar una respuesta nueva: no arrastrar eco de la anterior."""
        with self._lock:
            self._buffer.clear()

    def cerrar(self) -> None:
        self._entrada.put(None)
        self._hilo.join(timeout=1.0)

    def _procesar(self) -> None:
        from scipy.signal import resample_poly

        while True:
            bloque = self._entrada.get()
            if bloque is None:
                return
            remuestreado = resample_poly(bloque, SAMPLE_RATE, _TASA_KOKORO)
            enteros = np.clip(remuestreado * 32767, -32768, 32767).astype(np.int16)
            with self._lock:
                self._buffer.extend(enteros.tolist())


class MonitorBargeIn:
    """Decide si lo que llega al microfono, ya sin eco, es voz de verdad."""

    def __init__(self, referencia: ReferenciaEco, *, agresividad: int = 2) -> None:
        if not disponible():
            raise RuntimeError("Falta pyaec o webrtcvad: comprobar con eco.disponible() antes")
        self._referencia = referencia
        self._aec = Aec(
            frame_size=MUESTRAS_BLOQUE,
            filter_length=2048,
            sample_rate=SAMPLE_RATE,
            enable_preprocess=True,
        )
        self._vad = webrtcvad.Vad(agresividad)
        self._seguidos = 0

    def nueva_respuesta(self) -> None:
        """Antes de cada turno hablado: ni cuenta ni eco del anterior.

        Sin vaciar la referencia, los primeros bloques del turno nuevo se
        comparan contra el final del audio ya sonado -que ``tomar()`` seguiria
        devolviendo por no haber nada mas reciente- y el filtro arranca
        cancelando la senal equivocada.
        """
        self._seguidos = 0
        self._referencia.vaciar()

    def procesar(self, bloque_mic: np.ndarray) -> bool:
        """``bloque_mic``: float32 a 16 kHz, ``MUESTRAS_BLOQUE`` muestras.

        True la primera vez que confirma voz real, tras varios bloques
        seguidos -y en los siguientes, mientras la voz continue-, para que
        quien llama decida que hacer con eso una sola vez.
        """
        rec = np.clip(bloque_mic * 32767, -32768, 32767).astype(np.int16).tolist()
        eco = self._referencia.tomar(len(rec))
        limpio = self._aec.cancel_echo(rec, eco)

        pcm = np.array(limpio, dtype=np.int16).tobytes()
        es_voz = self._vad.is_speech(pcm, SAMPLE_RATE)

        self._seguidos = self._seguidos + 1 if es_voz else 0
        return self._seguidos >= BLOQUES_PARA_DISPARAR
