"""Órdenes que atiende la memoria: recordar, consultar y olvidar.

``identify`` vive aquí y no en ``obsidian`` aunque escriba el vault: lo que hace
de verdad es guardar un recuerdo, y volcarlo al vault es una consecuencia.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from doombot.orders import Sesion, orden

if TYPE_CHECKING:
    from doombot.phrases.matcher import Match


@orden("remember")
def recordar(s: Sesion, m: Match) -> None:
    if not m.argument:
        s.aviso("¿que quieres que recuerde?")
        return
    s.ultimo_guardado = s.mem.remember(m.argument)
    s.decir(f"Apuntado: {m.argument}")


@orden("identify")
def identificar(s: Sesion, m: Match) -> None:
    """Un hecho SOBRE EL USUARIO, que va siempre en el prompt."""
    if not m.argument:
        s.aviso("¿que quieres que sepa de ti?")
        return
    from doombot.obsidian import escribir_perfil

    s.ultimo_guardado = s.mem.remember(m.argument, kind="perfil")
    escribir_perfil(s.mem)
    s.decir(f"Anotado sobre ti: {m.argument}")


@orden("recall")
def consultar(s: Sesion, m: Match) -> None:
    encontrados = s.mem.recall(m.argument)
    for r in encontrados:
        s.traza(f"recuerda ({r.similarity:.2f}) {r.text}")
    if not encontrados:
        s.decir("No tengo nada guardado sobre eso.")
        return
    # Se manda la entrada entera, no solo el argumento: el modelo responde
    # mejor a "que sabes sobre X" que a "X" a secas.
    s.responder(s.con_contexto(s.entrada, s.mem.as_context(m.argument)))


@orden("forget")
def olvidar(s: Sesion, m: Match) -> None:
    """Solo el último. Borrar por descripción exigiría confirmar cuál, y una
    orden de voz que borra memoria sin confirmación es mala idea.

    Si era un hecho sobre el usuario, sale también de ``usuario.md``: el
    fichero manda (D-043), y si se quedara ahí volvería en la siguiente
    sincronización."""
    previo = s.mem.get(s.ultimo_guardado) if s.ultimo_guardado is not None else None
    if s.ultimo_guardado is not None and s.mem.forget(s.ultimo_guardado):
        s.ultimo_guardado = None
        if previo is not None and previo.kind == "perfil":
            import contextlib

            from doombot.obsidian import quitar_hecho

            with contextlib.suppress(ValueError):
                quitar_hecho(previo.text)
        s.decir("Olvidado.")
    else:
        s.decir("No hay nada reciente que olvidar.")
