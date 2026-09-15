"""El cliente de n8n, probado sin n8n (D-030).

Mismo truco que test_ollama.py: un transporte HTTP falso responde lo que
convenga a cada prueba, asi que nada de esto necesita un n8n arrancado.

Lo que protegen estos tests es la salvaguarda, no el protocolo HTTP: que un
nombre fuera de la lista blanca no dispare ninguna peticion, y que el nombre
se resuelva normalizado igual que el resto de ordenes de voz.
"""

from __future__ import annotations

import httpx
import pytest

from doombot.actions.n8n import N8nClient, WorkflowResult
from doombot.backends.base import BackendError
from doombot.config import Settings


def cliente_falso(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def cliente_que_no_deberia_llamarse() -> httpx.Client:
    """Para las pruebas de la lista blanca: si la peticion sale, algo esta mal."""

    def handler(request):
        raise AssertionError(f"no deberia haberse llamado a {request.url}")

    return cliente_falso(handler)


# -- disparo normal -----------------------------------------------------------
def test_dispara_el_webhook_del_flujo_conocido():
    llamada = {}

    def handler(request):
        llamada["url"] = str(request.url)
        llamada["method"] = request.method
        return httpx.Response(200, text="ok")

    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego": "webhook/riego-jardin"},
        client=cliente_falso(handler),
    )
    resultado = n8n.trigger("riego")

    assert llamada["method"] == "POST"
    assert llamada["url"] == "http://localhost:5678/webhook/riego-jardin"
    assert resultado == WorkflowResult(success=True, status_code=200, output="ok")


def test_el_nombre_se_normaliza_como_las_demas_ordenes():
    """Whisper puede devolver tildes, mayusculas y signos distintos cada vez."""

    def handler(request):
        return httpx.Response(200, text="ok")

    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego del jardin": "webhook/riego"},
        client=cliente_falso(handler),
    )
    assert n8n.trigger("¡Riego DEL Jardín!").success is True


# -- la lista blanca es la salvaguarda -----------------------------------------
def test_un_nombre_fuera_de_la_lista_no_dispara_nada():
    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego": "webhook/riego"},
        client=cliente_que_no_deberia_llamarse(),
    )
    with pytest.raises(BackendError, match="lista de flujos permitidos"):
        n8n.trigger("borra el disco duro")


def test_el_aviso_dice_que_flujos_si_estan_disponibles():
    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego": "x", "backup": "y"},
        client=cliente_que_no_deberia_llamarse(),
    )
    with pytest.raises(BackendError, match="riego") as exc:
        n8n.trigger("otra cosa")
    assert "backup" in str(exc.value)


def test_lista_vacia_tambien_avisa_en_vez_de_fallar_raro():
    n8n = N8nClient(base_url="http://localhost:5678", client=cliente_que_no_deberia_llamarse())
    with pytest.raises(BackendError, match="ninguno configurado"):
        n8n.trigger("lo que sea")


def test_sin_base_url_avisa_antes_de_intentar_nada():
    n8n = N8nClient(workflows={"riego": "webhook/riego"}, client=cliente_que_no_deberia_llamarse())
    with pytest.raises(BackendError, match="DOOMBOT_N8N_BASE_URL"):
        n8n.trigger("riego")


# -- errores traducidos --------------------------------------------------------
def test_n8n_caido_da_un_mensaje_legible():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego": "webhook/riego"},
        client=cliente_falso(handler),
    )
    with pytest.raises(BackendError, match="No hay respuesta de n8n"):
        n8n.trigger("riego")


def test_webhook_inexistente_da_un_mensaje_legible():
    def handler(request):
        return httpx.Response(404, text="not registered")

    n8n = N8nClient(
        base_url="http://localhost:5678",
        workflows={"riego": "webhook/riego"},
        client=cliente_falso(handler),
    )
    with pytest.raises(BackendError, match="404"):
        n8n.trigger("riego")


# -- construccion desde la configuracion ---------------------------------------
def test_from_config_lee_la_lista_blanca():
    llamada = {}

    def handler(request):
        llamada["url"] = str(request.url)
        return httpx.Response(200, text="ok")

    cfg = Settings(
        ollama_host="http://127.0.0.1:11434",
        log_level="INFO",
        n8n_base_url="http://localhost:5678",
        n8n_workflows=(("riego", "webhook/riego"),),
    )
    n8n = N8nClient.from_config(cfg, client=cliente_falso(handler))
    n8n.trigger("riego")
    assert llamada["url"] == "http://localhost:5678/webhook/riego"


def test_parse_n8n_workflows_ignora_pares_mal_formados():
    from doombot.config import _parse_n8n_workflows

    assert _parse_n8n_workflows("riego:webhook/riego, sin_dos_puntos, :vacio, backup:") == (
        ("riego", "webhook/riego"),
    )
