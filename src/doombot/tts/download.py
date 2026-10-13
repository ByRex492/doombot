"""Descarga los ficheros de Kokoro, la primera vez que hacen falta.

A diferencia de Whisper (``faster_whisper`` descarga solo) o los embeddings
(``fastembed`` igual), kokoro-onnx no trae descarga automatica:
``KoKoroConfig.validate()`` se limita a fallar con la URL en el mensaje de
error. Esto es esa descarga, hecha aqui una vez para no repetirla a mano en
cada equipo.

Solo el modelo en fp32 (D-021: es el mas rapido en CPU en esta maquina,
medido, no el mas pequeno). fp16 e int8 no se descargan porque no se usan.
"""

from __future__ import annotations

from pathlib import Path

import httpx

# Viven aqui y no en synth.py para que descargar no exija tener instalado
# el extra voice-tts: synth importa kokoro_onnx y scipy al cargarse.
#
# Fichero de modelo elegido tras medir en esta maquina (ver D-021): fp32, no
# las variantes cuantizadas. fp16 e int8 pesan menos en disco pero en CPU van
# MAS LENTAS que fp32 -el hardware no acelera fp16 de forma nativa, y el int8
# cae en kernels de referencia sin optimizar-, asi que aqui "mas pequeno" no
# significa "mas rapido". Contraintuitivo, y por eso queda medido y no supuesto.
MODELO_ONNX = "kokoro-v1.0.onnx"
VOCES_BIN = "voices-v1.0.bin"

_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"

# Tamano esperado de cada fichero, para saber si una descarga a medias -por
# ejemplo, cortada por perder la conexion- quedo corta y hay que repetirla.
# No es una verificacion de integridad (para eso haria falta un hash), solo
# de que no falte el final.
_TAMANOS = {
    MODELO_ONNX: 325_505_369,
    VOCES_BIN: 28_214_398,
}

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


def modelos_completos(carpeta: Path) -> bool:
    """True si ambos ficheros ya estan y con el tamano esperado."""
    return all(
        (carpeta / nombre).is_file() and (carpeta / nombre).stat().st_size >= tamano
        for nombre, tamano in _TAMANOS.items()
    )


def asegurar_modelos(carpeta: Path, *, progreso: bool = True) -> None:
    """Descarga lo que falte de ``kokoro-v1.0.onnx`` y ``voices-v1.0.bin``.

    Unos 354 MB en total la primera vez; nada si ya estan. Se descarga a un
    fichero ``.parcial`` y se renombra al terminar, para que una descarga
    interrumpida a medias no se confunda con una completa la proxima vez.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, tamano_esperado in _TAMANOS.items():
        destino = carpeta / nombre
        if destino.is_file() and destino.stat().st_size >= tamano_esperado:
            continue
        if progreso:
            print(f"  descargando {nombre} ({tamano_esperado / 1_000_000:.0f} MB)...")
        _descargar(f"{_BASE}/{nombre}", destino)


def _descargar(url: str, destino: Path) -> None:
    parcial = destino.with_name(destino.name + ".parcial")
    with httpx.stream("GET", url, timeout=_TIMEOUT, follow_redirects=True) as r:
        r.raise_for_status()
        with parcial.open("wb") as f:
            for trozo in r.iter_bytes(chunk_size=1 << 20):
                f.write(trozo)
    parcial.replace(destino)
