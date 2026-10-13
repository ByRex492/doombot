"""Historial de conversaciones, por carpetas, como en Claude Code (D-038).

Cada conversacion es un JSON en ``data_dir()/conversaciones``: titulo, carpeta,
modo, lo que se ve en el registro (los eventos tal cual se pintaron) y el estado
del agente, para retomarla donde se dejo -no solo releerla-. Las carpetas
existen aunque esten vacias (``carpetas.json``).

Es estado privado: lo que se habla con D.O.O.M. Por eso vive en la carpeta de
datos y no en el repositorio (ver ``paths.data_dir``).

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

from doombot.backends.base import (
    LlamadaHerramienta,
    MensajeAgente,
    PasoModelo,
    ResultadoHerramienta,
)

_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$")
_MAX_TITULO = 80
_MAX_CARPETA = 60


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

    def borrar_carpeta(self, nombre: str) -> None:
        """Borra la carpeta, no lo que contiene: sus conversaciones pasan a "sin carpeta"."""
        for c in self.lista():
            if c["carpeta"] == nombre:
                self.mover(c["id"], "")
        self._guardar_carpetas([c for c in self.carpetas() if c != nombre])
