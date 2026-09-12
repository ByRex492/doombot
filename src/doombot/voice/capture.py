"""Captura de audio del microfono.

Primera pieza de la capa de voz y la unica que toca hardware directamente.
Produce ficheros WAV que consume ``Transcriber``, de ahi que el contrato de
transcripcion reciba una ruta y no un array: mantiene las dos piezas
independientes y permite reproducir a mano lo que se grabo cuando algo falla.

Dos decisiones que conviene entender antes de tocar nada:

**El dispositivo se elige por nombre, no por indice.** Este equipo expone mas
de veinte entradas -Oculus, Steam, VB-Cable, Realtek, el A50- repartidas entre
cuatro APIs de Windows, y los indices se desplazan al enchufar o quitar un USB.
Un indice guardado en la configuracion apunta manana a otro microfono. Un
fragmento del nombre sobrevive a eso.

**El umbral de silencio se calibra, no se fija.** Un valor constante funciona en
la habitacion donde se escribio y falla en cualquier otra: con un ventilador
cerca no detecta silencio nunca, y en una sala callada corta a media frase. Se
mide el ruido de fondo durante la primera fraccion de segundo y el umbral sale
de ahi.
"""

from __future__ import annotations

import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from doombot.backends.base import BackendError
from doombot.paths import data_dir

if TYPE_CHECKING:
    from collections.abc import Callable

# 16 kHz mono es el formato que esperan tanto Whisper como openWakeWord. Grabar
# a mas no mejora la transcripcion -el modelo remuestrea igualmente- y multiplica
# el tamano de los ficheros.
SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # int16

BLOQUE_MS = 50
BLOQUE_SEGUNDOS = BLOQUE_MS / 1000

_MISSING = (
    'sounddevice no esta instalado. Es una dependencia opcional:\n    pip install -e ".[voice]"'
)


@dataclass(frozen=True)
class InputDevice:
    """Una entrada de audio del sistema."""

    index: int
    name: str
    api: str
    channels: int

    def __str__(self) -> str:
        return f"[{self.index:3d}] {self.name}  ({self.api})"


@dataclass
class Recording:
    """Audio grabado, en disco.

    Es un gestor de contexto que borra el fichero al salir. La capa de voz graba
    muchas veces por sesion y cada grabacion solo interesa hasta que se
    transcribe; sin un borrado explicito la carpeta de datos crece sin techo, que
    es justo lo que ya paso una vez con los temporales del transcriptor.
    """

    path: Path
    duration: float
    elapsed: float = 0.0
    """Segundos de reloj que costo grabar.

    ``duration`` cuenta muestras; esto cuenta tiempo real. Si difieren mucho, el
    flujo esta perdiendo bloques y la grabacion no es fiel a lo que se dijo.
    """

    peak: float = 0.0
    """Amplitud maxima, de 0,0 a 1,0.

    Diagnostica el fallo mas comun y mas desconcertante: el microfono
    silenciado. Whisper transcribe un WAV mudo sin quejarse y devuelve cadena
    vacia, o una alucinacion corta que parece un fallo del modelo.
    """

    @property
    def parece_mudo(self) -> bool:
        """True si no se capto practicamente nada."""
        return self.peak < 0.01

    def discard(self) -> None:
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> Recording:
        return self

    def __exit__(self, *_: object) -> None:
        self.discard()


def listar_microfonos() -> list[InputDevice]:
    """Entradas de audio disponibles, en el orden que las da el sistema."""
    sd = _sounddevice()
    salida: list[InputDevice] = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            salida.append(
                InputDevice(
                    index=i,
                    name=str(d["name"]).strip(),
                    api=str(sd.query_hostapis(d["hostapi"])["name"]),
                    channels=int(d["max_input_channels"]),
                )
            )
    return salida


class Microphone:
    """Graba del microfono a WAV de 16 kHz mono."""

    def __init__(
        self,
        device: str | int | None = None,
        *,
        samplerate: int = SAMPLE_RATE,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        """``device`` admite un fragmento del nombre, un indice, o nada.

        Sin dispositivo se usa el que marque el sistema, que no siempre es el
        que uno espera: en el sobremesa el predeterminado es el microfono
        virtual del Oculus. Por eso conviene fijarlo en ``.env``.

        ``opener`` existe para las pruebas: sustituye la apertura del flujo de
        audio y permite ejercitar la grabacion y la deteccion de silencio sin
        microfono y sin sounddevice instalado.
        """
        self._device = device
        self._samplerate = samplerate
        self._opener = opener
        self._resolved: int | None = None

    @classmethod
    def from_settings(cls, cfg: Any = None, **kwargs: Any) -> Microphone:
        """Construye leyendo el dispositivo de la configuracion local."""
        if cfg is None:
            from doombot.config import settings

            cfg = settings()
        return cls(getattr(cfg, "audio_input", None) or None, **kwargs)

    @property
    def samplerate(self) -> int:
        return self._samplerate

    def abrir_flujo(self, bloque: int) -> Any:
        """Flujo de entrada abierto. Lo usa el bucle de escucha.

        Publico porque la espera de la palabra de activacion necesita leer
        bloques sueltos sin grabar nada a disco.
        """
        return self._abrir_flujo(bloque)

    # -- resolucion del dispositivo -----------------------------------------
    @property
    def device(self) -> int | None:
        """Indice resuelto. ``None`` significa el predeterminado del sistema."""
        if self._resolved is None and self._device is not None:
            self._resolved = self._resolve(self._device)
        return self._resolved

    def _resolve(self, device: str | int) -> int:
        if isinstance(device, int):
            return device
        if device.strip().isdigit():
            return int(device.strip())

        aguja = device.strip().lower()
        disponibles = listar_microfonos()
        candidatos = [d for d in disponibles if aguja in d.name.lower()]
        if not candidatos:
            listado = "\n".join(f"    {d}" for d in disponibles)
            raise BackendError(
                f"Ningun microfono contiene {device!r} en su nombre.\n"
                f"Disponibles:\n{listado}\n"
                "Ajusta DOOMBOT_AUDIO_INPUT en .env."
            )
        # Con varias APIs de Windows el mismo microfono aparece repetido -mas
        # aun con USB/Bluetooth, que Windows reinstancia en cada reconexion
        # ("A50 Mic", "2- A50 Mic", "3- A50 Mic"...)-. Medido con un A50 real:
        # "quedarse con el primero" no es fiable, puede ser una instancia
        # muerta que abre sin error pero no entrega ni una muestra (pico
        # 0.000 exacto). WASAPI es la que de verdad remuestrea con
        # ``_wasapi_auto_convert`` y en la practica la mas consistente, asi
        # que se prefiere si hay alguna entre los candidatos.
        wasapi = [d for d in candidatos if "wasapi" in d.api.lower()]
        return (wasapi or candidatos)[0].index

    @property
    def device_name(self) -> str:
        idx = self.device
        if idx is None:
            return "predeterminado del sistema"
        for d in listar_microfonos():
            if d.index == idx:
                return f"{d.name} ({d.api})"
        return f"dispositivo {idx}"

    # -- grabacion -----------------------------------------------------------
    def record(
        self,
        seconds: float,
        *,
        on_level: Callable[[float], None] | None = None,
    ) -> Recording:
        """Graba una duracion fija.

        ``on_level`` recibe el nivel de cada bloque, de 0,0 a 1,0. Es el dato que
        alimentara la animacion de la interfaz: sin el, la onda de la pantalla es
        decorativa; con el, reacciona a la voz de verdad.
        """
        return self._grabar(max_ms=int(seconds * 1000), silence_ms=None, on_level=on_level)

    def record_until_silence(
        self,
        *,
        max_ms: int = 30_000,
        silence_ms: int = 1_200,
        wait_ms: int = 10_000,
        on_level: Callable[[float], None] | None = None,
    ) -> Recording:
        """Graba hasta detectar silencio sostenido, o hasta el maximo.

        Es la forma que necesita un asistente: quien habla no sabe de antemano
        cuanto va a durar, y obligarle a pulsar una tecla para terminar rompe la
        idea de hablarle sin teclado.

        **La cuenta atras del silencio no empieza hasta oir voz por primera
        vez.** Sin esa condicion, el silencio de antes de empezar a hablar agota
        el contador y la grabacion termina antes de que a nadie le de tiempo a
        decir nada. Un suelo de duracion minima no basta: solo retrasa el corte.

        ``wait_ms`` es cuanto se espera a que alguien hable antes de rendirse.
        Se devuelve la grabacion igualmente, muda, para que quien llama pueda
        distinguir el caso mirando ``peak``.

        Los tiempos van en milisegundos porque el bloque de captura mide 50 ms:
        expresarlos en segundos obligaba a escribir fracciones que no son
        multiplos exactos del bloque y se redondeaban en silencio.
        """
        return self._grabar(
            max_ms=max_ms,
            silence_ms=silence_ms,
            wait_ms=wait_ms,
            on_level=on_level,
        )

    def _grabar(
        self,
        *,
        max_ms: int,
        silence_ms: int | None,
        wait_ms: int = 10_000,
        on_level: Callable[[float], None] | None = None,
    ) -> Recording:
        import numpy as np

        bloque = int(self._samplerate * BLOQUE_SEGUNDOS)
        bloques_max = max(1, max_ms // BLOQUE_MS)
        bloques_silencio = silence_ms // BLOQUE_MS if silence_ms else 0
        bloques_espera = wait_ms // BLOQUE_MS
        arranque = time.perf_counter()
        # Los primeros bloques miden el ruido de fondo antes de decidir nada.
        bloques_calibracion = 6

        trozos: list[Any] = []
        niveles_fondo: list[float] = []
        umbral: float | None = None
        seguidos_en_silencio = 0
        ha_hablado = False

        try:
            with self._abrir_flujo(bloque) as flujo:
                for n in range(bloques_max):
                    datos, _ = flujo.read(bloque)
                    muestras = np.asarray(datos, dtype=np.float32).reshape(-1)
                    trozos.append(muestras.copy())

                    nivel = float(np.sqrt(np.mean(muestras**2))) if muestras.size else 0.0
                    if on_level is not None:
                        on_level(min(1.0, nivel * 4.0))

                    if not silence_ms:
                        continue

                    if n < bloques_calibracion:
                        niveles_fondo.append(nivel)
                        continue

                    if umbral is None:
                        fondo = sum(niveles_fondo) / len(niveles_fondo) if niveles_fondo else 0.0
                        # El suelo minimo evita que en una sala muy callada el
                        # umbral quede tan bajo que cualquier crujido cuente
                        # como voz y la grabacion no termine nunca.
                        umbral = max(fondo * 3.0, 0.008)

                    if nivel >= umbral:
                        ha_hablado = True
                        seguidos_en_silencio = 0
                        continue

                    # La cuenta atras solo corre DESPUES de haber oido voz. Sin
                    # esta condicion, el silencio de antes de empezar a hablar
                    # agota el contador y corta la grabacion en seco.
                    if ha_hablado:
                        seguidos_en_silencio += 1
                        if seguidos_en_silencio >= bloques_silencio:
                            break
                    elif n >= bloques_espera:
                        # Nadie ha dicho nada en todo este rato. Se devuelve la
                        # grabacion muda igualmente: quien llama lo detecta por
                        # el pico y puede dar un mensaje util.
                        break
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise self._error(e) from e

        audio = np.concatenate(trozos) if trozos else np.zeros(0, dtype=np.float32)
        return self._escribir(audio, time.perf_counter() - arranque)

    def _abrir_flujo(self, bloque: int) -> Any:
        if self._opener is not None:
            return self._opener(samplerate=self._samplerate, channels=CHANNELS, blocksize=bloque)
        sd = _sounddevice()
        return sd.InputStream(
            samplerate=self._samplerate,
            channels=CHANNELS,
            blocksize=bloque,
            device=self.device,
            dtype="float32",
            extra_settings=self._wasapi_auto_convert(sd),
        )

    def _wasapi_auto_convert(self, sd: Any) -> Any:
        """``WasapiSettings(auto_convert=True)`` si el dispositivo es WASAPI, si no None.

        En modo compartido, WASAPI solo admite el formato nativo del
        dispositivo -tipicamente 44100 o 48000 Hz, casi nunca los 16 kHz que
        pide este modulo- y sin este ajuste ``InputStream`` falla con
        "Invalid sample rate" en cualquier microfono que no lo tenga por
        casualidad. ``auto_convert`` le pide a Windows que remuestree el
        solo; no afecta a MME ni a DirectSound, que no conocen este concepto
        y fallarian si se les pasara.
        """
        idx = self.device
        if idx is None:
            return None
        try:
            api = sd.query_hostapis(sd.query_devices(idx)["hostapi"])["name"]
        except Exception:  # noqa: BLE001 - si no se puede saber, se sigue sin el ajuste
            return None
        if "wasapi" not in api.lower():
            return None
        return sd.WasapiSettings(auto_convert=True)

    def _escribir(self, audio: Any, elapsed: float = 0.0) -> Recording:
        import numpy as np

        marca = time.strftime("%Y%m%d-%H%M%S")
        destino = _carpeta_audio() / f"captura-{marca}-{int(time.time() * 1000) % 100000}.wav"
        pico = float(np.max(np.abs(audio))) if audio.size else 0.0

        # De float32 en [-1, 1] a int16, que es lo que admite el modulo wave. El
        # recorte previo evita que un pico por encima de 1,0 de la vuelta y se
        # convierta en un chasquido.
        enteros = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        with wave.open(str(destino), "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(self._samplerate)
            w.writeframes(enteros.tobytes())

        return Recording(
            path=destino,
            duration=audio.size / self._samplerate if audio.size else 0.0,
            elapsed=elapsed,
            peak=pico,
        )

    # -- interno -------------------------------------------------------------
    def _error(self, e: Exception) -> BackendError:
        """Traduce los fallos tipicos de PortAudio a algo accionable."""
        msg = str(e)
        bajo = msg.lower()
        if "invalid sample rate" in bajo or "invalid device" in bajo:
            return BackendError(
                f"El microfono {self.device_name!r} no admite {self._samplerate} Hz.\n"
                "Prueba otro dispositivo en DOOMBOT_AUDIO_INPUT: las entradas WASAPI\n"
                "suelen aceptar mas formatos que las MME.\n"
                f"Detalle: {msg}"
            )
        if "unavailable" in bajo or "error querying device" in bajo:
            return BackendError(
                f"El microfono {self.device_name!r} no esta disponible: puede estar\n"
                "en uso por otro programa, o desconectado.\n"
                f"Detalle: {msg}"
            )
        return BackendError(f"Fallo grabando del microfono: {msg}")

    def __repr__(self) -> str:
        return f"Microphone(device={self._device!r}, samplerate={self._samplerate})"


def limpiar_audio_antiguo(max_edad_horas: float = 24.0) -> int:
    """Borra capturas huerfanas. Devuelve cuantas.

    Una grabacion se borra sola al salir de su gestor de contexto, pero un cierre
    brusco la deja en disco. Esta funcion recoge esos restos, para que un fallo
    puntual no se convierta en gigabytes con el tiempo.
    """
    limite = time.time() - max_edad_horas * 3600
    borrados = 0
    for f in _carpeta_audio().glob("captura-*.wav"):
        if f.stat().st_mtime < limite:
            f.unlink(missing_ok=True)
            borrados += 1
    return borrados


def _carpeta_audio() -> Path:
    """Bajo la carpeta de datos, nunca dentro del repositorio.

    Lo que se graba es lo que se ha dicho en voz alta delante del ordenador: el
    contenido mas sensible del proyecto. Ver ``paths.data_dir``.
    """
    d = data_dir() / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sounddevice() -> Any:
    try:
        import sounddevice as sd
    except ImportError as e:
        raise BackendError(_MISSING) from e
    return sd
