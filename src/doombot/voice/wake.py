"""Palabra de activacion: la oreja barata que esta siempre despierta.

Es lo que permite que D.O.O.M escuche todo el rato sin cocer el equipo.
Whisper transcribiendo en continuo consumiria entre el 28% y el 59% de un
nucleo —medido, RTF 0,28 a 0,59 en el portatil— y ademas transcribiria todo lo
que se hable en la habitacion, sin saber que va dirigido a el. Este detector
solo busca un patron acustico: unas decenas de MB de RAM y coste de CPU
practicamente nulo.

Se usa el modelo preentrenado ``hey_jarvis`` (D-005). Una palabra de activacion
es un patron de sonido, no una frase que haya que comprender, asi que sirve
aunque la conversacion siga en castellano.

Hay ademas un disparador manual —una tecla— porque depurar dependiendo de que
el detector te oiga es lento, y porque en un equipo sin microfono decente sigue
habiendo forma de usar el asistente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from doombot.backends.base import BackendError

if TYPE_CHECKING:
    from collections.abc import Callable

MODELO = "hey_jarvis"

# Por debajo de esto se ignora. openWakeWord devuelve una probabilidad de 0 a 1
# por cada bloque; 0,5 es el valor que recomienda el proyecto y el punto de
# partida razonable. Con muchos falsos disparos se sube, con detecciones
# perdidas se baja, midiendo en cada equipo.
UMBRAL = 0.5

_MISSING = (
    'openwakeword no esta instalado. Es una dependencia opcional:\n    pip install -e ".[voice]"'
)


@runtime_checkable
class WakeDetector(Protocol):
    """Contrato de la palabra de activacion.

    Lo cumple tanto el detector real como el manual, y por eso el bucle de
    escucha no sabe cual de los dos tiene delante.
    """

    def check(self, muestras: Any) -> Detection | None: ...

    def reset(self) -> None: ...

    @property
    def name(self) -> str: ...


@dataclass(frozen=True)
class Detection:
    """Una activacion, con lo seguro que estaba el detector."""

    word: str
    score: float


class WakeWord:
    """Detector por palabra de activacion, sobre openWakeWord."""

    def __init__(
        self,
        model: str = MODELO,
        *,
        threshold: float = UMBRAL,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        self._model_name = model
        self._threshold = threshold
        self._loader = loader
        self._model: Any | None = None

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def model(self) -> Any:
        """Carga perezosa, como en el resto de backends.

        Construir el detector para leer su configuracion no deberia costar la
        descarga de los pesos.
        """
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> Any:
        try:
            if self._loader is not None:
                return self._loader(self._model_name)

            try:
                from openwakeword.model import Model
            except ImportError as e:
                raise BackendError(_MISSING) from e

            try:
                return Model(wakeword_models=[self._model_name], inference_framework="onnx")
            except Exception:
                # Los pesos se descargan la primera vez. openWakeWord no lo
                # hace solo y falla con un error que no lo sugiere.
                import openwakeword

                openwakeword.utils.download_models([self._model_name])
                return Model(wakeword_models=[self._model_name], inference_framework="onnx")
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise BackendError(
                f"No se pudo cargar la palabra de activacion {self._model_name!r}: {e}"
            ) from e

    def check(self, muestras: Any) -> Detection | None:
        """Mira un bloque de audio. Devuelve la deteccion, o None.

        Espera int16 a 16 kHz, que es lo que pide openWakeWord. La captura
        trabaja en float32, asi que la conversion la hace el bucle de escucha:
        aqui se recibe ya en el formato correcto para no convertir dos veces.
        """
        try:
            puntuaciones = self.model.predict(muestras)
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise BackendError(f"Fallo detectando la palabra de activacion: {e}") from e

        for palabra, valor in puntuaciones.items():
            if float(valor) >= self._threshold:
                return Detection(word=str(palabra), score=float(valor))
        return None

    def reset(self) -> None:
        """Olvida el audio acumulado.

        Hay que llamarlo despues de cada activacion: el detector guarda una
        ventana de contexto y, sin limpiarla, la misma palabra dispara varias
        veces seguidas al volver a escuchar.
        """
        modelo = self._model
        if modelo is not None and hasattr(modelo, "reset"):
            modelo.reset()

    def __repr__(self) -> str:
        return f"WakeWord(model={self._model_name!r}, threshold={self._threshold})"


class PushToTalk:
    """Disparador manual: se activa cuando alguien pulsa.

    Cumple el mismo contrato que la palabra de activacion, asi que el bucle de
    escucha funciona igual con uno u otro. Existe por dos razones: depurar
    dependiendo de que el detector te oiga es lento, y un equipo con mal
    microfono sigue necesitando una forma de usar el asistente.
    """

    def __init__(self, pulsado: Callable[[], bool] | None = None) -> None:
        self._pulsado = pulsado if pulsado is not None else _enter_pulsado

    @property
    def name(self) -> str:
        return "manual"

    def check(self, muestras: Any = None) -> Detection | None:  # noqa: ARG002
        return Detection(word="manual", score=1.0) if self._pulsado() else None

    def reset(self) -> None:
        return

    def __repr__(self) -> str:
        return "PushToTalk()"


def _enter_pulsado() -> bool:
    """True si hay una pulsacion esperando, sin bloquear el bucle.

    Bloquear seria mas simple, pero impide que el bucle siga alimentando al
    detector de voz y al medidor de amplitud mientras espera.
    """
    try:
        import msvcrt
    except ImportError:  # pragma: no cover - solo existe en Windows
        return False
    if not msvcrt.kbhit():
        return False
    msvcrt.getch()
    return True
