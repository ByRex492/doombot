"""El generador de Ollama, probado sin Ollama.

Todo lo de aqui corre en cualquier equipo y sin GPU. Es posible porque la
clase acepta un cliente HTTP por parametro: se le pasa uno falso que responde
lo que convenga a cada prueba. Sin esa costura, estos tests exigirian un
servidor arrancado y un modelo de gigabytes descargado.
"""

from __future__ import annotations

import json

import httpx
import pytest

from doombot.backends.base import BackendError, TextGenerator
from doombot.backends.ollama import OllamaGenerator
from doombot.config import Settings
from doombot.profiles import Profile


def cliente_falso(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def perfil_portatil() -> Profile:
    return Profile(
        name="laptop",
        description="",
        min_vram_mb=2048,
        llm_model="llama3.2:3b",
        llm_num_ctx=4096,
        llm_num_gpu=99,
        llm_keep_alive="5m",
        stt_model="small",
        stt_device="cpu",
        stt_compute="int8",
    )


# -- el contrato ------------------------------------------------------------
def test_cumple_el_contrato():
    """No hereda de TextGenerator, pero lo satisface. Eso es un Protocol."""
    gen = OllamaGenerator("m")
    assert isinstance(gen, TextGenerator)
    assert not issubclass(OllamaGenerator, TextGenerator.__mro__[1])


def test_cualquier_objeto_con_los_metodos_vale():
    """Un doble de pruebas cumple el contrato sin importar nada del proyecto.

    Es lo que permitira desarrollar la memoria y las frases sin Ollama.
    """

    class Doble:
        model_name = "doble"

        def generate(self, prompt, *, system=None):
            return "respuesta fija"

        def stream(self, prompt, *, system=None):
            yield "respuesta fija"

    assert isinstance(Doble(), TextGenerator)


# -- construccion desde el perfil -------------------------------------------
def test_from_profile_traslada_los_ajustes(perfil_portatil):
    capturado = {}

    def handler(req: httpx.Request) -> httpx.Response:
        capturado.update(json.loads(req.content))
        return httpx.Response(200, json={"response": "ok"})

    cfg = Settings(ollama_host="http://127.0.0.1:11434", log_level="INFO")
    gen = OllamaGenerator.from_profile(perfil_portatil, cfg, client=cliente_falso(handler))
    gen.generate("hola")

    assert capturado["model"] == "llama3.2:3b"
    assert capturado["options"]["num_ctx"] == 4096
    assert capturado["options"]["num_gpu"] == 99  # el ajuste critico del portatil
    assert capturado["keep_alive"] == "5m"


def test_num_gpu_cero_no_se_envia():
    """0 significa 'decide tu'. Mandarlo diria 'ninguna capa en GPU'."""
    capturado = {}

    def handler(req: httpx.Request) -> httpx.Response:
        capturado.update(json.loads(req.content))
        return httpx.Response(200, json={"response": "ok"})

    OllamaGenerator("m", num_gpu=0, client=cliente_falso(handler)).generate("hola")
    assert "num_gpu" not in capturado["options"]


def test_from_profile_usa_el_host_de_la_configuracion(perfil_portatil):
    """Apuntar al sobremesa por red no cambia la clase, solo el host."""
    cfg = Settings(ollama_host="http://192.168.1.40:11434", log_level="INFO")
    gen = OllamaGenerator.from_profile(perfil_portatil, cfg)
    assert "192.168.1.40" in repr(gen)


# -- generacion --------------------------------------------------------------
def test_generate_devuelve_el_texto_limpio():
    def handler(req):
        return httpx.Response(200, json={"response": "  hola qué tal  ", "done": True})

    assert OllamaGenerator("m", client=cliente_falso(handler)).generate("x") == "hola qué tal"


def test_system_prompt_solo_si_lo_hay():
    cuerpos = []

    def handler(req):
        cuerpos.append(json.loads(req.content))
        return httpx.Response(200, json={"response": "ok"})

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    gen.generate("x")
    gen.generate("x", system="Eres D.O.O.M.")
    assert "system" not in cuerpos[0]
    assert cuerpos[1]["system"] == "Eres D.O.O.M."


def test_stream_va_entregando_fragmentos():
    lineas = [
        json.dumps({"response": "Hola"}),
        json.dumps({"response": " mundo"}),
        json.dumps({"done": True}),
    ]

    def handler(req):
        return httpx.Response(200, content="\n".join(lineas).encode())

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    assert list(gen.stream("x")) == ["Hola", " mundo"]


def test_stream_ignora_lineas_corruptas():
    """Un corte de red a mitad no debe reventar la voz."""

    def handler(req):
        contenido = f"{json.dumps({'response': 'a'})}\n{{rota\n{json.dumps({'done': True})}"
        return httpx.Response(200, content=contenido.encode())

    assert list(OllamaGenerator("m", client=cliente_falso(handler)).stream("x")) == ["a"]


# -- errores traducidos -------------------------------------------------------
def test_sin_servidor_dice_que_hacer():
    def handler(req):
        raise httpx.ConnectError("sin conexion", request=req)

    with pytest.raises(BackendError, match="DOOMBOT_OLLAMA_HOST"):
        OllamaGenerator("m", client=cliente_falso(handler)).generate("x")


def test_modelo_ausente_da_el_comando_de_descarga():
    def handler(req):
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(BackendError, match="ollama pull llama3.2:3b"):
        OllamaGenerator("llama3.2:3b", client=cliente_falso(handler)).generate("x")


def test_timeout_apunta_al_reparto_cpu_gpu():
    def handler(req):
        raise httpx.ReadTimeout("lento", request=req)

    with pytest.raises(BackendError, match="100% GPU"):
        OllamaGenerator("m", client=cliente_falso(handler)).generate("x")


def test_is_available_no_lanza():
    def handler(req):
        raise httpx.ConnectError("no", request=req)

    assert OllamaGenerator("m", client=cliente_falso(handler)).is_available() is False


# -- contra el Ollama de verdad ----------------------------------------------
@pytest.mark.hardware
def test_contra_ollama_real():
    """Se salta con: pytest -m 'not hardware'"""
    from doombot import profiles

    gen = OllamaGenerator.from_profile(profiles.current())
    if not gen.is_available():
        pytest.skip("Ollama no esta arrancado")
    assert gen.generate("Responde solo con la palabra: listo")
