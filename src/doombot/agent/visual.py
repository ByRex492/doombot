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

import contextlib
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


# -- el dibujante -------------------------------------------------------------------
# Un modelo con instrucciones solo de dibujo, sin herramientas ni conversacion
# alrededor: dibuja bastante mejor que el agente improvisando el SVG en mitad de
# una orden. Cuesta una peticion mas, y solo cuando hay que dibujar.
INSTRUCCIONES_DIBUJO = """Eres un ilustrador que dibuja en SVG para una interfaz oscura.
Devuelve SOLO el codigo SVG, sin explicaciones ni markdown.

Como trabajar:
1. Dentro del SVG, empieza con un comentario <!-- plan: ... --> donde decides la postura, las
   partes que lleva el objeto y la posicion y tamaño de cada una en el lienzo de 400x300.
2. Despues dibuja cada parte por separado, siguiendo el plan, con formas geometricas sencillas:
   ellipse, circle, rect con rx, line y path con curvas Q o C. Mejor pocas formas bien colocadas
   que una sola linea larga e improvisada.

Reglas:
- <svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg">. Sin fondo: es transparente.
- Color: stroke="currentColor"; si rellenas, fill="currentColor" con fill-opacity entre 0.12 y 0.35.
  Nunca negro ni blanco: el fondo ya es oscuro.
- Proporciones reales. Vista de perfil para animales y objetos. Centrado, ocupando el 70-80%.
- Trazo de 2 a 3, stroke-linecap="round" y stroke-linejoin="round".
- "Silueta": las mismas partes, todas con fill="currentColor" fill-opacity="0.3".
- Esquemas y diagramas: cajas con rect redondeado, texto legible (font-size 12 a 14,
  fill="currentColor"), flechas con <marker>.
- Prohibido: script, image, foreignObject, enlaces, style, atributos on*.

Ejemplo de como se trabaja (una taza; es solo una guia de metodo y estilo: cada objeto o
animal tiene sus propias partes y proporciones):
<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor"
 stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
<!-- plan: taza de frente, ligeramente desde arriba. cuerpo: rect redondeado (150,110) 110x120.
 boca: elipse arriba (205,110) 55x12. asa: curva a la derecha de (260,140) a (260,200). plato:
 elipse ancha (205,235) 105x14. vapor: tres curvas sobre la taza. -->
<rect x="150" y="110" width="110" height="120" rx="18" fill="currentColor" fill-opacity="0.15"/>
<ellipse cx="205" cy="110" rx="55" ry="12"/>
<path d="M260 140 C300 140 300 200 260 200"/>
<ellipse cx="205" cy="235" rx="105" ry="14" fill="currentColor" fill-opacity="0.12"/>
<path d="M185 90 Q175 75 185 60 M205 88 Q195 70 205 52 M225 90 Q215 75 225 60" stroke-width="2"/>
</svg>"""


# Medido el 13/10/2026 con el mismo encargo ("un caballo de perfil") y estas
# instrucciones: qwen3.8-27b dibujo el unico caballo reconocible de los modelos
# gratuitos de Groq, en 2 s; gpt-oss-120b, el que mejor usa herramientas, dibujo
# algo parecido a un perro. Gemini estaba saturado y no se pudo medir. Ver D-037.
DIBUJANTES_POR_DEFECTO = ("groq:qwen/qwen3.8-27b", "gemini")


def elegir_dibujante(
    cerebro: Any, preferidos: Any = DIBUJANTES_POR_DEFECTO, cfg: Any = None
) -> Any:
    """El modelo que dibuja: los preferidos primero, y el resto de la cadena detras.

    Cada preferido es un proveedor (``gemini``: el de la cadena) o una entrada
    ``proveedor:modelo``, que se monta aparte si hay clave -no hace falta que
    este en ``DOOMBOT_MODELOS``-. Si ninguno responde, dibuja el resto.
    """
    from doombot.backends.proveedores import construir, partir
    from doombot.backends.varios import Cadena, etiqueta

    if isinstance(preferidos, str):
        preferidos = [p.strip() for p in preferidos.split(",") if p.strip()]
    cadena = list(cerebro.generadores) if isinstance(cerebro, Cadena) else [cerebro]
    elegidos: list[Any] = []
    for pref in preferidos:
        if ":" in pref:
            proveedor, modelo = partir(pref)
            ya = [g for g in cadena if etiqueta(g) == f"{proveedor}/{modelo}"]
            if ya:
                elegidos += [g for g in ya if g not in elegidos]
            elif cfg is not None:
                # Sin clave para ese proveedor: se salta.
                with contextlib.suppress(ValueError):
                    elegidos.append(construir(pref, cfg))
        else:
            elegidos += [g for g in cadena if etiqueta(g).startswith(pref) and g not in elegidos]
    return Cadena([*elegidos, *(g for g in cadena if g not in elegidos)])


# -- la herramienta -----------------------------------------------------------------
# -- la herramienta -----------------------------------------------------------------
class Visual:
    """``mostrar_visual``: pinta en la pantalla que le pasen (la ventana)."""

    def __init__(self, pantalla: Callable[[dict[str, Any]], None], dibujante: Any = None) -> None:
        self._pantalla = pantalla
        self._dibujante = dibujante
        self.mostrados: list[str] = []

    def mostrar(self, titulo: str, encargo: str = "", grafica: Any = None, svg: str = "") -> str:
        titulo = (titulo or "").strip()[:80] or "Visual"
        if grafica:
            datos = {"titulo": titulo, "grafica": limpiar_grafica(grafica)}
        elif encargo and self._dibujante is not None:
            datos = {"titulo": titulo, "svg": self._dibujar(titulo, encargo)}
        elif svg:
            datos = {"titulo": titulo, "svg": limpiar_svg(svg)}
        else:
            return (
                "Error: pasa una grafica (para matematicas) o un encargo (para dibujos y esquemas)."
            )
        self._pantalla(datos)
        self.mostrados.append(titulo)
        return f"Mostrado en la pantalla del usuario: «{titulo}». Explicaselo brevemente."

    def _dibujar(self, titulo: str, encargo: str) -> str:
        """Le pide el dibujo al dibujante y lo limpia. Un SVG roto se pide una vez mas."""
        from doombot.backends.base import BackendError

        pedido = f"Dibuja: {titulo}. {encargo}"
        for intento in range(2):
            try:
                crudo = self._dibujante.generate(pedido, system=INSTRUCCIONES_DIBUJO)
            except BackendError as e:
                raise ValueError(f"El dibujante no responde: {e}") from e
            # El modelo a veces escribe algo antes o despues: se aisla el <svg>.
            inicio, fin = crudo.find("<svg"), crudo.rfind("</svg>")
            try:
                return limpiar_svg(
                    crudo[inicio : fin + 6] if inicio >= 0 and fin > inicio else crudo
                )
            except ValueError as e:
                if intento:
                    raise
                pedido += (
                    f"\n\nEl intento anterior no era un SVG valido ({e}). Devuelve solo el SVG."
                )
        raise AssertionError("inalcanzable")

    def herramientas(self) -> list[Herramienta]:
        return [
            Herramienta(
                "mostrar_visual",
                "Muestra en la pantalla del usuario una grafica, un esquema o un dibujo, en el "
                "lugar del nucleo. Usalo cuando pidan representar, dibujar, graficar o explicar "
                "algo visualmente, y tambien cuando un esquema explique mejor que el texto. "
                "Para matematicas (vectores, puntos, rectas, funciones) usa SIEMPRE `grafica`, "
                "nunca un dibujo: objeto con x e y (rangos [min,max] que incluyan todo, con algo "
                'de margen), vectores [{"de":[0,0],"a":[3,2],"nombre":"u"}], puntos [{"en":[1,2],'
                '"nombre":"P"}], segmentos [{"de":[..],"a":[..]}] y funciones [{"f":"x^2-1",'
                '"nombre":"f"}] (con +-*/^, sin cos tan sqrt abs exp log, pi, e). '
                "Para dibujos y esquemas usa `encargo`: describe con detalle que dibujar (objeto, "
                "postura, partes, estilo); lo dibuja un modelo especializado. "
                "Rellena solo uno de los dos.",
                self.mostrar,
                {
                    "titulo": texto("Titulo corto de lo que se muestra."),
                    "grafica": {"type": "object", "description": "Para matematicas (ver arriba)."},
                    "encargo": texto("Para dibujos y esquemas: descripcion detallada."),
                },
                requeridos=("titulo",),
                narrar=lambda a: f"Lo represento: {a.get('titulo') or 'visual'}",
                familia="visual",
            )
        ]
