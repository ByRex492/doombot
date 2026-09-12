"""El barge-in (D-027), contra `pyaec` y `webrtcvad` reales.

Sin mockear el AEC ni el VAD: lo que hay que verificar es justo si la
libreria de verdad cancela el eco y detecta voz, no si un doble hace lo que
le hemos dicho que haga. Lo unico sintetico son las senales de entrada -no
hay microfono ni altavoz reales en CI, ni falta que hace para esto: la
pregunta es si el algoritmo funciona, no si el hardware de esta maquina
concreta lo hace bien en una sala con eco de verdad (eso queda para probarlo
con voz real, igual que D-024 con la palabra de activacion)-.
"""

from __future__ import annotations

import numpy as np
import pytest

from doombot.voice.eco import _TASA_KOKORO as TASA_KOKORO
from doombot.voice.eco import (
    BLOQUES_PARA_DISPARAR,
    MUESTRAS_BLOQUE,
    SAMPLE_RATE,
    MonitorBargeIn,
    ReferenciaEco,
    disponible,
)

pytestmark = pytest.mark.skipif(not disponible(), reason="falta pyaec o webrtcvad-wheels")


def _tono(frecuencia: float, segundos: float, amplitud: float = 0.5) -> np.ndarray:
    """A 16 kHz -la tasa del microfono-, para alimentar directamente al monitor."""
    t = np.arange(int(SAMPLE_RATE * segundos)) / SAMPLE_RATE
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


def _tono_kokoro(frecuencia: float, segundos: float, amplitud: float = 0.5) -> np.ndarray:
    """A 24 kHz -la tasa de Kokoro-, para alimentar a ``ReferenciaEco.agregar``."""
    t = np.arange(int(TASA_KOKORO * segundos)) / TASA_KOKORO
    return (amplitud * np.sin(2 * np.pi * frecuencia * t)).astype(np.float32)


# -- ReferenciaEco ------------------------------------------------------------
def test_referencia_vacia_devuelve_ceros():
    ref = ReferenciaEco()
    assert ref.tomar(MUESTRAS_BLOQUE) == [0] * MUESTRAS_BLOQUE


def test_referencia_remuestrea_de_24k_a_16k():
    """0,5 s a 24 kHz (12000 muestras) deben dar ~8000 a 16 kHz, no 12000."""
    ref = ReferenciaEco()
    bloque_24k = _tono_kokoro(300, 0.5)
    assert len(bloque_24k) == 12_000
    ref.agregar(bloque_24k)
    ref.cerrar()  # espera a que el hilo interno termine de procesar

    todo = ref.tomar(SAMPLE_RATE * 2)
    no_ceros = [x for x in todo if x != 0]
    assert 7000 < len(no_ceros) < 8500


def test_vaciar_deja_la_referencia_a_ceros():
    ref = ReferenciaEco()
    ref.agregar(_tono(300, 0.2))
    ref.cerrar()
    ref.vaciar()
    assert ref.tomar(MUESTRAS_BLOQUE) == [0] * MUESTRAS_BLOQUE


# -- MonitorBargeIn ------------------------------------------------------------
def test_no_dispara_con_silencio():
    ref = ReferenciaEco()
    monitor = MonitorBargeIn(ref)
    silencio = np.zeros(MUESTRAS_BLOQUE, dtype=np.float32)
    for _ in range(20):
        assert monitor.procesar(silencio) is False


def test_no_dispara_solo_con_el_propio_eco():
    """El caso que justifica todo esto: la voz de D.O.O.M no debe cortarse sola.

    Por el camino real: la referencia se agrega a 24 kHz via ``agregar()``
    -mismo remuestreo que en produccion-, y lo que llega al "microfono" es esa
    misma senal con un retardo y una atenuacion tipicos de un altavoz a
    camara corta (D-027 midio ~15x de atenuacion del AEC en ese escenario).
    Un eco perfecto, sin retardo ni perdida, no ocurre nunca de verdad: es un
    caso degenerado que confunde al filtro adaptativo mas que ayudarlo, y
    probarlo asi daria una falsa alarma que no reproduce nada real.
    """
    ref = ReferenciaEco()
    monitor = MonitorBargeIn(ref)

    tono_24k = _tono_kokoro(300, 2.0)
    ref.agregar(tono_24k)
    ref.cerrar()

    tono_16k = _tono(300, 2.0)
    retardo = 30  # ~2 ms a 16 kHz, del orden del trayecto altavoz-microfono
    eco_mic = np.zeros_like(tono_16k)
    eco_mic[retardo:] = tono_16k[:-retardo] * 0.6

    n = len(eco_mic)
    posiciones = list(range(0, n - MUESTRAS_BLOQUE, MUESTRAS_BLOQUE))
    mitad = len(posiciones) // 2

    # Los primeros bloques son el filtro adaptandose todavia -no ha visto
    # suficiente senal para converger-, y ahi si puede colarse algun falso
    # disparo. Lo que importa es que deje de pasar una vez converge, en la
    # segunda mitad: se procesa todo en una sola pasada, en orden, para no
    # alterar el estado del filtro con una segunda vuelta sobre lo mismo.
    disparos_tras_convergencia = 0
    for j, i in enumerate(posiciones):
        disparo = monitor.procesar(eco_mic[i : i + MUESTRAS_BLOQUE])
        if disparo and j >= mitad:
            disparos_tras_convergencia += 1
    assert disparos_tras_convergencia == 0


def test_dispara_con_voz_que_no_estaba_en_la_referencia():
    """Sin nada que cancelar, una voz de verdad debe confirmarse tras varios bloques."""
    ref = ReferenciaEco()  # vacia: no hay eco que cancelar
    monitor = MonitorBargeIn(ref)

    # Una mezcla de tonos parecida a una voz, no un seno puro: webrtcvad
    # distingue por espectro y un seno limpio no siempre pasa por "voz".
    t = np.arange(MUESTRAS_BLOQUE) / SAMPLE_RATE
    bloque_voz = (
        0.3 * np.sin(2 * np.pi * 150 * t)
        + 0.2 * np.sin(2 * np.pi * 400 * t)
        + 0.1 * np.sin(2 * np.pi * 900 * t)
    ).astype(np.float32)

    disparado = any(monitor.procesar(bloque_voz) for _ in range(BLOQUES_PARA_DISPARAR + 2))
    assert disparado


def test_exige_varios_bloques_seguidos_no_uno_suelto():
    """Una interrupcion corta la racha: hace falta empezar de cero, no seguir."""
    ref = ReferenciaEco()
    monitor = MonitorBargeIn(ref)
    t = np.arange(MUESTRAS_BLOQUE) / SAMPLE_RATE
    bloque_voz = (0.3 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 400 * t)).astype(
        np.float32
    )
    silencio = np.zeros(MUESTRAS_BLOQUE, dtype=np.float32)

    for _ in range(BLOQUES_PARA_DISPARAR - 1):
        assert monitor.procesar(bloque_voz) is False  # todavia no llega al umbral

    # Una interrupcion larga -de sobra para que se asiente cualquier residuo
    # del AEC de la voz anterior, no solo para cortar la cuenta-.
    for _ in range(10):
        monitor.procesar(silencio)

    # Si la interrupcion no hubiera reiniciado nada, un bloque mas bastaria
    # -ya iba por BLOQUES_PARA_DISPARAR - 1-. Con el reinicio, no.
    assert monitor.procesar(bloque_voz) is False


def test_nueva_respuesta_reinicia_cuenta_y_referencia():
    ref = ReferenciaEco()
    ref.agregar(_tono(300, 0.2))
    ref.cerrar()
    monitor = MonitorBargeIn(ref)
    monitor._seguidos = 2  # noqa: SLF001 - se simula una racha a medias

    monitor.nueva_respuesta()

    assert monitor._seguidos == 0  # noqa: SLF001
    assert ref.tomar(MUESTRAS_BLOQUE) == [0] * MUESTRAS_BLOQUE
