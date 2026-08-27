"""Captura de audio, palabra de activacion y sintesis.

- ``capture``  microfono: grabacion a WAV, deteccion de silencio y nivel

Es la unica parte del paquete con dependencias opcionales: se instala con
``pip install -e ".[voice]"``. Los modulos de aqui importan sounddevice y
companiia dentro de las funciones, para que un equipo que solo edita y
documenta pueda importar el paquete sin tenerlas.
"""
