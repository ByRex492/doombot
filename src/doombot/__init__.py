"""D.O.O.M — asistente de voz local.

El paquete se organiza por responsabilidad, no por tecnologia:

- ``paths``    rutas del proyecto y de los datos locales
- ``config``   lo que cambia de un equipo a otro
- ``profiles`` deteccion de hardware y eleccion de perfil
- ``identity`` que dice saber hacer, derivado de lo que hay instalado
- ``backends`` contratos e implementaciones de modelo, voz y embeddings
- ``memory``   que recuerda D.O.O.M y como lo consulta
- ``phrases``  reconocimiento de frases textuales y ordenes
- ``orders``   registro donde cada capa declara las ordenes que atiende
- ``chat``     modo interactivo que junta todas las capas
- ``voice``    captura de audio, palabra de activacion y salida hablada
- ``tts``      sintesis de voz: convierte la respuesta en sonido
- ``hud_server`` transporte del HUD por WebSocket, hacia ui/prototipo/hud.html
- ``actions``  capa de acciones: delega tareas reales en Claude Code
- ``obsidian`` espejo legible de la memoria en el vault del proyecto
- ``files``    ficheros que el usuario le deja en el buzon, como contexto
"""

__version__ = "0.1.0"
