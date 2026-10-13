"""El puente entre la ventana y el agente (D-035).

La ventana (``ui/ventana/doom.html``) y el agente viven en el mismo proceso.
Se hablan por el ``js_api`` de pywebview, no por un servidor WebSocket como el
HUD (D-022): aqui no hay dos programas que conectar, y un puerto abierto en la
maquina para hablar consigo misma es una superficie que no hace falta.

- JavaScript -> Python: ``window.pywebview.api.<metodo>(...)``, los metodos
  publicos de ``Puente``.
- Python -> JavaScript: ``DOOM.evento({...})`` por ``evaluate_js``, un objeto
  JSON por cada cosa que pasa: lo que piensa, lo que hace, lo que abre, lo
  que pregunta.

**Todo el trabajo del agente va en UN hilo.** Playwright (el navegador
propio) solo funciona desde el hilo que lo creo, y pywebview atiende cada
llamada de JavaScript en un hilo distinto: sin un hilo fijo, la segunda orden
que tocara el navegador reventaria.

Los atributos son privados (``_``) a proposito: pywebview recorre los
publicos del objeto para exponerlos a JavaScript.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import queue
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from doombot.backends.base import BackendError

# Lo que tarda el usuario en contestar una confirmacion antes de darla por
# negada. Generoso: puede estar leyendo la segunda opinion.
_ESPERA_PERMISO = 600.0


def _releer_env() -> None:
    """Vuelve a leer .env, para que "Reintentar" vea una clave recien pegada.

    ``config.settings()`` se guarda en cache y ``load_env`` no pisa variables
    ya puestas: una clave vacia leida al abrir la ventana taparia la nueva.
    Se rellenan solo las que estan vacias -una variable puesta de verdad en
    el entorno sigue mandando sobre el fichero, como en el resto del
    proyecto- y se vacia la cache.
    """
    import os

    from doombot import config

    for clave, valor in config.load_env().items():
        if valor and not os.environ.get(clave, "").strip():
            os.environ[clave] = valor
    config.settings.cache_clear()


class Puente:
    def __init__(self, montar: Callable[..., Any] | None = None) -> None:
        self._montar = montar
        self._ventana: Any = None
        self._montaje: Any = None
        self._hilo = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agente")
        self._ocupado = threading.Event()
        self._ids = itertools.count(1)
        self._permisos: dict[int, queue.Queue[bool]] = {}
        self._cerrado = False
        self._desfasado = False

    def _conectar(self, ventana: Any) -> None:
        self._ventana = ventana

    # -- llamadas desde la ventana --------------------------------------------------
    def iniciar(self) -> dict[str, Any]:
        """Monta el agente (en su hilo) y dice con que cerebro se ha quedado."""
        return self._hilo.submit(self._montar_agente).result()

    def enviar(self, texto: str) -> dict[str, Any]:
        texto = (texto or "").strip()
        if not texto:
            return {"ok": False}
        if self._montaje is None:
            return {"ok": False, "error": "El agente no esta montado."}
        if self._ocupado.is_set():
            return {"ok": False, "error": "Sigo con la orden anterior."}
        self._ocupado.set()
        self._hilo.submit(self._ejecutar, texto)
        return {"ok": True}

    def responder(self, id_: int, si: bool) -> None:
        cola = self._permisos.get(int(id_))
        if cola is not None:
            cola.put(bool(si))

    def parar(self) -> None:
        if self._montaje is not None:
            self._montaje.agente.parar()
        # Una confirmacion pendiente cuenta como "no": si no, el agente se
        # quedaria esperando una respuesta que ya nadie va a dar.
        for cola in list(self._permisos.values()):
            cola.put(False)

    def nuevo(self) -> None:
        if self._montaje is not None:
            self._hilo.submit(self._montaje.agente.olvidar)

    # -- primeros pasos ----------------------------------------------------------
    def configuracion(self) -> dict[str, Any]:
        """Que hay configurado y que falta: para la pantalla de primeros pasos."""
        from doombot.ventana import primeros_pasos

        return primeros_pasos.estado()

    def guardar_clave(self, proveedor: str, clave: str, modelo: str = "") -> dict[str, Any]:
        from doombot.ventana import primeros_pasos

        resultado = primeros_pasos.guardar(proveedor, clave, modelo)
        if resultado.get("ok"):
            # El agente montado usa las claves de antes: se rehace al volver al chat.
            self._desfasado = True
        return resultado

    def probar_clave(self, proveedor: str) -> dict[str, Any]:
        from doombot.ventana import primeros_pasos

        return primeros_pasos.probar(proveedor)

    def abrir_enlace(self, url: str) -> None:
        """Un enlace de la conversacion se abre en el navegador del usuario.

        Nunca dentro de la ventana: navegaria fuera de la interfaz y la dejaria
        sin forma de volver. Solo http(s), para que un texto del modelo no
        pueda lanzar ``file://`` ni otros esquemas.
        """
        if str(url).startswith(("http://", "https://")):
            import webbrowser

            webbrowser.open(str(url), new=2)

    def _cerrar(self, *_: Any) -> None:
        """Al cerrar la ventana: el navegador propio se cierra en su hilo.

        Puede llegar dos veces -el evento de cierre de la ventana y el
        ``finally`` de ``abrir()`` tras un Ctrl+C-: la segunda no hace nada.
        """
        if self._cerrado:
            return
        self._cerrado = True
        self.parar()
        if self._montaje is not None:
            self._hilo.submit(self._montaje.cerrar)
        self._hilo.shutdown(wait=True, cancel_futures=False)

    # -- en el hilo del agente ----------------------------------------------------
    def _montar_agente(self) -> dict[str, Any]:
        from doombot.backends.varios import Cadena, etiqueta

        if self._montaje is not None and self._desfasado:
            self._montaje.cerrar()
            self._montaje = None
        self._desfasado = False
        if self._montaje is None:
            montar = self._montar
            if montar is None:
                from doombot.agent.montaje import montar

                _releer_env()
            try:
                self._montaje = montar(narrar=self._narrar, confirmar=self._confirmar)
            except ValueError as e:
                return {"ok": False, "error": str(e)}
            self._montaje.agente.observar = lambda evento, datos: self._emitir(evento, **datos)

        cerebro = self._montaje.agente.cerebro
        modelos = (
            [etiqueta(g) for g in cerebro.generadores]
            if isinstance(cerebro, Cadena)
            else [etiqueta(cerebro)]
        )
        return {
            "ok": True,
            "modelos": modelos,
            "avisos": list(getattr(self._montaje, "avisos", [])),
            "herramientas": len(self._montaje.agente.herramientas),
            "revisor": self._montaje.agente.revisar is not None,
        }

    def _ejecutar(self, texto: str) -> None:
        antes = len(self._montaje.abiertas())
        self._emitir("estado", estado="pensando")
        try:
            informe = self._montaje.agente.ejecutar(texto)
        except BackendError as e:
            self._emitir("fallo", texto=str(e))
        except Exception as e:  # noqa: BLE001 - la ventana no debe quedarse colgada
            self._emitir("fallo", texto=f"{type(e).__name__}: {e}")
        else:
            self._emitir(
                "respuesta",
                texto=informe.respuesta or "(sin respuesta)",
                completo=informe.completo,
                abiertas=self._montaje.abiertas()[antes:],
            )
        finally:
            self._ocupado.clear()
            self._emitir("estado", estado="reposo")

    def _narrar(self, tipo: str, texto: str) -> None:
        self._emitir(tipo, texto=texto)
        if tipo == "resultado" and self._montaje is not None:
            abiertas = self._montaje.abiertas()
            if abiertas:
                self._emitir("abiertas", lista=abiertas)

    def _confirmar(self, pregunta: str) -> bool:
        id_ = next(self._ids)
        cola: queue.Queue[bool] = queue.Queue(maxsize=1)
        self._permisos[id_] = cola
        # La segunda opinion llega pegada a la pregunta (agent/bucle.py); la
        # ventana la pinta aparte, debajo.
        pregunta, _, opinion = pregunta.partition("\n      Segunda opinion: ")
        self._emitir("permiso", id=id_, pregunta=pregunta.strip(), opinion=opinion.strip())
        try:
            return cola.get(timeout=_ESPERA_PERMISO)
        except queue.Empty:
            return False
        finally:
            self._permisos.pop(id_, None)
            self._emitir("permiso_fin", id=id_)

    def _emitir(self, tipo: str, **datos: Any) -> None:
        if self._ventana is None:
            return
        carga = json.dumps({"tipo": tipo, **datos})
        # Si la ventana se esta cerrando, no hay a quien contarselo.
        with contextlib.suppress(Exception):
            self._ventana.evaluate_js(f"window.DOOM && DOOM.evento({carga})")
