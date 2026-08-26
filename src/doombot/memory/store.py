"""Memoria de D.O.O.M.: guardar cosas y recuperarlas por significado.

El problema que resuelve no es el almacenamiento, sino la BUSQUEDA. Guardar
texto en SQLite es trivial; lo dificil es que al preguntar "cuanta VRAM
tengo?" aparezca el recuerdo "el portatil lleva una GTX 1050 con 3 GB", que
no comparte ni una palabra con la pregunta.

Por eso cada recuerdo se guarda junto a su vector. Buscar es comparar el
vector de la pregunta con los almacenados y devolver los mas parecidos.

Sobre la eleccion de SQLite plano y similitud calculada en Python, en vez de
una extension vectorial como sqlite-vec: con unos miles de recuerdos, comparar
en Python cuesta milisegundos, y evita una dependencia binaria que habria que
compilar o distribuir para cada equipo. Cuando el volumen lo justifique, la
migracion afecta solo al interior de recall() y no a nada de fuera.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from doombot.backends.embeddings import cosine_similarity
from doombot.paths import memory_db

if TYPE_CHECKING:
    from doombot.backends.base import Embedder

ESQUEMA = 1

# Umbral de similitud por debajo del cual un recuerdo se considera irrelevante.
#
# Medido con paraphrase-multilingual-MiniLM-L12-v2 sobre hechos reales del
# proyecto: los aciertos claros puntuan entre 0,51 y 0,67, y el ruido se queda
# por debajo de 0,26. El valor anterior, 0,30, dejaba pasar un falso positivo
# de 0,339 —"donde esta alojado el codigo?" recuperaba el recuerdo sobre el
# modelo de lenguaje en vez del del repositorio, que quedaba en 0,248—.
#
# No conviene subirlo mucho mas: por encima de 0,45 empiezan a caerse
# recuperaciones legitimas como "cuanta VRAM tengo?", que acerto con 0,434.
UMBRAL = 0.35


class MemoryError(RuntimeError):
    """Fallo de la memoria: base corrupta, modelo cambiado, etc."""


@dataclass(frozen=True)
class Recollection:
    """Un recuerdo recuperado, con lo cerca que estaba de la pregunta."""

    id: int
    text: str
    kind: str
    created_at: datetime
    similarity: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.text


def _empaquetar(vector: list[float]) -> bytes:
    """Vector -> bytes. float32 basta y ocupa la mitad que float64.

    384 dimensiones son 1,5 KB por recuerdo. La precision perdida es
    irrelevante para una similitud coseno, donde solo importa el orden
    relativo de los resultados.
    """
    return struct.pack(f"{len(vector)}f", *vector)


def _desempaquetar(datos: bytes) -> list[float]:
    return list(struct.unpack(f"{len(datos) // 4}f", datos))


class Memory:
    """Almacen de recuerdos con busqueda por significado.

    El embedder se recibe por parametro y no se construye aqui: la memoria
    depende del contrato ``Embedder``, no de fastembed. Asi se puede probar
    entera con un doble, sin descargar modelos.
    """

    def __init__(self, embedder: Embedder, db_path: Path | None = None) -> None:
        self._embedder = embedder
        self._path = Path(db_path) if db_path else memory_db()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path)
        self._db.row_factory = sqlite3.Row
        self._crear_esquema()
        self._comprobar_modelo()

    # -- ciclo de vida -------------------------------------------------------
    def _crear_esquema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                text       TEXT    NOT NULL,
                kind       TEXT    NOT NULL DEFAULT 'fact',
                vector     BLOB    NOT NULL,
                metadata   TEXT    NOT NULL DEFAULT '{}',
                created_at TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kind ON memories(kind);
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._db.commit()

    def _comprobar_modelo(self) -> None:
        """Detecta que la base se creo con otro modelo de embeddings.

        Es la comprobacion que evita el fallo mas dificil de diagnosticar de
        toda la memoria: con vectores de dos modelos mezclados nada revienta,
        las busquedas siguen devolviendo resultados, solo que sin sentido.
        """
        dims = str(self._embedder.dimensions)
        # El nombre no esta en el contrato minimo: un Embedder puede no
        # tenerlo, y entonces solo se comprueban las dimensiones.
        modelo = str(getattr(self._embedder, "model_name", "") or "")

        guardado = {f["key"]: f["value"] for f in self._db.execute("SELECT key, value FROM meta")}

        if "dimensions" not in guardado:
            self._db.executemany(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                [("dimensions", dims), ("schema", str(ESQUEMA)), ("model", modelo)],
            )
            self._db.commit()
            return

        if guardado["dimensions"] != dims:
            raise self._error_de_modelo(
                f"se creo con vectores de {guardado['dimensions']} dimensiones "
                f"y el embedder actual produce {dims}"
            )

        # Dos modelos pueden coincidir en tamano y diferir por completo en el
        # espacio que generan, asi que el nombre se comprueba aparte.
        previo = guardado.get("model", "")
        if modelo and previo and previo != modelo:
            raise self._error_de_modelo(
                f"se creo con el modelo {previo!r} y el embedder actual usa {modelo!r}"
            )

        if modelo and not previo:  # base anterior a que se guardara el nombre
            self._db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('model', ?)", (modelo,)
            )
            self._db.commit()

    def _error_de_modelo(self, causa: str) -> MemoryError:
        return MemoryError(
            f"La memoria de {self._path.name} {causa}. Los vectores de dos modelos "
            "distintos no son comparables: las busquedas devolverian resultados sin "
            "sentido en vez de fallar.\n"
            "Vuelve al modelo anterior en la seccion [embeddings] de profiles.toml, "
            "o borra la memoria para regenerarla desde cero.\n"
            f"    {self._path}"
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Memory:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # -- escribir ------------------------------------------------------------
    def remember(self, text: str, *, kind: str = "fact", metadata: dict | None = None) -> int:
        """Guarda un recuerdo y devuelve su id.

        Un texto identico ya guardado no se duplica: se devuelve el id del
        existente. Repetirle algo a un asistente es normal, y sin esto la
        busqueda acabaria devolviendo el mismo recuerdo varias veces ocupando
        los primeros puestos.
        """
        text = text.strip()
        if not text:
            raise MemoryError("No se puede guardar un recuerdo vacio.")

        previo = self._db.execute(
            "SELECT id FROM memories WHERE text = ? AND kind = ?", (text, kind)
        ).fetchone()
        if previo is not None:
            return int(previo["id"])

        vector = self._embedder.embed([text])[0]
        cur = self._db.execute(
            "INSERT INTO memories (text, kind, vector, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                text,
                kind,
                _empaquetar(vector),
                json.dumps(metadata or {}, ensure_ascii=False),
                datetime.now(UTC).isoformat(),
            ),
        )
        self._db.commit()
        return int(cur.lastrowid)

    def remember_many(self, textos: list[str], *, kind: str = "fact") -> list[int]:
        """Guarda varios de una vez.

        Vectoriza en un solo lote: el coste de un embedder esta dominado por
        la llamada, no por el numero de textos, asi que veinte de golpe cuestan
        mucho menos que veinte llamadas.
        """
        limpios = [t.strip() for t in textos if t.strip()]
        if not limpios:
            return []
        nuevos = [t for t in limpios if not self._existe(t, kind)]
        if nuevos:
            vectores = self._embedder.embed(nuevos)
            ahora = datetime.now(UTC).isoformat()
            self._db.executemany(
                "INSERT INTO memories (text, kind, vector, metadata, created_at) "
                "VALUES (?, ?, ?, '{}', ?)",
                [(t, kind, _empaquetar(v), ahora) for t, v in zip(nuevos, vectores, strict=True)],
            )
            self._db.commit()
        return [self._id_de(t, kind) for t in limpios]

    def _existe(self, text: str, kind: str) -> bool:
        return (
            self._db.execute(
                "SELECT 1 FROM memories WHERE text = ? AND kind = ?", (text, kind)
            ).fetchone()
            is not None
        )

    def _id_de(self, text: str, kind: str) -> int:
        fila = self._db.execute(
            "SELECT id FROM memories WHERE text = ? AND kind = ?", (text, kind)
        ).fetchone()
        return int(fila["id"])

    # -- leer ----------------------------------------------------------------
    def recall(
        self,
        query: str,
        *,
        limit: int = 5,
        min_similarity: float = UMBRAL,
        kind: str | None = None,
    ) -> list[Recollection]:
        """Recuerdos mas parecidos a la pregunta, de mas a menos.

        ``min_similarity`` es el umbral por debajo del cual un recuerdo se
        considera irrelevante. Importa mas de lo que parece: sin el, una
        pregunta sobre cualquier cosa devolveria SIEMPRE los cinco recuerdos
        menos malos, y el modelo respondera basandose en ellos por absurdos
        que sean. Es preferible no recordar nada que recordar algo que no
        viene a cuento.

        El valor por defecto sale de lo medido con este embedder. Ver UMBRAL.
        """
        query = query.strip()
        if not query:
            return []

        filas = self._filas(kind)
        if not filas:
            return []

        v_query = self._embedder.embed([query])[0]
        puntuados = [(cosine_similarity(v_query, _desempaquetar(f["vector"])), f) for f in filas]
        puntuados.sort(key=lambda p: p[0], reverse=True)

        return [
            self._a_recollection(f, sim) for sim, f in puntuados[:limit] if sim >= min_similarity
        ]

    def all(self, *, kind: str | None = None) -> list[Recollection]:
        """Todos los recuerdos, del mas reciente al mas antiguo."""
        filas = self._filas(kind)
        recuerdos = [self._a_recollection(f, 0.0) for f in filas]
        recuerdos.sort(key=lambda r: r.created_at, reverse=True)
        return recuerdos

    def get(self, id: int) -> Recollection | None:
        fila = self._db.execute("SELECT * FROM memories WHERE id = ?", (id,)).fetchone()
        return self._a_recollection(fila, 0.0) if fila else None

    def count(self, *, kind: str | None = None) -> int:
        if kind is None:
            return int(self._db.execute("SELECT COUNT(*) c FROM memories").fetchone()["c"])
        return int(
            self._db.execute("SELECT COUNT(*) c FROM memories WHERE kind = ?", (kind,)).fetchone()[
                "c"
            ]
        )

    def kinds(self) -> list[str]:
        return [
            r["kind"] for r in self._db.execute("SELECT DISTINCT kind FROM memories ORDER BY kind")
        ]

    # -- borrar --------------------------------------------------------------
    def forget(self, id: int) -> bool:
        cur = self._db.execute("DELETE FROM memories WHERE id = ?", (id,))
        self._db.commit()
        return cur.rowcount > 0

    def clear(self, *, kind: str | None = None) -> int:
        if kind is None:
            cur = self._db.execute("DELETE FROM memories")
        else:
            cur = self._db.execute("DELETE FROM memories WHERE kind = ?", (kind,))
        self._db.commit()
        return cur.rowcount

    # -- para el prompt ------------------------------------------------------
    def as_context(self, query: str, *, limit: int = 5, min_similarity: float = UMBRAL) -> str:
        """Los recuerdos relevantes, listos para meter en el prompt.

        Devuelve cadena vacia si no hay nada que venga a cuento, y eso es
        deliberado: quien llama debe poder distinguir "no se acuerda de nada"
        de "se acuerda de esto", en vez de recibir un bloque vacio con
        encabezado que el modelo interpretaria como que la memoria fallo.

        El bloque lleva una instruccion explicita de ignorar lo que no
        responda a la pregunta. Sin ella, un modelo pequeno trata el contexto
        como verdad obligatoria y construye sobre el aunque no venga a cuento:
        medido, ante un recuerdo equivocado sobre el modelo de lenguaje,
        respondio a "donde esta alojado el codigo?" inventando una ruta de
        carpetas y un fichero JSON que no existen. Sin memoria solo decia algo
        vago; con memoria mala se invento los detalles.
        """
        recuerdos = self.recall(query, limit=limit, min_similarity=min_similarity)
        if not recuerdos:
            return ""
        lineas = [f"- {r.text}" for r in recuerdos]
        return (
            "Estos son recuerdos tuyos que PODRIAN venir al caso. Usa solo los que "
            "respondan de verdad a la pregunta; si ninguno lo hace, di que no lo sabes "
            "en vez de deducir una respuesta a partir de ellos.\n" + "\n".join(lineas)
        )

    # -- interno -------------------------------------------------------------
    def _filas(self, kind: str | None) -> list[sqlite3.Row]:
        if kind is None:
            return list(self._db.execute("SELECT * FROM memories"))
        return list(self._db.execute("SELECT * FROM memories WHERE kind = ?", (kind,)))

    @staticmethod
    def _a_recollection(fila: sqlite3.Row, similarity: float) -> Recollection:
        return Recollection(
            id=int(fila["id"]),
            text=fila["text"],
            kind=fila["kind"],
            created_at=datetime.fromisoformat(fila["created_at"]),
            similarity=similarity,
            metadata=json.loads(fila["metadata"]),
        )

    def __repr__(self) -> str:
        return f"Memory(path={self._path.name!r}, recuerdos={self.count()})"
