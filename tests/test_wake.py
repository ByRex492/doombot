"""La palabra de activacion, contra un ``openwakeword`` falso.

El fallo real -medido con microfono real, la primera vez que se probo-: sin
rutas explicitas, ``Model`` busca ``melspectrogram.onnx``/``embedding_model.onnx``
dentro del paquete instalado (``site-packages/openwakeword/resources/``), no
en la carpeta de datos del proyecto donde ``_pesos()`` los descarga. Este test
comprueba justo eso: que ``Model`` recibe las rutas de ``carpeta``, no las
deja a su valor por defecto.
"""

from __future__ import annotations

import sys
import types

import pytest

from doombot.voice.wake import WakeWord


class ModeloFalso:
    """Registra con que kwargs se construyo, sin cargar nada de verdad."""

    instancia: ModeloFalso | None = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        ModeloFalso.instancia = self

    def predict(self, muestras):
        return {"hey_jarvis": 0.0}

    def reset(self) -> None:
        pass


@pytest.fixture
def openwakeword_falso(tmp_path, monkeypatch):
    """Un modulo ``openwakeword`` minimo, con los ficheros ya "descargados"."""
    carpeta = tmp_path / "openwakeword"
    carpeta.mkdir()
    for nombre in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        (carpeta / nombre).write_bytes(b"x")

    monkeypatch.setattr("doombot.voice.wake.models_dir", lambda: tmp_path)

    modulo = types.ModuleType("openwakeword")
    modulo.MODELS = {"hey_jarvis": {"model_path": "hey_jarvis_v0.1.tflite"}}
    modulo.utils = types.SimpleNamespace(download_models=lambda *a, **k: None)

    submodulo = types.ModuleType("openwakeword.model")
    submodulo.Model = ModeloFalso

    monkeypatch.setitem(sys.modules, "openwakeword", modulo)
    monkeypatch.setitem(sys.modules, "openwakeword.model", submodulo)
    ModeloFalso.instancia = None
    return carpeta


def test_pesos_devuelve_el_fichero_en_la_carpeta_de_datos(openwakeword_falso):
    w = WakeWord()
    assert w._pesos() == openwakeword_falso / "hey_jarvis_v0.1.onnx"


def test_pesos_falla_si_falta_un_auxiliar(openwakeword_falso):
    (openwakeword_falso / "melspectrogram.onnx").unlink()
    from doombot.backends.base import BackendError

    with pytest.raises(BackendError, match="melspectrogram"):
        WakeWord()._pesos()


def test_load_pasa_las_rutas_de_los_auxiliares_no_las_del_paquete(openwakeword_falso):
    """El fallo real: sin esto, Model busca en site-packages y falla con NO_SUCHFILE."""
    _ = WakeWord().model  # dispara _load()

    assert ModeloFalso.instancia is not None
    kwargs = ModeloFalso.instancia.kwargs
    assert kwargs["melspec_model_path"] == str(openwakeword_falso / "melspectrogram.onnx")
    assert kwargs["embedding_model_path"] == str(openwakeword_falso / "embedding_model.onnx")
    assert kwargs["wakeword_models"] == [str(openwakeword_falso / "hey_jarvis_v0.1.onnx")]


def test_load_es_perezoso(openwakeword_falso):
    WakeWord()
    assert ModeloFalso.instancia is None
