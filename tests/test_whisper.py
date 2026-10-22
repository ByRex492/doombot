"""El transcriptor, probado sin faster-whisper ni modelos descargados.

Mismo truco que con Ollama: la clase acepta un cargador por parametro, asi
que se le pasa uno falso. Sin esa costura habria que descargar cientos de MB
y tener el stack de audio instalado para probar cuatro lineas de logica.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from doombot.backends.base import BackendError, Transcriber
from doombot.backends.whisper import Transcription, WhisperTranscriber
from doombot.profiles import Profile


def test_faster_whisper_lee_un_wav_con_el_pyav_instalado(tmp_path):
    """faster-whisper y PyAV, de verdad: una version de PyAV que no casa rompe toda transcripcion.

    Pasaba con PyAV 19 y faster-whisper 1.2.1 (TypeError en av.open). Sin modelo ni GPU: solo
    leer el audio, que es donde fallaba.
    """
    audio = pytest.importorskip("faster_whisper.audio")
    import wave

    ruta = tmp_path / "silencio.wav"
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 8000)  # medio segundo
    muestras = audio.decode_audio(str(ruta), sampling_rate=16000)
    assert len(muestras) == 8000


class SegmentoFalso:
    def __init__(self, text: str) -> None:
        self.text = text


class InfoFalsa:
    language = "es"
    duration = 26.1


class ModeloFalso:
    """Imita lo justo de WhisperModel que usa el transcriptor."""

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def transcribe(self, ruta, **kwargs):
        self.ultimo = {"ruta": ruta, **kwargs}
        return [SegmentoFalso(" Hola "), SegmentoFalso(" modo silencioso ")], InfoFalsa()


@pytest.fixture
def perfil_portatil() -> Profile:
    return Profile(
        name="laptop",
        description="",
        min_vram_mb=2048,
        llm_model="llama3.2:3b",
        llm_num_ctx=4096,
        llm_num_gpu=99,
        llm_keep_alive="5m",
        stt_model="small",
        stt_device="cpu",
        stt_compute="int8",
    )


@pytest.fixture
def audio(tmp_path) -> Path:
    f = tmp_path / "prueba.wav"
    f.write_bytes(b"RIFF....WAVE")
    return f


# -- el contrato ------------------------------------------------------------
def test_cumple_el_contrato():
    assert isinstance(WhisperTranscriber(loader=ModeloFalso), Transcriber)


def test_un_doble_tambien_cumple_el_contrato():
    """Permite construir las frases y la memoria sin audio real."""

    class Doble:
        def transcribe(self, audio, *, language="es"):
            return "texto fijo"

    assert isinstance(Doble(), Transcriber)


# -- construccion desde el perfil -------------------------------------------
def test_from_profile_traslada_los_ajustes(perfil_portatil):
    t = WhisperTranscriber.from_profile(perfil_portatil, loader=ModeloFalso)
    assert "small" in repr(t)
    assert "cpu" in repr(t)  # la GPU la ocupa el modelo de lenguaje
    assert "int8" in repr(t)


def test_el_modelo_no_se_carga_hasta_usarlo(perfil_portatil):
    """Construirlo para leer su configuracion no debe costar la carga."""
    cargas = []

    def loader(*a, **k):
        cargas.append(a)
        return ModeloFalso()

    t = WhisperTranscriber.from_profile(perfil_portatil, loader=loader)
    assert cargas == []
    _ = t.model
    assert len(cargas) == 1
    _ = t.model
    assert len(cargas) == 1, "el modelo deberia cargarse una sola vez"


# -- transcripcion -----------------------------------------------------------
def test_transcribe_une_y_limpia_los_segmentos(audio):
    t = WhisperTranscriber(loader=ModeloFalso)
    assert t.transcribe(audio) == "Hola modo silencioso"


def test_conserva_la_frase_literal(audio):
    """La identificacion de frases exactas depende de que no se altere nada."""
    assert "modo silencioso" in WhisperTranscriber(loader=ModeloFalso).transcribe(audio)


def test_pasa_el_idioma(audio):
    modelo = ModeloFalso()
    t = WhisperTranscriber(loader=lambda *a, **k: modelo)
    t.transcribe(audio, language="en")
    assert modelo.ultimo["language"] == "en"


def test_detallado_calcula_el_rtf(audio):
    r = WhisperTranscriber(loader=ModeloFalso).transcribe_detailed(audio)
    assert isinstance(r, Transcription)
    assert r.duration == 26.1
    assert r.language == "es"
    assert 0 < r.rtf < 1, "con un modelo falso deberia ser practicamente cero"


def test_rtf_no_divide_por_cero():
    assert Transcription(text="", language="es", duration=0.0, elapsed=1.0).rtf == 0.0


# -- errores traducidos -------------------------------------------------------
def test_audio_inexistente(tmp_path):
    t = WhisperTranscriber(loader=ModeloFalso)
    with pytest.raises(BackendError, match="No existe el audio"):
        t.transcribe(tmp_path / "no-esta.wav")


def test_fallo_de_dll_menciona_el_redistributable(audio):
    def loader(*a, **k):
        raise FileNotFoundError("Could not find module 'ctranslate2.dll'")

    with pytest.raises(BackendError, match="VCRedist"):
        WhisperTranscriber(loader=loader).transcribe(audio)


def test_fallo_de_cuda_sugiere_pasar_a_cpu(audio):
    def loader(*a, **k):
        raise RuntimeError("CUDA failed with error out of memory")

    with pytest.raises(BackendError, match="stt_device"):
        WhisperTranscriber(device="cuda", loader=loader).transcribe(audio)


# -- contra faster-whisper de verdad -----------------------------------------
@pytest.mark.hardware
def test_transcripcion_real(tmp_path):
    """Genera audio con la voz de Windows y lo transcribe de vuelta."""
    pytest.importorskip("faster_whisper")
    import platform

    if platform.system() != "Windows":
        pytest.skip("usa el sintetizador de Windows")

    import subprocess

    wav = tmp_path / "real.wav"
    # Una frase larga a proposito. Transcribir tiene un coste fijo por llamada
    # de unos 4 s en este equipo, asi que sobre un audio de 3 s el RTF no puede
    # bajar de 1,5 por pura aritmetica: mediria el coste fijo, no la fluidez.
    frase = (
        "Doom, activa el modo silencioso y recuerdame revisar el presupuesto de "
        "memoria antes de escribir la primera capa."
    )
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es*' } "
        "| Select-Object -First 1; "
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }; "
        f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{frase}'); $s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=120)
    if not wav.is_file():
        pytest.skip("no se pudo generar el audio")

    from doombot import profiles

    t = WhisperTranscriber.from_profile(profiles.current())
    r = t.transcribe_detailed(wav)

    assert "modo silencioso" in r.text.lower()
    # Por debajo de 1 transcribe mas rapido de lo que se habla, que es la
    # condicion para que la voz no se acumule. Medido entre 0,28 y 0,59 segun
    # el estado del equipo: el margen del umbral cubre esa variacion.
    assert r.rtf < 1.0, f"demasiado lento para voz: RTF {r.rtf:.2f}"


def test_audio_corrupto_lo_dice_en_castellano(tmp_path):
    """El error de la capa de decodificacion no sugiere que falle el fichero."""
    f = tmp_path / "no-es-audio.wav"
    f.write_bytes(b"esto no es audio")

    def loader(*a, **k):
        class M:
            def transcribe(self, *a, **k):
                raise RuntimeError("[Errno 1094995529] Invalid data found when processing input")

        return M()

    with pytest.raises(BackendError, match="no parece un fichero de sonido"):
        WhisperTranscriber(loader=loader).transcribe(f)
