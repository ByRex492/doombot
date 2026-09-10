"""Post-procesado ligero de la voz sintetizada.

Dos efectos, ninguno del modelo: van sobre las muestras ya generadas por
Kokoro, con ``scipy`` -que el proyecto ya arrastra por Whisper-, sin anadir
ninguna dependencia nueva.

- ``recorte_graves``: pasa-altos para quitar el "mud" grave de una voz
  sintetica, que suena mas metalica sin el.
- ``reverberacion_sala_pequena``: una cola de reverberacion corta y sutil,
  para que no suene grabada en seco pegada al microfono.

Los dos son deliberadamente discretos. Esto es la voz de un asistente que hay
que entender a la primera, no un efecto de produccion: demasiada reverberacion
o un corte de graves demasiado alto devoran inteligibilidad, que es lo unico
que de verdad importa aqui.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, fftconvolve, sosfiltfilt


def recorte_graves(
    audio: NDArray[np.float32], sample_rate: int, *, corte_hz: float = 150.0, orden: int = 4
) -> NDArray[np.float32]:
    """Pasa-altos de fase cero por debajo de ``corte_hz``.

    150 Hz esta por debajo del fundamental de cualquier voz -incluida una
    grave masculina, que ronda 85-180 Hz- asi que no toca la voz en si, solo
    el zumbido y la resonancia de graves que anaden los altavoces baratos.

    Fase cero (``sosfiltfilt``, filtra dos veces: adelante y atras) para no
    desplazar los transitorios de las consonantes, que es lo que hace que un
    filtro con fase mal cuidada suene "embarrado" en vez de limpio.
    """
    if not len(audio):
        return audio
    sos = butter(orden, corte_hz, btype="highpass", fs=sample_rate, output="sos")
    return sosfiltfilt(sos, audio).astype(np.float32)


def _ir_sala_pequena(sample_rate: int, *, rt60: float, semilla: int = 0) -> NDArray[np.float32]:
    """Respuesta al impulso sintetica: ruido blanco con caida exponencial.

    No es una respuesta de sala real capturada -eso pediria un impulso
    grabado, y el proyecto no tiene ninguno-, pero para una cola de sala
    pequena y discreta el modelo clasico (ruido con envolvente exponencial)
    basta: es lo mismo que hacen los primeros reverbs algoritmicos.

    ``rt60`` es el tiempo hasta que la cola cae 60 dB, el estandar acustico
    para describir "cuanto dura" una reverberacion. Una sala pequena real
    ronda 0,2-0,4 s; una sala de conciertos pasa de 2 s.
    """
    rng = np.random.default_rng(semilla)
    n = int(sample_rate * rt60)
    ruido = rng.standard_normal(n).astype(np.float32)
    # tau tal que exp(-n/tau) = 10**(-60/20) = 0.001 al final de la cola
    tau = n / np.log(1000.0)
    envolvente = np.exp(-np.arange(n) / tau).astype(np.float32)
    ir = ruido * envolvente
    ir /= np.max(np.abs(ir)) + 1e-9
    return ir


def reverberacion_sala_pequena(
    audio: NDArray[np.float32],
    sample_rate: int,
    *,
    rt60: float = 0.3,
    mezcla: float = 0.15,
) -> NDArray[np.float32]:
    """Anade una cola de reverberacion corta, mezclada con la senal seca.

    ``mezcla`` es la proporcion de senal reverberada en el resultado (0 = solo
    seca, 1 = solo reverberada). 0,15 es sutil a proposito: sirve para que no
    suene pegada al microfono sin restar claridad a la voz.
    """
    if not len(audio):
        return audio
    ir = _ir_sala_pequena(sample_rate, rt60=rt60)
    mojada = fftconvolve(audio, ir, mode="full")[: len(audio)]
    pico = np.max(np.abs(mojada)) + 1e-9
    if pico > 1.0:
        mojada = mojada / pico
    return ((1.0 - mezcla) * audio + mezcla * mojada).astype(np.float32)
