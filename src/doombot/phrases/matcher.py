"""Reconocimiento de ordenes habladas.

Es la capa refleja de D.O.O.M. Cuando el usuario dice "para", tiene que callar
al instante y siempre: no puede depender de que un modelo de 3B a 29 tok/s
decida si eso era una orden. De ahi que aqui no haya modelo ninguno, solo
comparacion de texto, y que una orden se resuelva en microsegundos.

El problema real no es comparar cadenas, sino que lo que llega no es texto
limpio: es lo que devuelve el reconocimiento de voz. Medido con Whisper sobre
audio en espanol, una misma orden llega como

    "Modo silencioso"
    "¡DOOM! Activa el modo silencioso."
    "doom activa el modo silencioso"

con signos de apertura, mayusculas arbitrarias, tildes y muletillas alrededor.
Comparar eso con == no reconoceria nada. Por eso todo pasa antes por
``normalize``, y la busqueda admite tres grados de tolerancia.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Umbral de parecido para aceptar una orden con erratas. Calibrado sobre los
# fallos reales del reconocimiento de voz: "identifiqués" por "identifiques",
# "Alportatil" por "al portatil". Esos rondan 0,90 de parecido.
#
# Por debajo de 0,85 empiezan a colarse ordenes distintas entre si; el par mas
# peligroso medido es "para" contra "pare", que ya esta en 0,75.
UMBRAL_ERRATAS = 0.85

_PUNTUACION = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")


def normalize(texto: str) -> str:
    """Deja el texto en su forma comparable.

    Minusculas, sin tildes, sin puntuacion y con los espacios colapsados. Los
    signos de apertura del espanol importan mas de lo que parece: Whisper
    devuelve "¡DOOM!" y "¿que tal?", y sin quitarlos ninguna comparacion
    literal funcionaria.

    La ñ se conserva a proposito. Quitarle la tilde a "año" da "ano", que es
    otra palabra, y en una orden hablada eso puede cambiar el significado.
    """
    texto = texto.lower().strip()
    # Se descompone en caracteres base + marcas, se tiran las marcas y se
    # recompone. La ñ se protege antes porque su marca es parte de la letra.
    texto = texto.replace("ñ", "\x00")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = unicodedata.normalize("NFC", texto).replace("\x00", "ñ")
    texto = _PUNTUACION.sub(" ", texto)
    return _ESPACIOS.sub(" ", texto).strip()


def similarity(a: str, b: str) -> float:
    """Parecido entre dos textos ya normalizados, de 0 a 1."""
    return SequenceMatcher(None, a, b).ratio()


@dataclass(frozen=True)
class Command:
    """Una orden y las formas de decirla.

    ``prefix`` marca las que llevan argumento: "recuerda que el pan esta caro"
    reconoce la orden y captura el resto como texto. Sin esto solo se podrian
    definir ordenes fijas, y la mitad de lo que se le dice a un asistente
    lleva contenido detras.
    """

    name: str
    phrases: tuple[str, ...]
    prefix: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.phrases:
            raise ValueError(f"La orden {self.name!r} no tiene ninguna frase.")


@dataclass(frozen=True)
class Match:
    """Una orden reconocida."""

    command: str
    phrase: str  # la variante que coincidio
    confidence: float
    how: str  # exact | contains | fuzzy
    argument: str = ""  # lo que venia detras, en ordenes con prefijo
    metadata: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return True


def _partir_original(original: str, k: int) -> str:
    """Lo que queda del texto ORIGINAL tras las k primeras palabras normalizadas.

    No se puede cortar por posicion de caracter: normalize() cambia longitudes
    —quita signos, colapsa espacios— y "3.12" pasa a ser dos palabras donde
    habia una. Se recorre palabra a palabra contando cuantas normalizadas
    produce cada una hasta llegar a k.
    """
    palabras = original.split()
    contadas = 0
    for i, palabra in enumerate(palabras):
        n = normalize(palabra)
        contadas += len(n.split())
        if contadas >= k:
            return _limpiar_bordes(" ".join(palabras[i + 1 :]))
    return ""


# Signos que solo son ruido en los extremos. El punto de "3.12" o la coma de
# una enumeracion se conservan: van dentro, y ahi si dicen algo.
_BORDES = " .,;:!?¡¿\"'"


def _limpiar_bordes(texto: str) -> str:
    """Quita la puntuacion de cierre que anade el dictado, no la interna."""
    return texto.strip(_BORDES).strip()


class PhraseMatcher:
    """Reconoce ordenes en texto hablado.

    Prueba tres grados, de mas a menos exigente, y para en el primero que
    acierte. El orden importa: una coincidencia exacta nunca debe perder
    frente a una difusa que se parezca mas por casualidad.

        exact     el texto normalizado ES la orden
        contains  la orden aparece dentro de una frase mas larga
        fuzzy     se parece lo suficiente pese a las erratas del dictado
    """

    def __init__(self, commands: list[Command] | None = None, *, fuzzy: bool = True) -> None:
        self._commands: list[Command] = []
        self._fuzzy = fuzzy
        for c in commands or []:
            self.add(c)

    def add(self, command: Command) -> None:
        if any(c.name == command.name for c in self._commands):
            raise ValueError(f"Ya existe una orden llamada {command.name!r}.")
        self._commands.append(command)

    @property
    def commands(self) -> list[Command]:
        return list(self._commands)

    def match(self, texto: str) -> Match | None:
        """La orden reconocida, o None si el texto no es ninguna.

        Devolver None es lo normal y no un fallo: la mayoria de lo que se dice
        no son ordenes, sino cosas que hay que pasar al modelo.
        """
        limpio = normalize(texto)
        if not limpio:
            return None

        # El original viaja junto al normalizado porque el argumento de las
        # ordenes con prefijo se recorta del PRIMERO. Normalizar sirve para
        # comparar, no para almacenar: guardar el argumento ya normalizado
        # destruye los nombres propios sin vuelta atras —"GitHub" se convierte
        # en "github", "Python" en "python"— y ata los recuerdos a la
        # normalizacion vigente el dia que se guardaron.
        for intento in (self._exacto, self._contiene, self._difuso):
            if (m := intento(limpio, texto)) is not None:
                return m
        return None

    # -- los tres grados -----------------------------------------------------
    def _exacto(self, texto: str, original: str) -> Match | None:
        for c in self._commands:
            for f in c.phrases:
                if texto == normalize(f):
                    return Match(c.name, f, 1.0, "exact")
        return None

    def _contiene(self, texto: str, original: str) -> Match | None:
        """La orden dentro de una frase mas larga.

        Cubre el caso mas comun del dictado: "doom activa el modo silencioso"
        contiene "modo silencioso" con muletillas delante y detras.

        Se prefiere la frase mas larga que encaje. Si "para" y "para de hablar"
        son ordenes distintas, quedarse con la primera que aparezca dejaria la
        segunda inalcanzable.
        """
        mejor: tuple[int, Command, str] | None = None
        for c in self._commands:
            for f in c.phrases:
                n = normalize(f)
                if not n:
                    continue
                if c.prefix:
                    if texto.startswith(f"{n} ") and (mejor is None or len(n) > mejor[0]):
                        mejor = (len(n), c, f)
                elif re.search(rf"(?:^|\s){re.escape(n)}(?:\s|$)", texto) and (
                    mejor is None or len(n) > mejor[0]
                ):
                    mejor = (len(n), c, f)

        if mejor is None:
            return None
        largo, c, f = mejor
        # El argumento sale del ORIGINAL, con sus tildes y sus mayusculas.
        arg = _partir_original(original, len(normalize(f).split())) if c.prefix else ""
        # Cuanto mas ocupe la orden dentro de la frase, mas claro esta que era
        # una orden y no una mencion de pasada.
        confianza = min(1.0, 0.6 + 0.4 * (largo / max(len(texto), 1)))
        return Match(c.name, f, round(confianza, 3), "contains", arg)

    def _difuso(self, texto: str, original: str) -> Match | None:
        """Tolera las erratas del dictado.

        Solo se aplica a frases de longitud parecida: comparar una orden de
        tres letras con una frase de cuarenta siempre da parecido bajo, y
        dejarlo pasar solo anade falsos positivos.
        """
        if not self._fuzzy:
            return None

        if (m := self._difuso_prefijo(texto, original)) is not None:
            return m

        mejor: tuple[float, Command, str] | None = None
        for c in self._commands:
            if c.prefix:
                continue  # el parecido de la frase entera lo diluye el argumento
            for f in c.phrases:
                n = normalize(f)
                if not n or not (0.5 <= len(texto) / max(len(n), 1) <= 2.0):
                    continue
                s = similarity(texto, n)
                if s >= UMBRAL_ERRATAS and (mejor is None or s > mejor[0]):
                    mejor = (s, c, f)

        if mejor is None:
            return None
        s, c, f = mejor
        return Match(c.name, f, round(s, 3), "fuzzy")

    def _difuso_prefijo(self, texto: str, original: str) -> Match | None:
        """Ordenes con argumento cuando el prefijo llega con erratas.

        Comparar la frase entera no vale: el argumento es variable y diluye
        cualquier parecido. Se comparan solo las primeras palabras, tantas
        como tenga el prefijo, y el resto se toma como argumento.

        El caso que lo motivo es real: al dictar "que sabes sobre mi portatil",
        Whisper devolvio "que sabe sobre mi portatil" —sin la ese— y la orden
        dejaba de reconocerse pese a estar clarisima.
        """
        palabras = texto.split()
        mejor: tuple[float, Command, str, int] | None = None

        for c in self._commands:
            if not c.prefix:
                continue
            for f in c.phrases:
                n = normalize(f)
                k = len(n.split())
                if not n or len(palabras) <= k:
                    continue  # sin argumento detras no es una orden util
                s = similarity(" ".join(palabras[:k]), n)
                if s >= UMBRAL_ERRATAS and (mejor is None or s > mejor[0]):
                    mejor = (s, c, f, k)

        if mejor is None:
            return None
        s, c, f, k = mejor
        return Match(c.name, f, round(s, 3), "fuzzy", _partir_original(original, k))

    def __repr__(self) -> str:
        return f"PhraseMatcher({len(self._commands)} ordenes)"


# ---------------------------------------------------------------------------
# Ordenes basicas.
#
# Son las que un asistente de voz necesita para ser gobernable: poder callarlo,
# pararlo y decirle que recuerde algo. Las de control van primero a proposito:
# si algo va mal, "para" tiene que funcionar antes que cualquier otra cosa.
BASICAS = [
    Command(
        "stop",
        ("para", "detente", "alto", "cancela", "para ya"),
        description="Interrumpe lo que este haciendo",
    ),
    Command(
        "silence",
        ("modo silencioso", "silencio", "callate", "no hables"),
        description="Deja de responder en voz alta",
    ),
    Command(
        "speak",
        ("modo normal", "puedes hablar", "vuelve a hablar"),
        description="Reanuda la salida de voz",
    ),
    Command(
        "repeat",
        ("repite", "repitelo", "otra vez", "que has dicho"),
        description="Repite la ultima respuesta",
    ),
    Command(
        "remember",
        ("recuerda que", "apunta que", "no olvides que", "acuerdate de que"),
        prefix=True,
        description="Guarda lo que venga detras en la memoria",
    ),
    Command(
        "recall",
        ("que sabes sobre", "que recuerdas de", "que sabes de"),
        prefix=True,
        description="Busca en la memoria lo que venga detras",
    ),
    Command(
        "forget",
        ("olvida eso", "olvidalo", "borra eso"),
        description="Descarta el ultimo recuerdo guardado",
    ),
    Command(
        "identify",
        ("recuerda que yo", "recuerda sobre mi que", "mi nombre es", "me llamo"),
        prefix=True,
        description="Guarda un hecho SOBRE EL USUARIO, no un hecho general",
    ),
    Command(
        "act",
        ("ejecuta esto", "encargate del codigo", "tarea de codigo", "haz esto en el codigo"),
        prefix=True,
        description="Delega una tarea real en el agente de acciones",
    ),
    Command(
        "flow",
        ("activa el flujo",),
        prefix=True,
        description="Dispara un workflow de n8n de la lista blanca (D-030)",
    ),
    Command(
        "progress",
        ("anota el progreso", "apunta el progreso", "escribe el progreso"),
        prefix=True,
        description="Anade una nota de progreso al vault de Obsidian",
    ),
    Command(
        "read_file",
        # "lee" a secas queda fuera aposta: aparece en demasiadas frases
        # normales ("lee esto que te digo") y dispararia la orden sin querer.
        (
            "lee el archivo",
            "lee el fichero",
            "abre el archivo",
            "abre el fichero",
            "mira el archivo",
            "mira el fichero",
            "lee el documento",
            "lee lo ultimo que te deje",
        ),
        prefix=True,
        description="Lee un fichero del buzon y lo usa para responder",
    ),
]


def default_matcher(*, fuzzy: bool = True) -> PhraseMatcher:
    return PhraseMatcher(list(BASICAS), fuzzy=fuzzy)
