"""``paso()`` en Ollama y en Anthropic: la misma conversacion neutra, dos formatos.

Con un transporte falso de httpx, como test_ollama.py y test_anthropic.py: se
comprueba lo que se envia y como se lee lo que vuelve, sin red ni clave.
"""

from __future__ import annotations

import json

import httpx

from doombot.backends.anthropic import AnthropicGenerator
from doombot.backends.base import (
    EspecHerramienta,
    LlamadaHerramienta,
    PasoModelo,
    ResultadoHerramienta,
    ToolCaller,
)
from doombot.backends.ollama import OllamaGenerator

ESPEC = EspecHerramienta(
    "abrir_aplicacion",
    "Abre una app",
    {"type": "object", "properties": {"nombre": {"type": "string"}}, "required": ["nombre"]},
)
CONVERSACION = [
    "abre firefox",
    PasoModelo(
        "Abro Firefox.", (LlamadaHerramienta("t1", "abrir_aplicacion", {"nombre": "firefox"}),)
    ),
    ResultadoHerramienta("t1", "abrir_aplicacion", "Abierta Firefox."),
]


def capturar(respuesta: dict):
    enviado: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        enviado.update(json.loads(req.content))
        return httpx.Response(200, json=respuesta)

    return enviado, httpx.Client(transport=httpx.MockTransport(handler))


# -- Ollama ---------------------------------------------------------------------
def test_ollama_cumple_tool_caller():
    assert isinstance(OllamaGenerator("m"), ToolCaller)


def test_ollama_envia_herramientas_y_traduce_la_conversacion():
    enviado, cliente = capturar({"message": {"role": "assistant", "content": "Listo."}})
    gen = OllamaGenerator("qwen3:4b", client=cliente)

    paso = gen.paso(CONVERSACION, [ESPEC], system="reglas")

    assert paso == PasoModelo("Listo.")
    assert enviado["stream"] is False
    assert enviado["options"]["temperature"] == 0
    assert enviado["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "abrir_aplicacion",
                "description": "Abre una app",
                "parameters": ESPEC.parametros,
            },
        }
    ]
    assert enviado["messages"] == [
        {"role": "system", "content": "reglas"},
        {"role": "user", "content": "abre firefox"},
        {
            "role": "assistant",
            "content": "Abro Firefox.",
            "tool_calls": [
                {"function": {"name": "abrir_aplicacion", "arguments": {"nombre": "firefox"}}}
            ],
        },
        {"role": "tool", "content": "Abierta Firefox.", "tool_name": "abrir_aplicacion"},
    ]


def test_ollama_lee_llamadas_con_argumentos_objeto_o_texto_y_sin_id():
    _, cliente = capturar(
        {
            "message": {
                "content": "<think>el usuario quiere...</think>Voy.",
                "tool_calls": [
                    {"function": {"name": "a", "arguments": {"x": 1}}},
                    {"function": {"name": "b", "arguments": '{"y": "dos"}'}},
                ],
            }
        }
    )
    paso = OllamaGenerator("m", client=cliente).paso(["hola"], [ESPEC])

    assert paso.texto == "Voy."  # sin el razonamiento interno
    assert paso.llamadas == (
        LlamadaHerramienta("llamada_0", "a", {"x": 1}),
        LlamadaHerramienta("llamada_1", "b", {"y": "dos"}),
    )


# -- Anthropic ------------------------------------------------------------------
def test_anthropic_cumple_tool_caller():
    assert isinstance(AnthropicGenerator(api_key="x"), ToolCaller)


def test_anthropic_envia_herramientas_y_bloques():
    enviado, cliente = capturar({"content": [{"type": "text", "text": "Listo."}]})
    gen = AnthropicGenerator("claude-x", api_key="clave", client=cliente)

    paso = gen.paso([*CONVERSACION, "y ahora cierralo"], [ESPEC], system="reglas")

    assert paso == PasoModelo("Listo.")
    assert enviado["system"] == "reglas"
    assert enviado["temperature"] == 0
    assert enviado["tools"] == [
        {
            "name": "abrir_aplicacion",
            "description": "Abre una app",
            "input_schema": ESPEC.parametros,
        }
    ]
    assert enviado["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "abre firefox"}]},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Abro Firefox."},
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "abrir_aplicacion",
                    "input": {"nombre": "firefox"},
                },
            ],
        },
        # Resultado y orden nueva en el MISMO mensaje: la API exige alternar roles.
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "Abierta Firefox."},
                {"type": "text", "text": "y ahora cierralo"},
            ],
        },
    ]


def test_anthropic_lee_texto_y_tool_use():
    _, cliente = capturar(
        {
            "content": [
                {"type": "text", "text": "Abro la calculadora."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "abrir_aplicacion",
                    "input": {"nombre": "calc"},
                },
            ],
            "stop_reason": "tool_use",
        }
    )
    paso = AnthropicGenerator(api_key="x", client=cliente).paso(["abre la calculadora"], [ESPEC])
    assert paso == PasoModelo(
        "Abro la calculadora.",
        (LlamadaHerramienta("toolu_1", "abrir_aplicacion", {"nombre": "calc"}),),
    )
