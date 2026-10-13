"""``calcular``: aritmetica exacta para el agente, en vez de hacerla "de cabeza" (D-038).

Los modelos de lenguaje se equivocan con las cuentas, y lo hacen con
seguridad. Esta herramienta evalua expresiones matematicas de verdad -con
``math`` de Python- y devuelve el resultado; el modelo solo tiene que copiarlo.

**No es ``eval``.** La expresion se analiza con ``ast`` y solo se aceptan
numeros, los operadores aritmeticos, unas constantes y una lista cerrada de
funciones de ``math``. Cualquier otra cosa -nombres, atributos, llamadas a lo
que no esta en la lista- se rechaza antes de calcular nada. Y se acotan las
operaciones que podrian colgar el proceso (potencias y factoriales enormes).
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any

from doombot.agent.herramientas import Herramienta, texto

_BINARIOS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARIOS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CONSTANTES = {"pi": math.pi, "e": math.e, "tau": math.tau}
_FUNCIONES = {
    nombre: getattr(math, nombre)
    for nombre in (
        "sqrt", "cbrt", "exp", "log", "log10", "log2", "sin", "cos", "tan", "asin", "acos",
        "atan", "atan2", "sinh", "cosh", "tanh", "degrees", "radians", "floor", "ceil",
        "hypot", "gcd", "lcm", "factorial", "comb", "perm", "fabs",
    )
} | {"abs": abs, "round": round, "min": min, "max": max, "ln": math.log}  # fmt: skip
_MAX_EXPONENTE = 10_000
_MAX_FACTORIAL = 3_000


def _evaluar(nodo: ast.AST) -> Any:
    if isinstance(nodo, ast.Expression):
        return _evaluar(nodo.body)
    if (
        isinstance(nodo, ast.Constant)
        and isinstance(nodo.value, int | float)
        and not isinstance(nodo.value, bool)
    ):
        return nodo.value
    if isinstance(nodo, ast.Name) and nodo.id in _CONSTANTES:
        return _CONSTANTES[nodo.id]
    if isinstance(nodo, ast.UnaryOp) and type(nodo.op) in _UNARIOS:
        return _UNARIOS[type(nodo.op)](_evaluar(nodo.operand))
    if isinstance(nodo, ast.BinOp) and type(nodo.op) in _BINARIOS:
        izq, der = _evaluar(nodo.left), _evaluar(nodo.right)
        if isinstance(nodo.op, ast.Pow) and abs(der) > _MAX_EXPONENTE:
            raise ValueError(f"exponente demasiado grande ({der})")
        return _BINARIOS[type(nodo.op)](izq, der)
    if (
        isinstance(nodo, ast.Call)
        and isinstance(nodo.func, ast.Name)
        and nodo.func.id in _FUNCIONES
        and not nodo.keywords
    ):
        argumentos = [_evaluar(a) for a in nodo.args]
        if nodo.func.id in ("factorial", "comb", "perm") and any(
            abs(a) > _MAX_FACTORIAL for a in argumentos
        ):
            raise ValueError("numero demasiado grande para un factorial")
        return _FUNCIONES[nodo.func.id](*argumentos)
    raise ValueError(f"no se puede calcular «{ast.unparse(nodo)}»")


def calcular(expresion: str) -> str:
    """Una o varias expresiones separadas por ``;``. ``^`` vale como potencia."""
    salidas = []
    for trozo in (expresion or "").split(";"):
        trozo = trozo.strip()
        if not trozo:
            continue
        if len(trozo) > 300:
            return "Error: expresion demasiado larga."
        try:
            resultado = _evaluar(ast.parse(trozo.replace("^", "**"), mode="eval"))
        except (ValueError, TypeError, ZeroDivisionError, OverflowError, SyntaxError) as e:
            return f"Error en «{trozo}»: {e}"
        if isinstance(resultado, float):
            resultado = float(f"{resultado:.12g}")
            if resultado.is_integer() and abs(resultado) < 1e15:
                resultado = int(resultado)
        salidas.append(f"{trozo} = {resultado}")
    return "\n".join(salidas) or "Error: no hay nada que calcular."


def herramientas() -> list[Herramienta]:
    return [
        Herramienta(
            "calcular",
            "Calcula expresiones matematicas con exactitud. Usala para TODA la aritmetica, "
            "nunca calcules de cabeza. Operadores + - * / // % ^, parentesis, constantes pi e "
            "tau, y funciones sqrt cbrt exp log ln log10 log2 sin cos tan asin acos atan atan2 "
            "sinh cosh tanh degrees radians floor ceil hypot gcd lcm factorial comb perm abs "
            "round min max (trigonometria en radianes). Varias expresiones separadas por ;.",
            calcular,
            {"expresion": texto("La expresion, ej. 'sqrt(3^2 + 4^2); 9.81 * 2.5^2 / 2'.")},
            requeridos=("expresion",),
            narrar=lambda a: f"Calculo {a.get('expresion')}",
        )
    ]
