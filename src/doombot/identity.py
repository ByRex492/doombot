"""Quien dice ser D.O.O.M., derivado de lo que sabe hacer de verdad.

El system prompt NO se escribe a mano. Se construye a partir de las
capacidades realmente presentes en esta instalacion.

La razon es concreta y se descubrio auditando la build. Con un prompt fijo,
llama3.2:3b respondia "Te recordare comprar pan manana" sin existir ninguna
memoria, y "Abri el navegador" sin poder abrir nada. Un modelo pequeno tiende
a sonar servicial antes que a ser exacto.

Eso no es solo desagradable: impide desarrollar. Si el asistente dice "te lo
recordare" tanto con memoria como sin ella, al construir la memoria no hay
forma de distinguir que funciona de que esta rota. La honestidad del prompt
es, antes que una cuestion de trato, una condicion para poder probar nada.

Al declarar aqui lo que hay, el prompt se corrige solo segun avanza el
proyecto, en vez de quedarse obsoleto en cuanto se anade una capa.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec

NOMBRE = "D.O.O.M."


@dataclass(frozen=True)
class Capability:
    """Algo que D.O.O.M. sabe o no sabe hacer."""

    name: str
    available: bool
    puede: str  # como se describe cuando esta
    no_puede: str  # como se describe cuando falta


def _tiene_contenido(modulo: str) -> bool:
    """True si el modulo existe y expone algo publico.

    Los paquetes memory, phrases y voice estan creados pero vacios: la
    estructura primero, la implementacion despues. Mientras sigan vacios, sus
    capacidades no se anuncian.
    """
    try:
        mod = __import__(f"doombot.{modulo}", fromlist=["_"])
    except ImportError:
        return False
    return any(not x.startswith("_") for x in dir(mod))


def capabilities() -> list[Capability]:
    """Lo que esta instalacion puede hacer ahora mismo."""
    return [
        Capability(
            "conversar",
            True,
            "responder preguntas y conversar por texto",
            "",
        ),
        Capability(
            "transcribir",
            find_spec("faster_whisper") is not None,
            "convertir audio grabado en texto",
            "",
        ),
        Capability(
            "recordar",
            _tiene_contenido("memory"),
            "guardar cosas y recuperarlas mas tarde",
            "no guardas nada entre conversaciones",
        ),
        # Oir y hablar eran una sola capacidad cuando ambos vivian en voice/.
        # Con tts/ como paquete propio, dejarlas juntas hacia que D.O.O.M
        # dijera que responde en voz alta por el mero hecho de tener microfono,
        # que es exactamente la clase de mentira que este modulo existe para
        # evitar. Se parten: cada una mira su paquete.
        Capability(
            "escuchar",
            _tiene_contenido("voice"),
            "escuchar por el microfono lo que se te dice",
            "no oyes: hay que escribirte",
        ),
        Capability(
            "hablar",
            # tts/ ya no importa Kokoro al cargarse (ver su __init__), asi que
            # exponer algo publico no prueba nada: hay que mirar el motor.
            _tiene_contenido("tts") and find_spec("kokoro_onnx") is not None,
            "responder en voz alta, no solo por pantalla",
            "no tienes voz: respondes escribiendo",
        ),
        Capability(
            "actuar",
            _tiene_contenido("actions"),
            "delegar tareas de codigo reales -editar ficheros, ejecutar comandos- "
            "en el agente de acciones, y disparar workflows de n8n ya dados de alta",
            "no puedes abrir programas, ni tocar ficheros, ni manejar el equipo",
        ),
        Capability(
            "consultar",
            False,
            "buscar informacion actualizada",
            "no tienes acceso a internet ni a datos en tiempo real",
        ),
    ]


def system_prompt() -> str:
    """El prompt que se le pasa al modelo, honesto por construccion."""
    caps = capabilities()
    puede = [c.puede for c in caps if c.available and c.puede]
    no_puede = [c.no_puede for c in caps if not c.available and c.no_puede]

    partes = [
        f"Eres {NOMBRE}, un asistente que corre en el ordenador del usuario.",
        "Respondes en espanol, de forma breve y directa, sin preambulos.",
    ]
    if puede:
        partes.append("Puedes: " + "; ".join(puede) + ".")
    if no_puede:
        # "Limitaciones" y no "NO puedes", porque las frases ya vienen en
        # negativo y encadenarlas producia "NO puedes: no guardas nada".
        partes.append("Limitaciones: " + "; ".join(no_puede) + ".")

    # Esta es la instruccion que corrige el fallo observado. Sin ella, el
    # modelo contesta "Abri el navegador" a una orden que no puede ejecutar.
    partes.append(
        "Si te piden algo que no puedes hacer, dilo claramente en una frase. "
        "Nunca afirmes haber hecho algo que no has hecho, ni prometas recordar "
        "nada si no puedes guardarlo."
    )

    # "No puedo hacer eso" y "no se eso" son cosas distintas, y hace falta
    # decir las dos. Con solo la primera, ante "donde esta alojado el codigo?"
    # el modelo respondia inventando carpetas concretas del disco en vez de
    # reconocer que no tenia ni idea.
    partes.append(
        "Si no sabes algo, dilo. No inventes datos concretos —rutas, nombres, "
        "cifras, fechas— para rellenar una respuesta."
    )
    return " ".join(partes)


def resumen() -> str:
    """Linea legible para el diagnostico."""
    caps = capabilities()
    return ", ".join(f"{c.name}{'' if c.available else ' (no)'}" for c in caps)
