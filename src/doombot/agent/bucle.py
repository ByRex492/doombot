"""El bucle del agente: pensar, actuar, observar, hasta terminar (D-033).

No sabe que modelo hay detras ni que herramientas existen: recibe un
``ToolCaller`` y una lista de ``Herramienta``, y es lo unico que usa. Tampoco
sabe si la salida es una consola, la voz o el HUD: cuenta lo que hace por
``narrar`` y pide permiso por ``confirmar``, que inyecta quien lo monta.

Las salvaguardas viven aqui, no en cada herramienta, para que una
herramienta nueva no pueda saltarselas por olvido:

- **lista blanca**: el modelo solo puede invocar lo que esta en el catalogo;
- **confirmacion**: lo irreversible se pregunta antes, y una negativa se le
  devuelve al modelo como resultado para que no insista;
- **limite de pasos**: un modelo que se enreda no gira para siempre;
- **contexto acotado**: cada salida se trunca, y las antiguas se enmascaran
  (capa4-investigacion.md, punto 4).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from doombot.agent.herramientas import Herramienta, recortar, truncar
from doombot.backends.base import (
    BackendError,
    LlamadaHerramienta,
    MensajeAgente,
    ResultadoHerramienta,
    ToolCaller,
)

# Lo que se cuenta, para que quien muestre la narracion elija el formato:
#   comentario  lo que dice el modelo entre accion y accion
#   accion      lo que va a hacer una herramienta, antes de hacerlo
#   resultado   como salio, en una linea
#   error       la herramienta fallo o no se autorizo
Narrador = Callable[[str, str], None]

NEGADA = (
    "El usuario NO ha autorizado esta accion y no se ha ejecutado. No la repitas: "
    "busca otra forma o pregunta que prefiere."
)


@dataclass
class Informe:
    """Como acabo una tarea."""

    respuesta: str
    acciones: list[str] = field(default_factory=list)
    pasos: int = 0
    completo: bool = True


class Agente:
    def __init__(
        self,
        cerebro: ToolCaller,
        herramientas: Sequence[Herramienta],
        *,
        narrar: Narrador,
        confirmar: Callable[[str], bool],
        system: str | None = None,
        revisar: Callable[[str, str], str] | None = None,
        max_pasos: int = 20,
        max_resultado: int = 6000,
        ventana: int = 4,
    ) -> None:
        self.cerebro = cerebro
        self.herramientas = {h.nombre: h for h in herramientas}
        self.narrar = narrar
        self.confirmar = confirmar
        # Segunda opinion antes de lo irreversible (D-034): otro modelo lee la
        # orden y la accion propuesta y dice si encajan. No decide: su
        # opinion acompana a la pregunta, y quien decide sigue siendo el usuario.
        self.revisar = revisar
        self._tarea = ""
        self._system = system
        self._max_pasos = max_pasos
        self._max_resultado = max_resultado
        self._ventana = ventana
        # La conversacion sobrevive entre tareas, como una sesion de Claude
        # Code: "ahora cierralo" necesita saber que se abrio antes.
        self.conversacion: list[MensajeAgente] = []

    def olvidar(self) -> None:
        """Empieza de cero: otra tarea sin nada de lo anterior."""
        self.conversacion.clear()

    # -- el bucle ---------------------------------------------------------------
    def ejecutar(self, tarea: str) -> Informe:
        self._tarea = tarea
        self.conversacion.append(tarea)
        informe = Informe(respuesta="")
        especs = [h.espec() for h in self.herramientas.values()]

        for _ in range(self._max_pasos):
            paso = self.cerebro.paso(self._vista(), especs, system=self._system)
            self.conversacion.append(paso)
            informe.pasos += 1

            if not paso.llamadas:
                informe.respuesta = paso.texto
                return informe
            if paso.texto:
                self.narrar("comentario", paso.texto)

            pendientes = list(paso.llamadas)
            try:
                while pendientes:
                    llamada = pendientes[0]
                    contenido = self._atender(llamada, informe)
                    self.conversacion.append(
                        ResultadoHerramienta(llamada.id, llamada.nombre, contenido)
                    )
                    pendientes.pop(0)
            except KeyboardInterrupt:
                # Una llamada sin resultado deja la conversacion invalida para
                # la API de Anthropic: se cierran todas antes de salir.
                for llamada in pendientes:
                    self.conversacion.append(
                        ResultadoHerramienta(
                            llamada.id, llamada.nombre, "Interrumpido por el usuario."
                        )
                    )
                raise

        informe.completo = False
        informe.respuesta = (
            f"He llegado al limite de {self._max_pasos} pasos sin terminar. "
            "Dime si sigo o como quieres que lo haga."
        )
        return informe

    # -- interno ----------------------------------------------------------------
    def _atender(self, llamada: LlamadaHerramienta, informe: Informe) -> str:
        herramienta = self.herramientas.get(llamada.nombre)
        if herramienta is None:
            self.narrar("error", f"el modelo pidio una herramienta que no existe: {llamada.nombre}")
            return (
                f"Error: no existe la herramienta {llamada.nombre!r}. "
                f"Disponibles: {', '.join(sorted(self.herramientas))}."
            )

        argumentos: dict[str, Any] = dict(llamada.argumentos)
        faltan = [r for r in herramienta.requeridos if argumentos.get(r) in (None, "")]
        if faltan:
            return f"Error: faltan argumentos obligatorios: {', '.join(faltan)}."

        try:
            pregunta = herramienta.pregunta(argumentos)
        except Exception as e:  # noqa: BLE001 - si no se sabe evaluar el riesgo, se pregunta
            pregunta = f"{herramienta.contar(argumentos)} (no he podido evaluar el riesgo: {e})"
        if pregunta is not None and self.revisar is not None:
            propuesta = f"{herramienta.nombre}({argumentos}) -> {herramienta.contar(argumentos)}"
            try:
                pregunta += f"\n      Segunda opinion: {self.revisar(self._tarea, propuesta)}"
            except BackendError as e:
                pregunta += f"\n      (sin segunda opinion: {e})"
        if pregunta is not None and not self.confirmar(pregunta):
            self.narrar("error", f"no autorizado: {herramienta.contar(argumentos)}")
            return NEGADA

        accion = herramienta.contar(argumentos)
        self.narrar("accion", accion)
        informe.acciones.append(accion)
        try:
            salida = str(herramienta.funcion(**argumentos))
        except TypeError as e:
            # Argumentos que la funcion no acepta: el modelo se los invento.
            salida = f"Error: argumentos no validos para {herramienta.nombre}: {e}"
        except Exception as e:  # noqa: BLE001 - el fallo se le devuelve al modelo, no tumba la sesion
            salida = f"Error: {e}"

        fallo = salida.startswith("Error")
        self.narrar("error" if fallo else "resultado", recortar(salida, 160) or "hecho")
        return truncar(salida, self._max_resultado)

    def _vista(self) -> list[MensajeAgente]:
        """La conversacion que se le manda al modelo, con lo viejo enmascarado.

        Solo los ``ventana`` resultados mas recientes van enteros; los demas se
        sustituyen por una linea. El modelo ya los uso para decidir lo que vino
        despues, y volver a mandarlos llena el contexto sin aportar nada
        (observation masking, capa4-investigacion.md). La conversacion guardada
        no se toca: si hiciera falta, el dato sigue ahi.
        """
        indices = [
            i for i, m in enumerate(self.conversacion) if isinstance(m, ResultadoHerramienta)
        ]
        viejos = set(indices[: max(0, len(indices) - self._ventana)])
        vista: list[MensajeAgente] = []
        for i, m in enumerate(self.conversacion):
            if i in viejos and isinstance(m, ResultadoHerramienta):
                vista.append(
                    ResultadoHerramienta(
                        m.id, m.nombre, f"[resultado anterior de {m.nombre}, ya usado: omitido]"
                    )
                )
            else:
                vista.append(m)
        return vista
