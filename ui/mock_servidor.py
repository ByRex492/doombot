"""Servidor WS de prueba para el HUD, sin depender del orquestador real.

NO es el transporte definitivo -- ese lo escribe integracion, en el
orquestador, contra el mismo contrato (D-022 en docs/decisiones.md). Esto
es al WebSocket lo que el banco de pruebas de hud.html es a la voz: sirve
para comprobar el cliente de verdad, con un servidor de verdad, sin haber
montado todavia el lado Python del orquestador.

    py -3.12 -m pip install websockets
    py -3.12 ui/mock_servidor.py

Y abrir hud.html servido por http:// (no file://, por el microfono del
propio prototipo). En cuanto conecta, el HUD sale del banco de pruebas y
seguido el ciclo que manda este servidor.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time

import websockets

HOST, PORT = "127.0.0.1", 8765


async def _manda(ws, tipo: str, valor) -> None:
    await ws.send(json.dumps({"type": tipo, "value": valor}))


async def _amplitud_simulada(ws, segundos: float, nivel: float = 0.7) -> None:
    """Empuja amplitud a ~30 Hz durante `segundos`, con una envolvente
    silabica parecida a la del simulador en JS -- para que el ritmo se
    note real y no un diente de sierra."""
    fin = time.monotonic() + segundos
    t0 = time.monotonic()
    while time.monotonic() < fin:
        t = time.monotonic() - t0
        fase = 2 * math.pi * 4.3 * t + 1.4 * math.sin(2 * math.pi * 0.83 * t)
        silabas = 0.55 + 0.45 * math.sin(fase)
        v = max(0.0, min(1.0, nivel * silabas))
        await _manda(ws, "amplitude", round(v, 3))
        await asyncio.sleep(1 / 30)


async def ciclo(ws) -> None:
    """El mismo ciclo de conversacion que `D` en el banco de pruebas del
    HUD, para comparar transporte real contra el simulado en JS."""
    await _manda(ws, "reset", None)
    await asyncio.sleep(0.9)

    await _manda(ws, "state", "escuchando")
    await _amplitud_simulada(ws, 3.0, nivel=0.75)

    await _manda(ws, "state", "pensando")
    await _manda(ws, "caption", "…")
    await asyncio.sleep(1.6)

    await _manda(ws, "state", "hablando")
    await _manda(ws, "caption", "Diecinueve grados en el exterior. Cielo despejado hasta la tarde.")
    await _amplitud_simulada(ws, 4.5, nivel=0.65)

    await _manda(ws, "state", "dormido")
    await _manda(ws, "caption", None)


async def atender(ws) -> None:
    print(f"[mock] cliente conectado desde {ws.remote_address}")
    try:
        while True:
            await ciclo(ws)
            await asyncio.sleep(random.uniform(1.5, 3.0))
    except websockets.exceptions.ConnectionClosed:
        print("[mock] cliente desconectado")


async def main() -> None:
    print(f"[mock] escuchando en ws://{HOST}:{PORT}/hud (Ctrl+C para parar)")
    async with websockets.serve(atender, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
