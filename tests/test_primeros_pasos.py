"""Primeros pasos: guardar claves en .env y saber que falta. Siempre con un .env temporal."""

from __future__ import annotations

import os

import pytest

from doombot import config
from doombot.config import Settings, guardar_en_env
from doombot.ventana import primeros_pasos


@pytest.fixture
def env(tmp_path, monkeypatch):
    fichero = tmp_path / ".env"
    fichero.write_text(
        "# comentario que debe quedarse\nDOOMBOT_GROQ_API_KEY=\nDOOMBOT_MODELOS=gemini:g\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "ENV_FILE", fichero)
    for clave in ("DOOMBOT_GROQ_API_KEY", "DOOMBOT_MODELOS", "DOOMBOT_AGENT_BRAIN", "DOOMBOT_X"):
        monkeypatch.setenv(clave, "")
    yield fichero
    config.settings.cache_clear()


def test_guardar_sustituye_la_linea_y_conserva_lo_demas(env):
    guardar_en_env("DOOMBOT_GROQ_API_KEY", "gsk_123")
    guardar_en_env("DOOMBOT_X", "nuevo")
    lineas = env.read_text(encoding="utf-8").splitlines()
    assert lineas == [
        "# comentario que debe quedarse",
        "DOOMBOT_GROQ_API_KEY=gsk_123",
        "DOOMBOT_MODELOS=gemini:g",
        "DOOMBOT_X=nuevo",
    ]
    assert os.environ["DOOMBOT_GROQ_API_KEY"] == "gsk_123"


@pytest.mark.skipif(os.name != "posix", reason="permisos POSIX")
def test_el_fichero_con_claves_solo_lo_lee_su_dueno(env):
    guardar_en_env("DOOMBOT_GROQ_API_KEY", "gsk_123")
    assert env.stat().st_mode & 0o777 == 0o600


def test_un_salto_de_linea_no_cuela_otra_variable(env):
    with pytest.raises(ValueError):
        guardar_en_env(
            "DOOMBOT_GROQ_API_KEY", "gsk_1\nDOOMBOT_AGENT_PERMISSION_MODE=bypassPermissions"
        )


def test_guardar_clave_la_pone_en_la_lista_y_elige_cerebro(env):
    cfg = Settings(ollama_host="http://x", log_level="INFO", modelos=("gemini:g",))
    r = primeros_pasos.guardar("groq", "  gsk_abcdefgh1234  ", cfg=cfg)

    assert r == {"ok": True, "final": "1234"}
    texto = env.read_text(encoding="utf-8")
    assert "DOOMBOT_GROQ_API_KEY=gsk_abcdefgh1234" in texto
    assert "DOOMBOT_MODELOS=gemini:g,groq:openai/gpt-oss-120b" in texto
    assert "DOOMBOT_AGENT_BRAIN=varios" in texto


def test_guardar_con_otro_modelo_lo_sustituye(env):
    cfg = Settings(ollama_host="http://x", log_level="INFO", modelos=("groq:viejo", "gemini:g"))
    primeros_pasos.guardar("groq", "gsk_abcdefgh", "llama-3.3-70b-versatile", cfg=cfg)
    assert "DOOMBOT_MODELOS=groq:llama-3.3-70b-versatile,gemini:g" in env.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    ("proveedor", "clave", "error"),
    [
        ("groq", "", "Pega la clave"),
        ("groq", "gsk 123", "no parece una clave"),
        ("inventado", "x", "Proveedor desconocido"),
        ("mistral", "x", "Proveedor desconocido"),  # sin tutorial: no sale en primeros pasos
    ],
)
def test_guardar_rechaza_lo_que_no_es_una_clave(env, proveedor, clave, error):
    r = primeros_pasos.guardar(
        proveedor, clave, cfg=Settings(ollama_host="http://x", log_level="INFO")
    )
    assert not r["ok"] and error in r["error"]
    assert "DOOMBOT_GROQ_API_KEY=\n" in env.read_text(encoding="utf-8")


def test_el_estado_dice_que_hay_y_no_devuelve_la_clave(monkeypatch):
    monkeypatch.setattr(primeros_pasos, "_ollama_responde", lambda cfg: False)
    cfg = Settings(
        ollama_host="http://x",
        log_level="INFO",
        modelos=("groq:m1",),
        claves=(("groq", "gsk_secreta_1234"),),
    )
    e = primeros_pasos.estado(cfg)

    groq = next(p for p in e["proveedores"] if p["id"] == "groq")
    assert groq["configurada"] and groq["en_lista"] and groq["modelo"] == "m1"
    assert groq["final"] == "1234"
    assert "gsk_secreta" not in str(e)
    assert e["listos"] == 1
    assert [p["id"] for p in e["proveedores"]] == ["groq", "gemini", "nvidia", "openrouter"]


def test_probar_sin_clave_lo_dice():
    r = primeros_pasos.probar("groq", Settings(ollama_host="http://x", log_level="INFO"))
    assert not r["ok"] and "DOOMBOT_GROQ_API_KEY" in r["detalle"]
