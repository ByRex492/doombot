"""Configuracion comun de los tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _datos_aparte(tmp_path_factory, monkeypatch):
    """Cada test escribe sus datos en una carpeta temporal, nunca en la del usuario.

    Sin esto, un test que guarda algo -una conversacion, una preferencia, lo
    aprendido- lo dejaba en ``data_dir()`` de quien pasaba los tests: paso con
    el historial de conversaciones (D-038), que llego a llenar el historial real
    con conversaciones de prueba.
    """
    monkeypatch.setenv("DOOMBOT_DATA_DIR", str(tmp_path_factory.mktemp("datos")))


@pytest.fixture(autouse=True)
def _vault_aparte(tmp_path_factory, monkeypatch):
    """El perfil del usuario (``obsidian/usuario.md``) tampoco se toca en los tests.

    Vive en el repositorio, no en ``data_dir()``, asi que la carpeta de datos
    temporal de arriba no lo protege: sin esto, un test que anota algo en el
    perfil lo escribiria en el de verdad, y se subiria con el siguiente commit
    (D-043). Tambien evita lo contrario: que un test lea el perfil real.
    """
    from doombot.obsidian import vault

    monkeypatch.setattr(vault, "VAULT_DIR", tmp_path_factory.mktemp("vault"))


@pytest.fixture(autouse=True)
def _taller_aparte(tmp_path_factory, monkeypatch):
    """El taller (D-045) tampoco: sin esto, la ventana de los tests usaria ``~/taller``."""
    import shutil

    from doombot.agent import taller

    raiz = tmp_path_factory.mktemp("taller")
    monkeypatch.setattr(taller, "RAIZ_POR_DEFECTO", raiz)
    # Tambien si .env de quien pasa los tests pone DOOMBOT_TALLER: settings() va en cache.
    monkeypatch.setattr(
        taller, "crear_taller", lambda cfg=None: taller.Taller([raiz], git=shutil.which("git"))
    )


@pytest.fixture(autouse=True)
def _sin_voz(monkeypatch):
    """La ventana de los tests no abre el microfono ni carga Kokoro (D-046)."""
    from doombot.ventana import voz

    monkeypatch.setattr(
        voz, "crear_voz", lambda emitir, al_oir: voz.VozVentana(emitir=emitir, al_oir=al_oir)
    )
