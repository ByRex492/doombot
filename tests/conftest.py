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
