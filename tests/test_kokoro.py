"""El sintetizador Kokoro, probado sin el modelo real donde se puede.

Mismo truco que con Whisper y Ollama: ``KokoroSynthesizer`` recibe el objeto
``Kokoro`` ya construido, asi que se le pasa un doble. Sin esa costura, probar
cuatro lineas de logica de idioma o de troceo por frase costaria cargar 326 MB
de modelo en cada test.
"""

from __future__ import annotations

import numpy as np
import pytest

# synth.py importa kokoro_onnx (y dsp.py, scipy) al cargarse: sin el extra
# voice-tts no hay nada que probar aqui, y el resto de la suite sigue.
pytest.importorskip("kokoro_onnx")
pytest.importorskip("scipy")

from doombot.backends.base import SpeechSynthesizer  # noqa: E402
from doombot.tts.dsp import recorte_graves, reverberacion_sala_pequena  # noqa: E402
from doombot.tts.synth import VOZ_EN, KokoroSynthesizer, _frases, _idioma  # noqa: E402


class KokoroFalso:
    """Imita lo justo de ``kokoro_onnx.Kokoro`` que usa el sintetizador."""

    def __init__(self) -> None:
        self.llamadas: list[dict] = []

    def create(self, texto, *, voice, speed, lang, sentence_pause, clause_pause):
        self.llamadas.append(
            {
                "texto": texto,
                "voice": voice,
                "speed": speed,
                "lang": lang,
                "sentence_pause": sentence_pause,
                "clause_pause": clause_pause,
            }
        )
        # Medio segundo de silencio a 24 kHz: no hace falta audio de verdad
        # para probar el troceo, el idioma o el contrato.
        return np.zeros(12000, dtype=np.float32), 24000


# -- el contrato ---------------------------------------------------------
def test_cumple_el_contrato():
    assert isinstance(KokoroSynthesizer(KokoroFalso()), SpeechSynthesizer)


def test_say_devuelve_audio_con_la_frecuencia_de_kokoro():
    voz = KokoroSynthesizer(KokoroFalso())
    audio = voz.say("Hola, soy D.O.O.M.")
    assert audio.sample_rate == 24000
    assert len(audio.samples) > 0


# -- deteccion de idioma ---------------------------------------------------
@pytest.mark.parametrize(
    "texto",
    [
        "¿Qué hora es?",
        "El ratón está en la habitación pequeña",
        "Mañana empiezo con la capa de acciones",
    ],
)
def test_detecta_espanol_por_tildes_y_signos(texto):
    assert _idioma(texto)[0] == "es"


@pytest.mark.parametrize(
    "texto",
    [
        "What time is it now",
        "I have not seen this file before, can you check it",
        "This is a test of the English voice for D.O.O.M.",
    ],
)
def test_detecta_ingles_sin_senales_de_espanol(texto):
    assert _idioma(texto)[0] == "en-us"


def test_ante_la_duda_gana_el_espanol():
    """D-005 fija espanol como idioma por defecto de las respuestas."""
    assert _idioma("Doom")[0] == "es"
    assert _idioma("")[0] == "es"


def test_la_kokoro_falsa_recibe_el_idioma_y_la_voz_detectados():
    kokoro = KokoroFalso()
    KokoroSynthesizer(kokoro).say("What is the weather like today")
    assert kokoro.llamadas[0]["lang"] == "en-us"
    assert kokoro.llamadas[0]["voice"] == VOZ_EN


# -- troceo por frase para streaming ---------------------------------------
def test_frases_parte_en_los_puntos_que_cierran():
    assert _frases("Hola. ¿Qué tal? Bien.") == ["Hola.", "¿Qué tal?", "Bien."]


def test_frases_no_parte_una_sigla_con_puntos_internos():
    """'D.O.O.M.' no debe romperse en cuatro frases de una letra."""
    partes = _frases("Hola, soy D.O.O.M. Estoy midiendo la latencia.")
    assert partes == ["Hola, soy D.O.O.M.", "Estoy midiendo la latencia."]


def test_frases_con_texto_vacio_no_devuelve_nada():
    assert _frases("") == []


def test_frases_sin_puntuacion_final_devuelve_el_texto_entero():
    assert _frases("una frase sin punto final") == ["una frase sin punto final"]


def test_stream_hace_una_llamada_por_frase():
    kokoro = KokoroFalso()
    voz = KokoroSynthesizer(kokoro)
    trozos = list(voz.stream("Hola. Esto tiene dos frases."))
    assert len(trozos) == 2
    assert len(kokoro.llamadas) == 2
    assert kokoro.llamadas[0]["texto"] == "Hola."
    assert kokoro.llamadas[1]["texto"] == "Esto tiene dos frases."


def test_stream_con_una_sola_frase_da_un_solo_trozo():
    voz = KokoroSynthesizer(KokoroFalso())
    assert len(list(voz.stream("Una unica frase."))) == 1


# -- DSP: recorte de graves y reverberacion ---------------------------------
def test_recorte_de_graves_no_cambia_la_longitud():
    audio = np.random.default_rng(0).standard_normal(2400).astype(np.float32)
    assert len(recorte_graves(audio, 24000)) == len(audio)


def test_recorte_de_graves_con_silencio_no_falla():
    assert len(recorte_graves(np.zeros(0, dtype=np.float32), 24000)) == 0


def test_recorte_de_graves_atenua_un_tono_grave():
    """Un tono de 60 Hz -por debajo del corte- debe perder energia."""
    sr = 24000
    t = np.arange(sr) / sr
    tono_grave = np.sin(2 * np.pi * 60 * t).astype(np.float32)
    filtrado = recorte_graves(tono_grave, sr, corte_hz=150.0)
    assert np.sqrt(np.mean(filtrado**2)) < 0.1 * np.sqrt(np.mean(tono_grave**2))


def test_reverberacion_no_satura_por_encima_de_uno():
    audio = np.ones(4800, dtype=np.float32)
    mojado = reverberacion_sala_pequena(audio, 24000, mezcla=0.5)
    assert np.max(np.abs(mojado)) <= 1.0 + 1e-6


def test_reverberacion_con_mezcla_cero_deja_el_audio_casi_igual():
    audio = np.random.default_rng(1).standard_normal(2400).astype(np.float32)
    # mezcla=0 evita del todo la cola: solo queda la senal seca.
    igual = reverberacion_sala_pequena(audio, 24000, mezcla=0.0)
    assert np.allclose(igual, audio, atol=1e-6)


# -- contra Kokoro de verdad --------------------------------------------------
@pytest.mark.hardware
def test_sintesis_real_es_y_en():
    """Genera audio real con los ficheros de modelo descargados en esta maquina."""
    pytest.importorskip("kokoro_onnx")
    from doombot.paths import models_dir

    carpeta = models_dir() / "kokoro"
    if not (carpeta / "kokoro-v1.0.onnx").is_file():
        pytest.skip("modelo de Kokoro no descargado en esta maquina")

    voz = KokoroSynthesizer.from_models_dir(carpeta)
    audio_es = voz.say("Hola, soy D.O.O.M., tu asistente de voz local.")
    audio_en = voz.say("Hello, I am D.O.O.M., your local voice assistant.")

    assert audio_es.duration > 0
    assert audio_en.duration > 0
    assert voz.sample_rate == 24000
