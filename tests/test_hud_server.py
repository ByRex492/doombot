"""El transporte del HUD (D-022), contra un servidor y un cliente reales.

Un test de extremo a extremo en vez de mockear ``websockets``: lo que importa
verificar es justo lo que un mock no puede -que el JSON que sale por el cable
es el que espera ``ui/prototipo/hud.html``-.
"""

from __future__ import annotations

import asyncio

import pytest
import websockets

from doombot.hud_server import ServidorHUD


@pytest.fixture
def servidor():
    s = ServidorHUD(port=0)
    # Puerto 0 = que el SO elija uno libre; hace falta leerlo del socket real
    # tras arrancar, porque start() no lo devuelve.
    assert s.start()
    puerto = s._servidor.sockets[0].getsockname()[1]  # noqa: SLF001
    yield s, puerto
    s.stop()


def test_disponible_sin_websockets_instalado(monkeypatch):
    import doombot.hud_server as mod

    monkeypatch.setattr(mod, "websockets", None)
    assert ServidorHUD().disponible is False
    assert ServidorHUD().start() is False


def test_arranca_y_para_sin_clientes():
    s = ServidorHUD(port=0)
    assert s.start()
    s.stop()  # no debe colgarse ni lanzar sin nadie conectado


def test_el_cliente_recibe_los_mensajes_en_json(servidor):
    s, puerto = servidor

    async def _escenario():
        async with websockets.connect(f"ws://127.0.0.1:{puerto}") as ws:
            await asyncio.sleep(0.1)  # tiempo a que el servidor registre el cliente
            s.set_state("escuchando")
            s.set_amplitude(0.42)
            s.set_caption("hola")
            s.reset()

            import json

            return [json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0)) for _ in range(4)]

    recibidos = asyncio.run(_escenario())
    assert recibidos == [
        {"type": "state", "value": "escuchando"},
        {"type": "amplitude", "value": 0.42},
        {"type": "caption", "value": "hola"},
        {"type": "reset", "value": None},
    ]


def test_sin_clientes_no_falla_al_emitir():
    s = ServidorHUD(port=0)
    assert s.start()
    s.set_state("hablando")  # nadie escucha; no debe lanzar
    s.stop()
