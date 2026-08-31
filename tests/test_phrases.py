"""Reconocimiento de ordenes.

Todo corre sin modelo ni audio: es la unica capa del proyecto que no depende
de nada externo, y esa es justamente su razon de ser.

Los casos no son inventados. Salen de transcripciones reales de Whisper sobre
audio en espanol, que es lo que de verdad va a llegar aqui.
"""

from __future__ import annotations

import pytest

from doombot.phrases import (
    Command,
    PhraseMatcher,
    default_matcher,
    normalize,
    similarity,
)


@pytest.fixture
def m() -> PhraseMatcher:
    return default_matcher()


# ============================================================ normalizacion
@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("MODO SILENCIOSO", "modo silencioso"),
        ("  modo   silencioso  ", "modo silencioso"),
        ("Modo Silencioso.", "modo silencioso"),
        ("¡DOOM! Activa el modo silencioso.", "doom activa el modo silencioso"),
        ("¿Qué tal?", "que tal"),
        ("recuérdame", "recuerdame"),
        ("", ""),
    ],
)
def test_normalize(entrada, esperado):
    assert normalize(entrada) == esperado


def test_la_ñ_se_conserva():
    """Quitarle la tilde a la ñ da otra palabra: 'año' se convertiria en 'ano'."""
    assert normalize("MAÑANA") == "mañana"
    assert normalize("El año") == "el año"


def test_normalize_quita_los_signos_de_apertura():
    """Whisper devuelve '¡DOOM!' y '¿que?'; sin quitarlos nada coincidiria."""
    assert "¡" not in normalize("¡Para!")
    assert "¿" not in normalize("¿Paro?")


# ============================================================ coincidencia exacta
def test_orden_exacta(m):
    r = m.match("modo silencioso")
    assert r is not None
    assert r.command == "silence"
    assert r.how == "exact"
    assert r.confidence == 1.0


def test_la_exacta_ignora_mayusculas_y_puntuacion(m):
    for texto in ("MODO SILENCIOSO", "Modo silencioso.", "  modo silencioso  "):
        assert m.match(texto).command == "silence"


def test_todas_las_variantes_de_una_orden(m):
    for texto in ("para", "detente", "alto", "cancela"):
        assert m.match(texto).command == "stop", texto


# ============================================================ dentro de una frase
def test_reconoce_la_orden_con_muletillas_alrededor(m):
    """El caso mas comun del dictado."""
    r = m.match("¡DOOM! Activa el modo silencioso.")
    assert r.command == "silence"
    assert r.how == "contains"


def test_gana_la_frase_mas_larga():
    """Con 'para' y 'para de hablar' definidas, la segunda debe alcanzarse."""
    m = PhraseMatcher(
        [
            Command("stop", ("para",)),
            Command("stop_speaking", ("para de hablar",)),
        ]
    )
    assert m.match("para de hablar").command == "stop_speaking"
    assert m.match("para").command == "stop"


def test_no_reconoce_una_orden_dentro_de_otra_palabra(m):
    """'para' no debe dispararse dentro de 'preparar' ni de 'disparate'."""
    assert m.match("voy a preparar la cena") is None
    assert m.match("eso es un disparate") is None


def test_la_confianza_baja_si_la_orden_es_una_parte_pequena(m):
    corta = m.match("doom modo silencioso")
    larga = m.match("oye una cosa que te queria comentar sobre el modo silencioso y tal")
    assert corta.confidence > larga.confidence


# ============================================================ erratas del dictado
def test_tolera_una_errata(m):
    """Whisper devolvio 'identifiqués' e 'Alportatil' en pruebas reales."""
    r = m.match("modo silencios")
    assert r is not None
    assert r.command == "silence"
    assert r.how == "fuzzy"


def test_no_confunde_ordenes_parecidas():
    """El par mas peligroso medido: 'para' contra 'pare' esta en 0,75."""
    m = PhraseMatcher([Command("stop", ("para",)), Command("pay", ("paga",))])
    r = m.match("pare")
    assert r is None or r.command == "stop"


def test_el_modo_difuso_se_puede_apagar():
    m = default_matcher(fuzzy=False)
    assert m.match("modo silencios") is None
    assert m.match("modo silencioso") is not None


def test_no_compara_frases_de_longitud_dispar(m):
    """Una orden de tres letras contra una frase larga siempre da parecido bajo."""
    assert m.match("una reflexion larguisima sobre la vida y sus circunstancias") is None


# ============================================================ ordenes con argumento
def test_captura_lo_que_va_detras(m):
    r = m.match("recuerda que el pan esta caro")
    assert r.command == "remember"
    assert r.argument == "el pan esta caro"


def test_el_argumento_sobrevive_a_la_puntuacion(m):
    r = m.match("Apunta que mañana tengo clase de mates.")
    assert r.command == "remember"
    assert r.argument == "mañana tengo clase de mates"


def test_consulta_a_la_memoria(m):
    r = m.match("que sabes sobre mi portatil")
    assert r.command == "recall"
    assert r.argument == "mi portatil"


def test_un_prefijo_sin_argumento_no_cuenta(m):
    """'recuerda que' a secas no es una orden util."""
    r = m.match("recuerda que")
    assert r is None or r.argument == ""


# ============================================================ perfil del usuario y acciones
def test_identify_guarda_hechos_sobre_el_usuario(m):
    r = m.match("recuerda que yo trabajo en Anthropic")
    assert r.command == "identify"
    assert r.argument == "trabajo en Anthropic"


def test_identify_no_choca_con_remember(m):
    """'recuerda que yo' es mas larga que 'recuerda que': gana la mas especifica."""
    r = m.match("recuerda que el pan esta caro")
    assert r.command == "remember"


def test_act_delega_una_tarea(m):
    r = m.match("ejecuta esto: arregla el test que falla")
    assert r.command == "act"
    assert "arregla el test" in r.argument


# ============================================================ lo que NO es orden
@pytest.mark.parametrize(
    "texto",
    [
        "que tiempo hace mañana",
        "explicame que es un protocol en python",
        "cuanta VRAM tiene mi portatil",
        "hola que tal",
        "",
        "   ",
    ],
)
def test_lo_que_no_es_orden_devuelve_none(m, texto):
    """Devolver None es lo normal: casi nada de lo que se dice es una orden."""
    assert m.match(texto) is None


# ============================================================ configuracion
def test_no_se_pueden_repetir_nombres():
    m = PhraseMatcher([Command("stop", ("para",))])
    with pytest.raises(ValueError, match="Ya existe"):
        m.add(Command("stop", ("alto",)))


def test_una_orden_necesita_al_menos_una_frase():
    with pytest.raises(ValueError, match="ninguna frase"):
        Command("vacia", ())


def test_las_ordenes_de_control_van_primero():
    """Si algo va mal, 'para' tiene que funcionar antes que nada."""
    from doombot.phrases import BASICAS

    assert BASICAS[0].name == "stop"


def test_todas_las_basicas_se_reconocen(m):
    for c in m.commands:
        for f in c.phrases:
            texto = f"{f} algo" if c.prefix else f
            r = m.match(texto)
            assert r is not None, f"no se reconoce {f!r}"
            assert r.command == c.name, f"{f!r} se reconocio como {r.command}"


# ============================================================ similitud
def test_similarity_identicos():
    assert similarity("para", "para") == 1.0


def test_similarity_distintos():
    assert similarity("para", "elefante") < 0.5


# ============================================================ identidad
def test_ahora_doom_dice_que_entiende_ordenes():
    """identity detecta que phrases/ ya expone algo, sin tocar el prompt."""
    from doombot import identity

    assert any(not x.startswith("_") for x in dir(__import__("doombot.phrases", fromlist=["_"])))
    assert identity.system_prompt()


# ============================================================ velocidad
def test_reconocer_una_orden_es_instantaneo(m):
    """Es la razon de no usar el modelo: una orden no puede costar 300 ms."""
    import time

    t0 = time.perf_counter()
    for _ in range(1000):
        m.match("doom activa el modo silencioso")
    ms = time.perf_counter() - t0
    assert ms < 1.0, f"1000 reconocimientos tardaron {ms:.2f}s"


def test_reconoce_un_prefijo_con_erratas(m):
    """Caso real: Whisper devolvio 'que sabe sobre' en vez de 'que sabes sobre'.

    Comparar la frase entera no sirve —el argumento diluye el parecido—, asi
    que se comparan solo las primeras palabras.
    """
    r = m.match("que sabe sobre mi portatil")
    assert r is not None, "no reconocio la orden con la errata"
    assert r.command == "recall"
    assert r.how == "fuzzy"
    assert r.argument == "mi portatil"


def test_el_prefijo_con_erratas_sigue_necesitando_argumento(m):
    """Sin nada detras no es una orden util, aunque el prefijo se parezca."""
    assert m.match("que sabe sobre") is None


def test_una_errata_en_el_prefijo_no_inventa_ordenes(m):
    """Una frase normal no debe convertirse en orden por parecerse un poco."""
    assert m.match("que sabemos todos de la vida y sus cosas") is None


# ============================================================ el argumento intacto
def test_el_argumento_conserva_tildes_y_mayusculas(m):
    """Normalizar sirve para comparar, no para almacenar.

    Guardar el argumento ya normalizado destruye los nombres propios sin vuelta
    atras: "GitHub" pasaria a "github" y "Python" a "python".
    """
    r = m.match("Recuerda que el código está en GitHub, no en Python")
    assert r.command == "remember"
    assert r.argument == "el código está en GitHub, no en Python"


def test_el_argumento_conserva_la_puntuacion_interna(m):
    r = m.match("Apunta que necesito Python 3.12, no la 3.14")
    assert r.command == "remember"
    assert "3.12" in r.argument
    assert "Python" in r.argument


def test_el_argumento_difuso_tambien_conserva_el_original(m):
    """El caso de la errata de Whisper, ahora sin degradar el texto."""
    r = m.match("que sabe sobre mi portátil Húngaro")
    assert r.command == "recall"
    assert r.argument == "mi portátil Húngaro"


def test_partir_cuenta_palabras_normalizadas_no_caracteres():
    """normalize() cambia longitudes: '3.12' pasa a ser dos palabras."""
    from doombot.phrases.matcher import _partir_original

    assert _partir_original("Recuerda que Python 3.12", 2) == "Python 3.12"
    assert _partir_original("uno dos tres", 1) == "dos tres"
    assert _partir_original("uno dos", 5) == ""
