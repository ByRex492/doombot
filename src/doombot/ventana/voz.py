"""La voz en la ventana (D-046): hablarle a D.O.O.M y que conteste hablando.

Hasta ahora la voz vivia solo en la consola (``chat.py``), con ordenes por
palabras clave: "abre Steam" no era ninguna y acababa en un modelo sin
herramientas. Aqui lo que se oye va al agente, igual que lo escrito, asi que
se le habla con naturalidad y actua.

Las piezas son las de siempre -microfono, Whisper, Kokoro, la palabra de
activacion-; esto solo las ata a la ventana:

- **Pulsar para hablar** (el boton del microfono, o Ctrl+Espacio): graba hasta
  que te callas, transcribe y manda la orden. El microfono solo se abre al
  pulsar.
- **Manos libres**: escucha la palabra de activacion ("Hey Jarvis", el modelo
  preentrenado de D-005) en segundo plano. Decirla mientras habla le corta.
- **Responder hablando**: lo que se le pide por voz se contesta por voz. Sin
  codigo, listas ni enlaces leidos en alto: eso se queda en pantalla.

Todo es opcional y se dice que falta: sin microfono no hay entrada, sin
Kokoro no hay salida, y sin Whisper local se transcribe en Groq si hay clave.
"""

from __future__ import annotations

import contextlib
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from doombot.backends.base import BackendError

# Lo que corta en vez de mandarse como orden.
PARAR = frozenset({
    "para", "parate", "calla", "callate", "basta", "silencio", "stop", "detente", "vale ya",
    "deja de hablar", "cancela",
})  # fmt: skip
NEGACION = frozenset({"no", "no gracias", "mejor no", "cancela", "dejalo", "ni hablar", "nop"})

_BLOQUE_CODIGO = re.compile(r"```.*?(```|$)", re.DOTALL)
_ENLACE_MD = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_MARCAS = re.compile(r"[*_#`>|]+")


def para_voz(texto: str, limite: int = 700) -> str:
    """El texto de una respuesta tal como se dice: sin codigo, enlaces ni formato.

    Las respuestas largas se cortan en una frase y se dice que el resto esta en
    pantalla: escuchar dos minutos seguidos no ayuda a nadie.
    """
    hubo_codigo = bool(_BLOQUE_CODIGO.search(texto))
    t = _BLOQUE_CODIGO.sub(" ", texto)
    t = _ENLACE_MD.sub(r"\1", t)
    t = _URL.sub("el enlace", t)
    t = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", t, flags=re.MULTILINE)  # viñetas
    t = _MARCAS.sub("", t)
    t = " ".join(t.split())
    if len(t) > limite:
        corte = max(t.rfind(". ", 0, limite), t.rfind("? ", 0, limite), t.rfind("! ", 0, limite))
        t = t[: corte + 1] if corte > limite // 3 else t[:limite].rsplit(" ", 1)[0] + "…"
        t += " El resto lo tienes en pantalla."
    elif hubo_codigo:
        t += " Te dejo el código en pantalla."
    return t.strip()


class _HaciaVentana:
    """Lo que ``montar_voz`` cree que es el HUD: manda su nivel y su estado a la ventana."""

    def __init__(self, emitir: Callable[..., None]) -> None:
        self._emitir = emitir
        self._ultimo = 0.0

    def set_amplitude(self, v: float) -> None:
        ahora = time.monotonic()
        if ahora - self._ultimo >= 0.08:  # ~12 por segundo bastan para animar
            self._ultimo = ahora
            self._emitir("voz_nivel", nivel=round(float(v), 2))

    def set_state(self, estado: str) -> None:
        if estado == "dormido":
            self._emitir("voz", estado="reposo")

    def set_caption(self, texto: str) -> None:
        self._emitir("voz", estado="hablando")


class _Activacion:
    """La palabra de activacion, o el boton: lo primero que llegue."""

    def __init__(self, palabra: Any, pulsado: threading.Event) -> None:
        self._palabra = palabra
        self._pulsado = pulsado

    @property
    def name(self) -> str:
        return getattr(self._palabra, "name", "palabra de activacion")

    def check(self, muestras: Any) -> Any:
        from doombot.voice.wake import Detection

        if self._pulsado.is_set():
            self._pulsado.clear()
            return Detection(word="boton", score=1.0)
        return self._palabra.check(muestras)

    def reset(self) -> None:
        self._palabra.reset()


class VozVentana:
    """Entrada y salida de voz para la ventana. Cualquiera de las dos puede faltar."""

    def __init__(
        self,
        *,
        emitir: Callable[..., None],
        al_oir: Callable[[str], None],
        microfono: Any = None,
        transcriptor: Any = None,
        speaker: Any = None,
        palabra: Callable[[], Any] | None = None,
        motivo_entrada: str = "",
        motivo_salida: str = "",
        motivo_manos_libres: str = "",
    ) -> None:
        self._emitir = emitir
        self._al_oir = al_oir
        self._mic = microfono
        self._stt = transcriptor
        self._speaker = speaker
        self._palabra = palabra
        self._motivos = {
            "entrada": "" if microfono and transcriptor else motivo_entrada or "sin microfono",
            "salida": "" if speaker else motivo_salida or "sin voz",
            "manos_libres": "" if palabra else motivo_manos_libres or "sin palabra de activacion",
        }
        self._grabando = threading.Lock()
        self._pulsado = threading.Event()
        self._escucha: Any = None
        self._hilo_escucha: threading.Thread | None = None

    # -- que hay ------------------------------------------------------------------
    @property
    def entrada(self) -> bool:
        return self._mic is not None and self._stt is not None

    @property
    def salida(self) -> bool:
        return self._speaker is not None

    @property
    def en_manos_libres(self) -> bool:
        return self._hilo_escucha is not None and self._hilo_escucha.is_alive()

    def estado(self) -> dict[str, Any]:
        return {
            "entrada": self.entrada,
            "salida": self.salida,
            "manos_libres": self.entrada and self._palabra is not None,
            "escuchando": self.en_manos_libres,
            "stt": getattr(self._stt, "model_name", "") if self._stt else "",
            "motivos": {k: v for k, v in self._motivos.items() if v},
        }

    # -- escuchar ------------------------------------------------------------------
    def escuchar(self) -> bool:
        """Pulsar para hablar. False si no hay entrada o ya se esta grabando."""
        if not self.entrada:
            return False
        if self.en_manos_libres:
            self._pulsado.set()  # el hilo de escucha ya tiene el microfono
            return True
        if not self._grabando.acquire(blocking=False):
            return False
        threading.Thread(target=self._grabar, name="voz-pulsar", daemon=True).start()
        return True

    def _grabar(self) -> None:
        try:
            self.callar()  # hablarle encima le corta
            self._emitir("voz", estado="escuchando")
            with self._mic.record_until_silence(on_level=self._nivel) as grabacion:
                if grabacion.parece_mudo:
                    self._emitir("voz", estado="reposo", aviso="No te he oído.")
                    return
                self._emitir("voz", estado="transcribiendo")
                texto = self._stt.transcribe(grabacion.path)
            self._emitir("voz", estado="reposo")
            if texto.strip():
                self._al_oir(texto.strip())
        except Exception as e:  # noqa: BLE001 - igual: que se vea en la ventana
            self._emitir("voz", estado="reposo", aviso=f"Sin voz: {e}")
        finally:
            self._grabando.release()

    def _nivel(self, v: float) -> None:
        self._emitir("voz_nivel", nivel=round(float(v), 2))

    def manos_libres(self, activar: bool) -> dict[str, Any]:
        """Escuchar la palabra de activacion en segundo plano, o dejar de hacerlo."""
        if not activar:
            if self._escucha is not None:
                self._escucha.parar.set()
            if self._hilo_escucha is not None:
                self._hilo_escucha.join(timeout=2)
            self._hilo_escucha = self._escucha = None
            self._emitir("voz", estado="reposo")
            return self.estado()
        if self.en_manos_libres or not self.entrada or self._palabra is None:
            return self.estado()
        from doombot.voice.listener import Listener

        def al_cambiar(estado: Any) -> None:
            nombre = str(estado)
            if nombre == "escuchando":
                self._pulsado.clear()
                self.callar()  # la palabra de activacion le corta
            self._emitir("voz", estado={"dormido": "atento"}.get(nombre, nombre))

        self._escucha = Listener(
            self._mic,
            self._stt,
            _Activacion(self._palabra(), self._pulsado),
            on_state=al_cambiar,
            on_level=self._nivel,
        )
        escucha = self._escucha

        def bucle() -> None:
            try:
                for oido in escucha.listen():
                    if escucha.parar.is_set():
                        break
                    if not oido.vacio:
                        self._al_oir(oido.text.strip())
            except Exception as e:  # noqa: BLE001 - el hilo no debe morir en silencio
                self._emitir("voz", estado="reposo", aviso=f"Manos libres apagado: {e}")

        self._hilo_escucha = threading.Thread(target=bucle, name="voz-manos-libres", daemon=True)
        self._hilo_escucha.start()
        return self.estado()

    # -- hablar ----------------------------------------------------------------------
    def decir(self, texto: str) -> None:
        if self._speaker is None:
            return
        dicho = para_voz(texto)
        if dicho:
            self._emitir("voz", estado="hablando")
            self._speaker.say(dicho)

    def callar(self) -> None:
        if self._speaker is not None:
            with contextlib.suppress(Exception):
                self._speaker.stop()

    def preguntar(self, pregunta: str) -> None:
        """Dice la pregunta y, al acabar, escucha la respuesta sin palabra de activacion."""
        if not (self.salida and self.entrada):
            return

        def hacer() -> None:
            self.decir(f"{pregunta} ¿Lo hago?")
            with contextlib.suppress(Exception):
                self._speaker.wait(timeout=30)
            self.escuchar()

        threading.Thread(target=hacer, name="voz-pregunta", daemon=True).start()

    def cerrar(self) -> None:
        self.manos_libres(False)
        if self._speaker is not None:
            with contextlib.suppress(Exception):
                self._speaker.close()


def crear_voz(emitir: Callable[..., None], al_oir: Callable[[str], None]) -> VozVentana:
    """La voz de este equipo, con lo que haya instalado. Nunca lanza: dice que falta."""
    from doombot.config import settings

    cfg = settings()
    hacia = _HaciaVentana(emitir)
    piezas: dict[str, Any] = {}

    # Salida: Kokoro (D-021), con el mismo montaje que la consola.
    try:
        from doombot.voice.speaker import montar_voz

        voz = montar_voz(hacia)
        if voz is not None:
            piezas["speaker"] = voz.speaker
        else:
            piezas["motivo_salida"] = (
                'sin Kokoro: pip install -e ".[voice-tts]" y python -m doombot voz-descargar'
            )
    except ImportError as e:
        piezas["motivo_salida"] = f"sin voz de salida: {e}"

    # Entrada: el microfono y quien transcribe. El microfono no se abre aqui:
    # solo al pulsar, o al encender manos libres.
    from importlib.util import find_spec

    if find_spec("sounddevice") is None:
        piezas["motivo_entrada"] = 'sin acceso al microfono: pip install -e ".[voice]"'
    else:
        from doombot.voice.capture import Microphone

        piezas["microfono"] = Microphone.from_settings(cfg)
    if "microfono" in piezas:
        try:
            piezas["transcriptor"] = _transcriptor(cfg)
        except (ImportError, BackendError) as e:
            piezas["motivo_entrada"] = str(e)
            piezas.pop("microfono")

    # Manos libres: la palabra de activacion, que se carga al encenderlo.
    if find_spec("openwakeword") is not None:
        from doombot.voice.wake import WakeWord

        piezas["palabra"] = WakeWord
    else:
        piezas["motivo_manos_libres"] = 'falta openwakeword: pip install -e ".[voice]"'
    return VozVentana(emitir=emitir, al_oir=al_oir, **piezas)


def _transcriptor(cfg: Any) -> Any:
    """Whisper local si esta (D-002), Groq si no o si se pide (``DOOMBOT_STT``)."""
    from importlib.util import find_spec

    eleccion = getattr(cfg, "stt", "auto")
    local = find_spec("faster_whisper") is not None
    if eleccion == "local" or (eleccion == "auto" and local):
        if not local:
            raise BackendError(
                'DOOMBOT_STT=local pero falta faster-whisper (pip install -e ".[voice]")'
            )
        from doombot import profiles
        from doombot.backends.whisper import WhisperTranscriber

        return WhisperTranscriber.from_profile(profiles.current())
    from doombot.backends.stt_nube import TranscriptorNube

    clave = cfg.clave("groq")
    if not clave:
        raise BackendError(
            "sin quien transcriba: instala faster-whisper (extra voice) o pon la clave de Groq"
        )
    return TranscriptorNube(clave)
