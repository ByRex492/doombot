"""Repaso de la respuesta final por otro modelo (D-039). Sin red: modelos de juguete."""

from __future__ import annotations

import pytest

from doombot.agent.bucle import Agente
from doombot.agent.herramientas import Herramienta
from doombot.agent.refinado import Repasador
from doombot.agent.revision import revisor
from doombot.backends.base import BackendError, LlamadaHerramienta, PasoModelo
from doombot.backends.varios import Cadena
from doombot.config import _modo_refinar

LARGA = "Respuesta larga. " * 60


class Juguete:
    def __init__(self, nombre: str, respuesta: str = "", fallo: BackendError | None = None):
        self.proveedor = nombre
        self.model_name = nombre
        self.respuesta = respuesta or f"soy {nombre}"
        self.fallo = fallo
        self.llamadas: list[str] = []

    def generate(self, prompt, *, system=None, historial=()):
        self.llamadas.append(prompt)
        if self.fallo:
            raise self.fallo
        return self.respuesta


def cadena_que_respondio(*modelos: Juguete) -> Cadena:
    cadena = Cadena(modelos)
    cadena.generate("borrador")  # responde el primero: es el autor del borrador
    return cadena


# -- el repasador ---------------------------------------------------------------------
def test_repasa_otro_modelo_con_lo_consultado_y_el_borrador():
    a, b = Juguete("a"), Juguete("b", "Saiko publicó Sakura en 2024 (https://es.wikipedia.org).")
    cadena = cadena_que_respondio(a, b)
    texto, nota = Repasador(lambda: cadena)(
        "discografia de saiko",
        "Saiko publicó Sakura en 2023.",
        [("leer_url", "Álbumes: Sakura (2024)"), ("buscar_web", "Error: el buscador no responde")],
    )

    assert texto.startswith("Saiko publicó Sakura en 2024")
    assert nota == "corregida por b"
    pedido = b.llamadas[0]
    assert "Sakura (2024)" in pedido and "Sakura en 2023" in pedido
    assert "el buscador no responde" not in pedido  # los fallos no son datos
    assert len(a.llamadas) == 1  # el autor no se repasa a si mismo


@pytest.mark.parametrize("dice", ["OK", "OK.", "ok, el borrador es correcto", "", "Corto."])
def test_si_el_corrector_lo_da_por_bueno_o_no_da_una_respuesta_se_queda_el_borrador(dice):
    cadena = cadena_que_respondio(Juguete("a"), Juguete("b", dice or " "))
    texto, nota = Repasador(lambda: cadena)("x", LARGA, [])
    assert texto == LARGA and nota.startswith("sin cambios")


@pytest.mark.parametrize(
    ("respuesta", "consultado", "modo", "modelos", "esperado"),
    [
        ("He abierto la calculadora.", [("abrir_aplicacion", "Abierta")], "auto", 2, False),
        ("Sakura salio en 2024.", [("leer_url", "...")], "auto", 2, True),
        (LARGA, [], "auto", 2, True),
        ("He abierto la calculadora.", [], "siempre", 2, True),
        (LARGA, [("leer_url", "...")], "no", 2, False),
        (LARGA, [("leer_url", "...")], "auto", 1, False),
    ],
)
def test_que_respuestas_merecen_repaso(respuesta, consultado, modo, modelos, esperado):
    cadena = Cadena([Juguete(str(i)) for i in range(modelos)])
    assert Repasador(lambda: cadena, modo=modo).merece(respuesta, consultado) is esperado


@pytest.mark.parametrize(
    ("raw", "modo"),
    [("no", "no"), ("OFF", "no"), ("Siempre", "siempre"), ("", "auto"), ("sí", "auto")],
)
def test_el_modo_de_env(raw, modo):
    assert _modo_refinar(raw) == modo


# -- en el agente ---------------------------------------------------------------------
class Cerebro:
    model_name = "c"

    def __init__(self, *pasos):
        self.pasos = list(pasos)

    def paso(self, *a, **k):
        return self.pasos.pop(0)


class Repaso:
    def __init__(self, resultado=None, fallo=None):
        self.resultado, self.fallo, self.visto = resultado, fallo, None

    def merece(self, respuesta, consultado):
        return True

    def __call__(self, tarea, respuesta, consultado):
        self.visto = (tarea, respuesta, list(consultado))
        if self.fallo:
            raise self.fallo
        return self.resultado


def agente(repaso, narrado):
    leer = LlamadaHerramienta("c0", "leer_url", {"url": "x"})
    return Agente(
        Cerebro(PasoModelo("", (leer,)), PasoModelo("borrador")),
        [Herramienta("leer_url", "lee", lambda url: "Sakura (2024)")],
        narrar=lambda tipo, texto: narrado.append((tipo, texto)),
        confirmar=lambda p: True,
        repasar=repaso,
    )


def test_el_agente_da_la_respuesta_repasada_y_la_deja_en_la_conversacion():
    narrado: list = []
    repaso = Repaso(("corregida", "corregida por b"))
    a = agente(repaso, narrado)
    informe = a.ejecutar("discografia")

    assert informe.respuesta == "corregida"
    assert a.conversacion[-1] == PasoModelo("corregida")
    assert repaso.visto == ("discografia", "borrador", [("leer_url", "Sakura (2024)")])
    assert ("resultado", "Respuesta repasada: corregida por b") in narrado


def test_si_el_repaso_falla_se_da_el_borrador():
    narrado: list = []
    a = agente(Repaso(fallo=BackendError("b: sin cuota")), narrado)
    assert a.ejecutar("discografia").respuesta == "borrador"
    assert a.conversacion[-1] == PasoModelo("borrador")
    assert any(t == "error" and "sin repaso" in x for t, x in narrado)


# -- la segunda opinion en un modo (D-038) ----------------------------------------------
def test_el_revisor_excluye_al_que_propuso_en_la_cadena_del_modo():
    a, b = Juguete("a"), Juguete("b", "BIEN: encaja")
    arranque = cadena_que_respondio(a, b)  # en global respondio a...
    del_modo = cadena_que_respondio(b, a)  # ...pero en el modo propone b
    opinion = revisor(arranque, actual=lambda: del_modo)("x", "y")

    assert opinion == "soy a (a)"  # revisa a, no b, que es quien propuso
