"""Memoria de D.O.O.M.

Guarda cosas y las recupera por significado, no por palabras: preguntar
"cuanta VRAM tengo?" encuentra "el portatil lleva una GTX 1050 con 3 GB"
aunque no compartan ni un termino.

Es lo que compensa que el modelo sea pequeno. llama3.2:3b razona bien pero
sabe poco, y con la memoria la pregunta deja de ser que recuerda el modelo
para pasar a ser que puede leer.

    from doombot.backends.embeddings import FastEmbedder
    from doombot.memory import Memory

    with Memory(FastEmbedder.from_config()) as m:
        m.remember("El portatil lleva una GTX 1050 con 3 GB de VRAM")
        for r in m.recall("cuanta memoria grafica tengo?"):
            print(r.similarity, r.text)

Exportar estos nombres activa ademas la capacidad "recordar" en
``doombot.identity``, que detecta que este paquete ya expone algo y deja de
declarar que D.O.O.M. no guarda nada entre conversaciones.
"""

from doombot.memory.store import Memory, MemoryError, Recollection

__all__ = ["Memory", "MemoryError", "Recollection"]
