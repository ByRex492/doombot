"""La eleccion de perfil se hace por VRAM, no por nombre de equipo."""

from __future__ import annotations

import pytest

from doombot import profiles
from doombot.paths import PROFILES_FILE


@pytest.fixture
def cargados():
    return profiles.load_profiles()


def test_hay_un_perfil_de_ultimo_recurso(cargados):
    """Sin uno de min_vram_mb = 0, una maquina sin GPU no arrancaria."""
    assert any(d["min_vram_mb"] == 0 for d in cargados.values())


def test_todos_los_perfiles_estan_completos(cargados):
    obligatorios = {"min_vram_mb", "llm_model", "llm_num_ctx", "stt_model", "stt_device"}
    for nombre, d in cargados.items():
        faltan = obligatorios - d.keys()
        assert not faltan, f"Al perfil {nombre} le faltan: {sorted(faltan)}"


@pytest.mark.parametrize(
    ("vram", "esperado"),
    [
        (0, "cpu_only"),
        (1024, "cpu_only"),
        (3072, "laptop"),  # GTX 1050
        (6144, "laptop"),
        (16384, "workstation"),  # RTX 5060 Ti
    ],
)
def test_seleccion_por_vram(vram, esperado, cargados):
    assert profiles.select(vram, cargados) == esperado


def test_portatil_fuerza_gpu(cargados):
    """En una GPU de 3 GB, sin num_gpu alto Ollama deja la mitad en CPU.

    Medido: 12,3 tok/s con el valor por defecto frente a 29,3 forzandolo.
    """
    assert cargados["laptop"]["llm_num_gpu"] >= 99


def test_el_portatil_transcribe_en_cpu(cargados):
    """Con el modelo cargado sobran 489 MiB: la voz no cabe en esa GPU."""
    assert cargados["laptop"]["stt_device"] == "cpu"


def test_perfil_forzado_inexistente_avisa(monkeypatch):
    monkeypatch.setenv("DOOMBOT_PROFILE", "no_existe")
    with pytest.raises(RuntimeError, match="no existe"):
        profiles.current()


def test_perfil_forzado_se_respeta(monkeypatch):
    monkeypatch.setenv("DOOMBOT_PROFILE", "workstation")
    assert profiles.current().name == "workstation"


def test_deteccion_de_vram_no_revienta_sin_gpu():
    """Sin nvidia-smi debe devolver 0, no lanzar."""
    assert profiles.detect_vram_mb() >= 0


def test_el_fichero_de_perfiles_existe():
    assert PROFILES_FILE.is_file()
