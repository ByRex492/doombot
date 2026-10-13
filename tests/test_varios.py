"""Varios modelos (D-034): backend compatible con OpenAI, catalogo, cadena, consejo y revisor.

Sin red ni claves: transportes falsos de httpx y modelos de juguete.
"""

from __future__ import annotations

import json

import httpx
import pytest

from doombot.agent.bucle import Agente
from doombot.agent.herramientas import Herramienta
from doombot.agent.revision import revisor
from doombot.backends.base import (
    BackendError,
    EspecHerramienta,
    LlamadaHerramienta,
    PasoModelo,
    ResultadoHerramienta,
    TextGenerator,
    ToolCaller,
)
from doombot.backends.openai_compat import LimiteAlcanzado, OpenAICompatGenerator
from doombot.backends.proveedores import construir, construir_todos, partir
from doombot.backends.varios import Cadena, Consejo, etiqueta
from doombot.config import Settings


def cfg(**kw) -> Settings:
    return Settings(ollama_host="http://127.0.0.1:11434", log_level="INFO", **kw)


def cliente(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def respuesta(mensaje: dict, codigo: int = 200):
    enviado: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        enviado["url"] = str(req.url)
        enviado["auth"] = req.headers.get("authorization")
        enviado["cuerpo"] = json.loads(req.content)
        return httpx.Response(codigo, json={"choices": [{"message": mensaje}]})

    return enviado, cliente(handler)


# -- backend compatible con OpenAI ----------------------------------------------
def test_cumple_los_dos_contratos():
    g = OpenAICompatGenerator("m", base_url="https://x/v1", api_key="k", proveedor="groq")
    assert isinstance(g, TextGenerator)
    assert isinstance(g, ToolCaller)
    assert g.model_name == "groq/m"


def test_generate_manda_clave_y_url_y_quita_el_razonamiento():
    enviado, c = respuesta({"content": "<think>hmm</think>Madrid."})
    g = OpenAICompatGenerator("m", base_url="https://api.x/v1/", api_key="k", client=c)
    assert g.generate("capital de España", system="breve") == "Madrid."
    assert enviado["url"] == "https://api.x/v1/chat/completions"
    assert enviado["auth"] == "Bearer k"
    assert enviado["cuerpo"]["messages"][0] == {"role": "system", "content": "breve"}


def test_paso_traduce_al_formato_openai_y_lee_tool_calls():
    enviado, c = respuesta(
        {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_9",
                    "type": "function",
                    "function": {"name": "abrir_aplicacion", "arguments": '{"nombre": "calc"}'},
                }
            ],
        }
    )
    g = OpenAICompatGenerator("m", base_url="https://x/v1", api_key="k", client=c)
    espec = EspecHerramienta("abrir_aplicacion", "abre", {"type": "object", "properties": {}})
    conversacion = [
        "abre firefox",
        PasoModelo("", (LlamadaHerramienta("call_1", "abrir_aplicacion", {"nombre": "ff"}),)),
        ResultadoHerramienta("call_1", "abrir_aplicacion", "Abierta."),
    ]

    paso = g.paso(conversacion, [espec])

    assert paso == PasoModelo(
        "", (LlamadaHerramienta("call_9", "abrir_aplicacion", {"nombre": "calc"}),)
    )
    mensajes = enviado["cuerpo"]["messages"]
    assert mensajes[1]["tool_calls"][0]["function"]["arguments"] == '{"nombre": "ff"}'
    assert mensajes[2] == {"role": "tool", "tool_call_id": "call_1", "content": "Abierta."}
    assert enviado["cuerpo"]["temperature"] == 0
    assert enviado["cuerpo"]["tools"][0]["function"]["name"] == "abrir_aplicacion"


def test_stream_lee_eventos_sse():
    cuerpo = "\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Ho"}}]}',
            'data: {"choices":[{"delta":{"content":"la"}}]}',
            "data: [DONE]",
        ]
    ).encode()
    c = cliente(lambda req: httpx.Response(200, content=cuerpo))
    g = OpenAICompatGenerator("m", base_url="https://x/v1", api_key="k", client=c)
    assert "".join(g.stream("hola")) == "Hola"


def test_sin_cuota_es_un_error_propio():
    _, c = respuesta({}, codigo=429)
    g = OpenAICompatGenerator("m", base_url="https://x/v1", api_key="k", proveedor="groq", client=c)
    with pytest.raises(LimiteAlcanzado, match="limite de uso gratuito"):
        g.generate("x")


def test_sin_clave_dice_cual_falta():
    g = OpenAICompatGenerator("m", base_url="https://x/v1", proveedor="gemini")
    with pytest.raises(BackendError, match="DOOMBOT_GEMINI_API_KEY"):
        g.generate("x")


# -- catalogo -------------------------------------------------------------------
def test_partir_por_el_primer_dos_puntos():
    assert partir("ollama:qwen3:4b") == ("ollama", "qwen3:4b")
    assert partir("openrouter:x/y:free") == ("openrouter", "x/y:free")


def test_construir_cada_tipo():
    c = cfg(claves=(("groq", "k1"),), anthropic_api_key="ka")
    groq = construir("groq:openai/gpt-oss-120b", c)
    assert isinstance(groq, OpenAICompatGenerator)
    assert etiqueta(groq) == "groq/openai/gpt-oss-120b"
    assert etiqueta(construir("ollama:qwen3:4b", c)) == "ollama/qwen3:4b"
    assert etiqueta(construir("anthropic:claude-x", c)) == "anthropic/claude-x"


@pytest.mark.parametrize(
    ("entrada", "error"),
    [
        ("groq:modelo", "DOOMBOT_GROQ_API_KEY"),
        ("inventado:modelo", "proveedor desconocido"),
        ("groq", "falta el modelo"),
    ],
)
def test_construir_dice_que_falta(entrada, error):
    with pytest.raises(ValueError, match=error):
        construir(entrada, cfg())


def test_construir_todos_salta_los_que_no_tienen_clave():
    c = cfg(modelos=("groq:a", "gemini:b", "ollama:c"), claves=(("groq", "k"),))
    generadores, avisos = construir_todos(c)
    assert [etiqueta(g) for g in generadores] == ["groq/a", "ollama/c"]
    assert len(avisos) == 1 and "DOOMBOT_GEMINI_API_KEY" in avisos[0]
    assert "aistudio.google.com" in avisos[0]


def test_las_claves_salen_del_entorno(monkeypatch):
    from doombot import config

    monkeypatch.setenv("DOOMBOT_GROQ_API_KEY", "  gsk  ")
    monkeypatch.setenv("DOOMBOT_NVIDIA_API_KEY", "")
    monkeypatch.setenv("DOOMBOT_MODELOS", "groq:a, gemini:b")
    monkeypatch.setattr(config, "load_env", lambda *a, **k: {})
    config.settings.cache_clear()
    try:
        s = config.settings()
        assert s.clave("groq") == "gsk"
        assert s.clave("nvidia") == ""
        assert s.modelos == ("groq:a", "gemini:b")
    finally:
        config.settings.cache_clear()


# -- cadena -----------------------------------------------------------------------
class Juguete:
    """Un modelo que responde lo que se le diga, o falla como se le diga."""

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

    def stream(self, prompt, *, system=None, historial=()):
        if self.fallo:
            raise self.fallo
        yield from self.respuesta.split(" ")

    def paso(self, conversacion, herramientas, *, system=None):
        return PasoModelo(self.generate(str(conversacion[-1])))


def test_la_cadena_cumple_los_contratos():
    cadena = Cadena([Juguete("a")])
    assert isinstance(cadena, TextGenerator) and isinstance(cadena, ToolCaller)


def test_si_el_primero_falla_responde_el_siguiente_y_se_avisa():
    avisos: list[str] = []
    a, b = Juguete("a", fallo=BackendError("a: sin conexion")), Juguete("b")
    cadena = Cadena([a, b], avisar=avisos.append)

    assert cadena.generate("hola") == "soy b"
    assert cadena.paso(["hola"], []).texto == "soy b"
    assert cadena.ultimo is b
    assert avisos[:2] == ["a no responde (sin conexion)", "sigo con b"]


def test_sin_cuota_se_aparta_un_rato_y_luego_vuelve():
    reloj = [0.0]
    a = Juguete("a", fallo=LimiteAlcanzado("a: limite"))
    b = Juguete("b")
    cadena = Cadena([a, b], espera_limite=60, reloj=lambda: reloj[0])

    cadena.generate("1")
    cadena.generate("2")
    assert len(a.llamadas) == 1  # el segundo turno ya no lo intenta con a

    reloj[0] = 61
    a.fallo = None
    assert cadena.generate("3") == "soy a"


def test_si_todos_fallan_lo_dice_con_cada_motivo():
    cadena = Cadena(
        [Juguete("a", fallo=BackendError("a: x")), Juguete("b", fallo=BackendError("b: y"))]
    )
    with pytest.raises(BackendError, match="Ningun modelo") as e:
        cadena.generate("hola")
    assert "a: x" in str(e.value) and "b: y" in str(e.value)


def test_stream_cambia_de_modelo_solo_antes_del_primer_trozo():
    cadena = Cadena([Juguete("a", fallo=BackendError("a: caido")), Juguete("b", "hola que tal")])
    assert list(cadena.stream("x")) == ["hola", "que", "tal"]


# -- consejo ----------------------------------------------------------------------
def test_el_consejo_pregunta_a_todos_y_el_juez_compara():
    a, b = Juguete("a", "Madrid"), Juguete("b", "Madrid, desde 1561")
    juez = Juguete("juez", "Coinciden: Madrid.")
    veredicto = Consejo([a, b], juez=juez).consultar("capital de España")

    assert [o.texto for o in veredicto.opiniones] == ["Madrid", "Madrid, desde 1561"]
    assert veredicto.final == "Coinciden: Madrid."
    assert "Respuesta de a:\nMadrid" in juez.llamadas[0]
    assert "Respuesta de b:\nMadrid, desde 1561" in juez.llamadas[0]


def test_si_solo_responde_uno_se_dice_que_no_hay_contraste():
    consejo = Consejo([Juguete("a", "42"), Juguete("b", fallo=BackendError("b: caido"))])
    veredicto = consejo.consultar("x")
    assert veredicto.final.startswith("42")
    assert "sin contraste" in veredicto.final
    assert veredicto.opiniones[1].fallo


def test_si_no_responde_ninguno_falla():
    with pytest.raises(BackendError):
        Consejo([Juguete("a", fallo=BackendError("a: caido"))]).consultar("x")


# -- segunda opinion en el agente -------------------------------------------------
def test_el_revisor_es_otro_modelo_distinto_del_que_propuso():
    a, b = Juguete("a"), Juguete("b", "OJO: el usuario no pidio borrar nada")
    cadena = Cadena([a, b])
    cadena.generate("propuesta")  # responde a: es el que propone
    opinion = revisor(cadena)("abre firefox", "ejecutar_comando(rm -rf ~)")

    assert opinion == "OJO: el usuario no pidio borrar nada (b)"
    assert "rm -rf" in b.llamadas[0]


def test_con_un_solo_modelo_no_hay_revisor():
    assert revisor(Cadena([Juguete("a")])) is None


def test_la_segunda_opinion_acompana_a_la_pregunta():
    preguntas: list[str] = []
    llamada = LlamadaHerramienta("c0", "borrar", {"ruta": "x"})

    class Cerebro:
        model_name = "c"

        def __init__(self):
            self.pasos = [PasoModelo("", (llamada,)), PasoModelo("fin")]

        def paso(self, *a, **k):
            return self.pasos.pop(0)

    agente = Agente(
        Cerebro(),
        [Herramienta("borrar", "borra", lambda ruta: "borrado", confirmar=lambda a: "¿Borro x?")],
        narrar=lambda *a: None,
        confirmar=lambda p: preguntas.append(p) or False,
        revisar=lambda tarea, propuesta: f"OJO: no encaja con «{tarea}»",
    )
    agente.ejecutar("abre firefox")

    assert preguntas == ["¿Borro x?\n      Segunda opinion: OJO: no encaja con «abre firefox»"]
