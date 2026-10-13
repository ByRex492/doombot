"""Graficas precisas en la ventana: matematicas y estadistica (D-037).

La herramienta ``mostrar_grafica`` solo existe cuando hay una pantalla donde
pintar -la ventana-; en consola o por voz no se ofrece al modelo. Admite:

- ``grafica``: unos ejes con vectores, puntos, segmentos y funciones. El
  modelo da coordenadas; la ventana dibuja con precision.
- ``estadistica``: datos en barras, lineas, sectores, histograma o
  dispersion. **Los calculos se hacen aqui, no en el modelo**: medias,
  medianas, desviacion, porcentajes, intervalos y regresion. Los modelos se
  equivocan con la aritmetica; asi se les devuelven los numeros exactos para
  que los expliquen sin inventarlos.

Hubo tambien dibujos libres en SVG, con un modelo dibujante. Se quitaron tras
probarlos en real: los modelos gratuitos no dibujan con precision suficiente,
y el usuario decidio dejar esto solo para graficas (ver D-037).

Todo lo que llega del modelo se valida: solo claves conocidas, numeros
finitos y acotados, listas con tope. Lo que no vale se le explica al modelo
en el error, para que lo corrija en el siguiente paso.
"""

from __future__ import annotations

import json
import math
import re
import statistics
from collections.abc import Callable
from typing import Any

from doombot.agent.herramientas import Herramienta, texto

_EXPRESION = re.compile(r"^[0-9x+\-*/^().,\s a-z]{1,120}$")
_FUNCIONES = frozenset({"sin", "cos", "tan", "sqrt", "abs", "exp", "log", "ln", "pi", "e", "x"})
TIPOS = ("barras", "lineas", "sectores", "histograma", "dispersion")


def _num(v: Any) -> float:
    if isinstance(v, bool):
        raise ValueError("Se esperaba un numero.")
    n = float(v)
    if not math.isfinite(n) or abs(n) > 1e12:
        raise ValueError("Numero fuera de rango.")
    return n


def _par(v: Any) -> list[float]:
    if not isinstance(v, list | tuple) or len(v) != 2:
        raise ValueError("Se esperaba un par [x, y].")
    return [_num(v[0]), _num(v[1])]


def _nombre(v: Any, largo: int = 24) -> str:
    return str(v)[:largo] if v is not None else ""


def _rango(v: Any, defecto: list[float]) -> list[float]:
    try:
        a, b = _par(v)
    except (ValueError, TypeError):
        return defecto
    return [a, b] if a < b else defecto


def _objeto(dato: Any, que: str) -> dict:
    if isinstance(dato, str):
        try:
            dato = json.loads(dato)
        except json.JSONDecodeError as e:
            raise ValueError(f"La {que} no es JSON valido: {e}") from e
    if not isinstance(dato, dict):
        raise ValueError(f"La {que} tiene que ser un objeto.")
    return dato


def _redondo(n: float) -> float:
    """Sin colas de coma flotante (0.30000000000000004), y los enteros sin ".0".

    Este numero acaba en el texto que se le devuelve al modelo, y el modelo lo
    repite: "30" se lee mejor que "30.0".
    """
    r = float(f"{n:.6g}")
    return int(r) if r.is_integer() and abs(r) < 1e15 else r


# -- matematicas en ejes ----------------------------------------------------------------
def limpiar_grafica(dato: Any) -> dict[str, Any]:
    """Ejes con vectores, puntos, segmentos y funciones. ``ValueError`` si no hay nada."""
    dato = _objeto(dato, "grafica")

    def lista(clave: str, maximo: int, convertir: Callable[[dict], dict]) -> list[dict]:
        salida = []
        for item in (dato.get(clave) or [])[:maximo]:
            if isinstance(item, dict):
                try:
                    salida.append(convertir(item))
                except (ValueError, TypeError, KeyError):
                    continue
        return salida

    def funcion(i: dict) -> dict:
        f = str(i["f"]).lower().replace("**", "^")
        palabras = set(re.findall(r"[a-z]+", f))
        if not _EXPRESION.match(f) or not palabras <= _FUNCIONES:
            raise ValueError("Expresion no permitida.")
        return {"f": f, "nombre": _nombre(i.get("nombre"))}

    def flecha(i: dict) -> dict:
        return {
            "de": _par(i.get("de", [0, 0])),
            "a": _par(i["a"]),
            "nombre": _nombre(i.get("nombre")),
        }

    def punto(i: dict) -> dict:
        return {"en": _par(i["en"]), "nombre": _nombre(i.get("nombre"))}

    def segmento(i: dict) -> dict:
        return {"de": _par(i["de"]), "a": _par(i["a"]), "nombre": _nombre(i.get("nombre"))}

    limpia = {
        "x": _rango(dato.get("x"), [-10.0, 10.0]),
        "y": _rango(dato.get("y"), [-10.0, 10.0]),
        "vectores": lista("vectores", 40, flecha),
        "puntos": lista("puntos", 60, punto),
        "segmentos": lista("segmentos", 60, segmento),
        "funciones": lista("funciones", 8, funcion),
    }
    if not any(limpia[k] for k in ("vectores", "puntos", "segmentos", "funciones")):
        raise ValueError(
            "La grafica no tiene nada que dibujar: vectores, puntos, segmentos o funciones."
        )
    return limpia


# -- estadistica --------------------------------------------------------------------------
def _resumen(valores: list[float]) -> dict[str, float]:
    return {
        "n": len(valores),
        "suma": _redondo(sum(valores)),
        "media": _redondo(statistics.fmean(valores)),
        "mediana": _redondo(statistics.median(valores)),
        "desviacion": _redondo(statistics.stdev(valores)) if len(valores) > 1 else 0.0,
        "minimo": _redondo(min(valores)),
        "maximo": _redondo(max(valores)),
    }


def _categorias(dato: dict) -> list[str]:
    cats = [_nombre(c, 30) for c in (dato.get("categorias") or [])[:50]]
    if not cats:
        raise ValueError("Faltan las categorias (lista de nombres del eje x).")
    return cats


def _series_de_valores(dato: dict, cats: list[str]) -> list[dict]:
    crudas = dato.get("series")
    if not crudas and dato.get("valores") is not None:
        crudas = [{"nombre": "", "valores": dato["valores"]}]
    series = []
    for s in (crudas or [])[:6]:
        if not isinstance(s, dict):
            continue
        nombre = _nombre(s.get("nombre"))
        valores = [_num(v) for v in (s.get("valores") or [])]
        if len(valores) != len(cats):
            raise ValueError(
                f"La serie {nombre or 'sin nombre'} tiene {len(valores)} valores y hay "
                f"{len(cats)} categorias: tiene que haber uno por categoria."
            )
        series.append({"nombre": nombre, "valores": valores})
    if not series:
        raise ValueError('Faltan los datos: series [{"nombre": ..., "valores": [...]}].')
    return series


def limpiar_estadistica(dato: Any) -> dict[str, Any]:
    """Datos validados y calculos hechos. Incluye ``resumen``: el texto para el modelo."""
    dato = _objeto(dato, "estadistica")
    tipo = str(dato.get("tipo", "")).lower()
    if tipo not in TIPOS:
        raise ValueError(f"tipo tiene que ser uno de: {', '.join(TIPOS)}.")
    salida: dict[str, Any] = {
        "tipo": tipo,
        "eje_x": _nombre(dato.get("eje_x"), 40),
        "eje_y": _nombre(dato.get("eje_y"), 40),
    }
    lineas: list[str] = []

    if tipo in ("barras", "lineas"):
        cats = _categorias(dato)
        series = _series_de_valores(dato, cats)
        salida.update(categorias=cats, series=series)
        for s in series:
            r = _resumen(s["valores"])
            mayor = cats[s["valores"].index(max(s["valores"]))]
            menor = cats[s["valores"].index(min(s["valores"]))]
            lineas.append(
                f"{s['nombre'] or 'serie'}: total {r['suma']}, media {r['media']}, mediana "
                f"{r['mediana']}, maximo {r['maximo']} ({mayor}), minimo {r['minimo']} ({menor})"
            )

    elif tipo == "sectores":
        cats = _categorias(dato)
        valores = _series_de_valores(dato, cats)[0]["valores"]
        if any(v < 0 for v in valores) or sum(valores) <= 0:
            raise ValueError("En sectores los valores tienen que ser positivos y no sumar 0.")
        total = sum(valores)
        porcentajes = [_redondo(100 * v / total) for v in valores]
        salida.update(categorias=cats, valores=valores, porcentajes=porcentajes)
        lineas.append(f"total {_redondo(total)}")
        lineas += [
            f"{c}: {v:g} ({p:g}%)" for c, v, p in zip(cats, valores, porcentajes, strict=True)
        ]

    elif tipo == "histograma":
        datos = [_num(v) for v in (dato.get("datos") or [])[:5000]]
        if len(datos) < 2:
            raise ValueError("Un histograma necesita al menos dos datos en 'datos'.")
        lo, hi = min(datos), max(datos)
        pedidos = dato.get("intervalos")
        if isinstance(pedidos, int) and not isinstance(pedidos, bool) and 2 <= pedidos <= 60:
            k = pedidos
        else:
            k = max(5, min(30, math.ceil(math.log2(len(datos)) + 1)))  # regla de Sturges
        if hi == lo:
            hi = lo + 1
        ancho = (hi - lo) / k
        cuentas = [0] * k
        for v in datos:
            cuentas[min(k - 1, int((v - lo) / ancho))] += 1
        r = _resumen(datos)
        salida.update(
            intervalos=[
                {"desde": _redondo(lo + i * ancho), "hasta": _redondo(lo + (i + 1) * ancho), "n": n}
                for i, n in enumerate(cuentas)
            ],
            media=r["media"],
            mediana=r["mediana"],
        )
        mas = max(range(k), key=lambda i: cuentas[i])
        lineas.append(
            f"n {r['n']}, media {r['media']}, mediana {r['mediana']}, desviacion tipica "
            f"{r['desviacion']}, minimo {r['minimo']}, maximo {r['maximo']}; {k} intervalos de "
            f"ancho {_redondo(ancho)}; el mas poblado, "
            f"[{_redondo(lo + mas * ancho)}, {_redondo(lo + (mas + 1) * ancho)}) con {cuentas[mas]}"
        )

    else:  # dispersion
        series = []
        total = 0
        for s in (dato.get("series") or [])[:6]:
            if not isinstance(s, dict):
                continue
            puntos = [_par(p) for p in (s.get("puntos") or [])[: max(0, 1000 - total)]]
            total += len(puntos)
            if puntos:
                series.append({"nombre": _nombre(s.get("nombre")), "puntos": puntos})
        if not series:
            raise ValueError(
                'Faltan los puntos: series [{"nombre": ..., "puntos": [[x, y], ...]}].'
            )
        salida["series"] = series
        if dato.get("regresion"):
            for s in series:
                xs = [p[0] for p in s["puntos"]]
                ys = [p[1] for p in s["puntos"]]
                if len(set(xs)) < 2:
                    continue
                pendiente, ordenada = statistics.linear_regression(xs, ys)
                r = statistics.correlation(xs, ys) if len(set(ys)) > 1 else 0.0
                s["regresion"] = {
                    "pendiente": _redondo(pendiente),
                    "ordenada": _redondo(ordenada),
                    "r": _redondo(r),
                }
                lineas.append(
                    f"{s['nombre'] or 'serie'}: y = {_redondo(pendiente)}·x + {_redondo(ordenada)}"
                    f", r = {_redondo(r)}, r² = {_redondo(r * r)} ({len(xs)} puntos)"
                )
        if not lineas:
            lineas.append(f"{total} puntos en {len(series)} series")

    salida["resumen"] = "; ".join(lineas)
    return salida


# -- la herramienta -----------------------------------------------------------------------
class Graficas:
    """``mostrar_grafica``: pinta en la pantalla que le pasen (la ventana)."""

    def __init__(self, pantalla: Callable[[dict[str, Any]], None]) -> None:
        self._pantalla = pantalla
        self.mostradas: list[str] = []

    def mostrar(self, titulo: str, grafica: Any = None, estadistica: Any = None) -> str:
        titulo = (titulo or "").strip()[:80] or "Grafica"
        if estadistica:
            datos = limpiar_estadistica(estadistica)
            calculos = datos.pop("resumen")
            self._pantalla({"titulo": titulo, "estadistica": datos})
            self.mostradas.append(titulo)
            return (
                f"Mostrada en la pantalla del usuario: «{titulo}». Calculos exactos, usalos "
                f"al explicar en vez de calcular tu: {calculos}."
            )
        if grafica:
            self._pantalla({"titulo": titulo, "grafica": limpiar_grafica(grafica)})
            self.mostradas.append(titulo)
            return f"Mostrada en la pantalla del usuario: «{titulo}». Explicasela brevemente."
        return "Error: pasa una grafica (matematicas en ejes) o una estadistica (datos)."

    def herramientas(self) -> list[Herramienta]:
        return [
            Herramienta(
                "mostrar_grafica",
                "Muestra una grafica precisa en la pantalla del usuario, en el lugar del "
                "nucleo. Usala cuando pidan representar o graficar datos, estadisticas, "
                "funciones o vectores. Rellena solo uno: "
                "`grafica` para matematicas en ejes: {x:[min,max], y:[min,max] (que lo "
                'incluyan todo, con margen), vectores:[{"de":[0,0],"a":[3,2],"nombre":"u"}], '
                'puntos:[{"en":[1,2],"nombre":"P"}], segmentos:[{"de":[..],"a":[..]}], '
                'funciones:[{"f":"x^2-1","nombre":"f"}]} (con +-*/^, sin cos tan sqrt abs '
                "exp log, pi, e). "
                "`estadistica` para datos: {tipo: barras|lineas|sectores|histograma|dispersion, "
                'eje_x, eje_y}; barras, lineas y sectores llevan categorias:["A","B"] y '
                'series:[{"nombre":"2024","valores":[3,5]}] (un valor por categoria); '
                "histograma lleva datos:[...] e intervalos opcional; dispersion lleva "
                'series:[{"nombre":..,"puntos":[[x,y],..]}] y regresion:true si se quiere la '
                "recta. Los calculos (medias, porcentajes, intervalos, regresion) los hace la "
                "herramienta y te los devuelve: usalos en vez de calcular tu.",
                self.mostrar,
                {
                    "titulo": texto("Titulo corto de la grafica."),
                    "grafica": {"type": "object", "description": "Matematicas en ejes."},
                    "estadistica": {"type": "object", "description": "Datos y su tipo de grafica."},
                },
                requeridos=("titulo",),
                narrar=lambda a: f"Lo represento: {a.get('titulo') or 'grafica'}",
                familia="visual",
            )
        ]
