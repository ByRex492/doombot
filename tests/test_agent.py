"""El bucle del agente, con un cerebro de guion: sin modelo, sin red, sin tocar el equipo."""

from __future__ import annotations

import pytest

from doombot.agent.bucle import NEGADA, Agente
from doombot.agent.herramientas import Herramienta, texto, truncar
from doombot.backends.base import (
    LlamadaHerramienta,
    PasoModelo,
    ResultadoHerramienta,
    ToolCaller,
)


class CerebroGuion:
    """Devuelve los pasos que se le dan, en orden, y guarda lo que vio."""

    model_name = "guion"

    def __init__(self, *pasos: PasoModelo) -> None:
        self.pasos = list(pasos)
        self.vistas: list[list] = []

    def paso(self, conversacion, herramientas, *, system=None):
        self.vistas.append(list(conversacion))
        return self.pasos.pop(0)


def llamada(nombre: str, i: int = 0, **args) -> LlamadaHerramienta:
    return LlamadaHerramienta(id=f"c{i}", nombre=nombre, argumentos=args)


def eco(confirmar=None) -> tuple[Herramienta, list]:
    hechas: list = []

    def funcion(msg: str) -> str:
        hechas.append(msg)
        return f"eco: {msg}"

    return (
        Herramienta(
            "eco",
            "repite",
            funcion,
            {"msg": texto("lo que repetir")},
            requeridos=("msg",),
            narrar=lambda a: f"Repito {a['msg']}",
            confirmar=confirmar,
        ),
        hechas,
    )


def montar(cerebro, *herramientas, confirma=True, **kwargs):
    narrado: list[tuple[str, str]] = []
    preguntas: list[str] = []

    def confirmar(p: str) -> bool:
        preguntas.append(p)
        return confirma

    agente = Agente(
        cerebro,
        herramientas,
        narrar=lambda t, x: narrado.append((t, x)),
        confirmar=confirmar,
        **kwargs,
    )
    return agente, narrado, preguntas


def test_el_cerebro_de_guion_cumple_el_contrato():
    assert isinstance(CerebroGuion(), ToolCaller)


def test_actua_cuenta_lo_que_hace_y_termina():
    herramienta, hechas = eco()
    cerebro = CerebroGuion(
        PasoModelo("Voy a repetirlo.", (llamada("eco", msg="hola"),)),
        PasoModelo("Hecho: he repetido hola."),
    )
    agente, narrado, _ = montar(cerebro, herramienta)

    informe = agente.ejecutar("repite hola")

    assert hechas == ["hola"]
    assert informe.respuesta == "Hecho: he repetido hola."
    assert informe.acciones == ["Repito hola"]
    assert informe.pasos == 2 and informe.completo
    assert narrado == [
        ("comentario", "Voy a repetirlo."),
        ("accion", "Repito hola"),
        ("resultado", "eco: hola"),
    ]
    # El resultado vuelve al modelo emparejado con su llamada.
    ultimo = cerebro.vistas[1][-1]
    assert ultimo == ResultadoHerramienta("c0", "eco", "eco: hola")


def test_lo_irreversible_se_pregunta_y_una_negativa_no_se_ejecuta():
    herramienta, hechas = eco(confirmar=lambda a: f"¿repito {a['msg']}?")
    cerebro = CerebroGuion(
        PasoModelo("", (llamada("eco", msg="secreto"),)),
        PasoModelo("Vale, no lo hago."),
    )
    agente, narrado, preguntas = montar(cerebro, herramienta, confirma=False)

    agente.ejecutar("repite secreto")

    assert hechas == []
    assert preguntas == ["¿repito secreto?"]
    assert cerebro.vistas[1][-1].contenido == NEGADA
    assert ("error", "no autorizado: Repito secreto") in narrado


def test_con_permiso_si_se_ejecuta():
    herramienta, hechas = eco(confirmar=lambda a: "¿seguro?")
    cerebro = CerebroGuion(PasoModelo("", (llamada("eco", msg="x"),)), PasoModelo("ok"))
    agente, _, _ = montar(cerebro, herramienta, confirma=True)
    agente.ejecutar("x")
    assert hechas == ["x"]


def test_una_herramienta_inventada_no_tumba_nada():
    cerebro = CerebroGuion(
        PasoModelo("", (llamada("formatear_disco"),)), PasoModelo("No puedo hacer eso.")
    )
    herramienta, _ = eco()
    agente, _, _ = montar(cerebro, herramienta)

    informe = agente.ejecutar("formatea")

    resultado = cerebro.vistas[1][-1].contenido
    assert "no existe la herramienta 'formatear_disco'" in resultado
    assert "eco" in resultado
    assert informe.respuesta == "No puedo hacer eso."


def test_faltan_argumentos_o_sobran_se_le_dice_al_modelo():
    herramienta, hechas = eco()
    cerebro = CerebroGuion(
        PasoModelo("", (llamada("eco", 0), llamada("eco", 1, msg="a", inventado=1))),
        PasoModelo("fin"),
    )
    agente, _, _ = montar(cerebro, herramienta)
    agente.ejecutar("x")

    resultados = [m for m in cerebro.vistas[1] if isinstance(m, ResultadoHerramienta)]
    assert "faltan argumentos obligatorios: msg" in resultados[0].contenido
    assert "argumentos no validos" in resultados[1].contenido
    assert hechas == []


def test_un_fallo_de_la_herramienta_vuelve_como_resultado():
    def rompe() -> str:
        raise OSError("disco lleno")

    cerebro = CerebroGuion(PasoModelo("", (llamada("rompe"),)), PasoModelo("Ha fallado."))
    agente, narrado, _ = montar(cerebro, Herramienta("rompe", "falla", rompe))

    agente.ejecutar("x")

    assert cerebro.vistas[1][-1].contenido == "Error: disco lleno"
    assert narrado[-1] == ("error", "Error: disco lleno")


def test_un_modelo_que_no_para_se_corta():
    herramienta, _ = eco()
    cerebro = CerebroGuion(*[PasoModelo("", (llamada("eco", i, msg="otra"),)) for i in range(5)])
    agente, _, _ = montar(cerebro, herramienta, max_pasos=3)

    informe = agente.ejecutar("bucle")

    assert not informe.completo
    assert informe.pasos == 3
    assert "limite de 3 pasos" in informe.respuesta


def test_las_salidas_enormes_se_truncan():
    cerebro = CerebroGuion(PasoModelo("", (llamada("grande"),)), PasoModelo("ok"))
    agente, _, _ = montar(
        cerebro, Herramienta("grande", "mucho texto", lambda: "x" * 10_000), max_resultado=300
    )
    agente.ejecutar("x")
    contenido = cerebro.vistas[1][-1].contenido
    assert len(contenido) < 500
    assert "caracteres omitidos" in contenido


def test_los_resultados_viejos_se_enmascaran_pero_no_se_pierden():
    herramienta, _ = eco()
    cerebro = CerebroGuion(
        *[PasoModelo("", (llamada("eco", i, msg=f"m{i}"),)) for i in range(3)],
        PasoModelo("fin"),
    )
    agente, _, _ = montar(cerebro, herramienta, ventana=1)

    agente.ejecutar("x")

    vista_final = [m for m in cerebro.vistas[3] if isinstance(m, ResultadoHerramienta)]
    assert [r.contenido for r in vista_final] == [
        "[resultado anterior de eco, ya usado: omitido]",
        "[resultado anterior de eco, ya usado: omitido]",
        "eco: m2",
    ]
    guardados = [m for m in agente.conversacion if isinstance(m, ResultadoHerramienta)]
    assert guardados[0].contenido == "eco: m0"


def test_la_conversacion_sigue_entre_ordenes_hasta_olvidar():
    cerebro = CerebroGuion(PasoModelo("uno"), PasoModelo("dos"), PasoModelo("tres"))
    agente, _, _ = montar(cerebro)
    agente.ejecutar("primera")
    agente.ejecutar("segunda")
    assert cerebro.vistas[1][0] == "primera"

    agente.olvidar()
    agente.ejecutar("tercera")
    assert cerebro.vistas[2] == ["tercera"]


def test_cortar_con_ctrl_c_deja_la_conversacion_cerrada():
    """Cada llamada tiene su resultado, o la API de Anthropic rechaza el siguiente turno."""

    def corta() -> str:
        raise KeyboardInterrupt

    cerebro = CerebroGuion(PasoModelo("", (llamada("corta", 0), llamada("corta", 1))))
    agente, _, _ = montar(cerebro, Herramienta("corta", "x", corta))

    with pytest.raises(KeyboardInterrupt):
        agente.ejecutar("x")

    resultados = [m for m in agente.conversacion if isinstance(m, ResultadoHerramienta)]
    assert [r.id for r in resultados] == ["c0", "c1"]


def test_espec_es_un_json_schema_de_objeto():
    herramienta, _ = eco()
    espec = herramienta.espec()
    assert espec.parametros == {
        "type": "object",
        "properties": {"msg": {"type": "string", "description": "lo que repetir"}},
        "required": ["msg"],
    }


def test_truncar_deja_cabeza_y_cola():
    salida = "INICIO" + "x" * 1000 + "FINAL"
    recortada = truncar(salida, 120)
    assert recortada.startswith("INICIO")
    assert recortada.endswith("FINAL")
    assert truncar("corto", 120) == "corto"
