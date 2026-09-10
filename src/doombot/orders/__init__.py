"""Registro de órdenes: cada capa declara las suyas y nadie edita un fichero común.

**Por qué existe.** `chat.py` tenía siete bloques ``if orden.command == ...``
encadenados en una función de 293 líneas. Funcionaba, pero convertía el fichero
en el punto por el que pasa toda capa nueva: añadir una orden significaba tocar
esas veinte líneas. Con una sola persona es una molestia; con varias sesiones
trabajando en capas distintas a la vez es un conflicto de fusión garantizado en
cada rama, y ninguno resoluble automáticamente porque git no sabe en qué orden
van los bloques.

Ahora una capa nueva escribe ``su_paquete/orders.py``, decora sus manejadores, y
no toca nada compartido. El punto de colisión pasa a ser un punto de extensión.

**Cómo se cargan.** ``cargar()`` recorre los subpaquetes de ``doombot`` e importa
el módulo ``orders`` de los que lo tengan. Se descartó una lista explícita de
módulos: sería un fichero común más, y volvería el mismo problema con otro
nombre.

Un manejador recibe la ``Sesion`` —todo lo que puede necesitar— y el ``Match``,
y devuelve ``True`` si atendió la orden.
"""

from doombot.orders.registry import Sesion, cargar, despachar, orden, registradas

__all__ = ["Sesion", "cargar", "despachar", "orden", "registradas"]
