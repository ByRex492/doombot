"""Embeddings con fastembed.

Cumple ``Embedder``. Tercera y ultima implementacion de contrato, y la que
desbloquea la memoria: convierte texto en vectores que se pueden comparar
entre si para recuperar lo relevante sin que el modelo tenga que recordarlo.

Se eligio fastembed sobre sentence-transformers porque el segundo arrastra
PyTorch, unos 2 GB de dependencias para un modelo de 220 MB. fastembed corre
sobre onnxruntime en CPU, que ya hace falta para el resto del stack de audio.

El modelo es multilingue a proposito. Los bge-small y similares que suelen
recomendarse son solo ingleses, y aqui todo se habla en espanol.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from doombot.backends.base import BackendError
from doombot.paths import models_dir
from doombot.profiles import EmbeddingConfig, embedding_config

if TYPE_CHECKING:
    from collections.abc import Callable

_MISSING = (
    'fastembed no esta instalado. Es una dependencia opcional:\n    pip install -e ".[voice]"'
)


class FastEmbedder:
    """Convierte texto en vectores."""

    def __init__(
        self,
        model: str,
        dimensions: int,
        *,
        loader: Callable[..., Any] | None = None,
    ) -> None:
        self._model_name = model
        self._dimensions = dimensions
        self._loader = loader
        self._model: Any | None = None

    @classmethod
    def from_config(cls, config: EmbeddingConfig | None = None, **kwargs: Any) -> FastEmbedder:
        cfg = config or embedding_config()
        return cls(model=cfg.model, dimensions=cfg.dimensions, **kwargs)

    # -- carga perezosa ------------------------------------------------------
    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = self._load()
        return self._model

    def _load(self) -> Any:
        try:
            if self._loader is not None:
                return self._loader(self._model_name)

            try:
                from fastembed import TextEmbedding
            except ImportError as e:
                raise BackendError(_MISSING) from e

            return TextEmbedding(model_name=self._model_name, cache_dir=str(models_dir()))
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise BackendError(
                f"No se pudo cargar el modelo de embeddings {self._model_name!r}: {e}"
            ) from e

    # -- el contrato ---------------------------------------------------------
    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model_name(self) -> str:
        """Nombre del modelo. Fuera del contrato minimo, pero lo usa la memoria.

        Dos modelos distintos pueden producir vectores del mismo tamano, asi
        que comprobar solo las dimensiones no basta para detectar un cambio.
        """
        return self._model_name

    def embed(self, textos: list[str]) -> list[list[float]]:
        """Vectoriza una lista de textos, en el mismo orden.

        Comprueba que las dimensiones sean las declaradas en vez de fiarse.
        Si no coinciden, el modelo no es el que dice profiles.toml, y guardar
        esos vectores junto a los antiguos corromperia las busquedas sin dar
        ningun sintoma: simplemente empezarian a devolver cosas que no vienen
        a cuento.
        """
        if not textos:
            return []
        if any(not isinstance(t, str) for t in textos):
            raise BackendError("embed() espera una lista de cadenas.")

        try:
            vectores = [list(map(float, v)) for v in self.model.embed(textos)]
        except BackendError:
            raise
        except Exception as e:  # noqa: BLE001 - depende de la libreria
            raise BackendError(f"Fallo generando embeddings: {e}") from e

        if len(vectores) != len(textos):
            raise BackendError(f"Se pidieron {len(textos)} vectores y llegaron {len(vectores)}.")
        for v in vectores:
            if len(v) != self._dimensions:
                raise BackendError(
                    f"El modelo {self._model_name!r} devuelve vectores de {len(v)} "
                    f"dimensiones, pero profiles.toml declara {self._dimensions}. "
                    "Corrige 'dimensions' en la seccion [embeddings]; si el cambio es "
                    "intencionado, la memoria guardada con el modelo anterior deja de "
                    "ser comparable y hay que regenerarla."
                )
        return vectores

    def embed_one(self, texto: str) -> list[float]:
        return self.embed([texto])[0]

    def __repr__(self) -> str:
        return f"FastEmbedder(model={self._model_name!r}, dimensions={self._dimensions})"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Similitud coseno entre dos vectores, de -1 a 1.

    Vive aqui y no en la memoria porque es la operacion que da sentido a un
    embedding: sin una forma de comparar, un vector no sirve de nada.

    Se usa el coseno y no la distancia euclidea porque solo mide el angulo, y
    por tanto ignora la longitud del vector. Dos textos que dicen lo mismo con
    distinta extension apuntan en la misma direccion.
    """
    if len(a) != len(b):
        raise ValueError(f"Dimensiones distintas: {len(a)} y {len(b)}.")
    prod = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return prod / (na * nb)
