"""La captura de microfono, probada sin microfono.

Mismo truco que con Whisper y con Ollama: ``Microphone`` acepta un ``opener``
por parametro, asi que se le pasa un flujo falso que devuelve las muestras que
convenga a cada prueba. Sin esa costura no se podria comprobar la deteccion de
silencio, que es la logica con mas aristas de todo el modulo y la unica que
falla de formas dificiles de reproducir a mano.

Los ficheros se escriben en una carpeta temporal, no en la del usuario: una
prueba nunca debe dejar restos en los datos reales.
"""

from __future__ import annotations

import time
import wave

import numpy as np
import pytest

from doombot.backends.base import BackendError
from doombot.voice import capture
from doombot.voice.capture import (
    SAMPLE_RATE,
    InputDevice,
    Microphone,
    Recording,
    limpiar_audio_antiguo,
)


@pytest.fixture(autouse=True)
def carpeta_aislada(tmp_path, monkeypatch):
    """Redirige las grabaciones a un directorio temporal."""
    monkeypatch.setattr(capture, "_carpeta_audio", lambda: tmp_path)
    return tmp_path


class FlujoFalso:
    """Imita lo justo de ``sd.InputStream``: un gestor de contexto con ``read``.

    ``niveles`` es la amplitud de cada bloque sucesivo. Se repite el ultimo al
    agotarse, para no tener que enumerar treinta segundos de silencio.
    """

    def __init__(self, niveles: list[float], **kwargs) -> None:
        self.niveles = niveles
        self.kwargs = kwargs
        self.leidos = 0

    def __enter__(self) -> FlujoFalso:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def read(self, n: int):
        nivel = self.niveles[min(self.leidos, len(self.niveles) - 1)]
        self.leidos += 1
        # Ruido uniforme de la amplitud pedida: el RMS sale proporcional al
        # nivel, que es lo que mira la deteccion de silencio.
        muestras = np.full(n, nivel, dtype=np.float32)
        return muestras.reshape(-1, 1), False


def micro_con(niveles: list[float]) -> Microphone:
    return Microphone(opener=lambda **kw: FlujoFalso(niveles, **kw))


# -- el resultado ------------------------------------------------------------
def test_detecta_un_microfono_mudo():
    """El pico distingue 'no dijo nada' de 'el microfono estaba silenciado'."""
    assert Recording(path=None, duration=1.0, peak=0.0).parece_mudo
    assert not Recording(path=None, duration=1.0, peak=0.4).parece_mudo


def test_la_grabacion_se_borra_al_salir_del_contexto(carpeta_aislada):
    grabacion = micro_con([0.2]).record(0.2)
    assert grabacion.path.is_file()
    with grabacion:
        pass
    assert not grabacion.path.exists(), "la captura sobrevivio al gestor de contexto"


# -- grabacion ---------------------------------------------------------------
def test_graba_un_wav_de_16k_mono_con_la_duracion_pedida():
    grabacion = micro_con([0.3]).record(0.5)

    with wave.open(str(grabacion.path), "rb") as w:
        assert w.getframerate() == SAMPLE_RATE
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getnframes() == pytest.approx(SAMPLE_RATE * 0.5, rel=0.1)


def test_informa_del_nivel_de_cada_bloque():
    """Es el dato que alimentara la animacion de la interfaz."""
    niveles: list[float] = []
    micro_con([0.25]).record(0.5, on_level=niveles.append)

    assert len(niveles) == 10  # 0,5 s en bloques de 50 ms
    assert all(0.0 <= n <= 1.0 for n in niveles)
    assert max(niveles) > 0.0


# -- deteccion de silencio ---------------------------------------------------
def test_para_cuando_llega_el_silencio():
    """Ruido de fondo bajo, voz, y luego silencio: debe cortar por si solo."""
    niveles = [0.001] * 6 + [0.5] * 20 + [0.001] * 40
    grabacion = micro_con(niveles).record_until_silence(max_seconds=30.0, silence_seconds=0.5)
    # 6 de calibracion + 20 de voz + los 10 bloques de silencio que hacen 0,5 s.
    assert grabacion.duration == pytest.approx(36 * 0.05, rel=0.15)


def test_espera_a_oir_voz_antes_de_contar_el_silencio():
    """Regresion: la primera version cortaba antes de que diera tiempo a hablar.

    Contaba el silencio desde el primer bloque, asi que los segundos que uno
    tarda en reaccionar al mensaje agotaban el contador y la grabacion terminaba
    en seco. Un suelo de duracion minima no arreglaba nada: solo retrasaba el
    corte. La cuenta atras tiene que empezar al oir voz, no al abrir el flujo.
    """
    # Dos segundos largos de silencio ANTES de empezar a hablar.
    niveles = [0.001] * 40 + [0.5] * 20 + [0.001] * 20
    grabacion = micro_con(niveles).record_until_silence(
        max_seconds=30.0, silence_seconds=0.5, wait_seconds=5.0
    )
    assert grabacion.duration > 2.0, "corto antes de que empezara la voz"
    assert grabacion.peak > 0.1, "no llego a capturar la voz"


def test_se_rinde_si_nadie_habla():
    """Pero no se queda esperando indefinidamente."""
    grabacion = micro_con([0.001]).record_until_silence(
        max_seconds=30.0, silence_seconds=0.5, wait_seconds=1.0
    )
    assert grabacion.duration == pytest.approx(1.0, abs=0.2)
    assert grabacion.parece_mudo


def test_el_umbral_se_calibra_con_el_ruido_de_fondo():
    """El mismo nivel es voz o silencio segun el ruido de fondo que lo rodee.

    Con 0,5 constante desde el principio, ese valor ES el fondo y nunca cuenta
    como voz: la grabacion acaba rindiendose. En la prueba de mas arriba, ese
    mismo 0,5 sobre un fondo de 0,001 era voz clarisima. Esa es la diferencia
    entre calibrar el umbral y fijarlo por constante.
    """
    grabacion = micro_con([0.5]).record_until_silence(
        max_seconds=30.0, silence_seconds=0.5, wait_seconds=1.0
    )
    assert grabacion.duration == pytest.approx(1.0, abs=0.2), "considero voz el ruido de fondo"


def test_respeta_el_maximo_si_nunca_hay_silencio():
    grabacion = micro_con([0.001] * 6 + [0.9]).record_until_silence(
        max_seconds=1.0, silence_seconds=0.5
    )
    assert grabacion.duration == pytest.approx(1.0, rel=0.1)


# -- eleccion del dispositivo ------------------------------------------------
def test_encuentra_el_microfono_por_un_fragmento_del_nombre(monkeypatch):
    """Por nombre y no por indice: los indices bailan al mover un USB."""
    monkeypatch.setattr(
        capture,
        "listar_microfonos",
        lambda: [
            InputDevice(1, "Headset Microphone (Oculus Virtual)", "MME", 1),
            InputDevice(65, "Microfono de los auriculares (A50 Mic)", "WDM-KS", 1),
        ],
    )
    assert Microphone("a50").device == 65
    assert Microphone("oculus").device == 1


def test_un_nombre_que_no_existe_dice_cuales_hay(monkeypatch):
    monkeypatch.setattr(
        capture,
        "listar_microfonos",
        lambda: [InputDevice(1, "Headset Microphone", "MME", 1)],
    )
    with pytest.raises(BackendError) as e:
        _ = Microphone("no-existe").device

    mensaje = str(e.value)
    assert "Headset Microphone" in mensaje, "no lista las alternativas"
    assert "DOOMBOT_AUDIO_INPUT" in mensaje, "no dice donde se cambia"


def test_sin_dispositivo_usa_el_del_sistema():
    assert Microphone().device is None


# -- limpieza ----------------------------------------------------------------
def test_barre_las_capturas_huerfanas(carpeta_aislada):
    """Un cierre brusco deja ficheros que ningun contexto va a borrar."""
    viejo = carpeta_aislada / "captura-20260101-000000-1.wav"
    nuevo = carpeta_aislada / "captura-20260827-120000-2.wav"
    ajeno = carpeta_aislada / "memoria.db"
    for f in (viejo, nuevo, ajeno):
        f.write_bytes(b"")

    hace_dos_dias = time.time() - 48 * 3600
    import os

    os.utime(viejo, (hace_dos_dias, hace_dos_dias))

    assert limpiar_audio_antiguo(max_edad_horas=24) == 1
    assert not viejo.exists()
    assert nuevo.exists(), "borro una captura reciente"
    assert ajeno.exists(), "toco un fichero que no era suyo"
