"""Darle ficheros a D.O.O.M sin tener que describirlos con la voz.

El objetivo del proyecto es manejarlo sin manos, pero un fichero no se dicta:
nadie va a deletrear `C:\\Users\\...\\contrato-alquiler-2026.md` en voz alta.
La solucion es partir el gesto en dos, y que solo el primero use las manos:

1. Se suelta el fichero en el **buzon** (``paths.inbox_dir()``), una carpeta
   fuera del repositorio. Un arrastrar y soltar, sin hablar.
2. Despues se le pide de palabra: *"lee lo ultimo que te deje"* o *"lee el
   contrato"*. La resolucion por parecido evita tener que decir el nombre
   exacto, que es lo que hablando no se puede hacer.

Se descarto que la orden aceptara solo rutas literales: funciona escribiendo y
es inservible hablando, justo al reves de lo que necesita el proyecto.

- ``resolver``       lo dicho -> un fichero concreto del buzon o una ruta.
- ``leer``           fichero -> texto, recortado al techo del contexto.
- ``como_contexto``  texto -> bloque delimitado para el prompt.
- ``listar_buzon``   que hay ahora mismo en el buzon.
"""

from doombot.files.reader import (
    LIMITE_CARACTERES,
    Documento,
    como_contexto,
    leer,
    listar_buzon,
    resolver,
)

__all__ = [
    "LIMITE_CARACTERES",
    "Documento",
    "como_contexto",
    "leer",
    "listar_buzon",
    "resolver",
]
