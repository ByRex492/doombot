"""Que es una herramienta para el agente, y las piezas comunes para escribirlas.

Una herramienta es una funcion de Python con tres cosas alrededor:

- lo que el modelo ve de ella (nombre, descripcion, argumentos);
- como se cuenta al usuario lo que va a hacer (``narrar``);
- si hace falta su permiso antes (``confirmar``).

``confirmar`` recibe los argumentos y devuelve la pregunta, o ``None`` si la
accion es reversible y puede ir sola. Es una funcion y no un booleano fijo
porque el riesgo depende de los argumentos: ``ls`` no se confirma y ``rm`` si,
y escribir un fichero solo se confirma si ya existia (D-033).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from doombot.backends.base import EspecHerramienta


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    funcion: Callable[..., str]
    parametros: dict[str, dict[str, Any]] = field(default_factory=dict)
    requeridos: tuple[str, ...] = ()
    narrar: Callable[[dict[str, Any]], str] | None = None
    confirmar: Callable[[dict[str, Any]], str | None] | None = None
    familia: str = ""
    """``web``, ``apps``, ``ficheros`` o ``terminal``: la esfera de la ventana cambia segun esto."""

    def espec(self) -> EspecHerramienta:
        return EspecHerramienta(
            nombre=self.nombre,
            descripcion=self.descripcion,
            parametros={
                "type": "object",
                "properties": self.parametros,
                "required": list(self.requeridos),
            },
        )

    def contar(self, argumentos: dict[str, Any]) -> str:
        """La frase que ve el usuario antes de que se ejecute."""
        if self.narrar is not None:
            return self.narrar(argumentos)
        if not argumentos:
            return self.nombre
        resumen = ", ".join(f"{k}={v!r}" for k, v in argumentos.items())
        return f"{self.nombre}({recortar(resumen, 120)})"

    def pregunta(self, argumentos: dict[str, Any]) -> str | None:
        return self.confirmar(argumentos) if self.confirmar is not None else None


def texto(descripcion: str) -> dict[str, Any]:
    return {"type": "string", "description": descripcion}


def entero(descripcion: str) -> dict[str, Any]:
    return {"type": "integer", "description": descripcion}


def booleano(descripcion: str) -> dict[str, Any]:
    return {"type": "boolean", "description": descripcion}


def recortar(texto: str, largo: int) -> str:
    """Una linea corta para mostrar, no para el modelo."""
    plano = " ".join(texto.split())
    return plano if len(plano) <= largo else plano[: largo - 1] + "…"


def truncar(salida: str, max_chars: int) -> str:
    """Cabeza y cola de una salida enorme, avisando de lo que falta.

    Una sola lectura de fichero llega a comerse la mitad del contexto del
    portatil (capa4-investigacion.md, punto 4). Se queda con el principio y
    el final -donde suelen estar la cabecera y el error- y le dice al modelo
    que hay mas, para que lo pida por partes si lo necesita.
    """
    if len(salida) <= max_chars:
        return salida
    cabeza = salida[: max_chars * 2 // 3]
    cola = salida[-max_chars // 3 :]
    omitidos = len(salida) - len(cabeza) - len(cola)
    return (
        f"{cabeza}\n[... {omitidos} caracteres omitidos; pide un trozo concreto si "
        f"los necesitas ...]\n{cola}"
    )
