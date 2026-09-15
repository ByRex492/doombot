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


def test_grabacion_se_borra_al_salir(carpeta_aislada):
    grabacion = micro_con([0.2]).record(0.2)
    assert grabacion.path.is_file()
    with grabacion:
        pass
    assert not grabacion.path.exists(), "la captura sobrevivio al gestor de contexto"


# -- grabacion ---------------------------------------------------------------
def test_graba_wav_16k_mono():
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
    grabacion = micro_con(niveles).record_until_silence(max_ms=30_000, silence_ms=500)
    # 6 de calibracion + 20 de voz + los 10 bloques de silencio que hacen 0,5 s.
    assert grabacion.duration == pytest.approx(36 * 0.05, rel=0.15)


def test_espera_voz_antes_del_silencio():
    """Regresion: la primera version cortaba antes de que diera tiempo a hablar.

    Contaba el silencio desde el primer bloque, asi que los segundos que uno
    tarda en reaccionar al mensaje agotaban el contador y la grabacion terminaba
    en seco. Un suelo de duracion minima no arreglaba nada: solo retrasaba el
    corte. La cuenta atras tiene que empezar al oir voz, no al abrir el flujo.
    """
    # Dos segundos largos de silencio ANTES de empezar a hablar.
    niveles = [0.001] * 40 + [0.5] * 20 + [0.001] * 20
    grabacion = micro_con(niveles).record_until_silence(
        max_ms=30_000, silence_ms=500, wait_ms=5_000
    )
    assert grabacion.duration > 2.0, "corto antes de que empezara la voz"
    assert grabacion.peak > 0.1, "no llego a capturar la voz"


def test_se_rinde_si_nadie_habla():
    """Pero no se queda esperando indefinidamente."""
    grabacion = micro_con([0.001]).record_until_silence(
        max_ms=30_000, silence_ms=500, wait_ms=1_000
    )
    assert grabacion.duration == pytest.approx(1.0, abs=0.2)
    assert grabacion.parece_mudo


def test_umbral_calibrado_con_el_fondo():
    """El mismo nivel es voz o silencio segun el ruido de fondo que lo rodee.

    Con 0,5 constante desde el principio, ese valor ES el fondo y nunca cuenta
    como voz: la grabacion acaba rindiendose. En la prueba de mas arriba, ese
    mismo 0,5 sobre un fondo de 0,001 era voz clarisima. Esa es la diferencia
    entre calibrar el umbral y fijarlo por constante.
    """
    grabacion = micro_con([0.5]).record_until_silence(max_ms=30_000, silence_ms=500, wait_ms=1_000)
    assert grabacion.duration == pytest.approx(1.0, abs=0.2), "considero voz el ruido de fondo"


def test_respeta_el_maximo_si_nunca_hay_silencio():
    grabacion = micro_con([0.001] * 6 + [0.9]).record_until_silence(max_ms=1_000, silence_ms=500)
    assert grabacion.duration == pytest.approx(1.0, rel=0.1)


# -- eleccion del dispositivo ------------------------------------------------
def test_micro_por_fragmento(monkeypatch):
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


def test_entre_varias_apis_prefiere_wasapi(monkeypatch):
    """Medido con un A50 real: 'el primero' podia ser una instancia muerta.

    Windows reinstancia el mismo dispositivo USB en cada reconexion, y el de
    mas API antigua no siempre es el que de verdad entrega audio -daba pico
    0.000 exacto, sin error alguno al abrirlo-. WASAPI es la que ademas sabe
    remuestrear sola (``_wasapi_auto_convert``), asi que gana si esta.
    """
    monkeypatch.setattr(
        capture,
        "listar_microfonos",
        lambda: [
            InputDevice(14, "auriculares (3- A50 Mic)", "Windows DirectSound", 1),
            InputDevice(32, "auriculares (3- A50 Mic)", "Windows WASAPI", 1),
            InputDevice(55, "auriculares (A50 Mic)", "Windows WDM-KS", 1),
        ],
    )
    # opener presente: _capta_algo() no sondea sounddevice de verdad (ver su
    # docstring), asi que el orden que decide es el de _resolve(), no lo que
    # capte cada indice en esta maquina.
    assert Microphone("a50", opener=lambda **kw: None).device == 32


def test_sin_wasapi_entre_los_candidatos_se_queda_con_el_primero(monkeypatch):
    monkeypatch.setattr(
        capture,
        "listar_microfonos",
        lambda: [
            InputDevice(1, "auriculares (A50 Mic)", "MME", 1),
            InputDevice(10, "auriculares (A50 Mic)", "Windows DirectSound", 1),
        ],
    )
    assert Microphone("a50", opener=lambda **kw: None).device == 1


class SdFalso:
    """Lo justo de ``sounddevice`` que necesita ``_wasapi_auto_convert``."""

    def __init__(self, api: str) -> None:
        self._api = api
        self.pedido_con_auto_convert: bool | None = None

    def query_devices(self, idx):
        return {"hostapi": 0}

    def query_hostapis(self, _idx):
        return {"name": self._api}

    def WasapiSettings(self, *, auto_convert):  # noqa: N802 - mismo nombre que sounddevice
        self.pedido_con_auto_convert = auto_convert
        return "wasapi-settings"


def test_wasapi_pide_auto_convert():
    """Sin esto, WASAPI en modo compartido rechaza los 16 kHz que pide este modulo.

    Medido con un A50 real: ``InputStream`` fallaba con "Invalid sample
    rate" hasta anadir ``extra_settings=WasapiSettings(auto_convert=True)``.
    """
    mic = Microphone(5)
    sd_falso = SdFalso("Windows WASAPI")
    resultado = mic._wasapi_auto_convert(sd_falso)  # noqa: SLF001 - es justo lo que se prueba
    assert resultado == "wasapi-settings"
    assert sd_falso.pedido_con_auto_convert is True


def test_otras_apis_no_piden_nada_wasapi():
    mic = Microphone(5)
    for api in ("MME", "Windows DirectSound", "Windows WDM-KS"):
        assert mic._wasapi_auto_convert(SdFalso(api)) is None  # noqa: SLF001


def test_sin_dispositivo_resuelto_no_pide_wasapi():
    """``device=None`` es el predeterminado del sistema: no hay indice que consultar."""
    assert Microphone()._wasapi_auto_convert(SdFalso("Windows WASAPI")) is None  # noqa: SLF001


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
