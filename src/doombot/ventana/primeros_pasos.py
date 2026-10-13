"""Primeros pasos: que necesita el agente para funcionar, y ayudar a ponerlo (D-035).

La ventana lo ensena antes del chat cuando no hay ningun modelo utilizable, y
despues desde el boton de la cabecera. Para cada proveedor gratuito: como
conseguir la clave, donde, y un campo para pegarla y probarla sin abrir
``.env`` a mano. Ademas, el estado de lo opcional: el navegador propio
(Playwright) y un modelo local (Ollama).

Una clave pegada aqui va a ``.env`` (``config.guardar_en_env``) y a ningun otro
sitio: ni a la ventana de vuelta -solo sus cuatro ultimos caracteres, para
reconocerla- ni a ningun registro.
"""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from doombot.backends.base import BackendError
from doombot.backends.proveedores import PROVEEDORES, construir, partir
from doombot.config import Settings, guardar_en_env, settings
from doombot.paths import ENV_FILE

OLLAMA_DESCARGA = "https://ollama.com/download"
OLLAMA_SUGERIDO = "qwen3:4b"


def _modelos(cfg: Settings) -> dict[str, str]:
    """Proveedor -> modelo, de ``DOOMBOT_MODELOS`` (el primero de cada uno)."""
    salida: dict[str, str] = {}
    for entrada in cfg.modelos:
        proveedor, modelo = partir(entrada)
        salida.setdefault(proveedor, modelo)
    return salida


def _chromium_instalado() -> bool:
    propio = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    candidatas = (
        [Path(propio)]
        if propio
        else [
            Path.home() / ".cache" / "ms-playwright",
            Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
            Path.home() / "Library" / "Caches" / "ms-playwright",
        ]
    )
    return any(c.is_dir() and any(c.glob("chromium-*")) for c in candidatas)


def _ollama_responde(cfg: Settings) -> bool:
    from doombot.backends.ollama import OllamaGenerator

    return OllamaGenerator("x", host=cfg.ollama_host).is_available()


def estado(cfg: Settings | None = None) -> dict[str, Any]:
    cfg = cfg or settings()
    modelos = _modelos(cfg)
    proveedores = []
    for p in PROVEEDORES.values():
        if not p.pasos:
            continue
        clave = cfg.clave(p.nombre)
        proveedores.append(
            {
                "id": p.nombre,
                "titulo": p.titulo,
                "alta": p.alta,
                "pasos": list(p.pasos),
                "gratis": p.gratis,
                "nota": p.nota,
                "modelo": modelos.get(p.nombre) or p.sugerido,
                "en_lista": p.nombre in modelos,
                "configurada": bool(clave),
                "final": clave[-4:] if len(clave) >= 8 else "",
            }
        )
    ollama = {
        "host": cfg.ollama_host,
        "responde": _ollama_responde(cfg),
        "en_lista": "ollama" in modelos,
        "descarga": OLLAMA_DESCARGA,
        "sugerido": OLLAMA_SUGERIDO,
    }
    return {
        "proveedores": proveedores,
        "listos": sum(1 for p in proveedores if p["configurada"] and p["en_lista"])
        + (1 if ollama["en_lista"] and ollama["responde"] else 0),
        "navegador": {
            "playwright": find_spec("playwright") is not None,
            "chromium": _chromium_instalado(),
        },
        "ollama": ollama,
        "env": str(ENV_FILE),
    }


def guardar(proveedor: str, clave: str, modelo: str = "", cfg: Settings | None = None) -> dict:
    """Guarda la clave en .env, y deja el proveedor en ``DOOMBOT_MODELOS`` con su modelo."""
    p = PROVEEDORES.get(proveedor)
    if p is None or not p.pasos:
        return {"ok": False, "error": f"Proveedor desconocido: {proveedor!r}."}
    clave = (clave or "").strip()
    if not clave:
        return {"ok": False, "error": "Pega la clave antes de guardar."}
    if any(c.isspace() for c in clave) or len(clave) > 400:
        return {
            "ok": False,
            "error": "Eso no parece una clave: no puede llevar espacios ni saltos.",
        }

    cfg = cfg or settings()
    guardar_en_env(f"DOOMBOT_{proveedor.upper()}_API_KEY", clave)

    modelo = (modelo or "").strip() or _modelos(cfg).get(proveedor) or p.sugerido
    lista = list(cfg.modelos)
    for i, entrada in enumerate(lista):
        if partir(entrada)[0] == proveedor:
            lista[i] = f"{proveedor}:{modelo}"
            break
    else:
        lista.append(f"{proveedor}:{modelo}")
    guardar_en_env("DOOMBOT_MODELOS", ",".join(lista))
    # Sin cerebro elegido para el agente, usaria el de DOOMBOT_LLM_BACKEND
    # -Ollama por defecto- y la clave recien guardada no serviria de nada.
    if not cfg.agent_brain:
        guardar_en_env("DOOMBOT_AGENT_BRAIN", "varios")
    return {"ok": True, "final": clave[-4:]}


def probar(proveedor: str, cfg: Settings | None = None) -> dict:
    """Una peticion minima al modelo del proveedor: si responde, la clave vale."""
    cfg = cfg or settings()
    p = PROVEEDORES.get(proveedor)
    modelo = _modelos(cfg).get(proveedor) or (p.sugerido if p else "")
    try:
        generador = construir(f"{proveedor}:{modelo}", cfg, max_tokens=64)
        generador.generate("Responde solo con la palabra: listo")
    except (ValueError, BackendError) as e:
        return {"ok": False, "detalle": str(e)}
    return {"ok": True, "detalle": f"{proveedor}/{modelo} responde."}
