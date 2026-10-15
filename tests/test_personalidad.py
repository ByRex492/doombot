"""La personalidad de D.O.O.M (D-044) y el prompt que habla como una persona."""

from __future__ import annotations

import pytest

from doombot.agent import personalidad
from doombot.agent.memoria import Memoria
from doombot.agent.montaje import montar, system_prompt
from doombot.backends.base import PasoModelo
from doombot.obsidian import vault
from doombot.ventana.puente import Puente


def test_sin_elegir_es_el_companero(tmp_path):
    actual = personalidad.leer(tmp_path)
    assert actual["base"] == "companero"
    assert actual["texto"] == personalidad.ESTILOS["companero"][1]


def test_se_guarda_y_se_lee(tmp_path):
    personalidad.guardar("jarvis", "Formal, con ironía británica.", tmp_path)
    assert personalidad.leer(tmp_path) == {
        "base": "jarvis",
        "texto": "Formal, con ironía británica.",
    }
    assert personalidad.para_prompt(tmp_path) == "Tu personalidad: Formal, con ironía británica."


def test_un_estilo_desconocido_es_propio(tmp_path):
    personalidad.guardar("inventado", "Habla como un pirata.", tmp_path)
    assert personalidad.leer(tmp_path)["base"] == "propia"


def test_editarla_a_mano_en_obsidian_vale(tmp_path):
    personalidad.guardar("companero", "Algo.", tmp_path)
    ruta = vault.personalidad_path(tmp_path)
    contenido = ruta.read_text(encoding="utf-8").replace("Algo.", "Muy breve.\nY con humor.")
    ruta.write_text(contenido, encoding="utf-8")
    assert personalidad.leer(tmp_path)["texto"] == "Muy breve.\nY con humor."


@pytest.mark.parametrize("texto", ["", "   ", "x" * 2001])
def test_no_se_guarda_vacia_ni_enorme(tmp_path, texto):
    with pytest.raises(ValueError):
        personalidad.guardar("companero", texto, tmp_path)


def test_hay_varios_estilos_para_elegir():
    ids = [e["id"] for e in personalidad.catalogo()]
    assert ids[0] == "companero" and {"jarvis", "mentor", "gamer", "sobrio"} <= set(ids)


def test_la_ventana_la_ensena_y_la_guarda():
    puente = Puente(memoria=Memoria())
    datos = puente.perfil()["personalidad"]
    assert datos["base"] == "companero" and len(datos["estilos"]) == 5
    assert puente.guardar_personalidad("mentor", "Paciente.") == {"ok": True}
    assert puente.perfil()["personalidad"]["texto"] == "Paciente."
    assert puente.guardar_personalidad("mentor", "")["ok"] is False


class Guion:
    model_name = "guion"

    def __init__(self, *pasos):
        self.pasos = list(pasos)
        self.prompts: list[str] = []

    def paso(self, conversacion, herramientas, *, system=None):
        self.prompts.append(system or "")
        return self.pasos.pop(0)


def test_el_agente_la_lee_en_cada_orden(tmp_path):
    memoria = Memoria(vault_dir=tmp_path)
    cerebro = Guion(PasoModelo("Hola."), PasoModelo("Buenas, señor."))
    m = montar(narrar=lambda *a: None, confirmar=lambda p: True, cerebro_=cerebro, memoria=memoria)
    m.agente.ejecutar("hola")
    memoria.guardar_personalidad("jarvis", "Formal: le llamas señor.")  # sin volver a montar
    m.agente.ejecutar("hola otra vez")
    assert "compañero de equipo" in cerebro.prompts[0]
    assert "Formal: le llamas señor." in cerebro.prompts[1]


def test_el_prompt_habla_como_una_persona():
    prompt = system_prompt()
    assert "Como hablas:" in prompt and "Como trabajas:" in prompt
    assert "abre Steam" in prompt  # entender la intencion, no solo palabras clave
    # La regla que hacia decir "Voy a responder." antes de un saludo ya no obliga a narrar.
    assert "si solo hay que contestar, contesta" in prompt
