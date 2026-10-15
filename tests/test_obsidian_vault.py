"""El vault de Obsidian, probado sobre una carpeta temporal.

Nada aqui toca el vault real del repositorio: todas las funciones aceptan
``vault_dir`` para poder apuntar a ``tmp_path`` en las pruebas, igual que
``Memory`` acepta ``db_path``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from doombot.memory import Recollection
from doombot.obsidian import vault
from doombot.obsidian.vault import anotar_progreso, escribir_perfil, sincronizar_perfil


class MemoriaFalsa:
    """Doble minimo: solo lo que ``vault`` necesita de ``Memory``."""

    def __init__(self) -> None:
        self.guardado: list[tuple[str, str]] = []

    def all(self, *, kind=None):
        return [
            Recollection(id=i, text=t, kind=k, created_at=datetime.now(UTC))
            for i, (t, k) in enumerate(self.guardado)
            if kind is None or k == kind
        ]

    def remember_many(self, textos, *, kind="fact"):
        for t in textos:
            if (t, kind) not in self.guardado:
                self.guardado.append((t, kind))
        return list(range(len(textos)))

    def forget(self, id):
        if 0 <= id < len(self.guardado):
            self.guardado[id] = ("", "olvidado")
            return True
        return False


# -- escribir_perfil ------------------------------------------------------------
def test_escribir_perfil_crea_el_fichero_con_los_hechos(tmp_path):
    mem = MemoriaFalsa()
    mem.guardado = [("vive en Madrid", "perfil"), ("un hecho general", "fact")]

    ruta = escribir_perfil(mem, vault_dir=tmp_path)

    contenido = ruta.read_text(encoding="utf-8")
    assert "vive en Madrid" in contenido
    assert "un hecho general" not in contenido  # solo kind='perfil'


def test_escribir_perfil_sin_hechos_deja_solo_la_cabecera(tmp_path):
    ruta = escribir_perfil(MemoriaFalsa(), vault_dir=tmp_path)
    assert "Usuario" in ruta.read_text(encoding="utf-8")


def test_escribir_perfil_anade_lo_nuevo_y_respeta_el_fichero(tmp_path):
    """El fichero manda (D-043): escribir anade lo aprendido por voz, no borra lo que habia."""
    vault.guardar_perfil(
        vault.Perfil(campos={"nombre": "Alex"}, hechos=["escrito a mano"]), vault_dir=tmp_path
    )
    mem = MemoriaFalsa()
    mem.guardado = [("dicho por voz", "perfil"), ("escrito a mano", "perfil")]

    escribir_perfil(mem, vault_dir=tmp_path)

    p = vault.leer_perfil(tmp_path)
    assert p.hechos == ["escrito a mano", "dicho por voz"]  # sin duplicar, en orden
    assert p.campos == {"nombre": "Alex"}  # los datos de la ventana no se pierden


# -- sincronizar_perfil -----------------------------------------------------------
def test_sincronizar_perfil_sin_fichero_no_falla(tmp_path):
    assert sincronizar_perfil(MemoriaFalsa(), vault_dir=tmp_path) == 0


def test_sincronizar_perfil_lee_las_lineas_con_guion(tmp_path):
    ruta = vault.perfil_path(tmp_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        "# Usuario\n\nTexto suelto que no es un hecho.\n\n- tiene 32 años\n- vive en Madrid\n",
        encoding="utf-8",
    )

    mem = MemoriaFalsa()
    n = sincronizar_perfil(mem, vault_dir=tmp_path)

    assert n == 2
    assert ("tiene 32 años", "perfil") in mem.guardado
    assert ("vive en Madrid", "perfil") in mem.guardado
    assert not any("Texto suelto" in t for t, _ in mem.guardado)


def test_ida_y_vuelta_no_pierde_ni_duplica(tmp_path):
    """Escribir, sincronizar, y volver a escribir da lo mismo."""
    mem = MemoriaFalsa()
    mem.guardado = [("un hecho", "perfil")]
    escribir_perfil(mem, vault_dir=tmp_path)

    n = sincronizar_perfil(mem, vault_dir=tmp_path)
    assert n == 1
    assert mem.guardado.count(("un hecho", "perfil")) == 1  # no se duplico


def test_sincronizar_olvida_lo_que_se_borro_del_fichero(tmp_path):
    mem = MemoriaFalsa()
    mem.guardado = [("sigue", "perfil"), ("borrado en la ventana", "perfil"), ("otro", "fact")]
    vault.guardar_perfil(vault.Perfil(hechos=["sigue"]), vault_dir=tmp_path)

    assert sincronizar_perfil(mem, vault_dir=tmp_path) == 1

    assert ("sigue", "perfil") in mem.guardado
    assert ("borrado en la ventana", "perfil") not in mem.guardado
    assert ("otro", "fact") in mem.guardado  # los recuerdos no son del perfil


def test_sin_fichero_no_se_olvida_nada(tmp_path):
    mem = MemoriaFalsa()
    mem.guardado = [("dato", "perfil")]
    sincronizar_perfil(mem, vault_dir=tmp_path)
    assert mem.guardado == [("dato", "perfil")]


# -- el perfil (D-043) -------------------------------------------------------------
def test_el_perfil_va_y_vuelve_entero(tmp_path):
    perfil = vault.Perfil(
        campos={"nombre": 'Alex "el del HUD"', "estilo": "Directo.\nCon ejemplos."},
        hechos=["tiene unas Meta Quest 3S", "vive con dos gatos"],
    )
    vault.guardar_perfil(perfil, vault_dir=tmp_path)
    assert vault.leer_perfil(tmp_path) == perfil


def test_las_propiedades_de_obsidian_no_son_hechos_y_se_conservan(tmp_path):
    """Una lista en las propiedades (``tags``) lleva guiones: no son hechos, ni se pierden."""
    ruta = vault.perfil_path(tmp_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        "---\nnombre: Alex\ntags:\n  - personal\n---\n# Usuario\n\n- un hecho\n",
        encoding="utf-8",
    )

    p = vault.leer_perfil(tmp_path)
    assert p.campos == {"nombre": "Alex"}  # escrito a pelo, como lo deja Obsidian
    assert p.hechos == ["un hecho"]

    vault.anotar_hecho("otro hecho", vault_dir=tmp_path)
    contenido = ruta.read_text(encoding="utf-8")
    assert "tags:\n  - personal" in contenido
    assert vault.leer_perfil(tmp_path).hechos == ["un hecho", "otro hecho"]


def test_anotar_y_quitar_hechos(tmp_path):
    assert vault.anotar_hecho("  - tiene   un perro ", vault_dir=tmp_path) == "tiene un perro"
    vault.anotar_hecho("tiene un perro", vault_dir=tmp_path)  # no se duplica
    vault.anotar_hecho("juega al padel", vault_dir=tmp_path)
    assert vault.leer_perfil(tmp_path).hechos == ["tiene un perro", "juega al padel"]

    assert vault.quitar_hecho(0, vault_dir=tmp_path) == "tiene un perro"
    assert vault.quitar_hecho("juega al padel", vault_dir=tmp_path) == "juega al padel"
    assert vault.leer_perfil(tmp_path).hechos == []


def test_quitar_lo_que_no_esta_avisa(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        vault.quitar_hecho(3, vault_dir=tmp_path)
    with pytest.raises(ValueError):
        vault.quitar_hecho("no esta", vault_dir=tmp_path)


def test_perfil_para_prompt():
    assert vault.perfil_para_prompt(vault.Perfil()) == ""
    texto = vault.perfil_para_prompt(
        vault.Perfil(
            campos={"nombre": "Alejandro", "llamame": "Alex", "ubicacion": "Valencia",
                    "estilo": "Breve y directo"},
            hechos=["tiene unas Meta Quest 3S"],
        )
    )  # fmt: skip
    assert "Se llama Alejandro; llamale Alex" in texto
    assert "Vive en: Valencia" in texto
    assert "- tiene unas Meta Quest 3S" in texto
    assert texto.endswith("Como quiere que le respondas: Breve y directo")


def test_perfil_para_prompt_no_se_come_el_contexto():
    largo = vault.Perfil(hechos=[f"hecho numero {i} " * 5 for i in range(200)])
    assert len(vault.perfil_para_prompt(largo)) <= 2500


# -- anotar_progreso ---------------------------------------------------------------
def test_anotar_progreso_crea_el_fichero_del_dia(tmp_path):
    ahora = datetime(2026, 8, 31, 9, 15)
    ruta = anotar_progreso("primera nota", ahora=ahora, vault_dir=tmp_path)

    assert ruta.name == "2026-08-31.md"
    contenido = ruta.read_text(encoding="utf-8")
    assert "# 2026-08-31" in contenido
    assert "## Mañana" in contenido
    assert "09:15" in contenido
    assert "primera nota" in contenido


def test_anotar_progreso_separa_manana_y_tarde(tmp_path):
    anotar_progreso("nota de la manana", ahora=datetime(2026, 8, 31, 9, 0), vault_dir=tmp_path)
    ruta = anotar_progreso(
        "nota de la tarde", ahora=datetime(2026, 8, 31, 17, 0), vault_dir=tmp_path
    )

    contenido = ruta.read_text(encoding="utf-8")
    assert contenido.index("## Mañana") < contenido.index("nota de la manana")
    assert contenido.index("## Tarde") < contenido.index("nota de la tarde")
    assert contenido.index("nota de la manana") < contenido.index("## Tarde")


def test_anotar_progreso_acumula_en_el_mismo_turno(tmp_path):
    ahora = datetime(2026, 8, 31, 10, 0)
    anotar_progreso("primera", ahora=ahora, vault_dir=tmp_path)
    ruta = anotar_progreso("segunda", ahora=ahora, vault_dir=tmp_path)

    contenido = ruta.read_text(encoding="utf-8")
    assert contenido.count("## Mañana") == 1  # no se repite la cabecera
    assert "primera" in contenido
    assert "segunda" in contenido


def test_anotar_progreso_dias_distintos_van_a_ficheros_distintos(tmp_path):
    r1 = anotar_progreso("dia 1", ahora=datetime(2026, 8, 31, 10, 0), vault_dir=tmp_path)
    r2 = anotar_progreso("dia 2", ahora=datetime(2026, 9, 1, 10, 0), vault_dir=tmp_path)
    assert r1 != r2
    assert "dia 1" not in r2.read_text(encoding="utf-8")
