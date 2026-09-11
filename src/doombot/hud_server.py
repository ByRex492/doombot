"""Transporte real del HUD: retransmite el estado de D.O.O.M por WebSocket.

Contrato con ``ui/prototipo/hud.html`` (D-022, capa/hud): JSON
``{"type": "state"|"amplitude"|"caption"|"reset", "value": ...}`` en
``ws://127.0.0.1:8765/hud``. ``ui/mock_servidor.py`` simula ese mismo
contrato para probar el cliente sin esto; este modulo es el que habla con el
orquestador de verdad -- lo escribe integracion porque vive en ``chat.py``,
que capa/hud no puede tocar.

Opcional a proposito: sin el extra ``hud`` instalado (sin ``websockets``),
D.O.O.M sigue funcionando por texto exactamente igual, solo que sin nadie
escuchando el WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import TYPE_CHECKING, Any

try:
    import websockets
except ImportError:  # pragma: no cover - el extra `hud` es opcional
    websockets = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

HOST_POR_DEFECTO = "127.0.0.1"
PUERTO_POR_DEFECTO = 8765


class ServidorHUD:
    """Arranca en un hilo propio; el resto del proceso sigue sincrono.

    Un hilo con su propio bucle de ``asyncio`` porque ``chat.py`` es
    sincrono de punta a punta (D-006: el orquestador crece capa a capa desde
    un bucle simple) y convertirlo entero a async por esto no compensa.
    """

    def __init__(self, host: str = HOST_POR_DEFECTO, port: int = PUERTO_POR_DEFECTO) -> None:
        self._host = host
        self._port = port
        self._clientes: set[ServerConnection] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._hilo: threading.Thread | None = None
        self._listo = threading.Event()
        self._servidor: Any = None

    @property
    def disponible(self) -> bool:
        """False si falta ``websockets`` (extra ``hud`` no instalado)."""
        return websockets is not None

    def start(self) -> bool:
        """Arranca el servidor en segundo plano.

        ``False`` si falta ``websockets`` o si el arranque falla -puerto
        ocupado, otra instancia ya escuchando-. Nunca lanza: un HUD que no
        conecta no puede tumbar la sesion de texto.
        """
        if not self.disponible:
            return False
        self._hilo = threading.Thread(target=self._correr, daemon=True)
        self._hilo.start()
        self._listo.wait(timeout=5.0)
        return self._servidor is not None

    def stop(self) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._hilo:
            self._hilo.join(timeout=2.0)

    # -- el hilo del servidor ------------------------------------------------
    def _correr(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            # La propia construccion de `Serve` (dentro de `websockets.serve`)
            # pide un bucle en marcha con `get_running_loop()`, asi que tiene
            # que evaluarse desde dentro de una corutina y no como argumento
            # de `run_until_complete` -eso la evaluaria antes de que el bucle
            # este corriendo, y falla con "no running event loop".
            self._servidor = self._loop.run_until_complete(self._arrancar())
        except OSError:
            self._servidor = None
        finally:
            self._listo.set()

        if self._servidor is None:
            return
        try:
            self._loop.run_forever()
        finally:
            self._servidor.close()
            self._loop.run_until_complete(self._servidor.wait_closed())

    async def _arrancar(self) -> Any:
        return await websockets.serve(self._atender, self._host, self._port)

    async def _atender(self, ws: ServerConnection) -> None:
        self._clientes.add(ws)
        try:
            async for _ in ws:
                pass  # el HUD no manda nada, solo escucha
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clientes.discard(ws)

    def _emitir(self, tipo: str, valor: Any) -> None:
        if self._loop is None or not self._clientes:
            return
        mensaje = json.dumps({"type": tipo, "value": valor})
        asyncio.run_coroutine_threadsafe(self._difundir(mensaje), self._loop)

    async def _difundir(self, mensaje: str) -> None:
        muertos = set()
        for ws in list(self._clientes):
            try:
                await ws.send(mensaje)
            except websockets.exceptions.ConnectionClosed:
                muertos.add(ws)
        self._clientes -= muertos

    # -- el contrato con hud.html ---------------------------------------------
    def set_state(self, nombre: str) -> None:
        """``dormido`` | ``escuchando`` | ``pensando`` | ``hablando`` | ``error``."""
        self._emitir("state", nombre)

    def set_amplitude(self, nivel: float) -> None:
        """0-1, la misma escala que ``Audio.level()`` (ver backends/base.py)."""
        self._emitir("amplitude", nivel)

    def set_caption(self, texto: str | None) -> None:
        self._emitir("caption", texto)

    def reset(self) -> None:
        self._emitir("reset", None)
