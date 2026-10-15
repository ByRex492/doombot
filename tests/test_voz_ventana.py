"""La voz en la ventana (D-046), con microfono, transcriptor y altavoz de mentira."""

from __future__ import annotations

import contextlib
import threading
import time

import httpx
import numpy as np
import pytest

from doombot.agent.memoria import Memoria
from doombot.agent.montaje import montar
from doombot.backends.base import BackendError, LlamadaHerramienta, PasoModelo
from doombot.backends.stt_nube import TranscriptorNube
from doombot.ventana import voz as modulo_voz
from doombot.ventana.puente import _NOTA_VOZ, Puente
from doombot.ventana.voz import VozVentana, para_voz


# -- dobles ------------------------------------------------------------------------------
class Grabacion:
    def __init__(self, mudo: bool = False) -> None:
        self.parece_mudo = mudo
        self.path = "audio.wav"
        self.duration = 1.0
        self.peak = 0.5

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


class Flujo:
    def read(self, bloque):
        time.sleep(0.005)
        return np.zeros((bloque, 1), dtype=np.float32), False

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None


class Micro:
    samplerate = 16_000

    def __init__(self, mudo: bool = False) -> None:
        self.mudo = mudo
        self.grabaciones = 0

    def record_until_silence(self, **_kw):
        self.grabaciones += 1
        return Grabacion(self.mudo)

    def abrir_flujo(self, bloque):
        return Flujo()


class Transcriptor:
    model_name = "falso"

    def __init__(self, *textos: str) -> None:
        self.textos = list(textos)

    def transcribe(self, _audio, *, language="es"):
        return self.textos.pop(0) if self.textos else ""


class Altavoz:
    def __init__(self) -> None:
        self.dicho: list[str] = []
        self.parado = 0

    def say(self, texto):
        self.dicho.append(texto)

    def stop(self):
        self.parado += 1

    def wait(self, timeout=None):
        return True

    def close(self):
        pass


class PalabraALaTercera:
    """Una palabra de activacion que salta en el tercer bloque, una sola vez."""

    name = "hey_jarvis"

    def __init__(self) -> None:
        self.n = 0

    def check(self, _muestras):
        from doombot.voice.wake import Detection

        self.n += 1
        return Detection("hey_jarvis", 0.9) if self.n == 3 else None

    def reset(self):
        pass


def esperar(condicion, segundos=3.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if condicion():
            return True
        time.sleep(0.02)
    return False


class Eventos(list):
    def __call__(self, tipo, **datos):
        self.append({"tipo": tipo, **datos})


# -- lo que se dice en voz alta --------------------------------------------------------------
def test_para_voz_quita_lo_que_no_se_lee():
    texto = (
        "## Hecho\nHe creado **main.py**, mira [la doc](https://pygame.org):\n"
        "- uno\n- dos\n```python\nprint('hola')\n```\nY ya está. https://x.com/y"
    )
    dicho = para_voz(texto)
    assert "```" not in dicho and "print" not in dicho and "**" not in dicho
    assert "la doc" in dicho and "pygame.org" not in dicho and "el enlace" in dicho
    assert dicho.endswith("Te dejo el código en pantalla.")


def test_para_voz_corta_lo_largo_en_una_frase():
    largo = "Esta es una frase de prueba bastante normal. " * 40
    dicho = para_voz(largo, limite=200)
    assert len(dicho) < 260 and dicho.endswith("El resto lo tienes en pantalla.")


# -- entrada y salida ---------------------------------------------------------------------
def test_sin_piezas_dice_que_falta():
    v = VozVentana(emitir=Eventos(), al_oir=lambda t: None, motivo_entrada="sin sounddevice")
    estado = v.estado()
    assert not estado["entrada"] and not estado["salida"] and not estado["manos_libres"]
    assert estado["motivos"]["entrada"] == "sin sounddevice"
    assert v.escuchar() is False


def test_pulsar_para_hablar_graba_transcribe_y_entrega():
    oidos: list[str] = []
    eventos = Eventos()
    altavoz = Altavoz()
    v = VozVentana(
        emitir=eventos,
        al_oir=oidos.append,
        microfono=Micro(),
        transcriptor=Transcriptor("abre steam"),
        speaker=altavoz,
    )
    assert v.escuchar()
    assert esperar(lambda: oidos == ["abre steam"])
    assert altavoz.parado == 1  # hablarle encima le corta
    estados = [e.get("estado") for e in eventos if e["tipo"] == "voz"]
    assert estados == ["escuchando", "transcribiendo", "reposo"]


def test_si_no_hablas_no_manda_nada():
    oidos: list[str] = []
    eventos = Eventos()
    v = VozVentana(emitir=eventos, al_oir=oidos.append, microfono=Micro(mudo=True),
                   transcriptor=Transcriptor("x"))  # fmt: skip
    v.escuchar()
    assert esperar(lambda: any(e.get("aviso") == "No te he oído." for e in eventos))
    assert oidos == []


def test_manos_libres_escucha_la_palabra_y_se_apaga():
    oidos: list[str] = []
    eventos = Eventos()
    v = VozVentana(
        emitir=eventos,
        al_oir=oidos.append,
        microfono=Micro(),
        transcriptor=Transcriptor("qué tiempo hace"),
        palabra=PalabraALaTercera,
    )
    assert v.manos_libres(True)["escuchando"]
    assert esperar(lambda: oidos == ["qué tiempo hace"])
    assert any(e.get("estado") == "atento" for e in eventos)
    assert not v.manos_libres(False)["escuchando"]
    assert not v.en_manos_libres


def test_con_manos_libres_el_boton_no_abre_otro_microfono():
    oidos: list[str] = []
    micro = Micro()

    class Nunca(PalabraALaTercera):
        def check(self, _m):
            return None

    v = VozVentana(emitir=Eventos(), al_oir=oidos.append, microfono=micro,
                   transcriptor=Transcriptor("hola"), palabra=Nunca)  # fmt: skip
    v.manos_libres(True)
    assert v.escuchar()  # lo atiende el hilo de manos libres, sin palabra
    assert esperar(lambda: oidos == ["hola"])
    v.manos_libres(False)


def test_decir_y_callar():
    altavoz = Altavoz()
    v = VozVentana(emitir=Eventos(), al_oir=lambda t: None, speaker=altavoz)
    v.decir("**Hecho.** Ver https://x.com")
    assert altavoz.dicho == ["Hecho. Ver el enlace"]
    v.callar()
    assert altavoz.parado == 1


# -- quien transcribe ----------------------------------------------------------------------
def test_transcriptor_en_groq(tmp_path):
    vistos = []

    def responder(peticion: httpx.Request) -> httpx.Response:
        vistos.append(peticion)
        return httpx.Response(200, text="abre steam\n")

    t = TranscriptorNube("gsk_x", client=httpx.Client(transport=httpx.MockTransport(responder)))
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    assert t.transcribe(audio) == "abre steam"
    cuerpo = vistos[0].content
    assert b"whisper-large-v3-turbo" in cuerpo and b'name="language"' in cuerpo
    assert vistos[0].headers["Authorization"] == "Bearer gsk_x"


def test_transcriptor_sin_cuota_o_sin_clave(tmp_path):
    with pytest.raises(BackendError):
        TranscriptorNube("")
    t = TranscriptorNube(
        "k", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429)))
    )
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    with pytest.raises(BackendError, match="sin cuota"):
        t.transcribe(audio)


@pytest.mark.parametrize(
    ("stt", "hay_local", "clave", "esperado"),
    [
        ("auto", False, "k", "groq/"),
        ("nube", True, "k", "groq/"),
        ("auto", False, "", "error"),
        ("local", False, "k", "error"),
    ],
)
def test_quien_transcribe_segun_la_configuracion(monkeypatch, stt, hay_local, clave, esperado):
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda n: object() if (n == "faster_whisper" and hay_local) else None,
    )

    class Cfg:
        def clave(self, _p):
            return clave

    Cfg.stt = stt
    if esperado == "error":
        with pytest.raises(BackendError):
            modulo_voz._transcriptor(Cfg())
    else:
        assert modulo_voz._transcriptor(Cfg()).model_name.startswith(esperado)


# -- con la ventana ------------------------------------------------------------------------
class VentanaFalsa:
    def __init__(self) -> None:
        self.eventos: list[dict] = []
        self.hay = threading.Condition()

    def evaluate_js(self, js: str) -> None:
        import json

        carga = js[js.index("DOOM.evento(") + len("DOOM.evento(") : -1]
        with self.hay:
            self.eventos.append(json.loads(carga))
            self.hay.notify_all()

    def esperar(self, tipo: str, **datos) -> dict:
        fin = time.monotonic() + 5
        with self.hay:
            while time.monotonic() < fin:
                for e in self.eventos:
                    if e["tipo"] == tipo and all(e.get(k) == v for k, v in datos.items()):
                        return e
                self.hay.wait(0.05)
        raise AssertionError(f"no llego {tipo} {datos}: {self.eventos}")


class Guion:
    model_name = "guion"

    def __init__(self, *pasos):
        self.pasos = list(pasos)
        self.prompts: list[str] = []

    def paso(self, conversacion, herramientas, *, system=None):
        self.prompts.append(system or "")
        return self.pasos.pop(0)


def puente_con_voz(*pasos):
    cerebro = Guion(*pasos)
    altavoz = Altavoz()
    puente = Puente(lambda **kw: montar(cerebro_=cerebro, **kw), memoria=Memoria())
    ventana = VentanaFalsa()
    puente._conectar(ventana)
    puente._voz = VozVentana(emitir=puente._emitir, al_oir=puente._al_oir, speaker=altavoz,
                             microfono=Micro(), transcriptor=Transcriptor())  # fmt: skip
    puente._voz_preparada.set()
    puente.iniciar()
    return puente, ventana, cerebro, altavoz


def test_lo_que_se_dice_es_una_orden_y_se_contesta_hablando():
    puente, ventana, cerebro, altavoz = puente_con_voz(PasoModelo("Abro **Steam**."))
    puente._al_oir("abre steam")
    ventana.esperar("oido", texto="abre steam")
    ventana.esperar("estado", estado="reposo")
    assert altavoz.dicho == ["Abro Steam."]
    assert _NOTA_VOZ in cerebro.prompts[0]
    puente._cerrar()


def test_lo_escrito_no_se_lee_en_alto_salvo_que_se_pida():
    puente, ventana, cerebro, altavoz = puente_con_voz(PasoModelo("Hecho."), PasoModelo("Otra."))
    puente.enviar("hola")
    ventana.esperar("estado", estado="reposo")
    assert altavoz.dicho == [] and _NOTA_VOZ not in cerebro.prompts[0]

    from doombot.ventana import preferencias

    preferencias.guardar({**preferencias.leer(), "voz_siempre": True})
    ventana.eventos.clear()
    puente.enviar("otra")
    ventana.esperar("estado", estado="reposo")
    assert altavoz.dicho == ["Otra."]
    puente._cerrar()


def test_para_dicho_en_voz_corta_y_no_se_manda():
    puente, ventana, _cerebro, altavoz = puente_con_voz()
    puente._al_oir("Para.")
    assert altavoz.parado >= 1
    assert not any(e["tipo"] == "oido" for e in ventana.eventos)
    puente._cerrar()


def test_un_permiso_se_contesta_hablando():
    from doombot.agent.herramientas import Herramienta, texto

    peligro = Herramienta(
        "borrar", "borra", lambda que: f"borrado {que}", {"que": texto("x")},
        confirmar=lambda a: f"Voy a borrar {a['que']}.",
    )  # fmt: skip
    cerebro = Guion(
        PasoModelo("", (LlamadaHerramienta("1", "borrar", {"que": "fotos"}),)),
        PasoModelo("Borrado."),
    )

    def montar_con(**kw):
        m = montar(cerebro_=cerebro, **kw)
        m.agente.herramientas["borrar"] = peligro
        return m

    altavoz = Altavoz()
    puente = Puente(montar_con, memoria=Memoria())
    ventana = VentanaFalsa()
    puente._conectar(ventana)
    puente._voz = VozVentana(emitir=puente._emitir, al_oir=puente._al_oir, speaker=altavoz,
                             microfono=Micro(), transcriptor=Transcriptor())  # fmt: skip
    puente._voz_preparada.set()
    puente.iniciar()

    puente._al_oir("borra las fotos")
    ventana.esperar("permiso")
    assert esperar(lambda: any("Voy a borrar fotos" in d for d in altavoz.dicho))
    puente._al_oir("qué")  # no se entiende: se vuelve a preguntar, no se decide
    ventana.esperar("aviso")
    puente._al_oir("sí, adelante")
    ventana.esperar("permiso_fin", si=True)
    ventana.esperar("estado", estado="reposo")
    puente._cerrar()


def test_si_esta_ocupado_avisa_en_vez_de_encolar():
    puente, ventana, _c, _a = puente_con_voz()
    puente._ocupado.set()
    puente._al_oir("otra cosa")
    ventana.esperar("aviso")
    assert not any(e["tipo"] == "oido" for e in ventana.eventos)
    puente._ocupado.clear()
    with contextlib.suppress(Exception):
        puente._cerrar()


def test_la_ventana_dice_que_voz_hay():
    puente = Puente(memoria=Memoria())
    assert puente.voz() == {"cargando": True}
    puente._voz = VozVentana(emitir=lambda *a, **k: None, al_oir=lambda t: None)
    puente._voz_preparada.set()
    assert puente.voz()["entrada"] is False
    assert puente.hablar()["ok"] is False
