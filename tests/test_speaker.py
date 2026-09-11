"""El Speaker sin tarjeta de sonido ni Kokoro.

Lo que de verdad puede romperse aqui es el troceo incremental -que decide
cuando una frase esta cerrada mientras el texto llega a pedazos- y que las
ordenes de control lleguen al sitio correcto. Lo demas (que suene) se probo
con audio real y queda medido en D-023.
"""

from __future__ import annotations

from doombot.backends.base import Audio
from doombot.orders import despachar
from doombot.orders.registry import Sesion
from doombot.phrases.matcher import Match
from doombot.voice.speaker import Speaker, partir_incremental


# -- el troceo ---------------------------------------------------------------
def test_una_frase_cerrada_sale_y_el_resto_espera():
    frases, resto = partir_incremental("Hola, buenos dias. Como est")
    assert frases == ["Hola, buenos dias."]
    assert resto == " Como est"


def test_la_sigla_no_se_parte_por_sus_puntos_internos():
    """ "D.O.O.M." lleva tres puntos que no cierran nada y uno que si."""
    frases, resto = partir_incremental("Soy D.O.O.M. Estoy listo. Y sigo")
    assert frases == ["Soy D.O.O.M.", "Estoy listo."]
    assert resto == " Y sigo"


def test_cerrar_suelta_lo_que_quede_aunque_no_termine_en_punto():
    """Cuando el modelo dice la ultima palabra, no se espera a un punto que no llegara."""
    frases, resto = partir_incremental("y eso es todo", cerrar=True)
    assert frases == ["y eso es todo"]
    assert resto == ""


def test_una_frase_muy_corta_se_pega_a_la_siguiente():
    """Sintetizar "Si." solo suena entrecortado y paga el coste fijo de Kokoro."""
    frases, _ = partir_incremental("Si. Claro que puedo ayudarte con eso. ")
    assert frases == ["Si. Claro que puedo ayudarte con eso."]


def test_llegando_token_a_token_salen_las_mismas_frases():
    """La propiedad que importa: el troceo no depende de por donde se corte la entrada."""
    texto = "Primera frase. Segunda, con coma. Y la tercera!"
    esperado, _ = partir_incremental(texto, cerrar=True)

    pendiente, salidas = "", []
    for ch in texto:
        pendiente += ch
        f, pendiente = partir_incremental(pendiente)
        salidas += f
    f, _ = partir_incremental(pendiente, cerrar=True)
    salidas += f
    assert salidas == esperado


# -- el Speaker con dobles -------------------------------------------------
class SintetizadorDoble:
    def __init__(self):
        self.dichas: list[str] = []

    def say(self, texto):
        self.dichas.append(texto)
        return Audio([0.0] * 10, 24000)

    def stream(self, texto):
        yield self.say(texto)

    voice_name = "doble"
    sample_rate = 24000


class ReproductorDoble:
    def __init__(self):
        self.recibidos = 0
        self.parado = False

    def play(self, audio):
        self.recibidos += 1

    def stop(self):
        self.parado = True

    def wait(self, timeout=None):
        return True

    def close(self):
        pass


def _speaker():
    s, p = SintetizadorDoble(), ReproductorDoble()
    return Speaker(s, p), s, p


def test_el_chorro_se_dice_por_frases_y_se_devuelve_entero():
    sp, synth, _ = _speaker()
    texto = sp.speak_stream(iter(["Hola. ", "Que ", "tal estas? ", "Bien"]))
    sp.wait()
    assert texto == "Hola. Que tal estas? Bien"
    assert synth.dichas == ["Hola. Que tal estas?", "Bien"]


def test_silenciado_no_sintetiza_nada():
    s, p = SintetizadorDoble(), ReproductorDoble()
    sp = Speaker(s, p, silenciado=lambda: True)
    sp.say("Esto no deberia sonar.")
    sp.wait()
    assert s.dichas == []


def test_stop_corta_el_reproductor():
    sp, _, player = _speaker()
    sp.stop()
    assert player.parado


# -- las ordenes -------------------------------------------------------------
def _sesion(speaker=None):
    return Sesion(
        gen=None, mem=None, cfg=None, perfil=None, agente=None,
        responder=lambda p: None,
        con_contexto=lambda q, *e: q,
        preguntar=lambda _: "",
        speaker=speaker,
    )  # fmt: skip


def test_para_llega_al_speaker_y_ya_no_dice_que_no_puede(capsys):
    sp, _, player = _speaker()
    assert despachar(_sesion(sp), Match("stop", "para", 1.0, "exact")) is True
    assert player.parado
    assert "no puedo" not in capsys.readouterr().out


def test_repite_vuelve_a_decir_lo_ultimo_y_lo_dice_en_voz_alta():
    sp, synth, _ = _speaker()
    s = _sesion(sp)
    s.ultima_respuesta = "Diecinueve grados."
    despachar(s, Match("repeat", "repite", 1.0, "exact"))
    sp.wait()
    assert synth.dichas == ["Diecinueve grados."]
    assert s.ultima_respuesta == "Diecinueve grados."


def test_repite_sin_nada_que_repetir_lo_dice():
    s = _sesion()
    despachar(s, Match("repeat", "repite", 1.0, "exact"))
    assert "nada" in s.ultima_respuesta.lower()
