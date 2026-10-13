"""Enseñar en vez de contar: graficas, esquemas y dibujos en la ventana (D-037).

La herramienta ``mostrar_visual`` solo existe cuando hay una pantalla donde
pintar -la ventana-; en consola o por voz no se ofrece al modelo. Admite dos
cosas:

- ``grafica``: una descripcion de lo que hay que dibujar en unos ejes
  (vectores, puntos, segmentos, funciones). La ventana lo dibuja con
  precision; el modelo no tiene que calcular pixeles, solo coordenadas.
- ``svg``: un dibujo o esquema libre, en SVG.

**El SVG se limpia antes de llegar a la ventana, sin excepciones.** Un SVG
puede llevar ``<script>``, manejadores ``onload``, enlaces o recursos
externos, y la ventana tiene acceso a Python (``js_api``): un dibujo con
codigo, venga de un modelo equivocado o de una pagina que le ha colado
instrucciones, podria pedir cosas al agente. ``limpiar_svg`` reconstruye el
dibujo desde cero con una lista blanca de etiquetas y atributos; lo que no
esta en ella no pasa.
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from doombot.agent.herramientas import Herramienta, texto

_MAX_SVG = 60_000

_ETIQUETAS = frozenset({
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "defs", "marker", "lineargradient", "radialgradient", "stop",
    "title", "desc", "clippath",
})  # fmt: skip
_ATRIBUTOS = frozenset({
    "viewbox", "preserveaspectratio", "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy",
    "r", "rx", "ry", "fx", "fy", "width", "height", "points", "transform", "id",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset",
    "opacity", "font-size", "font-weight", "font-family", "font-style", "text-anchor",
    "dominant-baseline", "letter-spacing", "offset", "stop-color", "stop-opacity",
    "gradientunits", "gradienttransform", "marker-start", "marker-mid", "marker-end",
    "markerwidth", "markerheight", "markerunits", "refx", "refy", "orient",
    "clip-path", "clippathunits", "dx", "dy", "rotate",
})  # fmt: skip
# Las etiquetas de SVG distinguen mayusculas (linearGradient); se comparan en
# minusculas, y al reconstruir se usa la forma correcta.
_FORMA = {e.lower(): e for e in ("linearGradient", "radialGradient", "clipPath")}
_ATRIB_FORMA = {
    a.lower(): a
    for a in (
        "viewBox", "preserveAspectRatio", "gradientUnits", "gradientTransform",
        "markerWidth", "markerHeight", "markerUnits", "refX", "refY", "clipPathUnits",
    )
}  # fmt: skip
_URL_INTERNA = re.compile(r"^\s*url\(\s*#[\w.-]+\s*\)\s*$")
_PELIGROSO = re.compile(r"javascript:|data:|expression\(|@import", re.IGNORECASE)


def _local(nombre: str) -> tuple[str, str]:
    """``{espacio}nombre`` -> (espacio, nombre)."""
    if nombre.startswith("{"):
        espacio, _, local = nombre[1:].partition("}")
        return espacio, local
    return "", nombre


def limpiar_svg(crudo: str) -> str:
    """El SVG reconstruido solo con lo permitido. ``ValueError`` si no es un SVG."""
    texto = (crudo or "").strip()
    # Los modelos a veces lo envuelven en un bloque de codigo de markdown.
    texto = re.sub(r"^```(?:svg|xml)?\s*|\s*```$", "", texto).strip()
    if not texto or len(texto) > _MAX_SVG:
        raise ValueError("El SVG esta vacio o es demasiado grande.")
    # Sin DOCTYPE no hay entidades: ni externas (XXE) ni anidadas que se
    # multiplican al expandirse (billion laughs). Es la defensa que daria
    # defusedxml, sin añadir una dependencia para esto solo.
    if re.search(r"<!(DOCTYPE|ENTITY)", texto, re.IGNORECASE):
        raise ValueError("El SVG no puede llevar DOCTYPE ni entidades.")
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise ValueError(f"El SVG no es XML valido: {e}") from e
    if _local(raiz.tag)[1].lower() != "svg":
        raise ValueError("La raiz tiene que ser <svg>.")

    def copiar(origen: ET.Element) -> ET.Element | None:
        espacio, nombre = _local(origen.tag)
        nombre = nombre.lower()
        if espacio not in ("", "http://www.w3.org/2000/svg") or nombre not in _ETIQUETAS:
            return None
        destino = ET.Element(_FORMA.get(nombre, nombre))
        for clave, valor in origen.attrib.items():
            espacio_a, local_a = _local(clave)
            local_a = local_a.lower()
            if espacio_a or local_a not in _ATRIBUTOS:
                continue  # fuera on*, href, style, class y todo lo que lleve espacio (xlink)
            if _PELIGROSO.search(valor) or ("url(" in valor and not _URL_INTERNA.match(valor)):
                continue
            destino.set(_ATRIB_FORMA.get(local_a, local_a), valor)
        destino.text = origen.text if nombre in ("text", "tspan", "title", "desc") else None
        for hijo in origen:
            copia = copiar(hijo)
            if copia is not None:
                if nombre in ("text", "tspan"):
                    copia.tail = hijo.tail
                destino.append(copia)
        return destino

    limpio = copiar(raiz)
    assert limpio is not None
    # Sin viewBox no se puede escalar al hueco del nucleo: se deduce del tamaño.
    if "viewBox" not in limpio.attrib:
        ancho = re.sub(r"[^\d.]", "", limpio.get("width", "")) or "400"
        alto = re.sub(r"[^\d.]", "", limpio.get("height", "")) or "300"
        limpio.set("viewBox", f"0 0 {ancho} {alto}")
    limpio.attrib.pop("width", None)
    limpio.attrib.pop("height", None)
    limpio.set("xmlns", "http://www.w3.org/2000/svg")
    return ET.tostring(limpio, encoding="unicode")


# -- graficas ---------------------------------------------------------------------
_EXPRESION = re.compile(r"^[0-9x+\-*/^().,\s a-z]{1,120}$")
_FUNCIONES = frozenset({"sin", "cos", "tan", "sqrt", "abs", "exp", "log", "ln", "pi", "e", "x"})


def _num(v: Any) -> float:
    n = float(v)
    if not math.isfinite(n) or abs(n) > 1e6:
        raise ValueError("Numero fuera de rango.")
    return n


def _par(v: Any) -> list[float]:
    if not isinstance(v, list | tuple) or len(v) != 2:
        raise ValueError("Se esperaba un par [x, y].")
    return [_num(v[0]), _num(v[1])]


def _nombre(v: Any) -> str:
    return str(v)[:24] if v is not None else ""


def _rango(v: Any, defecto: list[float]) -> list[float]:
    try:
        a, b = _par(v)
    except (ValueError, TypeError):
        return defecto
    return [a, b] if a < b else defecto


def limpiar_grafica(dato: Any) -> dict[str, Any]:
    """La descripcion de la grafica, validada. ``ValueError`` si no queda nada que dibujar."""
    if isinstance(dato, str):
        try:
            dato = json.loads(dato)
        except json.JSONDecodeError as e:
            raise ValueError(f"La grafica no es JSON valido: {e}") from e
    if not isinstance(dato, dict):
        raise ValueError("La grafica tiene que ser un objeto.")

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


# -- la herramienta -----------------------------------------------------------------
class Visual:
    """``mostrar_visual``: pinta en la pantalla que le pasen (la ventana)."""

    def __init__(self, pantalla: Callable[[dict[str, Any]], None]) -> None:
        self._pantalla = pantalla
        self.mostrados: list[str] = []

    def mostrar(self, titulo: str, svg: str = "", grafica: Any = None) -> str:
        titulo = (titulo or "").strip()[:80] or "Visual"
        if grafica:
            datos = {"titulo": titulo, "grafica": limpiar_grafica(grafica)}
        elif svg:
            datos = {"titulo": titulo, "svg": limpiar_svg(svg)}
        else:
            return "Error: pasa una grafica (para matematicas) o un svg (para dibujos y esquemas)."
        self._pantalla(datos)
        self.mostrados.append(titulo)
        return f"Mostrado en la pantalla del usuario: «{titulo}». Explicaselo brevemente."

    def herramientas(self) -> list[Herramienta]:
        return [
            Herramienta(
                "mostrar_visual",
                "Muestra en la pantalla del usuario una grafica, un esquema o un dibujo, en el "
                "lugar del nucleo. Usalo cuando pidan representar, dibujar, graficar o explicar "
                "algo visualmente, y tambien cuando un esquema explique mejor que el texto. "
                "Para matematicas usa `grafica`: objeto con x e y (rangos [min,max]), "
                'vectores [{"de":[0,0],"a":[3,2],"nombre":"u"}], puntos [{"en":[1,2],'
                '"nombre":"P"}], segmentos [{"de":[..],"a":[..]}] y funciones [{"f":"x^2-1",'
                '"nombre":"f"}] (con +-*/^, sin cos tan sqrt abs exp log, pi, e). '
                "Para dibujos y esquemas usa `svg`: un SVG sencillo con viewBox 0 0 400 300, "
                'solo formas y texto (sin scripts ni imagenes), con stroke="currentColor" '
                "para que tome el color de la interfaz. Rellena solo uno de los dos.",
                self.mostrar,
                {
                    "titulo": texto("Titulo corto de lo que se muestra."),
                    "grafica": {"type": "object", "description": "Para matematicas (ver arriba)."},
                    "svg": texto("Para dibujos y esquemas: el SVG completo."),
                },
                requeridos=("titulo",),
                narrar=lambda a: f"Lo represento: {a.get('titulo') or 'visual'}",
                familia="visual",
            )
        ]
