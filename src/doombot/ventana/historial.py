"""Historial de conversaciones, por carpetas, como en Claude Code (D-038).

Cada conversacion es un JSON en ``data_dir()/conversaciones``: titulo, carpeta,
modo, lo que se ve en el registro (los eventos tal cual se pintaron) y el estado
del agente, para retomarla donde se dejo -no solo releerla-. Las carpetas
existen aunque esten vacias (``carpetas.json``).

Es estado privado: lo que se habla con D.O.O.M. Por eso vive en la carpeta de
datos y no en el repositorio (ver ``paths.data_dir``).

Una carpeta es tambien un **proyecto** (D-040): unas instrucciones, unas notas
y el resumen de cada conversacion, que reciben todas las demas de la carpeta.
Asi un chat puede seguir lo que se decidio en otro.

Los identificadores llegan de la ventana: se validan contra un patron antes de
convertirse en nombre de fichero, para que nada fuera de la carpeta se pueda
leer ni borrar con un ``../``.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from doombot.agent.herramientas import Herramienta, texto, truncar
from doombot.backends.base import (
    LlamadaHerramienta,
    MensajeAgente,
    PasoModelo,
    ResultadoHerramienta,
)

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
_MAX_TITULO = 80
_MAX_CARPETA = 60
_MAX_INSTRUCCIONES = 4000
_MAX_NOTA = 300
_MAX_NOTAS = 40
_MAX_RESUMEN = 1500
# Lo que cabe del proyecto en el prompt de cada chat: con las capas gratuitas,
# cada paso del agente lo reenvia (limite de tokens por minuto).
_MAX_CONTEXTO = 5000
_MAX_CHAT_LEIDO = 8000


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def titulo_de(texto: str) -> str:
    """El titulo de una conversacion nueva: su primera orden, recortada."""
    plano = " ".join((texto or "").split())
    return plano if len(plano) <= 48 else plano[:47] + "…"


# -- el estado del agente, a JSON y de vuelta -----------------------------------------------
def serializar(conversacion: list[MensajeAgente]) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    for m in conversacion:
        if isinstance(m, str):
            salida.append({"t": "usuario", "texto": m})
        elif isinstance(m, PasoModelo):
            salida.append(
                {
                    "t": "modelo",
                    "texto": m.texto,
                    "llamadas": [
                        {
                            "id": ll.id,
                            "nombre": ll.nombre,
                            "argumentos": ll.argumentos,
                            "extra": ll.extra,
                        }
                        for ll in m.llamadas
                    ],
                }
            )
        elif isinstance(m, ResultadoHerramienta):
            salida.append(
                {"t": "resultado", "id": m.id, "nombre": m.nombre, "contenido": m.contenido}
            )
    return salida


def deserializar(datos: list[dict[str, Any]]) -> list[MensajeAgente]:
    salida: list[MensajeAgente] = []
    for d in datos or []:
        tipo = d.get("t")
        if tipo == "usuario":
            salida.append(str(d.get("texto", "")))
        elif tipo == "modelo":
            salida.append(
                PasoModelo(
                    str(d.get("texto", "")),
                    tuple(
                        LlamadaHerramienta(
                            str(ll.get("id", "")),
                            str(ll.get("nombre", "")),
                            dict(ll.get("argumentos") or {}),
                            dict(ll.get("extra") or {}),
                        )
                        for ll in d.get("llamadas") or []
                    ),
                )
            )
        elif tipo == "resultado":
            salida.append(
                ResultadoHerramienta(
                    str(d.get("id", "")), str(d.get("nombre", "")), str(d.get("contenido", ""))
                )
            )
    return salida


class Historial:
    def __init__(self, carpeta: Path | None = None) -> None:
        if carpeta is None:
            from doombot.paths import data_dir

            carpeta = data_dir() / "conversaciones"
        self.carpeta = carpeta
        self.carpeta.mkdir(parents=True, exist_ok=True)
        self._cerrojo = threading.Lock()

    # -- conversaciones ------------------------------------------------------------------
    @staticmethod
    def nuevo_id() -> str:
        return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"

    def _ruta(self, id_: str) -> Path:
        if not _ID.match(str(id_)):
            raise ValueError(f"Identificador no valido: {id_!r}")
        return self.carpeta / f"{id_}.json"

    def nueva(self, titulo: str, carpeta: str = "", modo: str = "global") -> dict[str, Any]:
        return {
            "id": self.nuevo_id(),
            "titulo": titulo_de(titulo) or "Conversación",
            "carpeta": self._carpeta(carpeta),
            "modo": modo,
            "creada": _ahora(),
            "actualizada": _ahora(),
            "registro": [],
            "agente": [],
        }

    def guardar(self, conv: dict[str, Any]) -> None:
        conv["actualizada"] = _ahora()
        ruta = self._ruta(conv["id"])
        temporal = ruta.with_suffix(".tmp")
        with self._cerrojo:
            # Primero a un temporal y despues se sustituye: un cierre a medias no
            # deja una conversacion corrupta.
            temporal.write_text(json.dumps(conv, ensure_ascii=False), encoding="utf-8")
            temporal.replace(ruta)

    def leer(self, id_: str) -> dict[str, Any] | None:
        try:
            return json.loads(self._ruta(id_).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def lista(self) -> list[dict[str, Any]]:
        """Resumen de todas, de la mas reciente a la mas antigua."""
        salida = []
        for fichero in self.carpeta.glob("*.json"):
            if not _ID.match(fichero.stem):
                continue
            try:
                c = json.loads(fichero.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            salida.append(
                {k: c.get(k, "") for k in ("id", "titulo", "carpeta", "modo", "actualizada")}
            )
        return sorted(salida, key=lambda c: c["actualizada"], reverse=True)

    def _cambiar(self, id_: str, **campos: Any) -> bool:
        conv = self.leer(id_)
        if conv is None:
            return False
        conv.update(campos)
        self.guardar(conv)
        return True

    def renombrar(self, id_: str, titulo: str) -> bool:
        titulo = " ".join((titulo or "").split())[:_MAX_TITULO]
        return bool(titulo) and self._cambiar(id_, titulo=titulo)

    def mover(self, id_: str, carpeta: str) -> bool:
        return self._cambiar(id_, carpeta=self._carpeta(carpeta))

    def borrar(self, id_: str) -> bool:
        ruta = self._ruta(id_)
        with self._cerrojo:
            if ruta.is_file():
                ruta.unlink()
                return True
        return False

    # -- carpetas ----------------------------------------------------------------------------
    def _carpeta(self, nombre: str) -> str:
        return " ".join((nombre or "").split())[:_MAX_CARPETA]

    def _fichero_carpetas(self) -> Path:
        return self.carpeta / "carpetas.json"

    def carpetas(self) -> list[str]:
        try:
            guardadas = json.loads(self._fichero_carpetas().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            guardadas = []
        en_uso = {c["carpeta"] for c in self.lista() if c["carpeta"]}
        return sorted({*(c for c in guardadas if isinstance(c, str) and c), *en_uso}, key=str.lower)

    def _guardar_carpetas(self, carpetas: list[str]) -> None:
        with self._cerrojo:
            self._fichero_carpetas().write_text(json.dumps(sorted(set(carpetas))), encoding="utf-8")

    def crear_carpeta(self, nombre: str) -> str:
        nombre = self._carpeta(nombre)
        if not nombre:
            raise ValueError("La carpeta necesita un nombre.")
        self._guardar_carpetas([*self.carpetas(), nombre])
        return nombre

    def renombrar_carpeta(self, vieja: str, nueva: str) -> None:
        nueva = self._carpeta(nueva)
        if not nueva:
            raise ValueError("La carpeta necesita un nombre.")
        for c in self.lista():
            if c["carpeta"] == vieja:
                self.mover(c["id"], nueva)
        self._guardar_carpetas([nueva if c == vieja else c for c in self.carpetas()])
        proyectos = self._proyectos()
        if vieja in proyectos:
            proyectos[nueva] = proyectos.pop(vieja)
            self._guardar_proyectos(proyectos)

    def borrar_carpeta(self, nombre: str) -> None:
        """Borra la carpeta, no lo que contiene: sus conversaciones pasan a "sin carpeta"."""
        for c in self.lista():
            if c["carpeta"] == nombre:
                self.mover(c["id"], "")
        self._guardar_carpetas([c for c in self.carpetas() if c != nombre])
        proyectos = self._proyectos()
        if proyectos.pop(nombre, None) is not None:
            self._guardar_proyectos(proyectos)

    # -- proyectos (D-040) -------------------------------------------------------------------
    def _fichero_proyectos(self) -> Path:
        return self.carpeta / "proyectos.json"

    def _proyectos(self) -> dict[str, dict[str, Any]]:
        try:
            datos = json.loads(self._fichero_proyectos().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return datos if isinstance(datos, dict) else {}

    def _guardar_proyectos(self, datos: dict[str, dict[str, Any]]) -> None:
        with self._cerrojo:
            self._fichero_proyectos().write_text(
                json.dumps(datos, ensure_ascii=False), encoding="utf-8"
            )

    def _cambiar_proyecto(self, nombre: str, **campos: Any) -> None:
        nombre = self._carpeta(nombre)
        if not nombre:
            raise ValueError("Las conversaciones sin carpeta no son un proyecto.")
        proyectos = self._proyectos()
        proyectos.setdefault(nombre, {}).update(campos)
        self._guardar_proyectos(proyectos)

    def chats_de(self, nombre: str) -> list[dict[str, Any]]:
        """Las conversaciones del proyecto, con su resumen, de la mas reciente a la mas antigua."""
        salida = []
        for c in self.lista():
            if c["carpeta"] == nombre:
                conv = self.leer(c["id"]) or {}
                salida.append({**c, "resumen": conv.get("resumen", "")})
        return salida

    def proyecto(self, nombre: str) -> dict[str, Any]:
        datos = self._proyectos().get(nombre, {})
        return {
            "nombre": nombre,
            "instrucciones": datos.get("instrucciones", ""),
            "notas": list(datos.get("notas", [])),
            "chats": self.chats_de(nombre),
        }

    def guardar_instrucciones(self, nombre: str, instrucciones: str) -> None:
        self._cambiar_proyecto(
            nombre, instrucciones=(instrucciones or "").strip()[:_MAX_INSTRUCCIONES]
        )

    def anotar_proyecto(self, nombre: str, nota: str) -> str:
        nota = " ".join((nota or "").split())[:_MAX_NOTA]
        if not nota:
            raise ValueError("La nota esta vacia.")
        notas = [*self.proyecto(nombre)["notas"], f"{datetime.now():%Y-%m-%d} {nota}"]
        self._cambiar_proyecto(nombre, notas=notas[-_MAX_NOTAS:])
        return nota

    def borrar_nota_proyecto(self, nombre: str, indice: int) -> None:
        notas = self.proyecto(nombre)["notas"]
        if not 0 <= indice < len(notas):
            raise ValueError("Esa nota ya no existe.")
        del notas[indice]
        self._cambiar_proyecto(nombre, notas=notas)

    def contexto_proyecto(self, nombre: str, excluir: str = "") -> str:
        """Lo que sabe del proyecto cada chat suyo: instrucciones, notas y los demas chats."""
        p = self.proyecto(nombre)
        partes = [
            f"Esta conversacion es parte del proyecto «{nombre}», que tiene otras. Sigue lo que "
            "se haya decidido en ellas salvo que el usuario diga otra cosa."
        ]
        if p["instrucciones"]:
            partes.append(f"Instrucciones del proyecto (del usuario):\n{p['instrucciones']}")
        if p["notas"]:
            partes.append("Notas del proyecto:\n" + "\n".join(f"- {n}" for n in p["notas"]))
        otros = [c for c in p["chats"] if c["id"] != excluir]
        if otros:
            lineas = [
                f"- «{c['titulo']}»: {c['resumen'] or '(sin resumen todavia)'}" for c in otros[:12]
            ]
            partes.append(
                "Otras conversaciones del proyecto (resumenes; lo completo, con "
                "leer_conversacion_proyecto):\n" + "\n".join(lineas)
            )
        return truncar("\n\n".join(partes), _MAX_CONTEXTO)

    def leer_chat(self, nombre: str, cual: str) -> str:
        """Lo que se pidio y se respondio en un chat del proyecto, por su titulo (o parte)."""
        buscado = " ".join((cual or "").split()).lower()
        candidatos = [
            c for c in self.chats_de(nombre) if buscado and buscado in c["titulo"].lower()
        ] or [c for c in self.chats_de(nombre) if c["id"] == cual]
        if not candidatos:
            titulos = ", ".join(f"«{c['titulo']}»" for c in self.chats_de(nombre)) or "ninguna"
            return f"Error: no hay ninguna conversacion asi en el proyecto. Hay: {titulos}."
        conv = self.leer(candidatos[0]["id"]) or {}
        lineas = []
        for m in conv.get("agente", []):
            if m.get("t") == "usuario":
                lineas.append(f"Usuario: {m.get('texto', '')}")
            elif m.get("t") == "modelo" and not m.get("llamadas") and m.get("texto"):
                lineas.append(f"D.O.O.M: {m['texto']}")
        cuerpo = "\n\n".join(lineas) or "(vacia)"
        return f"Conversacion «{conv.get('titulo', '')}»:\n" + truncar(cuerpo, _MAX_CHAT_LEIDO)


class ProyectoActivo:
    """El proyecto de la conversacion abierta, tal como lo ve el agente (D-040)."""

    def __init__(self, historial: Historial, nombre: str, actual: Any = lambda: "") -> None:
        self.historial = historial
        self.nombre = nombre
        self._actual = actual
        """Id de la conversacion abierta: no se le cuenta su propio resumen."""

    def contexto(self) -> str:
        return self.historial.contexto_proyecto(self.nombre, excluir=self._actual())

    def herramientas(self) -> list[Herramienta]:
        return [
            Herramienta(
                "leer_conversacion_proyecto",
                "Lee lo que se pidio y respondio en otra conversacion de este proyecto (por su "
                "titulo o parte de el), para seguir lo que se decidio alli: un diseño, un plan, "
                "unos datos.",
                lambda conversacion: self.historial.leer_chat(self.nombre, conversacion),
                {"conversacion": texto("Titulo, o parte del titulo, de la conversacion.")},
                requeridos=("conversacion",),
                narrar=lambda a: f"Leo la conversación «{a.get('conversacion')}» del proyecto",
                familia="consulta",
            ),
            Herramienta(
                "anotar_en_proyecto",
                "Apunta en el proyecto una decision o dato clave que deban conocer sus demas "
                "conversaciones (ej. 'Paleta: azul #1e3a8a y dorado'). Una frase concreta. Solo "
                "lo decidido con el usuario, no lo leido en paginas o ficheros.",
                lambda nota: (
                    f"Apuntado en «{self.nombre}»: "
                    + self.historial.anotar_proyecto(self.nombre, nota)
                ),
                {"nota": texto("La decision o el dato, en una frase.")},
                requeridos=("nota",),
                narrar=lambda a: f"Lo apunto en el proyecto: {a.get('nota')}",
                familia="consulta",
            ),
        ]
