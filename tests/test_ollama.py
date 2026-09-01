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
        return httpx.Response(200, json={"message": {"content": "ok"}})

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
        return httpx.Response(200, json={"message": {"content": "ok"}})

    OllamaGenerator("m", num_gpu=0, client=cliente_falso(handler)).generate("hola")
    assert "num_gpu" not in capturado["options"]


def test_from_profile_usa_el_host(perfil_portatil):
    """Apuntar al sobremesa por red no cambia la clase, solo el host."""
    cfg = Settings(ollama_host="http://192.168.1.40:11434", log_level="INFO")
    gen = OllamaGenerator.from_profile(perfil_portatil, cfg)
    assert "192.168.1.40" in repr(gen)


# -- generacion --------------------------------------------------------------
def test_generate_devuelve_el_texto_limpio():
    def handler(req):
        return httpx.Response(200, json={"message": {"content": "  hola qué tal  "}, "done": True})

    assert OllamaGenerator("m", client=cliente_falso(handler)).generate("x") == "hola qué tal"


def test_system_prompt_solo_si_lo_hay():
    cuerpos = []

    def handler(req):
        cuerpos.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    gen.generate("x")
    gen.generate("x", system="Eres D.O.O.M.")

    # Sin system: un unico mensaje de usuario.
    assert [m["role"] for m in cuerpos[0]["messages"]] == ["user"]
    # Con system: va delante, como mensaje con rol propio.
    assert [m["role"] for m in cuerpos[1]["messages"]] == ["system", "user"]
    assert cuerpos[1]["messages"][0]["content"] == "Eres D.O.O.M."


def test_stream_va_entregando_fragmentos():
    lineas = [
        json.dumps({"message": {"content": "Hola"}}),
        json.dumps({"message": {"content": " mundo"}}),
        json.dumps({"done": True}),
    ]

    def handler(req):
        return httpx.Response(200, content="\n".join(lineas).encode())

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    assert list(gen.stream("x")) == ["Hola", " mundo"]


def test_stream_ignora_lineas_corruptas():
    """Un corte de red a mitad no debe reventar la voz."""

    def handler(req):
        bueno = json.dumps({"message": {"content": "a"}})
        contenido = f"{bueno}\n{{rota\n{json.dumps({'done': True})}"
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


# -- D-008: el endpoint no puede volver a cambiarse -------------------------
def test_usa_api_chat():
    """D-008. Medido en el sobremesa: /api/generate con gemma4:12b devolvia
    respuestas VACIAS. El fallo no aparece con todos los modelos —llama3.2:3b
    respondia bien— y por eso paso semanas sin detectarse: el codigo funcionaba
    en una maquina y devolvia el vacio en la otra.
    """
    rutas = []

    def handler(req: httpx.Request) -> httpx.Response:
        rutas.append(req.url.path)
        return httpx.Response(200, json={"message": {"content": "ok"}})

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    gen.generate("x")
    assert rutas == ["/api/chat"], f"deberia usar /api/chat, uso {rutas}"


def test_el_stream_tambien_usa_api_chat():
    rutas = []

    def handler(req: httpx.Request) -> httpx.Response:
        rutas.append(req.url.path)
        lineas = [
            json.dumps({"message": {"content": "hola"}}),
            json.dumps({"done": True}),
        ]
        return httpx.Response(200, content="\n".join(lineas).encode())

    gen = OllamaGenerator("m", client=cliente_falso(handler))
    assert list(gen.stream("x")) == ["hola"]
    assert rutas == ["/api/chat"]


def test_nadie_usa_api_generate():
    """Buscado en el codigo, no solo en este backend."""
    from doombot.paths import PROJECT_ROOT

    culpables = []
    for py in (PROJECT_ROOT / "src").rglob("*.py"):
        for n, linea in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if "/api/generate" in linea and not linea.lstrip().startswith("#"):
                culpables.append(f"{py.name}:{n}")
    assert not culpables, "D-008 prohibe /api/generate: " + ", ".join(culpables)


# -- keep_alive: el tipo importa, no solo el valor -------------------------
def test_keep_alive_numerico_va_como_numero():
    """El perfil `workstation` escribe llm_keep_alive = "-1" en profiles.toml.

    Medido contra el Ollama del sobremesa: enviar la cadena "-1" devuelve 400
    porque no es una duracion valida; enviar el numero -1 devuelve 200. El
    fichero de perfiles es dato medido y puede escribirlo de las dos formas,
    asi que la conversion vive en el backend.
    """
    cuerpos = []

    def handler(req: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "listo"}})

    gen = OllamaGenerator("m", keep_alive="-1", client=cliente_falso(handler))
    gen.generate("hola")

    assert cuerpos[0]["keep_alive"] == -1
    assert not isinstance(cuerpos[0]["keep_alive"], str)


def test_keep_alive_con_duracion_se_respeta():
    """ "5m" no es un numero: se manda tal cual, que es lo que Ollama espera."""
    cuerpos = []

    def handler(req: httpx.Request) -> httpx.Response:
        cuerpos.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "listo"}})

    gen = OllamaGenerator("m", keep_alive="5m", client=cliente_falso(handler))
    gen.generate("hola")

    assert cuerpos[0]["keep_alive"] == "5m"
