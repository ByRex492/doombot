"""Transcripcion de audio con faster-whisper.

Cumple ``Transcriber``. Igual que el generador de Ollama, no hereda de nada:
tener los metodos basta.

El perfil decide el tamano del modelo y donde corre. En el portatil eso es
``small`` en CPU con ``int8``, no por falta de GPU sino porque la ocupa entera
el modelo de lenguaje: con el cargado quedan 489 MiB. Medido ahi, transcribe
26 s de audio en 3,8 s (RTF 0,15), y 4,1 s con el modelo generando a la vez.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doombot.backends.base import BackendError
from doombot.paths import models_dir
from doombot.profiles import Profile

if TYPE_CHECKING:
    from collections.abc import Callable

# faster-whisper es dependencia opcional (extra "voice"). El import va dentro
# de la funcion para que importar este modulo no falle en un equipo que solo
# edita y documenta, y para que el mensaje de error diga que instalar.
_MISSING = (
    'faster-whisper no esta instalado. Es una dependencia opcional:\n    pip install -e ".[voice]"'
)


@dataclass(frozen=True)
class Transcription:
    """Resultado con los datos que hacen falta para diagnosticar."""

    text: str
    language: str
    duration: float  # segundos de audio
    elapsed: float  # segundos de transcripcion, sin contar la carga

    @property
    def rtf(self) -> float:
        """Factor de tiempo real: proceso dividido por duracion del audio.

        Es la cifra que dice si la voz va a ir fluida. Por debajo de 0,3 no se
        nota; por encima de 1,0 el asistente tarda mas de lo que duro hablar.
        """
        return self.elapsed / self.duration if self.duration else 0.0


class WhisperTranscriber:
    """Convierte audio en texto."""

    def __init__(
        self,
        model: str = "small",
        *,
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 0,
        beam_size: int = 1,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads
        self._beam_size = beam_size

        # El cargador se puede sustituir, igual que el cliente HTTP del
        # generador. Es lo que permite probar esta clase sin descargar un
        # modelo de cientos de MB ni tener faster-whisper instalado.
        self._loader = loader
        self._model: Any | None = None

    @classmethod
    def from_profile(cls, profile: Profile, **kwargs: Any) -> WhisperTranscriber:
        return cls(
            model=profile.stt_model,
            device=profile.stt_device,
            compute_type=profile.stt_compute,
            **kwargs,
        )

    # -- carga perezosa ------------------------------------------------------
    @property
    def model(self) -> Any:
        """Carga el modelo la primera vez que se pide.

        No se carga en el constructor porque tarda cerca de dos segundos en
        caliente y bastante mas la primera vez, cuando hay que descargarlo.
        Construir el transcriptor para consultar su configuracion no deberia
        costar eso.
        """
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> Any:
        """Construye el modelo. Un unico try cubre las dos vias.

        El cargador inyectado recibe el mismo trato que el real a proposito:
        si solo se tradujeran los errores de faster-whisper, los tests que
        simulan un fallo de carga no probarian el camino que de verdad se
        recorre en produccion.
        """
        try:
            if self._loader is not None:
                return self._loader(
                    self._model_name,
                    device=self._device,
                    compute_type=self._compute_type,
                )

            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise BackendError(_MISSING) from e

            return WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=self._cpu_threads,
                download_root=str(models_dir()),
            )
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise self._error(e) from e

    # -- el contrato ---------------------------------------------------------
    def transcribe(self, audio: Path, *, language: str = "es") -> str:
        return self.transcribe_detailed(audio, language=language).text

    def transcribe_detailed(self, audio: Path, *, language: str = "es") -> Transcription:
        """Transcribe devolviendo tambien las cifras de rendimiento."""
        ruta = Path(audio)
        if not ruta.is_file():
            raise BackendError(f"No existe el audio: {ruta}")

        # La carga se resuelve ANTES de arrancar el cronometro. Es perezosa, y
        # la primera vez incluye descargar el modelo: dejarla dentro inflaba
        # el RTF de la primera llamada hasta hacerlo inutil (9,35 medido, con
        # 28,7 s de los que 26 eran descarga).
        modelo = self.model

        t0 = time.perf_counter()
        try:
            segmentos, info = modelo.transcribe(
                str(ruta), language=language, beam_size=self._beam_size
            )
            texto = " ".join(s.text.strip() for s in segmentos).strip()
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise self._error(e) from e

        return Transcription(
            text=texto,
            language=getattr(info, "language", language),
            duration=float(getattr(info, "duration", 0.0)),
            elapsed=time.perf_counter() - t0,
        )

    # -- interno -------------------------------------------------------------
    def _error(self, e: Exception) -> BackendError:
        """Traduce los fallos tipicos a algo accionable.

        El de las DLL es el que costo encontrar al montar el portatil: sin el
        Visual C++ Redistributable, ctranslate2 falla al cargar su propio DLL
        con un FileNotFoundError que no dice nada de la causa.
        """
        msg = str(e)
        # Audio ilegible. El error que llega es de la capa de decodificacion y
        # dice cosas como "[Errno 1094995529] Invalid data found", que no
        # sugiere que el problema sea el fichero.
        if "invalid data" in msg.lower() or "1094995529" in msg:
            return BackendError(
                "El audio no se pudo decodificar: no parece un fichero de sonido valido, "
                "o esta corrupto. Se admite WAV, MP3, FLAC, OGG y M4A.\n"
                f"Detalle: {msg}"
            )
        if isinstance(e, FileNotFoundError) or "DLL" in msg or "ctranslate2" in msg.lower():
            return BackendError(
                "ctranslate2 no pudo cargar sus DLL. Suele faltar el Visual C++ "
                "Redistributable:\n"
                "    winget install --id Microsoft.VCRedist.2015+.x64 --exact --silent\n"
                f"Detalle: {msg}"
            )
        if self._device == "cuda" and ("cuda" in msg.lower() or "cudnn" in msg.lower()):
            return BackendError(
                f"No se pudo usar CUDA para {self._model_name!r}. En una GPU sin VRAM "
                'libre, pon stt_device = "cpu" en el perfil de profiles.toml.\n'
                f"Detalle: {msg}"
            )
        return BackendError(f"Fallo transcribiendo con {self._model_name!r}: {msg}")

    def __repr__(self) -> str:
        return (
            f"WhisperTranscriber(model={self._model_name!r}, "
            f"device={self._device!r}, compute_type={self._compute_type!r})"
        )
