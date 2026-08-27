"""La configuracion local no debe filtrarse al repositorio."""

from __future__ import annotations

from doombot import config
from doombot.paths import PROJECT_ROOT


def test_env_no_esta_versionado():
    """.env lleva IPs y rutas del equipo. Si se versiona, se rompe el otro."""
    ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in ignore


def test_existe_la_plantilla():
    assert (PROJECT_ROOT / ".env.example").is_file()


def test_load_env_sin_fichero_no_falla(tmp_path):
    assert config.load_env(tmp_path / "no-existe") == {}


def test_load_env_lee_pares(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('# comentario\nDOOMBOT_X="valor"\nVACIA=\n\nmal formada\n', encoding="utf-8")
    monkeypatch.delenv("DOOMBOT_X", raising=False)
    leidas = config.load_env(f)
    assert leidas["DOOMBOT_X"] == "valor"
    assert "mal formada" not in leidas


def test_el_entorno_manda_sobre_el_fichero(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("DOOMBOT_X=del_fichero\n", encoding="utf-8")
    monkeypatch.setenv("DOOMBOT_X", "del_entorno")
    config.load_env(f)
    import os

    assert os.environ["DOOMBOT_X"] == "del_entorno"


def test_detecta_ollama_remoto(monkeypatch):
    local = config.Settings(ollama_host="http://127.0.0.1:11434", log_level="INFO")
    remoto = config.Settings(ollama_host="http://192.168.1.40:11434", log_level="INFO")
    assert not local.is_remote_ollama
    assert remoto.is_remote_ollama
