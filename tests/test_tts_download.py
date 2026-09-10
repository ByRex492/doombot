"""Descarga de los ficheros de Kokoro, probada sin red.

``asegurar_modelos`` se llama con un ``carpeta`` de ``tmp_path``, y la propia
``httpx.stream`` se sustituye por un doble: ni un byte real cruza la red al
correr estos tests.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from doombot.tts import download


class RespuestaFalsa:
    def __init__(self, contenido: bytes) -> None:
        self._contenido = contenido

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self, chunk_size: int):
        yield self._contenido


@pytest.fixture
def sin_red(monkeypatch):
    """Cada URL pedida devuelve un contenido fijo, sin tocar la red."""
    pedidas: list[str] = []

    @contextmanager
    def stream_falso(metodo, url, **kwargs):
        pedidas.append(url)
        yield RespuestaFalsa(b"contenido de prueba")

    monkeypatch.setattr(download.httpx, "stream", stream_falso)
    return pedidas


def test_modelos_completos_falso_si_falta_un_fichero(tmp_path):
    (tmp_path / download.MODELO_ONNX).write_bytes(b"x" * download._TAMANOS[download.MODELO_ONNX])
    assert not download.modelos_completos(tmp_path)


def test_modelos_completos_falso_si_el_tamano_no_llega(tmp_path):
    for nombre, tamano in download._TAMANOS.items():
        (tmp_path / nombre).write_bytes(b"x" * (tamano - 1))
    assert not download.modelos_completos(tmp_path)


def test_modelos_completos_true_con_los_dos_ficheros_enteros(tmp_path):
    for nombre, tamano in download._TAMANOS.items():
        (tmp_path / nombre).write_bytes(b"x" * tamano)
    assert download.modelos_completos(tmp_path)


def test_asegurar_modelos_no_toca_la_red_si_ya_estan(tmp_path, sin_red):
    for nombre, tamano in download._TAMANOS.items():
        (tmp_path / nombre).write_bytes(b"x" * tamano)
    download.asegurar_modelos(tmp_path, progreso=False)
    assert sin_red == []


def test_asegurar_modelos_descarga_solo_lo_que_falta(tmp_path, sin_red, monkeypatch):
    # Reduce los tamanos esperados para no tener que fabricar 354 MB en el test.
    monkeypatch.setitem(download._TAMANOS, download.MODELO_ONNX, 4)
    monkeypatch.setitem(download._TAMANOS, download.VOCES_BIN, 4)
    (tmp_path / download.VOCES_BIN).write_bytes(b"x" * 4)  # este ya esta completo

    download.asegurar_modelos(tmp_path, progreso=False)

    assert len(sin_red) == 1
    assert download.MODELO_ONNX in sin_red[0]
    assert (tmp_path / download.MODELO_ONNX).is_file()
    assert not (tmp_path / f"{download.MODELO_ONNX}.parcial").exists()


def test_asegurar_modelos_no_deja_el_fichero_parcial(tmp_path, sin_red, monkeypatch):
    monkeypatch.setitem(download._TAMANOS, download.MODELO_ONNX, 4)
    monkeypatch.setitem(download._TAMANOS, download.VOCES_BIN, 4)
    download.asegurar_modelos(tmp_path, progreso=False)
    assert not any(p.name.endswith(".parcial") for p in tmp_path.iterdir())
