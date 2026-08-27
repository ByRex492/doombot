"""La memoria.

Casi todo corre con un embedder falso: la memoria depende del contrato
``Embedder``, no de fastembed, asi que se puede probar entera sin descargar
nada. Lo unico que necesita el modelo real es la recuperacion por significado,
que es justo lo que un doble no puede simular.
"""

from __future__ import annotations

import hashlib

import pytest

from doombot.memory import Memory, MemoryError, Recollection

DIMS = 16


class EmbedderFalso:
    """Vectores deterministas por hash. Sin semantica, pero estables."""

    def __init__(self, dims: int = DIMS) -> None:
        self.dimensions = dims
        self.llamadas = 0

    def embed(self, textos: list[str]) -> list[list[float]]:
        self.llamadas += 1
        out = []
        for t in textos:
            h = hashlib.sha256(t.encode()).digest()
            out.append([h[i % len(h)] / 255.0 for i in range(self.dimensions)])
        return out


@pytest.fixture
def emb() -> EmbedderFalso:
    return EmbedderFalso()


@pytest.fixture
def mem(emb, tmp_path) -> Memory:
    with Memory(emb, tmp_path / "test.db") as m:
        yield m


# ============================================================ guardar
def test_guardar_devuelve_un_id(mem):
    assert isinstance(mem.remember("el portatil tiene 3 GB de VRAM"), int)


def test_lo_guardado_se_puede_recuperar_por_id(mem):
    i = mem.remember("hola mundo")
    r = mem.get(i)
    assert isinstance(r, Recollection)
    assert r.text == "hola mundo"
    assert r.kind == "fact"


def test_no_guarda_vacios(mem):
    with pytest.raises(MemoryError, match="vacio"):
        mem.remember("   ")


def test_no_duplica_lo_mismo(mem):
    """Repetirle algo a un asistente es normal.

    Sin esto, el mismo recuerdo ocuparia varios de los primeros puestos en
    cada busqueda y desplazaria a los demas.
    """
    a = mem.remember("el cielo es azul")
    b = mem.remember("el cielo es azul")
    assert a == b
    assert mem.count() == 1


def test_mismo_texto_otro_tipo(mem):
    a = mem.remember("revisar el presupuesto", kind="fact")
    b = mem.remember("revisar el presupuesto", kind="task")
    assert a != b
    assert mem.count() == 2


def test_guarda_metadatos(mem):
    i = mem.remember("con extras", metadata={"origen": "voz", "confianza": 0.9})
    assert mem.get(i).metadata == {"origen": "voz", "confianza": 0.9}


def test_lote_una_sola_llamada(emb, tmp_path):
    """El coste de un embedder lo domina la llamada, no el numero de textos."""
    with Memory(emb, tmp_path / "lote.db") as m:
        antes = emb.llamadas
        ids = m.remember_many(["uno", "dos", "tres"])
        assert len(ids) == 3
        assert emb.llamadas == antes + 1


def test_el_lote_ignora_vacios_y_duplicados(mem):
    mem.remember("ya estaba")
    ids = mem.remember_many(["ya estaba", "  ", "nuevo"])
    assert len(ids) == 2
    assert mem.count() == 2


# ============================================================ recuperar
def test_recall_encuentra_lo_identico(mem):
    mem.remember("la capital de Francia es Paris")
    r = mem.recall("la capital de Francia es Paris")
    assert r and r[0].similarity > 0.99


def test_recall_sin_nada_guardado(mem):
    assert mem.recall("lo que sea") == []


def test_recall_con_pregunta_vacia(mem):
    mem.remember("algo")
    assert mem.recall("") == []


def test_recall_respeta_el_limite(mem):
    mem.remember_many([f"recuerdo numero {i}" for i in range(10)])
    assert len(mem.recall("recuerdo", limit=3, min_similarity=-1.0)) == 3


def test_recall_ordena_de_mas_a_menos_parecido(mem):
    mem.remember_many([f"texto {i}" for i in range(8)])
    sims = [r.similarity for r in mem.recall("texto 3", limit=8, min_similarity=-1.0)]
    assert sims == sorted(sims, reverse=True)


def test_el_umbral_descarta_lo_irrelevante(mem):
    """Sin umbral, cualquier pregunta devolveria los cinco menos malos.

    Y el modelo respondera basandose en ellos por absurdos que sean: es
    preferible no recordar nada que recordar algo que no viene a cuento.
    """
    mem.remember("el cielo es azul")
    assert mem.recall("cualquier cosa", min_similarity=0.999) == []
    assert mem.recall("cualquier cosa", min_similarity=-1.0) != []


def test_recall_filtra_por_tipo(mem):
    mem.remember("un hecho", kind="fact")
    mem.remember("una tarea", kind="task")
    r = mem.recall("algo", kind="task", min_similarity=-1.0)
    assert len(r) == 1
    assert r[0].kind == "task"


# ============================================================ inventario
def test_count_y_kinds(mem):
    mem.remember("a", kind="fact")
    mem.remember("b", kind="task")
    mem.remember("c", kind="task")
    assert mem.count() == 3
    assert mem.count(kind="task") == 2
    assert mem.kinds() == ["fact", "task"]


def test_all_devuelve_lo_mas_reciente_primero(mem):
    mem.remember("primero")
    mem.remember("segundo")
    assert [r.text for r in mem.all()][0] in ("primero", "segundo")
    assert len(mem.all()) == 2


# ============================================================ borrar
def test_forget(mem):
    i = mem.remember("efimero")
    assert mem.forget(i) is True
    assert mem.get(i) is None
    assert mem.forget(i) is False


def test_clear_por_tipo(mem):
    mem.remember("a", kind="fact")
    mem.remember("b", kind="task")
    assert mem.clear(kind="task") == 1
    assert mem.count() == 1


def test_clear_todo(mem):
    mem.remember_many(["a", "b", "c"])
    assert mem.clear() == 3
    assert mem.count() == 0


# ============================================================ persistencia
def test_sobrevive_al_cierre(emb, tmp_path):
    """Lo que se guarda hoy sigue ahi manana. Es el punto de todo esto."""
    ruta = tmp_path / "persistente.db"
    with Memory(emb, ruta) as m:
        m.remember("el portatil lleva una GTX 1050")
    with Memory(EmbedderFalso(), ruta) as m:
        assert m.count() == 1
        assert m.recall("el portatil lleva una GTX 1050")[0].similarity > 0.99


def test_detecta_cambio_de_dimensiones(emb, tmp_path):
    """El fallo mas dificil de diagnosticar de toda la memoria.

    Con vectores de dos modelos mezclados nada revienta: las busquedas siguen
    devolviendo resultados, solo que sin sentido.
    """
    ruta = tmp_path / "cambio.db"
    with Memory(emb, ruta) as m:
        m.remember("algo")
    with pytest.raises(MemoryError, match="dimensiones"):
        Memory(EmbedderFalso(dims=32), ruta)


def test_la_base_no_cae_dentro_del_repositorio(emb, tmp_path, monkeypatch):
    from doombot.paths import PROJECT_ROOT

    monkeypatch.setenv("DOOMBOT_DATA_DIR", str(tmp_path))
    with Memory(emb) as m:
        assert PROJECT_ROOT.resolve() not in tmp_path.resolve().parents
        assert m.count() == 0


# ============================================================ para el prompt
def test_contexto_vacio_si_nada_encaja(mem):
    """Vacio y no un encabezado suelto: el modelo leeria eso como un fallo."""
    mem.remember("el cielo es azul")
    assert mem.as_context("cualquier cosa", min_similarity=0.999) == ""


def test_as_context_lista_los_recuerdos(mem):
    mem.remember("el portatil lleva una GTX 1050")
    ctx = mem.as_context("el portatil lleva una GTX 1050")
    assert "Notas de tu memoria" in ctx
    assert "- el portatil lleva una GTX 1050" in ctx


# ============================================================ identidad
def test_capacidad_recordar_activa():
    """identity detecta que memory/ ya expone algo y activa la capacidad sola.

    Es la prueba de que el prompt se corrige segun avanza el proyecto en vez
    de quedarse obsoleto.
    """
    from doombot import identity

    caps = {c.name: c for c in identity.capabilities()}
    assert caps["recordar"].available
    assert "no guardas nada entre conversaciones" not in identity.system_prompt()


# ============================================================ con el modelo real
@pytest.mark.hardware
def test_recupera_por_significado(tmp_path):
    """LA prueba. Ninguna palabra de la pregunta esta en el recuerdo.

    Usa el fixture tmp_path y no tempfile.mkdtemp(): el segundo no se limpia
    nunca, y dejaba una carpeta huerfana en %TEMP% por cada ejecucion de la
    bateria. pytest borra las suyas conservando solo las tres ultimas.
    """
    pytest.importorskip("fastembed")

    from doombot.backends.embeddings import FastEmbedder

    ruta = tmp_path / "real.db"
    with Memory(FastEmbedder.from_config(), ruta) as m:
        m.remember_many(
            [
                "El portatil lleva una GTX 1050 con 3 GB de memoria grafica",
                "El pan se compra en la panaderia de la esquina",
                "Python 3.12 es la version que exige el proyecto",
            ]
        )
        r = m.recall("cuanta VRAM tengo disponible?")
        assert r, "no recupero nada"
        assert "GTX 1050" in r[0].text, f"recupero lo que no era: {r[0].text}"
        print("\n  pregunta : cuanta VRAM tengo disponible?")
        print(f"  recuerdo : {r[0].text}")
        print(f"  similitud: {r[0].similarity:.3f}")


def test_detecta_cambio_de_modelo(tmp_path):
    """Dos modelos distintos pueden dar vectores del mismo tamano.

    Es el caso real que destapo fastembed 0.8: el mismo modelo cambio de CLS
    a mean pooling, produciendo vectores distintos con las mismas 384
    dimensiones. Comprobar solo el tamano no lo habria detectado.
    """

    class ConNombre(EmbedderFalso):
        def __init__(self, nombre, dims=DIMS):
            super().__init__(dims)
            self.model_name = nombre

    ruta = tmp_path / "modelo.db"
    with Memory(ConNombre("modelo-a"), ruta) as m:
        m.remember("algo")
    with pytest.raises(MemoryError, match="modelo-a"):
        Memory(ConNombre("modelo-b"), ruta)


def test_un_embedder_sin_nombre_sigue_valiendo(tmp_path):
    """model_name no esta en el contrato minimo: es opcional."""
    ruta = tmp_path / "sin-nombre.db"
    with Memory(EmbedderFalso(), ruta) as m:
        m.remember("algo")
    with Memory(EmbedderFalso(), ruta) as m:
        assert m.count() == 1


def test_el_umbral_por_defecto_es_el_medido():
    """Ver el comentario de UMBRAL: 0,30 dejaba pasar un falso positivo."""
    from doombot.memory.store import UMBRAL

    assert UMBRAL == 0.35


def test_contexto_invita_a_descartar(mem):
    mem.remember("el portatil lleva una GTX 1050")
    ctx = mem.as_context("el portatil lleva una GTX 1050")
    assert "ignoralas" in ctx


def test_el_contexto_no_contiene_frases_copiables(mem):
    """Un modelo de 3B repite la instruccion en vez de interpretarla.

    Con "si ninguno lo hace, di que no lo sabes" en el encabezado, contestaba
    literalmente "No lo sabes." incluso teniendo delante el recuerdo correcto.
    """
    mem.remember("el portatil lleva una GTX 1050")
    ctx = mem.as_context("el portatil lleva una GTX 1050").lower()
    for citable in ("di que no lo sabes", "responde que no", "no lo sabes"):
        assert citable not in ctx, f"el encabezado contiene una frase copiable: {citable!r}"
