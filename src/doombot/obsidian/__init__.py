"""Vault de Obsidian del proyecto: espejo legible de la memoria de D.O.O.M.

``memory/`` es rapido pero es una caja cerrada -SQLite con vectores, no algo
que se abra comodo con un editor-. Este paquete conecta ese cerebro interno
con un vault de Obsidian que vive DENTRO del repositorio (``paths.VAULT_DIR``),
para que el usuario pueda leer y editar a mano lo que D.O.O.M sabe, y para
que el traspaso entre equipos sea el mismo `git pull` de siempre, sin
exportar ni copiar nada aparte.

Dos direcciones, ninguna sustituye a la memoria real:

- ``escribir_perfil``   D.O.O.M -> vault. Anade lo que la voz ha aprendido del usuario.
- ``sincronizar_perfil``   vault -> D.O.O.M. Aprende lo que el usuario edito
  a mano en el vault, igual que si lo hubiera dicho por voz, y olvida lo borrado.
- ``leer_perfil`` / ``guardar_perfil``   el perfil entero -datos y hechos-, que
  la ventana edita y el agente lee en cada orden (D-043).
- ``anotar_progreso``   D.O.O.M -> vault. Bitacora de sesion, separada por
  dia y por turno (manana/tarde).
"""

from doombot.obsidian.vault import (
    CAMPOS_PERFIL,
    Perfil,
    anotar_hecho,
    anotar_progreso,
    escribir_perfil,
    guardar_perfil,
    leer_perfil,
    perfil_para_prompt,
    quitar_hecho,
    sincronizar_perfil,
)

__all__ = [
    "CAMPOS_PERFIL",
    "Perfil",
    "anotar_hecho",
    "anotar_progreso",
    "escribir_perfil",
    "guardar_perfil",
    "leer_perfil",
    "perfil_para_prompt",
    "quitar_hecho",
    "sincronizar_perfil",
]
