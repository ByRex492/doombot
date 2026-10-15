"""La memoria del agente (D-043): quien es el usuario, siempre; lo demas, cuando viene a cuento.

Dos piezas que ya existian para la voz, por fin al alcance del agente:

- **El perfil** (``obsidian/usuario.md``, ``doombot.obsidian``): quien es el
  usuario y como quiere que le respondan. Entra en el prompt de TODAS las
  ordenes. Se edita en la ventana (Perfil), por voz ("recuerda que yo...") o a
  mano en Obsidian, y viaja con el repositorio entre equipos.
- **Los recuerdos** (``memory.db``, ``doombot.memory``): datos sueltos que se
  buscan por significado y entran en el prompt solo si se parecen a la orden.
  Son de cada equipo, como el historial. Necesitan fastembed; sin el, el
  perfil sigue funcionando y las herramientas de recuerdos no se ofrecen.

Lo que se guarda para siempre puede envenenar todas las conversaciones que
vengan, asi que se pide permiso cuando hay riesgo: siempre para el perfil -va
en todos los prompts y sube a GitHub con el repositorio-, y para un recuerdo
solo si en la misma orden se ha leido algo de fuera (una pagina, un fichero,
un comando). Es lo que impide que un texto leido se cuele como "algo que me
dijo el usuario". Las contraseñas, claves y datos bancarios no se guardan
nunca, ni con permiso.

Cada operacion abre su propia conexion a ``memory.db``: SQLite no deja usar
una conexion desde otro hilo, y la ventana consulta la memoria desde los
suyos mientras el agente trabaja en el propio.
"""

from __future__ import annotations

import contextlib
import re
import threading
from collections.abc import Callable
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from doombot.agent import personalidad
from doombot.agent.herramientas import Herramienta, entero, texto
from doombot.memory import Memory
from doombot.obsidian import (
    CAMPOS_PERFIL,
    anotar_hecho,
    guardar_perfil,
    leer_perfil,
    perfil_para_prompt,
    quitar_hecho,
)
from doombot.obsidian.vault import perfil_path

if TYPE_CHECKING:
    from doombot.backends.base import Embedder
    from doombot.memory import Recollection

FUERA = frozenset({"web", "ficheros", "terminal"})
"""Las familias de herramientas que traen texto de fuera (ver ``Herramienta.familia``)."""

_SECRETO = re.compile(
    # claves de API con prefijo conocido
    r"\b(gsk_|sk-|sk_live_|AIza|nvapi-|ghp_|github_pat_|xox[abp]-)[\w-]{8,}"
    # numeros de tarjeta: 13 a 19 cifras, con o sin separadores
    r"|\b(?:\d[ -]?){12,18}\d\b"
    # IBAN
    r"|\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){4,}"
    # "la contraseña es ...", "pin: ...", "clave del wifi = ..."
    r"|\b(contrase(ñ|n)as?|password|passwd|pin|clave (de acceso|del wifi|secreta|de la api|api)"
    r"|api key)\b[^.\n]{0,25}?(\bes\b|\bson\b|:|=)",
    re.IGNORECASE,
)

_RECHAZO = (
    "Error: eso parece una contrasena, una clave o un dato bancario, y eso no se guarda nunca "
    "en la memoria. Dile al usuario que lo guarde en un gestor de contrasenas."
)

_RECHAZO_PERFIL = (
    "Eso parece una contrasena, una clave o un dato bancario: no lo guardo (el perfil viaja con "
    "el repositorio)."
)

_CABECERA_RECUERDOS = (
    "Notas de tu memoria, de conversaciones anteriores, por si vienen al caso: usa solo las "
    "que traten de lo pedido."
)


def parece_secreto(texto_: str) -> bool:
    return bool(_SECRETO.search(texto_))


def _una_linea(t: Any) -> str:
    return " ".join(str(t or "").split()).removeprefix("- ").strip()


def _fecha(r: Recollection) -> str:
    return f"{r.created_at.astimezone():%d/%m/%Y}"


class Contexto(NamedTuple):
    """Lo que la memoria aporta a una orden."""

    texto: str
    recordados: list[str]
    aviso: str = ""
    """Por que no se ha podido buscar en los recuerdos, si ha fallado."""


class Memoria:
    """El perfil y los recuerdos, tal como los usan el agente y la ventana."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        *,
        ruta: Path | None = None,
        vault_dir: Path | None = None,
        motivo: str = "",
    ) -> None:
        self._embedder = embedder
        self._ruta = ruta
        self._vault = vault_dir
        self.motivo = "" if embedder is not None else motivo
        """Por que no hay recuerdos, si no los hay: para contarlo en la ventana."""
        self.leido_fuera: Callable[[], bool] = lambda: False
        """Si en la orden en curso ya se ha leido algo de fuera. Lo conecta ``montar``."""
        self._cerrojo = threading.Lock()
        self._preparado = False

    @property
    def activa(self) -> bool:
        """Si hay recuerdos, ademas del perfil."""
        return self._embedder is not None

    def _abrir(self) -> Memory:
        return Memory(self._embedder, self._ruta)

    def _preparar(self, *, esperar: bool = True) -> bool:
        """Carga el modelo de embeddings una sola vez, aunque lo pidan dos hilos a la vez.

        Con ``esperar=False`` no espera a otro hilo que ya lo este cargando: una
        orden no debe quedarse parada por la precarga, va sin recuerdos.
        """
        if self._preparado:
            return True
        if not self._cerrojo.acquire(blocking=esperar):
            return False
        try:
            if not self._preparado:
                self._embedder.embed(["preparar la memoria"])
                self._preparado = True
            return True
        finally:
            self._cerrojo.release()

    def precargar(self) -> None:
        """Carga el modelo en segundo plano si hay recuerdos, para que la primera orden no espere.

        Sin recuerdos no hace falta: hasta que se guarde el primero no hay nada
        que comparar, y cargar unos cientos de MB para nada es lo que se evita.
        """
        if not self.activa:
            return

        def cargar() -> None:
            with contextlib.suppress(Exception):
                with self._abrir() as m:
                    if not m.count(kind="fact"):
                        return
                self._preparar()

        threading.Thread(target=cargar, name="memoria", daemon=True).start()

    # -- en cada orden ----------------------------------------------------------
    def contexto(self, tarea: str) -> Contexto:
        """Su personalidad (D-044), el perfil, y los recuerdos que se parezcan a la orden."""
        bloques = [
            personalidad.para_prompt(self._vault),
            perfil_para_prompt(leer_perfil(self._vault)),
        ]
        recordados: list[str] = []
        aviso = ""
        if self.activa:
            try:
                with self._abrir() as m:
                    if m.count(kind="fact") and self._preparar(esperar=False):
                        recordados = [r.text for r in m.recall(tarea, limit=5, kind="fact")]
            except Exception as e:  # noqa: BLE001 - sin recuerdos, pero con el perfil
                aviso = str(e)
        if recordados:
            bloques.append(_CABECERA_RECUERDOS + "\n" + "\n".join(f"- {t}" for t in recordados))
        return Contexto("\n\n".join(b for b in bloques if b), recordados, aviso)

    # -- las herramientas -------------------------------------------------------
    def anotar_usuario(self, hecho: str) -> str:
        hecho = _una_linea(hecho)
        if parece_secreto(hecho):
            return _RECHAZO
        return f"Apuntado en el perfil del usuario: {anotar_hecho(hecho, self._vault)}"

    def recordar(self, hecho: str) -> str:
        hecho = _una_linea(hecho)
        if not hecho:
            return "Error: no hay nada que recordar."
        if parece_secreto(hecho):
            return _RECHAZO
        self._preparar()
        with self._abrir() as m:
            id_ = m.remember(hecho, kind="fact", metadata={"origen": "agente"})
        return f"Recordado como #{id_}: {hecho}"

    def buscar(self, consulta: str = "") -> str:
        consulta = _una_linea(consulta)
        with self._abrir() as m:
            total = m.count(kind="fact")
            if not total:
                return "No hay nada guardado en la memoria todavia."
            if consulta:
                self._preparar()
                encontrados = m.recall(consulta, limit=8, kind="fact")
                if not encontrados:
                    return f"No hay nada guardado que se parezca a «{consulta}»."
                cabecera = "Recuerdos parecidos, de mas a menos:"
            else:
                encontrados = m.all(kind="fact")[:15]
                cabecera = f"Lo ultimo guardado ({len(encontrados)} de {total}):"
        lineas = [f"- #{r.id} ({_fecha(r)}) {r.text}" for r in encontrados]
        return cabecera + "\n" + "\n".join(lineas)

    def olvidar(self, id: int) -> str:  # noqa: A002 - es el nombre que ve el modelo
        with self._abrir() as m:
            r = m.get(int(id))
            if r is None or r.kind != "fact":
                return f"Error: no hay ningun recuerdo #{id}."
            m.forget(r.id)
        return f"Olvidado #{r.id}: {r.text}"

    def _texto(self, id_: Any) -> str:
        with contextlib.suppress(Exception), self._abrir() as m:
            r = m.get(int(id_))
            if r is not None:
                return r.text
        return f"#{id_}"

    def _permiso_recordar(self, argumentos: dict[str, Any]) -> str | None:
        if not self.leido_fuera():
            return None
        return (
            f"Voy a recordar «{_una_linea(argumentos.get('hecho'))}». En esta orden he leído "
            "páginas, ficheros o comandos: comprueba que el dato es tuyo y no de lo leído."
        )

    def herramientas(self) -> list[Herramienta]:
        perfil = Herramienta(
            "anotar_sobre_usuario",
            "Apunta en el perfil del usuario un dato duradero SOBRE EL que el mismo te haya "
            "contado: su nombre, a que se dedica, donde vive, sus gustos, sus equipos, personas "
            "cercanas. El perfil lo lees en todas las conversaciones. Una frase corta, en tercera "
            "persona. Nunca contrasenas, claves ni datos bancarios.",
            self.anotar_usuario,
            {"hecho": texto("El dato, en una frase. Ej. 'Tiene unas Meta Quest 3S'.")},
            requeridos=("hecho",),
            narrar=lambda a: f"Lo apunto en tu perfil: {_una_linea(a.get('hecho'))}",
            confirmar=lambda a: (
                f"Voy a apuntar en tu perfil, que leo en todas las conversaciones: "
                f"«{_una_linea(a.get('hecho'))}»."
            ),
            familia="memoria",
        )
        if not self.activa:
            return [perfil]
        return [
            perfil,
            Herramienta(
                "recordar",
                "Guarda un dato para futuras conversaciones; se te recordara solo cuando venga a "
                "cuento. Para lo que el usuario te pide recordar o le servira mas adelante: un "
                "plan, una fecha, donde guardo algo, lo decidido. Quien es el usuario va con "
                "anotar_sobre_usuario, y como prefiere que trabajes, con aprender. Nunca "
                "contrasenas, claves ni datos bancarios.",
                self.recordar,
                {
                    "hecho": texto(
                        "El dato completo, que se entienda solo. "
                        "Ej. 'El examen de redes es el 12 de noviembre'."
                    )
                },
                requeridos=("hecho",),
                narrar=lambda a: f"Lo recuerdo: {_una_linea(a.get('hecho'))}",
                confirmar=self._permiso_recordar,
                familia="memoria",
            ),
            Herramienta(
                "buscar_en_memoria",
                "Busca por significado en lo que recuerdas de conversaciones anteriores. Sin "
                "consulta, lista lo ultimo guardado. Usalo si el usuario pregunta por algo que "
                "pudo contarte antes.",
                self.buscar,
                {"consulta": texto("Que buscar, ej. 'fecha del examen'. Vacio: lo ultimo.")},
                narrar=lambda a: (
                    f"Busco en mi memoria: {a['consulta']}"
                    if a.get("consulta")
                    else "Repaso lo último que recuerdo"
                ),
                familia="memoria",
            ),
            Herramienta(
                "olvidar_recuerdo",
                "Borra un recuerdo por su numero (el #id que da buscar_en_memoria). Solo si el "
                "usuario lo pide.",
                self.olvidar,
                {"id": entero("El numero del recuerdo.")},
                requeridos=("id",),
                narrar=lambda a: f"Olvido el recuerdo #{a.get('id')}",
                confirmar=lambda a: f"Voy a borrar de la memoria: «{self._texto(a.get('id'))}».",
                familia="memoria",
            ),
        ]

    # -- para la ventana --------------------------------------------------------
    def estado(self) -> dict[str, Any]:
        total = 0
        if self.activa:
            with contextlib.suppress(Exception), self._abrir() as m:
                total = m.count(kind="fact")
        return {"activa": self.activa, "motivo": self.motivo, "recuerdos": total}

    def perfil(self) -> dict[str, Any]:
        p = leer_perfil(self._vault)
        return {
            "campos": {c: p.campos.get(c, "") for c in CAMPOS_PERFIL},
            "hechos": p.hechos,
            "ruta": str(perfil_path(self._vault)),
        }

    def personalidad(self) -> dict[str, Any]:
        return {**personalidad.leer(self._vault), "estilos": personalidad.catalogo()}

    def guardar_personalidad(self, base: str, texto: str) -> None:
        """``ValueError`` si queda vacia o es demasiado larga."""
        personalidad.guardar(str(base or ""), str(texto or ""), self._vault)

    def guardar_datos(self, campos: dict[str, Any]) -> None:
        """Los datos del perfil (nombre, a que se dedica...). ``ValueError`` si no se guardan."""
        p = leer_perfil(self._vault)
        for c in CAMPOS_PERFIL:
            if c in campos:
                valor = str(campos[c] or "").strip()[:800]
                if parece_secreto(valor):
                    raise ValueError(_RECHAZO_PERFIL)
                p.campos[c] = valor
        guardar_perfil(p, self._vault)

    def anotar_perfil(self, hecho: str) -> str:
        hecho = _una_linea(hecho)
        if parece_secreto(hecho):
            raise ValueError(_RECHAZO_PERFIL)
        return anotar_hecho(hecho, self._vault)

    def quitar_del_perfil(self, indice: int) -> str:
        return quitar_hecho(int(indice), self._vault)

    def lista(self, consulta: str = "", *, limite: int = 200) -> list[dict[str, Any]]:
        """Los recuerdos, del mas reciente al mas antiguo; con consulta, los que encajen.

        Primero los que contienen el texto tal cual y despues los parecidos por
        significado: quien busca en la lista suele recordar una palabra exacta.
        """
        if not self.activa:
            return []
        consulta = _una_linea(consulta)
        with self._abrir() as m:
            todos = m.all(kind="fact")
            if consulta:
                bajo = consulta.lower()
                literales = [r for r in todos if bajo in r.text.lower()]
                vistos = {r.id for r in literales}
                self._preparar()
                parecidos = m.recall(consulta, limit=30, kind="fact")
                todos = literales + [r for r in parecidos if r.id not in vistos]
        return [
            {"id": r.id, "texto": r.text, "fecha": _fecha(r), "origen": r.metadata.get("origen")}
            for r in todos[:limite]
        ]

    def borrar(self, id_: int) -> bool:
        with self._abrir() as m:
            r = m.get(int(id_))
            return r is not None and r.kind == "fact" and m.forget(r.id)


def crear_memoria(vault_dir: Path | None = None) -> Memoria:
    """La memoria de esta instalacion: con recuerdos si hay fastembed, solo el perfil si no."""
    if find_spec("fastembed") is None:
        return Memoria(
            vault_dir=vault_dir,
            motivo='Los recuerdos necesitan fastembed: pip install -e ".[memoria]"',
        )
    from doombot.backends.embeddings import FastEmbedder

    return Memoria(FastEmbedder.from_config(), vault_dir=vault_dir)
