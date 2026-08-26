"""D.O.O.M — asistente de voz local.

El paquete se organiza por responsabilidad, no por tecnologia:

- ``paths``    rutas del proyecto y de los datos locales
- ``config``   lo que cambia de un equipo a otro
- ``profiles`` deteccion de hardware y eleccion de perfil
- ``backends`` contratos e implementaciones de modelo, voz y embeddings
- ``memory``   que recuerda D.O.O.M y como lo consulta
- ``phrases``  reconocimiento de frases textuales y ordenes
- ``voice``    captura de audio, palabra de activacion y sintesis
"""

__version__ = "0.1.0"
