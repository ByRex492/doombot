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

Y al final, el repaso (D-039): si hay quien lo haga, otro modelo revisa la
respuesta antes de darla.
"""

from __future__ import annotations

import dataclasses
import difflib
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from doombot.agent.herramientas import Herramienta, recortar, truncar
from doombot.backends.base import (
    BackendError,
    LlamadaHerramienta,
    MensajeAgente,
    PasoModelo,
    ResultadoHerramienta,
    ToolCaller,
)

# Lo que se cuenta, para que quien muestre la narracion elija el formato:
#   comentario  lo que dice el modelo entre accion y accion
#   accion      lo que va a hacer una herramienta, antes de hacerlo
#   resultado   como salio, en una linea
#   error       la herramienta fallo o no se autorizo
#   aviso       algo que conviene saber y no es un fallo (un modelo sin cuota,
#               y la cadena sigue con otro)
Narrador = Callable[[str, str], None]


class Repasador(Protocol):
    """Quien repasa la respuesta final (``agent/refinado.py``).

    ``consultado`` son los resultados de herramientas de esta tarea, como
    ``(nombre, contenido)``: lo que el corrector usa para comprobar datos.
    """

    def merece(self, respuesta: str, consultado: Sequence[tuple[str, str]]) -> bool: ...

    def __call__(
        self, tarea: str, respuesta: str, consultado: Sequence[tuple[str, str]]
    ) -> tuple[str, str]: ...


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
        repasar: Repasador | None = None,
        max_pasos: int = 20,
        # Con las capas gratuitas el limite es de tokens por minuto (Groq: unos
        # 8.000): cada paso reenvia todo, asi que lo leido se recorta mas.
        max_resultado: int = 3500,
        ventana: int = 3,
    ) -> None:
        self.cerebro = cerebro
        self.herramientas = {h.nombre: h for h in herramientas}
        self.narrar = narrar
        self.confirmar = confirmar
        # Segunda opinion antes de lo irreversible (D-034): otro modelo lee la
        # orden y la accion propuesta y dice si encajan. No decide: su
        # opinion acompana a la pregunta, y quien decide sigue siendo el usuario.
        self.revisar = revisar
        self.repasar = repasar
        self._tarea = ""
        # Para interfaces que quieren mas que texto -la esfera de la ventana
        # cambia de modo segun la herramienta-: ("pensando", {"paso": n}) antes
        # de cada consulta al modelo, ("herramienta", {"nombre", "familia"})
        # antes de ejecutar una. La consola no lo necesita y lo deja a None.
        self.observar: Callable[[str, dict[str, Any]], None] | None = None
        self._parar = False
        self.system = system
        # Lo que se anade al prompt en cada orden, segun la orden (D-043): el
        # perfil del usuario y los recuerdos que vengan a cuento. Va aparte de
        # ``system`` porque los modos lo reescriben entero (D-038), y porque
        # depende de lo que se pide: no se guarda en la conversacion.
        self.contexto: Callable[[str], str] | None = None
        # Al acabar cada orden, con lo pedido y como acabo: el diario del taller
        # (D-045) apunta ahi que se hizo. Si falla, la orden ya esta hecha.
        self.al_terminar: Callable[[str, Informe], None] | None = None
        self._inicio = 0
        self._max_pasos = max_pasos
        self._max_resultado = max_resultado
        self._ventana = ventana
        # La conversacion sobrevive entre tareas, como una sesion de Claude
        # Code: "ahora cierralo" necesita saber que se abrio antes.
        self.conversacion: list[MensajeAgente] = []

    def olvidar(self) -> None:
        """Empieza de cero: otra tarea sin nada de lo anterior."""
        self.conversacion.clear()

    def parar(self) -> None:
        """Pide que la tarea en curso termine en cuanto acabe el paso actual.

        Para interfaces sin Ctrl+C. No corta una herramienta a medias -un
        fichero a medio escribir es peor que esperar un segundo-: se para entre
        paso y paso.
        """
        self._parar = True

    # -- el bucle ---------------------------------------------------------------
    def ejecutar(self, tarea: str) -> Informe:
        informe = self._ejecutar(tarea)
        if self.al_terminar is not None:
            try:
                self.al_terminar(tarea, informe)
            except Exception as e:  # noqa: BLE001 - ver al_terminar
                self.narrar("aviso", f"no he podido apuntarlo: {recortar(str(e), 140)}")
        return informe

    def _ejecutar(self, tarea: str) -> Informe:
        self._tarea = tarea
        self._parar = False
        self.conversacion.append(tarea)
        inicio = self._inicio = len(self.conversacion)
        informe = Informe(respuesta="")
        especs = [h.espec() for h in self.herramientas.values()]
        system = self._prompt(tarea)

        for n in range(self._max_pasos):
            if self._parar:
                return self._parado(informe)
            self._avisar("pensando", {"paso": n + 1})
            paso = self.cerebro.paso(self._vista(), especs, system=system)
            self.conversacion.append(paso)
            informe.pasos += 1

            if not paso.llamadas:
                informe.respuesta = self._repasar(paso, inicio)
                return informe
            if paso.texto:
                self.narrar("comentario", paso.texto)

            pendientes = list(paso.llamadas)
            try:
                while pendientes:
                    if self._parar:
                        raise KeyboardInterrupt
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
                if self._parar:
                    return self._parado(informe)
                raise

        informe.completo = False
        informe.respuesta = (
            f"He llegado al limite de {self._max_pasos} pasos sin terminar. "
            "Dime si sigo o como quieres que lo haga."
        )
        return informe

    def usadas(self) -> list[str]:
        """Las herramientas que ya han dado resultado en la orden en curso, en orden."""
        return [
            m.nombre
            for m in self.conversacion[self._inicio :]
            if isinstance(m, ResultadoHerramienta)
        ]

    # -- interno ----------------------------------------------------------------
    def _prompt(self, tarea: str) -> str | None:
        """El prompt de esta orden: el de siempre, mas lo que aporte ``contexto``.

        Si el contexto falla -la memoria no abre, el modelo de embeddings no
        carga-, la orden sigue sin el: no saber de que se acuerda no es motivo
        para no hacer lo que se pide.
        """
        if self.contexto is None:
            return self.system
        try:
            extra = self.contexto(tarea)
        except Exception as e:  # noqa: BLE001 - ver arriba
            self.narrar("aviso", f"sin memoria en esta orden: {recortar(str(e), 140)}")
            extra = ""
        return "\n\n".join(p for p in (self.system, extra) if p) or None

    def _avisar(self, evento: str, datos: dict[str, Any]) -> None:
        if self.observar is not None:
            self.observar(evento, datos)

    def _parado(self, informe: Informe) -> Informe:
        self._parar = False
        informe.completo = False
        informe.respuesta = "Parado. Dime como sigo."
        return informe

    def _repasar(self, paso: PasoModelo, inicio: int) -> str:
        """La respuesta final, repasada por otro modelo si lo merece (D-039).

        Si el repaso falla, se da el borrador: un corrector caido no puede
        dejar al usuario sin la respuesta que ya estaba hecha.
        """
        if self.repasar is None:
            return paso.texto
        consultado = [
            (m.nombre, m.contenido)
            for m in self.conversacion[inicio:]
            if isinstance(m, ResultadoHerramienta)
        ]
        if not self.repasar.merece(paso.texto, consultado):
            return paso.texto
        self.narrar("comentario", "Repaso la respuesta con otro modelo")
        self._avisar("pensando", {"paso": 0, "texto": "repasando la respuesta…"})
        try:
            texto, nota = self.repasar(self._tarea, paso.texto, consultado)
        except BackendError as e:
            self.narrar("error", f"sin repaso: {recortar(str(e), 140)}")
            return paso.texto
        self.narrar("resultado", f"Respuesta repasada: {nota}")
        if texto != paso.texto:
            # Lo que queda en la conversacion es lo que leyo el usuario: "y eso
            # de antes..." se refiere a la respuesta corregida, no al borrador.
            self.conversacion[-1] = dataclasses.replace(paso, texto=texto)
        return texto

    def _atender(self, llamada: LlamadaHerramienta, informe: Informe) -> str:
        herramienta = self.herramientas.get(llamada.nombre)
        if herramienta is None:
            # Un nombre casi igual al de una herramienta real ("clickar" por
            # "clicar") es un despiste del modelo, no otra peticion: se usa la
            # que queria y se cuenta.
            parecidas = difflib.get_close_matches(
                llamada.nombre, self.herramientas, n=1, cutoff=0.8
            )
            if parecidas:
                herramienta = self.herramientas[parecidas[0]]
                self.narrar(
                    "comentario", f"«{llamada.nombre}» no existe: uso «{herramienta.nombre}»"
                )
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
        self._avisar("herramienta", {"nombre": herramienta.nombre, "familia": herramienta.familia})
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
