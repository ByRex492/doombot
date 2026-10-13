"""Skills, modos, lo aprendido y la calculadora (D-038)."""

from __future__ import annotations

import pytest

from doombot.agent.calculo import calcular
from doombot.agent.montaje import montar
from doombot.agent.skills import GLOBAL, Aprendizajes, cargar_skills, leer_skill
from doombot.backends.base import PasoModelo
from doombot.paths import SKILLS_DIR


def escribir_skill(raiz, nombre, cabecera_extra="", cuerpo="Instrucciones de prueba."):
    carpeta = raiz / nombre
    carpeta.mkdir(parents=True)
    (carpeta / "SKILL.md").write_text(
        f"---\nname: {nombre}\ndescription: Una skill de prueba.\n{cabecera_extra}---\n{cuerpo}\n",
        encoding="utf-8",
    )
    return carpeta


# -- SKILL.md ------------------------------------------------------------------------------
def test_las_skills_del_repositorio_se_leen_todas():
    skills = cargar_skills(SKILLS_DIR)
    assert set(skills) == {"diseno", "investigacion", "programacion", "ciencias"}
    ciencias = skills["ciencias"]
    assert ciencias.titulo == "Ciencias" and ciencias.color == "#ffc23d"
    assert "calcular" in ciencias.herramientas
    assert ciencias.modelos[0] == "groq:openai/gpt-oss-120b"
    assert "calcular" in ciencias.instrucciones


def test_metadata_y_herramientas_permitidas(tmp_path):
    carpeta = escribir_skill(
        tmp_path,
        "cocina",
        'allowed-tools: navegar calcular\nmetadata:\n  titulo: Cocina\n  color: "#ff0000"\n'
        "  modelos: gemini groq:x/y\n",
    )
    s = leer_skill(carpeta)
    assert (s.titulo, s.color, s.modelos, s.herramientas) == (
        "Cocina",
        "#ff0000",
        ("gemini", "groq:x/y"),
        ("navegar", "calcular"),
    )


@pytest.mark.parametrize(
    "nombre_en_cabecera",
    ["Mayusculas", "otra-carpeta", "global", "../fuera"],
)
def test_un_nombre_raro_no_se_carga(tmp_path, nombre_en_cabecera):
    carpeta = tmp_path / "skill"
    carpeta.mkdir()
    (carpeta / "SKILL.md").write_text(
        f"---\nname: {nombre_en_cabecera}\ndescription: x\n---\ncuerpo\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        leer_skill(carpeta)
    assert cargar_skills(tmp_path) == {}  # y no impide cargar el resto


def test_una_skill_personal_sustituye_a_la_del_repositorio(tmp_path):
    repo, personal = tmp_path / "repo", tmp_path / "personal"
    escribir_skill(repo, "ciencias", cuerpo="la del repo")
    escribir_skill(personal, "ciencias", cuerpo="la mia")
    assert cargar_skills(repo, personal)["ciencias"].instrucciones == "la mia"


# -- modos en el agente ---------------------------------------------------------------------
class Cerebro:
    model_name = "c"

    def paso(self, *a, **k):
        return PasoModelo("fin")

    def generate(self, prompt, *, system=None, historial=()):
        return f"respuesta a «{prompt}»"


def montado():
    return montar(
        narrar=lambda *a: None, confirmar=lambda p: True, cerebro_=Cerebro(), pantalla=print
    )


def test_arranca_en_global_con_todo_y_los_expertos():
    m = montado()
    assert m.modos.actual == GLOBAL
    herramientas = set(m.agente.herramientas)
    assert {
        "ejecutar_comando",
        "navegar",
        "calcular",
        "mostrar_grafica",
        "aprender",
        "consultar_skill",
    } <= herramientas
    assert "consultar_skill" in m.agente.system and "programacion" in m.agente.system


def test_un_modo_cambia_instrucciones_y_herramientas_y_volver_a_global_lo_restaura():
    m = montado()
    m.modos.aplicar("ciencias")
    assert m.modos.actual == "ciencias"
    assert set(m.agente.herramientas) == {
        "calcular", "mostrar_grafica", "buscar_web", "navegar", "leer_pagina",
        "abrir_en_navegador", "leer_fichero", "aprender",
    }  # fmt: skip
    assert "Estas en el modo Ciencias" in m.agente.system
    assert "ejecutar_comando" not in m.agente.herramientas

    m.modos.aplicar(GLOBAL)
    assert "ejecutar_comando" in m.agente.herramientas
    assert "modo Ciencias" not in m.agente.system


def test_un_modo_que_no_existe_es_global():
    m = montado()
    assert m.modos.aplicar("inventado") == GLOBAL


def test_consultar_a_un_experto_usa_sus_instrucciones():
    m = montado()
    respuesta = m.modos.consultar("programacion", "¿que es una closure?")
    assert respuesta.startswith("Respuesta del experto de Programación")
    assert "closure" in respuesta
    assert m.modos.consultar("inventado", "x").startswith("Error")


# -- lo aprendido -------------------------------------------------------------------------
def test_lo_aprendido_en_un_modo_llega_a_ese_modo_y_al_global(tmp_path):
    m = montado()
    m.modos.notas = Aprendizajes(tmp_path)
    m.modos.aplicar("programacion")
    assert "Apuntado" in m.modos.aprender("Prefiere el codigo con type hints")

    m.modos.aplicar("programacion")
    assert "type hints" in m.agente.system
    m.modos.aplicar(GLOBAL)
    assert "type hints" in m.agente.system  # el global se realimenta de todos los modos
    m.modos.aplicar("diseno")
    assert "type hints" not in m.agente.system  # pero no ensucia a los demas


def test_aprender_pide_confirmacion():
    m = montado()
    aprender = m.agente.herramientas["aprender"]
    assert "recordar para siempre" in aprender.pregunta({"nota": "x"})


def test_las_notas_se_pueden_borrar_y_no_crecen_sin_limite(tmp_path):
    notas = Aprendizajes(tmp_path)
    notas.anotar("ciencias", "a" * 1000)
    assert len(notas.leer("ciencias")[0]) < 260
    notas.anotar("ciencias", "segunda")
    notas.borrar("ciencias", 0)
    assert [n.split(" ", 1)[1] for n in notas.leer("ciencias")] == ["segunda"]
    with pytest.raises(ValueError):
        notas.anotar("../fuera", "x")


# -- calcular -------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("expresion", "esperado"),
    [
        ("2 + 2", "2 + 2 = 4"),
        ("sqrt(3^2 + 4^2)", "sqrt(3^2 + 4^2) = 5"),
        ("9.81 * 2.5^2 / 2", "9.81 * 2.5^2 / 2 = 30.65625"),
        ("0.1 + 0.2", "0.1 + 0.2 = 0.3"),
        ("factorial(10)", "factorial(10) = 3628800"),
        ("sin(pi/2)", "sin(pi/2) = 1"),
    ],
)
def test_calcula_bien(expresion, esperado):
    assert calcular(expresion) == esperado


def test_varias_expresiones_a_la_vez():
    assert calcular("1+1; 2*3") == "1+1 = 2\n2*3 = 6"


@pytest.mark.parametrize(
    "malo",
    [
        "__import__('os').system('ls')",
        "open('/etc/passwd')",
        "(1).__class__",
        "x + 1",
        "9 ^ 999999",
        "factorial(100000)",
        "1/0",
    ],
)
def test_no_ejecuta_codigo_ni_se_cuelga(malo):
    assert calcular(malo).startswith("Error")
