"""El generador de embeddings.

Un embedder no se puede verificar como un generador de texto. Su salida son
listas de 384 numeros que ningun humano puede leer: no existe un "resultado
correcto" con el que comparar. Se verifica por PROPIEDADES, que son
afirmaciones que deben cumplirse sea cual sea el valor concreto.

Cuatro familias, de menos a mas interesante:

1. Forma        - tantos vectores como textos, y del tamano declarado.
2. Determinismo - el mismo texto da siempre el mismo vector. Si fallara, la
                  memoria guardaria un vector y buscaria con otro distinto.
3. Coherencia   - un texto es identico a si mismo (similitud 1).
4. Semantica    - LA importante: textos que significan lo mismo estan mas
                  cerca que textos que no. Es lo unico que prueba que el
                  embedder sirve para recuperar memoria relevante.

Las tres primeras corren con un doble. La cuarta necesita el modelo real,
porque es justo lo que un doble no puede simular.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from doombot.backends.base import BackendError, Embedder
from doombot.backends.embeddings import FastEmbedder, cosine_similarity
from doombot.profiles import EmbeddingConfig, embedding_config

DIMS = 384


class ModeloFalso:
    """Produce vectores deterministas a partir del hash del texto.

    No tiene ninguna semantica: sirve para comprobar forma y determinismo,
    no para comprobar que los significados parecidos queden cerca.
    """

    def __init__(self, dims: int = DIMS) -> None:
        self.dims = dims

    def embed(self, textos):
        for t in textos:
            h = hashlib.sha256(t.encode()).digest()
            yield [((h[i % len(h)] + i) % 255) / 255.0 for i in range(self.dims)]


@pytest.fixture
def embedder() -> FastEmbedder:
    return FastEmbedder("falso", DIMS, loader=lambda *_: ModeloFalso())


# ============================================================ 1. contrato
def test_cumple_el_contrato(embedder):
    assert isinstance(embedder, Embedder)


def test_un_doble_tambien_cumple_el_contrato():
    class Doble:
        dimensions = 3

        def embed(self, textos):
            return [[0.0, 0.0, 1.0] for _ in textos]

    assert isinstance(Doble(), Embedder)


def test_el_modelo_no_se_carga_hasta_usarlo():
    cargas = []

    def loader(*_):
        cargas.append(1)
        return ModeloFalso()

    e = FastEmbedder("falso", DIMS, loader=loader)
    assert cargas == []
    e.embed(["hola"])
    assert len(cargas) == 1
    e.embed(["adios"])
    assert len(cargas) == 1


# ============================================================ 2. forma
def test_un_vector_por_texto(embedder):
    assert len(embedder.embed(["uno", "dos", "tres"])) == 3


def test_las_dimensiones_son_las_declaradas(embedder):
    for v in embedder.embed(["hola", "que tal"]):
        assert len(v) == DIMS == embedder.dimensions


def test_lista_vacia_devuelve_lista_vacia(embedder):
    assert embedder.embed([]) == []


def test_embed_one_devuelve_un_solo_vector(embedder):
    assert len(embedder.embed_one("hola")) == DIMS


def test_rechaza_lo_que_no_sea_texto(embedder):
    with pytest.raises(BackendError, match="lista de cadenas"):
        embedder.embed(["bien", 42])


# ============================================================ 3. determinismo
def test_el_mismo_texto_da_el_mismo_vector(embedder):
    """Si esto fallara, la memoria guardaria un vector y buscaria con otro."""
    assert embedder.embed_one("modo silencioso") == embedder.embed_one("modo silencioso")


def test_textos_distintos_dan_vectores_distintos(embedder):
    assert embedder.embed_one("hola") != embedder.embed_one("adios")


def test_el_orden_se_conserva(embedder):
    """La memoria empareja cada vector con su texto por posicion."""
    textos = ["primero", "segundo", "tercero"]
    en_lote = embedder.embed(textos)
    uno_a_uno = [embedder.embed_one(t) for t in textos]
    assert en_lote == uno_a_uno


# ============================================================ 4. desajustes
def test_detecta_dimensiones_que_no_cuadran():
    """Cambiar de modelo sin actualizar profiles.toml corrompe la memoria.

    Y lo hace en silencio: las busquedas seguirian funcionando, solo que
    devolviendo cosas que no vienen a cuento. De ahi que se compruebe.
    """
    e = FastEmbedder("falso", 768, loader=lambda *_: ModeloFalso(dims=384))
    with pytest.raises(BackendError, match="dimensions"):
        e.embed(["hola"])


def test_from_config_lee_profiles_toml():
    cfg = embedding_config()
    e = FastEmbedder.from_config(cfg, loader=lambda *_: ModeloFalso(cfg.dimensions))
    assert e.dimensions == cfg.dimensions
    assert cfg.model in repr(e)


def test_el_modelo_de_embeddings_es_global():
    """No esta en ningun perfil: tiene que ser el mismo en las dos maquinas."""
    from doombot.profiles import load_profiles

    for nombre, d in load_profiles().items():
        assert not any("embed" in k for k in d), (
            f"El perfil {nombre} define embeddings. Deben ser globales: dos modelos "
            "distintos producen vectores que no se pueden comparar."
        )


# ============================================================ 5. similitud
def test_similitud_de_un_vector_consigo_mismo():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0, abs_tol=1e-9)


def test_vectores_opuestos():
    assert math.isclose(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0, abs_tol=1e-9)


def test_vectores_perpendiculares():
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_la_similitud_ignora_la_longitud():
    """Es la razon de usar coseno: mide el angulo, no el tamano.

    Dos textos que dicen lo mismo con distinta extension apuntan en la misma
    direccion aunque sus vectores tengan magnitudes distintas.
    """
    assert math.isclose(cosine_similarity([1.0, 1.0], [5.0, 5.0]), 1.0, abs_tol=1e-9)


def test_el_vector_cero_no_revienta():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_dimensiones_distintas_dan_error():
    with pytest.raises(ValueError, match="Dimensiones distintas"):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


# ============================================================ 6. semantica real
@pytest.mark.hardware
def test_el_significado_queda_cerca():
    """LA prueba que importa. Un doble no puede simularla.

    Si esto falla, el embedder no sirve para recuperar memoria por mucho que
    todo lo anterior pase: devolveria recuerdos que no vienen a cuento.
    """
    pytest.importorskip("fastembed")
    e = FastEmbedder.from_config()

    orden = "activa el modo silencioso"
    parecido = "silencia la salida de voz del asistente"
    distinto = "cual es la capital de Francia"

    v_orden, v_parecido, v_distinto = e.embed([orden, parecido, distinto])
    sim_cerca = cosine_similarity(v_orden, v_parecido)
    sim_lejos = cosine_similarity(v_orden, v_distinto)

    print(f"\n  parafrasis : {sim_cerca:.3f}")
    print(f"  sin relacion: {sim_lejos:.3f}")

    assert sim_cerca > sim_lejos, "el embedder no distingue significados"
    assert sim_cerca > 0.5, f"deberia reconocer la parafrasis: {sim_cerca:.3f}"


@pytest.mark.hardware
def test_multilingue():
    """El modelo es multilingue: los bge-small habituales son solo ingleses."""
    pytest.importorskip("fastembed")
    e = FastEmbedder.from_config()

    es, en, otro = e.embed(["un perro corriendo", "a dog running", "una factura pendiente"])
    assert cosine_similarity(es, en) > cosine_similarity(es, otro)


@pytest.mark.hardware
def test_dimensiones_reales():
    """profiles.toml declara 384. Si el modelo real no coincide, embed() avisa."""
    pytest.importorskip("fastembed")
    cfg = embedding_config()
    assert isinstance(cfg, EmbeddingConfig)
    assert len(FastEmbedder.from_config().embed_one("prueba")) == cfg.dimensions
