"""Preferencias de la ventana: solo valores validos llegan al CSS de la ventana."""

from __future__ import annotations

from doombot.ventana import preferencias
from doombot.ventana.preferencias import DEFECTO, guardar, leer, limpiar


def test_lo_valido_se_conserva():
    datos = {
        "tema": "holograma",
        "c1": "#FFAE2B",
        "c2": "#ffd88a",
        "luz": 1.3,
        "fondo": 0.2,
        "velocidad": 0.5,
        "por_herramienta": False,
        "circuitos": False,
        "crt": False,
        "voz_siempre": True,
        "manos_libres": True,
        "perfiles": [],
    }
    assert limpiar(datos) == {**datos, "c1": "#ffae2b"}


def test_lo_raro_vuelve_al_defecto_sin_romper():
    datos = {
        "tema": "inventado",
        "c1": "red; background: url(http://x)",  # no puede colarse CSS
        "c2": "#12345",
        "luz": True,  # un bool no es un brillo
        "fondo": "0.5",
        "velocidad": 99,
        "crt": "si",
        "otra": 1,
    }
    limpio = limpiar(datos)
    assert limpio["tema"] == "jarvis"
    assert limpio["c1"] == DEFECTO["c1"] and limpio["c2"] == DEFECTO["c2"]
    assert limpio["luz"] == DEFECTO["luz"] and limpio["fondo"] == DEFECTO["fondo"]
    assert limpio["velocidad"] == 2.0  # recortado a su maximo
    assert limpio["crt"] is True
    assert "otra" not in limpio


def test_guardar_y_leer(tmp_path):
    ruta = tmp_path / "ventana.json"
    guardar({"tema": "neon", "c1": "#ff2bd6", "luz": 0.4}, ruta)
    assert leer(ruta)["tema"] == "neon"
    assert leer(ruta)["luz"] == 0.4


def test_sin_fichero_o_roto_da_el_defecto(tmp_path):
    assert leer(tmp_path / "no-existe.json") == DEFECTO
    roto = tmp_path / "roto.json"
    roto.write_text("{no es json", encoding="utf-8")
    assert leer(roto) == DEFECTO


PERFIL = {"id": "perfil-abc123", "nombre": "Noche", "c1": "#FF00AA", "c2": "#112233"}


def test_un_perfil_propio_se_guarda_y_puede_ser_el_tema():
    limpio = limpiar({"tema": "perfil-abc123", "c1": "#000000", "perfiles": [PERFIL]})
    assert limpio["perfiles"] == [{**PERFIL, "c1": "#ff00aa"}]
    assert limpio["tema"] == "perfil-abc123"
    # Con un perfil activo, se pintan sus colores aunque llegue otro c1.
    assert (limpio["c1"], limpio["c2"]) == ("#ff00aa", "#112233")


def test_un_tema_que_no_es_fijo_ni_un_perfil_guardado_no_vale():
    limpio = limpiar({"tema": "perfil-borrado", "perfiles": [PERFIL]})
    assert limpio["tema"] == "jarvis"


def test_un_perfil_roto_se_descarta_entero():
    rotos = [
        {**PERFIL, "id": "otro"},  # sin el prefijo perfil-
        {**PERFIL, "id": "perfil-x", "c1": "red;}"},  # no puede colarse CSS
        {**PERFIL, "id": "perfil-y", "nombre": " \n\t "},
        {**PERFIL, "id": "perfil-z", "nombre": 7},
        "no es un perfil",
    ]
    assert limpiar({"perfiles": rotos})["perfiles"] == []
    assert limpiar({"perfiles": "tampoco"})["perfiles"] == []


def test_el_nombre_se_queda_en_una_linea_corta():
    largo = {**PERFIL, "nombre": "  Mi\nperfil\x00 " + "x" * 50}
    (perfil,) = limpiar({"perfiles": [largo]})["perfiles"]
    assert perfil["nombre"].startswith("Mi perfil x")
    assert len(perfil["nombre"]) == 32


def test_sin_ids_repetidos_y_con_tope():
    muchos = [{**PERFIL, "id": f"perfil-{n}"} for n in range(preferencias.MAX_PERFILES + 5)]
    assert len(limpiar({"perfiles": muchos})["perfiles"]) == preferencias.MAX_PERFILES
    assert len(limpiar({"perfiles": [PERFIL, PERFIL]})["perfiles"]) == 1


def test_los_perfiles_sobreviven_a_guardar_y_leer(tmp_path):
    ruta = tmp_path / "ventana.json"
    guardar({"tema": "perfil-abc123", "perfiles": [PERFIL]}, ruta)
    leido = leer(ruta)
    assert leido["tema"] == "perfil-abc123"
    assert leido["perfiles"][0]["nombre"] == "Noche"


def test_el_defecto_no_se_comparte_entre_lecturas():
    limpiar(None)["perfiles"].append(PERFIL)
    assert DEFECTO["perfiles"] == []
    assert limpiar(None)["perfiles"] == []


def test_vive_fuera_del_repositorio():
    from doombot.paths import PROJECT_ROOT

    assert PROJECT_ROOT not in preferencias.fichero().parents
