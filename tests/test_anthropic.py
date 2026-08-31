"""El generador de Anthropic, probado sin clave ni red.

Mismo enfoque que test_ollama.py: un transporte falso de httpx sustituye la
API real, asi que estos tests corren en cualquier equipo y sin gastar cuota.
"""

from __future__ import annotations

import json

import httpx
import pytest

from doombot.backends.anthropic import AnthropicGenerator
from doombot.backends.base import BackendError, TextGenerator
from doombot.config import Settings


def cliente_falso(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def sse(*eventos: dict) -> bytes:
    """Arma un cuerpo de server-sent events como el de la API real."""
    return "\n".join(f"data: {json.dumps(e)}" for e in eventos).encode()


# -- el contrato --------------------------------------------------------------
def test_cumple_el_contrato():
    gen = AnthropicGenerator("claude-sonnet-5", api_key="x")
    assert isinstance(gen, TextGenerator)
    assert not issubclass(AnthropicGenerator, TextGenerator.__mro__[1])


# -- construccion desde la configuracion --------------------------------------
def test_from_config_traslada_los_ajustes():
    cfg = Settings(
        ollama_host="http://127.0.0.1:11434",
        log_level="INFO",
        anthropic_api_key="clave-de-prueba",
        anthropic_model="claude-opus-5",
    )
    gen = AnthropicGenerator.from_config(cfg)
    assert gen.model_name == "claude-opus-5"
    assert gen.is_available()


def test_sin_clave_no_esta_disponible():
    assert AnthropicGenerator("m").is_available() is False


# -- generacion ----------------------------------------------------------------
def test_generate_junta_los_bloques_de_texto():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "  hola qué tal  "}]},
        )

    gen = AnthropicGenerator("m", api_key="x", client=cliente_falso(handler))
    assert gen.generate("x") == "hola qué tal"


def test_generate_sin_clave_no_llega_a_la_red():
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("no deberia llamar a la red sin clave")

    with pytest.raises(BackendError, match="DOOMBOT_ANTHROPIC_API_KEY"):
        AnthropicGenerator("m", client=cliente_falso(handler)).generate("x")


def test_cuerpo_incluye_modelo_y_mensaje():
    capturado = {}

    def handler(req: httpx.Request) -> httpx.Response:
        capturado.update(json.loads(req.content))
        return httpx.Response(200, json={"content": []})

    AnthropicGenerator("claude-sonnet-5", api_key="x", client=cliente_falso(handler)).generate(
        "hola"
    )
    assert capturado["model"] == "claude-sonnet-5"
    assert capturado["messages"] == [{"role": "user", "content": "hola"}]
    assert capturado["stream"] is False


def test_system_prompt_solo_si_lo_hay():
    cuerpos = []

    def handler(req: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(req.content))
        return httpx.Response(200, json={"content": []})

    gen = AnthropicGenerator("m", api_key="x", client=cliente_falso(handler))
    gen.generate("x")
    gen.generate("x", system="Eres D.O.O.M.")
    assert "system" not in cuerpos[0]
    assert cuerpos[1]["system"] == "Eres D.O.O.M."


def test_la_clave_va_en_la_cabecera():
    cabeceras = []

    def handler(req: httpx.Request) -> httpx.Response:
        cabeceras.append(req.headers)
        return httpx.Response(200, json={"content": []})

    AnthropicGenerator("m", api_key="clave-secreta", client=cliente_falso(handler)).generate("x")
    assert cabeceras[0]["x-api-key"] == "clave-secreta"


# -- streaming ------------------------------------------------------------------
def test_stream_entrega_solo_los_deltas_de_texto():
    cuerpo = sse(
        {"type": "message_start"},
        {"type": "content_block_start", "index": 0},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hola"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " mundo"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_stop"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=cuerpo)

    gen = AnthropicGenerator("m", api_key="x", client=cliente_falso(handler))
    assert list(gen.stream("x")) == ["Hola", " mundo"]


def test_stream_ignora_lineas_que_no_son_delta_de_texto():
    cuerpo = sse(
        {"type": "ping"},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "a"}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
        {"type": "message_stop"},
    )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=cuerpo)

    gen = AnthropicGenerator("m", api_key="x", client=cliente_falso(handler))
    assert list(gen.stream("x")) == ["a"]


def test_stream_sin_clave_no_llega_a_la_red():
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("no deberia llamar a la red sin clave")

    with pytest.raises(BackendError, match="DOOMBOT_ANTHROPIC_API_KEY"):
        list(AnthropicGenerator("m", client=cliente_falso(handler)).stream("x"))


# -- errores traducidos ----------------------------------------------------------
def test_clave_invalida_dice_donde_arreglarlo():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    with pytest.raises(BackendError, match="DOOMBOT_ANTHROPIC_API_KEY"):
        AnthropicGenerator("m", api_key="mala", client=cliente_falso(handler)).generate("x")


def test_modelo_ausente_apunta_a_la_variable_de_entorno():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "model not found"}})

    gen = AnthropicGenerator("modelo-que-no-existe", api_key="x", client=cliente_falso(handler))
    with pytest.raises(BackendError, match="DOOMBOT_ANTHROPIC_MODEL"):
        gen.generate("x")


def test_limite_de_peticiones():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with pytest.raises(BackendError, match="Limite de peticiones"):
        AnthropicGenerator("m", api_key="x", client=cliente_falso(handler)).generate("x")


def test_sin_conexion_lo_dice():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin conexion", request=req)

    with pytest.raises(BackendError, match="conexion a internet"):
        AnthropicGenerator("m", api_key="x", client=cliente_falso(handler)).generate("x")


def test_timeout_lo_dice():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=req)

    with pytest.raises(BackendError, match="tardo demasiado"):
        AnthropicGenerator("m", api_key="x", client=cliente_falso(handler)).generate("x")


def test_stream_traduce_errores_http_tambien():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

    with pytest.raises(BackendError, match="DOOMBOT_ANTHROPIC_API_KEY"):
        list(AnthropicGenerator("m", api_key="mala", client=cliente_falso(handler)).stream("x"))


# -- contra la API real ----------------------------------------------------------
@pytest.mark.hardware
def test_contra_anthropic_real():
    """Se salta con: pytest -m 'not hardware'. Necesita DOOMBOT_ANTHROPIC_API_KEY."""
    from doombot.config import settings

    gen = AnthropicGenerator.from_config(settings())
    if not gen.is_available():
        pytest.skip("DOOMBOT_ANTHROPIC_API_KEY no esta configurada")
    assert gen.generate("Responde solo con la palabra: listo")
