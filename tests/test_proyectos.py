"""Proyectos: chats de una carpeta que comparten instrucciones, notas y resumenes (D-040)."""

from __future__ import annotations

import json
import threading
import time

import pytest

from doombot.agent.montaje import montar
from doombot.agent.skills import GLOBAL
from doombot.backends.base import LlamadaHerramienta, PasoModelo
from doombot.ventana.historial import Historial, ProyectoActivo
from doombot.ventana.puente import Puente


class VentanaFalsa:
    def __init__(self) -> None:
        self.eventos: list[dict] = []
        self.hay = threading.Condition()

    def evaluate_js(self, js: str) -> None:
        with self.hay:
            self.eventos.append(json.loads(js[js.index("DOOM.evento(") + 12 : -1]))
            self.hay.notify_all()

    def esperar_reposo(self, veces: int = 1) -> None:
        fin = time.monotonic() + 5
        with self.hay:
            while time.monotonic() < fin:
                if sum(e.get("estado") == "reposo" for e in self.eventos) >= veces:
                    return
                self.hay.wait(0.05)
        raise AssertionError(self.eventos)


class Guion:
    """Responde por guion en el agente; ``generate`` es lo que usa el resumen."""

    model_name = "guion"

    def __init__(self, *pasos: PasoModelo, resumen: str = "") -> None:
        self.pasos = list(pasos)
        self.resumen = resumen
        self.systems: list[str] = []

    def paso(self, conversacion, herramientas, *, system=None):
        self.systems.append(system or "")
        return self.pasos.pop(0)

    def generate(self, prompt, *, system=None, historial=()):
        return self.resumen


def con_chat(historial: Historial, carpeta: str, titulo: str, resumen: str, respuesta: str) -> str:
    conv = historial.nueva(titulo, carpeta)
    conv["resumen"] = resumen
    conv["agente"] = [
        {"t": "usuario", "texto": titulo},
        {"t": "modelo", "texto": "", "llamadas": [{"id": "1", "nombre": "x", "argumentos": {}}]},
        {"t": "resultado", "id": "1", "nombre": "x", "contenido": "SECRETO de una pagina"},
        {"t": "modelo", "texto": respuesta, "llamadas": []},
    ]
    historial.guardar(conv)
    return conv["id"]


# -- el almacen -----------------------------------------------------------------------------
def test_el_contexto_junta_instrucciones_notas_y_los_otros_chats(tmp_path):
    h = Historial(tmp_path)
    h.crear_carpeta("Galeón")
    h.guardar_instrucciones("Galeón", "App de recetas pirata.")
    h.anotar_proyecto("Galeón", "Paleta: azul marino y dorado")
    propio = con_chat(h, "Galeón", "Diseño", "Tres pantallas: inicio, recetas, mapa.", "x")
    con_chat(h, "Otro", "Ajeno", "no deberia salir", "x")

    contexto = h.contexto_proyecto("Galeón")
    assert "App de recetas pirata." in contexto and "azul marino y dorado" in contexto
    assert "«Diseño»: Tres pantallas" in contexto and "no deberia salir" not in contexto
    assert "«Diseño»" not in h.contexto_proyecto("Galeón", excluir=propio)  # el suyo no


def test_leer_otro_chat_da_lo_pedido_y_lo_respondido_sin_lo_leido(tmp_path):
    h = Historial(tmp_path)
    con_chat(h, "Galeón", "Diseño de la app", "", "Pantalla de inicio con un cofre.")

    leido = h.leer_chat("Galeón", "diseño")
    assert "Usuario: Diseño de la app" in leido and "D.O.O.M: Pantalla de inicio" in leido
    assert "SECRETO" not in leido
    assert "«Diseño de la app»" in h.leer_chat("Galeón", "no existe")  # dice cuales hay


def test_renombrar_y_borrar_el_proyecto_mueven_sus_datos(tmp_path):
    h = Historial(tmp_path)
    h.guardar_instrucciones("Viejo", "instrucciones")
    h.renombrar_carpeta("Viejo", "Nuevo")
    assert h.proyecto("Nuevo")["instrucciones"] == "instrucciones"
    h.borrar_carpeta("Nuevo")
    assert h.proyecto("Nuevo")["instrucciones"] == ""
    with pytest.raises(ValueError):
        h.guardar_instrucciones("", "sin carpeta no es un proyecto")


# -- en los modos ---------------------------------------------------------------------------
def test_el_proyecto_llega_a_cualquier_modo_y_se_puede_quitar(tmp_path):
    h = Historial(tmp_path)
    h.guardar_instrucciones("Galeón", "App de recetas pirata.")
    m = montar(narrar=lambda *a: None, confirmar=lambda p: True, cerebro_=Guion())

    m.modos.poner_proyecto(ProyectoActivo(h, "Galeón"))
    for modo in (GLOBAL, "diseno"):
        m.modos.aplicar(modo)
        assert "App de recetas pirata." in m.agente.system
        assert {"leer_conversacion_proyecto", "anotar_en_proyecto"} <= set(m.agente.herramientas)

    m.modos.poner_proyecto(None)
    assert "pirata" not in m.agente.system
    assert "anotar_en_proyecto" not in m.agente.herramientas


# -- de punta a punta, por la ventana -----------------------------------------------------------
def test_un_chat_del_proyecto_deja_su_resumen_y_el_siguiente_lo_recibe(tmp_path):
    h = Historial(tmp_path)
    anotar = LlamadaHerramienta("c0", "anotar_en_proyecto", {"nota": "Nombre: Galeón"})
    cerebro = Guion(
        PasoModelo("", (anotar,)),
        PasoModelo("Propongo tres pantallas: inicio, recetas y mapa."),
        PasoModelo("Pantalla de inicio con el cofre."),
        resumen="Diseño: tres pantallas (inicio, recetas, mapa).",
    )
    puente = Puente(lambda **kw: montar(cerebro_=cerebro, **kw), historial=h)
    ventana = VentanaFalsa()
    puente._conectar(ventana)
    puente.iniciar()

    puente.nuevo("Galeón")
    primero = puente.enviar("diseña la app")["id"]
    ventana.esperar_reposo()
    assert h.leer(primero)["resumen"] == "Diseño: tres pantallas (inicio, recetas, mapa)."
    assert h.proyecto("Galeón")["notas"][0].endswith("Nombre: Galeón")

    puente.nuevo("Galeón")
    puente.enviar("genera la pantalla de inicio")
    ventana.esperar_reposo(2)
    system = cerebro.systems[-1]
    assert "«diseña la app»: Diseño: tres pantallas" in system
    assert "Nombre: Galeón" in system
    puente._cerrar()
