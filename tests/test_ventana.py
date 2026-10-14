"""El puente entre la ventana y el agente, sin ventana: un doble recoge lo que se le pinta."""

from __future__ import annotations

import json
import threading
import time

from doombot.agent.herramientas import Herramienta, texto
from doombot.agent.montaje import montar
from doombot.backends.base import LlamadaHerramienta, PasoModelo
from doombot.ventana import HTML
from doombot.ventana.puente import Puente


class VentanaFalsa:
    def __init__(self) -> None:
        self.eventos: list[dict] = []
        self.hay = threading.Condition()

    def evaluate_js(self, js: str) -> None:
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

    def __init__(self, *pasos: PasoModelo) -> None:
        self.pasos = list(pasos)

    def paso(self, conversacion, herramientas, *, system=None):
        return self.pasos.pop(0)


def puente_con(*pasos: PasoModelo, herramientas=()) -> tuple[Puente, VentanaFalsa]:
    def montar_prueba(**kw):
        m = montar(cerebro_=Guion(*pasos), **kw)
        for h in herramientas:
            m.agente.herramientas[h.nombre] = h
        return m

    puente = Puente(montar_prueba)
    ventana = VentanaFalsa()
    puente._conectar(ventana)
    return puente, ventana


def test_la_ventana_existe():
    assert HTML.is_file()
    assert "DOOM.evento" in HTML.read_text(encoding="utf-8")


def test_iniciar_dice_con_que_cerebro_se_queda():
    puente, _ = puente_con()
    info = puente.iniciar()
    assert info["ok"] and info["modelos"] == ["guion/guion"]
    # 17 del agente + calcular + mostrar_grafica (hay pantalla) + aprender y consultar_skill
    assert info["herramientas"] == 21
    puente._cerrar()


def test_una_orden_se_cuenta_paso_a_paso():
    eco = Herramienta(
        "eco", "repite", lambda msg: f"eco {msg}", {"msg": texto("x")}, familia="web",
        narrar=lambda a: f"Repito {a['msg']}",
    )  # fmt: skip
    puente, ventana = puente_con(
        PasoModelo("Voy a repetirlo.", (LlamadaHerramienta("1", "eco", {"msg": "hola"}),)),
        PasoModelo("Hecho."),
        herramientas=[eco],
    )
    puente.iniciar()
    assert puente.enviar("repite hola")["ok"]
    ventana.esperar("estado", estado="reposo")

    tipos = [e["tipo"] for e in ventana.eventos]
    assert tipos == [
        "estado",
        "pensando",
        "comentario",
        "herramienta",
        "accion",
        "resultado",
        "pensando",
        "respuesta",
        "historial",  # la conversacion se guarda al acabar la orden (D-038)
        "estado",
    ]
    assert ventana.esperar("herramienta")["familia"] == "web"
    assert ventana.esperar("accion")["texto"] == "Repito hola"
    assert ventana.esperar("respuesta")["texto"] == "Hecho."
    puente._cerrar()


def test_la_confirmacion_espera_al_boton_y_la_opinion_va_aparte():
    hechas = []
    borrar = Herramienta(
        "borrar",
        "borra",
        lambda: hechas.append(1) or "borrado",
        confirmar=lambda a: "¿Borro?\n      Segunda opinion: OJO: no lo pidio",
    )
    puente, ventana = puente_con(
        PasoModelo("", (LlamadaHerramienta("1", "borrar", {}),)),
        PasoModelo("fin"),
        herramientas=[borrar],
    )
    puente.iniciar()
    puente.enviar("borra")
    permiso = ventana.esperar("permiso")
    assert permiso["pregunta"] == "¿Borro?"
    assert permiso["opinion"] == "OJO: no lo pidio"
    assert hechas == []

    puente.responder(permiso["id"], True)
    ventana.esperar("estado", estado="reposo")
    assert hechas == [1]
    puente._cerrar()


def test_parar_cuenta_como_no_en_una_confirmacion_pendiente():
    hechas = []
    borrar = Herramienta(
        "borrar", "borra", lambda: hechas.append(1) or "x", confirmar=lambda a: "¿?"
    )
    puente, ventana = puente_con(
        PasoModelo("", (LlamadaHerramienta("1", "borrar", {}),)),
        PasoModelo("no seguire"),
        herramientas=[borrar],
    )
    puente.iniciar()
    puente.enviar("borra")
    ventana.esperar("permiso")
    puente.parar()
    respuesta = ventana.esperar("respuesta")
    assert hechas == []
    assert respuesta["completo"] is False
    puente._cerrar()


def test_no_acepta_otra_orden_mientras_trabaja():
    lenta = Herramienta("lenta", "tarda", lambda: time.sleep(0.3) or "ya")
    puente, ventana = puente_con(
        PasoModelo("", (LlamadaHerramienta("1", "lenta", {}),)),
        PasoModelo("fin"),
        herramientas=[lenta],
    )
    puente.iniciar()
    assert puente.enviar("primera")["ok"]
    assert puente.enviar("segunda") == {"ok": False, "error": "Sigo con la orden anterior."}
    ventana.esperar("estado", estado="reposo")
    puente._cerrar()


def test_sin_cerebro_lo_dice_en_vez_de_romper():
    def falla(**kw):
        raise ValueError("Ningun modelo de DOOMBOT_MODELOS se puede usar")

    puente = Puente(falla)
    info = puente.iniciar()
    assert info == {"ok": False, "error": "Ningun modelo de DOOMBOT_MODELOS se puede usar"}
    assert puente.enviar("hola")["ok"] is False
    puente._cerrar()


def test_los_enlaces_solo_se_abren_si_son_web(monkeypatch):
    import webbrowser

    abiertos = []
    monkeypatch.setattr(webbrowser, "open", lambda url, new=0: abiertos.append(url))
    puente = Puente()
    puente.abrir_enlace("https://aemet.es")
    puente.abrir_enlace("file:///etc/passwd")
    puente.abrir_enlace("javascript:alert(1)")
    assert abiertos == ["https://aemet.es"]
    puente._cerrar()


def test_pywebview_solo_ve_metodos():
    """pywebview expone a JavaScript los atributos publicos del objeto: ninguno debe serlo."""
    puente = Puente()
    publicos = [n for n in vars(puente) if not n.startswith("_")]
    assert publicos == []
    puente._cerrar()


def test_reintentar_ve_una_clave_pegada_despues_de_abrir(monkeypatch, tmp_path):
    """La clave vacia leida al abrir no debe tapar la que se pega luego en .env."""
    from doombot import config
    from doombot.ventana import puente as modulo

    env = tmp_path / ".env"
    env.write_text("DOOMBOT_GROQ_API_KEY=\n", encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.setenv("DOOMBOT_GROQ_API_KEY", "")
    monkeypatch.setenv("DOOMBOT_GEMINI_API_KEY", "la-del-entorno")

    env.write_text(
        "DOOMBOT_GROQ_API_KEY=gsk_nueva\nDOOMBOT_GEMINI_API_KEY=la-del-fichero\n", encoding="utf-8"
    )
    modulo._releer_env()
    try:
        assert config.settings().clave("groq") == "gsk_nueva"
        assert config.settings().clave("gemini") == "la-del-entorno"  # el entorno sigue mandando
    finally:
        config.settings.cache_clear()


def test_cerrar_dos_veces_no_rompe():
    puente, _ = puente_con()
    puente.iniciar()
    puente._cerrar()
    puente._cerrar()


def test_cerrar_no_espera_a_un_agente_ocupado():
    """Con una peticion larga en marcha, cerrar la ventana no se queda colgado."""
    puente = Puente()
    puente._hilo.submit(time.sleep, 3)
    inicio = time.monotonic()
    puente._cerrar()
    assert time.monotonic() - inicio < 1


# -- historial y modos (D-038) -----------------------------------------------------------
def test_una_orden_crea_su_conversacion_y_se_puede_retomar(tmp_path):
    from doombot.ventana.historial import Historial

    historial = Historial(tmp_path)

    def montar_prueba(**kw):
        return montar(cerebro_=Guion(PasoModelo("Hola."), PasoModelo("Sigo aqui.")), **kw)

    puente = Puente(montar_prueba, historial=historial)
    puente._conectar(VentanaFalsa())
    puente.iniciar()
    assert puente.nuevo("Trabajo") == {"ok": True}
    assert puente.poner_modo("programacion")["modo"] == "programacion"
    id_ = puente.enviar("primera orden")["id"]
    puente._ventana.esperar("estado", estado="reposo")

    guardada = historial.leer(id_)
    assert guardada["titulo"] == "primera orden" and guardada["carpeta"] == "Trabajo"
    assert guardada["modo"] == "programacion"
    assert [e["tipo"] for e in guardada["registro"]] == ["tu", "respuesta"]

    # Una nueva olvida; abrir la anterior la retoma con su estado y su modo.
    puente.nuevo()
    puente.poner_modo("global")
    assert puente._montaje.agente.conversacion == []
    abierta = puente.abrir_conversacion(id_)
    assert abierta["ok"] and abierta["modo"] == "programacion"
    assert puente._montaje.agente.conversacion[0] == "primera orden"
    assert puente.historial()["actual"] == id_
    puente._cerrar()


def test_borrar_la_conversacion_abierta_empieza_una_nueva(tmp_path):
    from doombot.ventana.historial import Historial

    historial = Historial(tmp_path)
    puente = Puente(
        lambda **kw: montar(cerebro_=Guion(PasoModelo("ok")), **kw), historial=historial
    )
    puente._conectar(VentanaFalsa())
    puente.iniciar()
    id_ = puente.enviar("algo")["id"]
    puente._ventana.esperar("estado", estado="reposo")

    assert puente.borrar_conversacion(id_) == {"ok": True}
    assert historial.lista() == []
    assert puente.historial()["actual"] is None
    assert puente.abrir_conversacion("../../x")["ok"] is False
    puente._cerrar()
