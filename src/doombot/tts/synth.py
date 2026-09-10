"""Sintetizador de voz sobre Kokoro (kokoro-onnx), cumpliendo ``SpeechSynthesizer``.

No hereda de ``backends.base.SpeechSynthesizer``: es un ``Protocol``, y le basta
con tener ``say``, ``stream``, ``voice_name`` y ``sample_rate``. Ver D-021 en
docs/decisiones.md para el porque de kokoro-onnx frente al paquete ``kokoro``
(PyTorch), y las medidas que respaldan la eleccion de modelo, voces y ritmo.
"""

from __future__ import annotations

import queue
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from kokoro_onnx import Kokoro

from doombot.tts.dsp import recorte_graves, reverberacion_sala_pequena

if TYPE_CHECKING:
    from doombot.backends.base import Audio

# Fichero de modelo elegido tras medir en esta maquina (ver D-021): fp32, no
# las variantes cuantizadas. fp16 e int8 pesan menos en disco pero en CPU van
# MAS LENTAS que fp32 -el hardware no acelera fp16 de forma nativa, y el int8
# cae en kernels de referencia sin optimizar-, asi que aqui "mas pequeno" no
# significa "mas rapido". Contraintuitivo, y por eso queda medido y no supuesto.
MODELO_ONNX = "kokoro-v1.0.onnx"
VOCES_BIN = "voices-v1.0.bin"

# Un idioma, una voz por defecto. El espanol solo tiene tres voces en el
# catalogo de Kokoro (bastantes menos que el ingles, D-005 lo daba por
# esperado): ef_dora es la unica femenina y la que mejor sono en la prueba de
# oido. em_alex queda como alternativa masculina.
VOZ_ES = "ef_dora"
VOZ_EN = "af_heart"

# Cadencia: mas lenta que el 1.0 por defecto, pedida explicitamente para que
# la voz no atropelle las frases. 0.85 es un 15% mas lento sin sonar
# arrastrado -ver la nota de oido en D-021 para el rango probado-.
VELOCIDAD = 0.85

# Pausas mas largas que las de fabrica (0.25 / 0.10) para la cadencia pedida:
# limpias entre frases, breves entre clausulas.
PAUSA_FRASE = 0.4
PAUSA_CLAUSULA = 0.15

# Heuristica de idioma, no una libreria de deteccion. El contrato
# ``SpeechSynthesizer.say(texto)`` no lleva parametro de idioma -lo decide
# quien sintetiza, no quien llama-, y anadir una dependencia de deteccion de
# idioma para dos idiomas fijos es mas peso del que pesa el problema.
#
# Dos senales, en orden: tildes/ñ/signos de apertura son espanol inequivoco;
# si no aparece ninguna, se cuenta que fraccion de las palabras son de una
# lista de funcionales del ingles ("the", "is", "you"...) que casi nunca
# aparecen en espanol. Por debajo del umbral gana el espanol, que D-005 fija
# como idioma por defecto de las respuestas de D.O.O.M.
_SENAL_ES = re.compile(r"[ñáéíóúÑÁÉÍÓÚ¿¡]")
_PALABRAS_EN = frozenset([
    "the", "is", "are", "you", "and", "to", "of", "in", "it", "that", "this",
    "with", "for", "on", "have", "has", "was", "were", "what", "how", "can",
    "your", "not", "do", "does", "will", "would", "could", "i", "we", "they",
    "he", "she",
])  # fmt: skip
_UMBRAL_EN = 0.25


def _idioma(texto: str) -> tuple[str, str]:
    """(codigo de idioma para el phonemizer, voz por defecto)."""
    if _SENAL_ES.search(texto):
        return "es", VOZ_ES
    palabras = re.findall(r"[a-zA-Z']+", texto.lower())
    if palabras:
        proporcion_en = sum(1 for p in palabras if p in _PALABRAS_EN) / len(palabras)
        if proporcion_en >= _UMBRAL_EN:
            return "en-us", VOZ_EN
    return "es", VOZ_ES


class KokoroSynthesizer:
    """Convierte texto en voz con Kokoro, bilingue es/en.

    Devuelve muestras (``Audio``), nunca reproduce ni escribe a disco: eso es
    de la capa de voz, no de esto (ver el contrato en backends/base.py).
    """

    def __init__(
        self,
        kokoro: Kokoro,
        *,
        voz_es: str = VOZ_ES,
        voz_en: str = VOZ_EN,
        velocidad: float = VELOCIDAD,
        pausa_frase: float = PAUSA_FRASE,
        pausa_clausula: float = PAUSA_CLAUSULA,
        graves_hz: float = 150.0,
        reverberacion: float = 0.15,
    ) -> None:
        self._kokoro = kokoro
        self._voz_es = voz_es
        self._voz_en = voz_en
        self._velocidad = velocidad
        self._pausa_frase = pausa_frase
        self._pausa_clausula = pausa_clausula
        self._graves_hz = graves_hz
        self._reverberacion = reverberacion
        self._ultima_voz = voz_es

    @classmethod
    def from_models_dir(cls, carpeta: Path, **kwargs: object) -> KokoroSynthesizer:
        """Construye cargando ``MODELO_ONNX`` y ``VOCES_BIN`` de ``carpeta``.

        ``carpeta`` es ``paths.models_dir() / "kokoro"``; se pasa ya resuelta
        en vez de leerla aqui para no importar ``paths`` en un modulo que solo
        necesita saber donde estan dos ficheros.

        Fuerza ``CPUExecutionProvider`` en vez de dejar que kokoro-onnx
        pruebe TensorRT y CUDA primero (D-021: sin pip real para CUDA 13/
        Blackwell todavia, los dos fallan y ensucian el arranque con un
        "EP Error" que parece un fallo y no lo es, antes de caer solo en
        CPU). Medido en esta maquina, CPU ya va comodamente por debajo de
        tiempo real -no hace falta la GPU, que ademas libera para el LLM.
        """
        import onnxruntime as rt

        sesion = rt.InferenceSession(str(carpeta / MODELO_ONNX), providers=["CPUExecutionProvider"])
        kokoro = Kokoro.from_session(sesion, str(carpeta / VOCES_BIN))
        return cls(kokoro, **kwargs)

    # -- el contrato -----------------------------------------------------
    def say(self, texto: str) -> Audio:
        from doombot.backends.base import Audio as AudioReal

        lang, voz = _idioma(texto)
        self._ultima_voz = voz
        muestras, sr = self._kokoro.create(
            texto,
            voice=voz,
            speed=self._velocidad,
            lang=lang,
            sentence_pause=self._pausa_frase,
            clause_pause=self._pausa_clausula,
        )
        muestras = self._procesar(muestras, sr)
        return AudioReal(samples=muestras, sample_rate=sr)

    def stream(self, texto: str) -> Iterator[Audio]:
        """Un trozo de audio por frase, sintetizando la siguiente por delante.

        El troceo de ``kokoro-onnx`` es por lote de fonemas (hasta 510), no
        por frase: medido en esta maquina, un parrafo tipico de D.O.O.M. de
        tres o cuatro frases cabe entero en un solo lote y ``create_stream``
        no devuelve nada hasta tenerlo todo -el mismo tiempo que ``say``, sin
        ningun beneficio-. Iterar aqui frase a frase es lo que de verdad
        adelanta el primer sonido, que es el proposito del contrato.
        """
        from doombot.backends.base import Audio as AudioReal

        lang, voz = _idioma(texto)
        self._ultima_voz = voz

        def _sintetizar(frase: str) -> tuple[np.ndarray, int]:
            return self._kokoro.create(
                frase,
                voice=voz,
                speed=self._velocidad,
                lang=lang,
                sentence_pause=self._pausa_frase,
                clause_pause=self._pausa_clausula,
            )

        for muestras, sr in _pipeline_por_frase(_frases(texto), _sintetizar):
            yield AudioReal(samples=self._procesar(muestras, sr), sample_rate=sr)

    @property
    def voice_name(self) -> str:
        return self._ultima_voz

    @property
    def sample_rate(self) -> int:
        from kokoro_onnx.config import SAMPLE_RATE

        return SAMPLE_RATE

    # -- interno -----------------------------------------------------------
    def _procesar(self, muestras: np.ndarray, sr: int) -> np.ndarray:
        muestras = recorte_graves(muestras, sr, corte_hz=self._graves_hz)
        if self._reverberacion:
            muestras = reverberacion_sala_pequena(muestras, sr, mezcla=self._reverberacion)
        return muestras

    def __repr__(self) -> str:
        return f"KokoroSynthesizer(voz_es={self._voz_es!r}, voz_en={self._voz_en!r})"


# Fin de frase: puntuacion de cierre seguida de espacio. Exige el espacio a
# proposito -y no solo el signo- para no trocear "D.O.O.M. Estoy..." por cada
# punto interno de la sigla: esos no llevan espacio detras, el que SI cierra
# la frase si.
_FIN_FRASE = re.compile(r"(?<=[.!?…])\s+")


def _frases(texto: str) -> list[str]:
    """El texto partido en frases; el propio ``texto`` si no se pudo partir."""
    partes = [p.strip() for p in _FIN_FRASE.split(texto.strip()) if p.strip()]
    return partes or ([texto] if texto.strip() else [])


def _pipeline_por_frase(frases: list[str], sintetizar):
    """Sintetiza la frase siguiente en un hilo mientras se entrega la actual.

    Cola de tamano 1: un hueco para lo que se esta entregando, uno para lo
    que se sintetiza por delante -el mismo equilibrio que usa
    ``kokoro.create_stream`` para su propio troceo por lotes-. Sin esto, cada
    frase esperaria a que quien consume el generador pida la siguiente para
    empezar a calcularla, y el streaming no ganaria nada frente a ``say``.
    """
    cola: queue.Queue = queue.Queue(maxsize=1)
    FIN = object()

    def _correr() -> None:
        try:
            for frase in frases:
                cola.put(sintetizar(frase))
        except Exception as e:  # noqa: BLE001 - se reenvia al hilo que llama
            cola.put(e)
        finally:
            cola.put(FIN)

    hilo = threading.Thread(target=_correr, daemon=True)
    hilo.start()
    while True:
        item = cola.get()
        if item is FIN:
            return
        if isinstance(item, Exception):
            raise item
        yield item
