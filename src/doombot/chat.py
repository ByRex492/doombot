"""Modo interactivo: escribir a D.O.O.M. y ver como reacciona.

Junta por primera vez las cuatro capas en un bucle: reconoce ordenes, consulta
la memoria, genera con el modelo. Es lo que permite probar el sistema entero
sin escribir Python.

Muestra ademas por que hace lo que hace —que orden reconocio, que recuerdos
encontro y con que parecido—, porque probando importa mas entender la decision
que leer la respuesta. La voz llegara despues; de momento se escribe.
"""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass
from typing import Any

from doombot import profiles
from doombot.actions.claude_code import ClaudeCodeAgent
from doombot.actions.n8n import N8nClient
from doombot.backends.anthropic import AnthropicGenerator
from doombot.backends.base import BackendError, TextGenerator
from doombot.backends.embeddings import FastEmbedder
from doombot.backends.ollama import OllamaGenerator
from doombot.config import Settings, settings
from doombot.files import listar_buzon
from doombot.hud_server import ServidorHUD
from doombot.identity import resumen, system_prompt
from doombot.memory import Memory
from doombot.obsidian import escribir_perfil, sincronizar_perfil
from doombot.orders import Sesion, despachar
from doombot.paths import VAULT_DIR, inbox_dir, memory_db
from doombot.phrases import PhraseMatcher, default_matcher
from doombot.profiles import Profile
from doombot.voice.eco import MonitorBargeIn
from doombot.voice.speaker import Speaker, montar_voz


def _forzar_utf8() -> None:
    """Windows entrega la consola en cp1252, no en UTF-8.

    Sin esto, escribir "mi portátil" guardaba "mi portÃ¡til" en la memoria: la
    tilde se lee con una codificacion y se escribe con otra. Y no es un
    problema cosmetico, porque ese texto corrupto es el que se vectoriza y el
    que se recupera despues.

    Se reconfiguran los tres flujos con errors="replace" para que un caracter
    que la consola no sepa representar salga como un interrogante en vez de
    tumbar la sesion entera.
    """
    for flujo in (sys.stdin, sys.stdout, sys.stderr):
        # Un flujo redirigido o sin soporte se queda como esta: mejor seguir
        # con la codificacion que haya que no arrancar.
        with contextlib.suppress(AttributeError, OSError, ValueError):
            flujo.reconfigure(encoding="utf-8", errors="replace")


AYUDA = """
Escribe lo que quieras. Se reconocen ordenes:

  recuerda que <algo>      guarda un hecho en la memoria
  recuerda que yo <algo>   guarda un hecho SOBRE TI, siempre presente
  que sabes sobre <algo>   lo busca y responde con lo que encuentre
  olvida eso               borra el ultimo recuerdo guardado
  ejecuta esto <tarea>     delega una tarea real en el agente de acciones
  activa el flujo <nombre>  dispara un workflow de n8n de la lista blanca
  pregunta a claude <algo>  manda esta pregunta a Claude, no al backend por defecto
  apunta el progreso <algo>  anade una nota al vault de Obsidian
  lee el archivo <cual>    lee un fichero del buzon y responde sobre el
  lee lo ultimo que te deje   el mas reciente que hayas soltado ahi
  para                     calla en el acto (con voz activa)
  modo silencioso          deja de hablar hasta "modo normal"

Cualquier otra cosa va al modelo. Ademas:

  /memoria                 lista todo lo guardado
  /borrar                  vacia la memoria
  /entrada                 lista los ficheros del buzon
  /obsidian                relee usuario.md por si lo editaste a mano
  /estado                  que sabe hacer esta instalacion
  /salir                   terminar
"""


def _contexto_usuario(mem: Memory) -> str:
    """Hechos guardados SOBRE el usuario, siempre presentes en el prompt.

    A diferencia de ``Memory.as_context()``, no se filtra por parecido con la
    pregunta: quien habla y que hace es relevante para cualquier conversacion,
    no solo para las que lo mencionan de pasada.
    """
    perfil = mem.all(kind="perfil")
    if not perfil:
        return ""
    lineas = [f"- {r.text}" for r in perfil]
    return "Lo que sabes del usuario, siempre relevante:\n" + "\n".join(lineas)


def _con_contexto(mem: Memory, pregunta: str, *extra: str) -> str:
    bloques = [b for b in (_contexto_usuario(mem), *extra) if b]
    if not bloques:
        return pregunta
    return "\n\n".join([*bloques, f"Pregunta: {pregunta}"])


# Fraccion del contexto del perfil activo que se reserva al historial. El
# resto lo necesitan el prompt del sistema, la pregunta actual y el propio
# hueco para que el modelo responda: darselo todo al historial lo dejaria sin
# sitio para pensar (D-026).
_FRACCION_HISTORIAL = 0.3

# Caracteres por token, a ojo. Mismo tipo de aproximacion que D-019 usa para
# el recorte del buzon: no compensa arrastrar un tokenizador solo para esto,
# y el margen de la fraccion de arriba ya absorbe el error.
_CARACTERES_POR_TOKEN = 4


def _recortar_historial(historial: list[dict[str, str]], num_ctx: int) -> list[dict[str, str]]:
    """Los turnos mas recientes que quepan en el presupuesto de caracteres.

    Se guarda el historial entero en la ``Sesion`` -no cuesta nada mantenerlo,
    ni una conversacion de horas pesa lo que el propio contexto del modelo- y
    se recorta solo aqui, al construir cada peticion. Asi el presupuesto sigue
    al perfil activo (D-004): el portatil recorta antes que el sobremesa sin
    que nadie tenga que acordarse de ajustarlo a mano.
    """
    presupuesto = int(num_ctx * _FRACCION_HISTORIAL * _CARACTERES_POR_TOKEN)
    recortado: list[dict[str, str]] = []
    total = 0
    for turno in reversed(historial):
        total += len(turno["content"])
        if total > presupuesto and recortado:
            break
        recortado.append(turno)
    recortado.reverse()
    return recortado


def _generador(perfil: Profile, cfg: Settings) -> TextGenerator:
    """El TextGenerator que toca segun DOOMBOT_LLM_BACKEND.

    Ollama por defecto (D-009: latencia local, funciona sin conexion).
    Anthropic es el segundo backend, seleccionable sin tocar el resto del
    bucle porque ambos cumplen el mismo contrato.
    """
    if cfg.llm_backend == "anthropic":
        return AnthropicGenerator.from_config(cfg)
    if cfg.llm_backend == "varios":
        # D-034: los modelos de DOOMBOT_MODELOS en fila; si uno falla, el
        # siguiente. Los que no tienen clave se avisan y se saltan.
        from doombot.backends.proveedores import construir_todos
        from doombot.backends.varios import Cadena

        generadores, avisos = construir_todos(cfg)
        for aviso in avisos:
            print(f"  (sin usar: {aviso})", file=sys.stderr)
        if generadores:
            return Cadena(generadores)
        print("  (ningun modelo de DOOMBOT_MODELOS disponible: uso Ollama)", file=sys.stderr)
    return OllamaGenerator.from_profile(perfil, cfg)


@dataclass
class _Motor:
    """Todo lo que necesita una conversacion, montado una vez.

    Lo comparten el modo escrito (``run``) y el hablado (``run_voz``): cambia
    como entra el texto y por donde sale la respuesta, no las piezas.
    """

    perfil: Profile
    cfg: Settings
    gen: TextGenerator
    embedder: FastEmbedder
    agente: ClaudeCodeAgent
    n8n: N8nClient
    matcher: PhraseMatcher
    hud: ServidorHUD
    speaker: Speaker | None
    barge_in: MonitorBargeIn | None
    """None sin `pyaec`/`webrtcvad`, o directamente sin voz (D-027)."""

    def cerrar(self) -> None:
        if self.speaker is not None:
            self.speaker.close()
        self.hud.stop()


def _arrancar() -> _Motor | None:
    """Monta el motor comun, o devuelve None con el motivo ya impreso.

    El orden importa: el LLM es imprescindible y se comprueba primero; el HUD y
    la voz son opcionales y nunca impiden arrancar (ver sus docstrings).
    """
    try:
        perfil = profiles.current()
    except (RuntimeError, OSError) as e:
        print(f"No se pudo determinar el perfil: {e}", file=sys.stderr)
        return None

    cfg = settings()
    gen = _generador(perfil, cfg)
    if not gen.is_available():
        if cfg.llm_backend == "anthropic":
            print("Falta DOOMBOT_ANTHROPIC_API_KEY en .env.", file=sys.stderr)
        else:
            print("Ollama no responde. Arrancalo y vuelve a intentarlo.", file=sys.stderr)
        return None

    if isinstance(gen, OllamaGenerator):
        # Sin esto, la primera pregunta real paga la carga del modelo en VRAM
        # -9-23 s medidos, D-029- justo cuando el usuario ya espera respuesta.
        print("Cargando el modelo en la GPU...")
        t0 = time.perf_counter()
        if gen.precalentar():
            print(f"  listo en {time.perf_counter() - t0:.1f}s")
        else:
            print("  no se pudo precalentar; la primera respuesta ira mas lenta")

    matcher = default_matcher()
    embedder = FastEmbedder.from_config()
    # Construirlo no lanza ningun proceso -eso solo pasa en .run()-, asi que se
    # crea siempre, se use o no en esta sesion.
    agente = ClaudeCodeAgent.from_config(cfg)
    # Mismo criterio: construir el cliente no dispara ningun webhook. Sin
    # DOOMBOT_N8N_BASE_URL, la orden "flow" avisa con un mensaje claro en vez
    # de fallar al arrancar (D-030).
    n8n = N8nClient.from_config(cfg)

    # El HUD es opcional en los dos sentidos: sin el extra `hud` instalado no se
    # intenta siquiera (disponible=False), y si el puerto esta ocupado start()
    # devuelve False sin lanzar. Nada depende de esto.
    hud = ServidorHUD()
    if hud.start():
        print(f"HUD conectado en {hud.url}" if hasattr(hud, "url") else "HUD conectado")
    elif hud.disponible:
        print("  aviso: el WebSocket del HUD no pudo arrancar (puerto ocupado?)", file=sys.stderr)

    # La voz es opcional en cadena: sin `voice-tts`, sin los modelos de Kokoro,
    # o si algo falla al cargarlos, montar_voz devuelve None y se sigue igual.
    voz = montar_voz(hud)
    speaker = voz.speaker if voz is not None else None
    barge_in = voz.barge_in if voz is not None else None
    if speaker is not None:
        print("Voz activa (Kokoro).")
        if barge_in is not None:
            print("Barge-in automatico activo: hablar encima corta a D.O.O.M.")

    print(f"D.O.O.M. · perfil {perfil.name} · {cfg.llm_backend}/{gen.model_name}")
    print(f"memoria en {memory_db()}")
    return _Motor(perfil, cfg, gen, embedder, agente, n8n, matcher, hud, speaker, barge_in)


def run() -> int:
    """Modo escrito: se teclea, se lee, y si hay voz tambien se oye."""
    _forzar_utf8()
    motor = _arrancar()
    if motor is None:
        return 1
    print("Escribe /ayuda para ver las ordenes, /salir para terminar.\n")
    try:
        return _bucle(
            motor.gen,
            motor.embedder,
            motor.agente,
            motor.n8n,
            motor.matcher,
            motor.perfil,
            motor.cfg,
            motor.hud,
            motor.speaker,
        )
    finally:
        motor.cerrar()


_ANCHO_BARRA = 30


def _barra_nivel(nivel: float) -> None:
    """Nivel del microfono en la propia consola, en vivo.

    Sin esto, el modo manos libres no da ninguna pista de si esta oyendo algo
    -el nivel solo llegaba al HUD, que hace falta abrir aparte-. Mismo dibujo
    que ``python -m doombot micro probar``, para que sea la misma referencia
    visual en los dos sitios.
    """
    lleno = int(min(1.0, nivel) * _ANCHO_BARRA)
    print("\r  [" + "#" * lleno + " " * (_ANCHO_BARRA - lleno) + "]", end="", flush=True)


def run_voz(*, manual: bool = False) -> int:
    """Modo manos libres: palabra de activacion, se escucha, se responde hablando.

    Cierra el bucle que hasta ahora estaba en piezas sueltas: el Listener
    (Capa 2) oye y transcribe, ``_atender`` es la misma orquestacion que el
    modo escrito, y el Speaker responde en voz alta. Los estados del Listener
    -escuchando, transcribiendo- y los de la respuesta -pensando, hablando- van
    al mismo HUD, asi que el orbe refleja el turno entero.

    ``manual`` cambia la palabra de activacion por pulsar una tecla: es como se
    depura sin depender de que el detector te oiga.
    """
    _forzar_utf8()
    try:
        from doombot.backends.whisper import WhisperTranscriber
        from doombot.voice import Listener, Microphone, PushToTalk, WakeWord
    except ImportError as e:
        print(f"Falta el stack de voz de entrada: {e}", file=sys.stderr)
        return 1

    motor = _arrancar()
    if motor is None:
        return 1
    if motor.speaker is None:
        print(
            "Sin voz de salida el modo manos libres no tiene sentido: responderia por "
            "pantalla. Instala voice-tts y descarga los modelos (python -m doombot voz-descargar).",
            file=sys.stderr,
        )
        motor.cerrar()
        return 1

    try:
        mic = Microphone.from_settings()
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        motor.cerrar()
        return 1

    detector = PushToTalk() if manual else WakeWord()
    print(f"Microfono: {mic.device_name}")
    print(f"Activacion: {detector.name}")
    print("Di la palabra de activacion y habla. Ctrl+C para salir.\n")

    def nivel_escucha(v: float) -> None:
        motor.hud.set_amplitude(v)
        _barra_nivel(v)

    transcriber = WhisperTranscriber.from_profile(motor.perfil)

    # Los estados de la escucha van al HUD igual que los de la respuesta: el
    # orbe muestra el turno completo, no solo la mitad hablada.
    escucha = Listener(
        mic,
        transcriber,
        detector,
        on_state=lambda e: motor.hud.set_state(str(e)),
        on_level=nivel_escucha,
    )

    def preguntar_voz(pregunta: str) -> str:
        """``Sesion.preguntar`` en modo manos libres: lo dice y escucha la respuesta.

        No hace falta repetir la palabra de activacion -seguimos en el mismo
        turno-, asi que graba directo con el propio microfono en vez de pasar
        por el Listener. Sin voz de salida activa (``motor.speaker is None``)
        este cierre no se usa: ``run_voz`` ya exige altavoz para arrancar.
        """
        motor.hud.set_state("hablando")
        motor.speaker.say(pregunta)  # type: ignore[union-attr]
        motor.speaker.wait(timeout=30)  # type: ignore[union-attr]
        motor.hud.set_state("escuchando")
        with mic.record_until_silence(on_level=nivel_escucha) as grabacion:
            motor.hud.set_state("dormido")
            if grabacion.parece_mudo:
                return ""
            return transcriber.transcribe(grabacion.path)

    try:
        with Memory(motor.embedder) as mem:
            sesion = _montar_sesion(
                motor.gen,
                mem,
                motor.cfg,
                motor.perfil,
                motor.agente,
                motor.n8n,
                motor.hud,
                motor.speaker,
                preguntar=preguntar_voz,
            )
            motor.hud.set_state("dormido")
            for oido in escucha.listen():
                print()  # cierra la linea de la barra de nivel, que no lleva salto
                if oido.vacio:
                    continue
                print(f"tu> {oido.text}")
                if motor.barge_in is not None:
                    motor.barge_in.nueva_respuesta()
                _atender(sesion, motor.matcher, mem, oido.text)
                _esperar_hablando(motor, mic)
    except KeyboardInterrupt:
        print()
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    finally:
        motor.cerrar()
    return 0


def _esperar_hablando(motor: _Motor, mic: Any) -> None:
    """Espera a que D.O.O.M termine de hablar, escuchando por si le interrumpen.

    Sin ``barge_in`` (D-027 no disponible, o sin voz), la espera de siempre:
    a ciegas, con el microfono cerrado. Con el, el microfono se abre YA, en
    paralelo a la respuesta: cada bloque pasa por el cancelador de eco y el
    detector de voz (``MonitorBargeIn``), y en cuanto confirma que es voz de
    verdad -no el eco de la propia voz de D.O.O.M-, corta en el acto
    (``Speaker.stop()``, el mismo mecanismo que la orden "para").
    """
    if motor.speaker is None:
        return
    if motor.barge_in is None:
        motor.speaker.wait(timeout=60)
        return

    import numpy as np

    from doombot.voice.eco import MUESTRAS_BLOQUE

    try:
        with mic.abrir_flujo(MUESTRAS_BLOQUE) as flujo:
            while motor.speaker.is_speaking:
                datos, _ = flujo.read(MUESTRAS_BLOQUE)
                muestras = np.asarray(datos, dtype=np.float32).reshape(-1)
                if motor.barge_in.procesar(muestras):
                    print("  (barge-in: te he oido, callo)")
                    motor.speaker.stop()
                    return
    except BackendError as e:
        # Un fallo del microfono aqui no debe tumbar la respuesta a medias:
        # se sigue sin escuchar, como si no hubiera barge-in.
        print(f"  (barge-in interrumpido: {e})", file=sys.stderr)
        motor.speaker.wait(timeout=60)


def _bucle(  # noqa: C901 - es un despachador, la longitud es la propia lista
    gen: TextGenerator,
    embedder: FastEmbedder,
    agente: ClaudeCodeAgent,
    n8n: N8nClient,
    matcher: PhraseMatcher,
    perfil: Profile,
    cfg: Settings,
    hud: ServidorHUD,
    speaker: Speaker | None,
) -> int:
    with Memory(embedder) as mem:
        sesion = _montar_sesion(gen, mem, cfg, perfil, agente, n8n, hud, speaker)
        hud.set_state("dormido")
        while True:
            try:
                # Se limpian tambien BOM y espacios invisibles: al pegar
                # texto desde otro sitio se cuelan, y "/estado﻿" no
                # coincidiria con ningun comando.
                entrada = input("tu> ").strip().strip("﻿​ ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not entrada:
                continue

            # --- comandos de la propia consola -----------------------------
            if entrada in ("/salir", "/exit", "/q"):
                return 0
            if entrada == "/ayuda":
                print(AYUDA)
                continue
            if entrada == "/estado":
                print(f"  {resumen()}")
                print(f"  {mem.count()} recuerdos guardados")
                continue
            if entrada == "/memoria":
                todos = mem.all()
                if not todos:
                    print("  (vacia)")
                for r in todos:
                    print(f"  [{r.id}] {r.text}")
                continue
            if entrada == "/borrar":
                print(f"  borrados {mem.clear()} recuerdos")
                sesion.ultimo_guardado = None
                continue
            if entrada == "/entrada":
                ficheros = listar_buzon()
                if not ficheros:
                    print(f"  (buzon vacio) deja ficheros en {inbox_dir()}")
                for f in ficheros:
                    print(f"  {f.name}  ({f.stat().st_size / 1024:.1f} kB)")
                continue
            if entrada == "/obsidian":
                n = sincronizar_perfil(mem)
                escribir_perfil(mem)
                print(f"  {n} lineas leidas de {VAULT_DIR / 'usuario.md'}")
                continue

            _atender(sesion, matcher, mem, entrada)


def _montar_sesion(gen, mem, cfg, perfil, agente, n8n, hud, speaker, *, preguntar=input) -> Sesion:
    """Una sola Sesion para toda la conversacion, escrita o hablada.

    Los manejadores la mutan (que se guardo lo ultimo, que se respondio) y el
    bucle no necesita saber cuales de ellos lo hacen. Se saca aqui porque el
    modo texto y el de voz la construyen igual: lo unico que cambia entre
    ellos es de donde sale ``entrada`` y a donde va la respuesta -de eso ya se
    encargan ``preguntar`` y ``responder``-, y el modo escrito le basta con
    ``input`` mientras que el hablado necesita decir la pregunta y escuchar.
    """
    sesion = Sesion(
        gen=gen,
        mem=mem,
        cfg=cfg,
        perfil=perfil,
        agente=agente,
        n8n=n8n,
        speaker=speaker,
        hud=hud,
        responder=lambda prompt: _responder(sesion, prompt),
        con_contexto=lambda pregunta, *extra: _con_contexto(mem, pregunta, *extra),
        preguntar=preguntar,
    )
    return sesion


def _atender(sesion: Sesion, matcher: PhraseMatcher, mem: Memory, texto: str) -> None:
    """Atiende una frase del usuario, venga de teclado o de voz.

    Todo lo que ocurre entre que D.O.O.M recibe algo y termina de responder:
    reconocer si es una orden y despacharla, o pasarlo al modelo con el
    contexto de la memoria. No sabe de donde vino el texto, y esa es justo la
    razon de que exista aparte del bucle: el modo escrito y el hablado lo
    comparten sin duplicar la orquestacion.
    """
    sesion.entrada = texto
    sesion.estado("pensando")
    if sesion.hud is not None:
        sesion.hud.set_caption(None)

    orden = matcher.match(texto)
    if orden:
        if not despachar(sesion, orden):
            # La orden existe pero nadie la implementa todavia. Se dice tal
            # cual: identity.py existe para que D.O.O.M no mienta sobre lo que
            # sabe hacer, y callarlo aqui seria mentir.
            sesion.traza(f"orden {orden.command} ({orden.how}, {orden.confidence})")
            sesion.decir(f"[{orden.command}] entendido, pero aun no puedo hacerlo.")
        _cerrar_turno(sesion)
        return

    contexto = mem.as_context(texto)
    if contexto:
        for linea in contexto.splitlines()[1:]:
            sesion.traza(f"contexto {linea.lstrip('- ')}")
    sesion.responder(sesion.con_contexto(texto, contexto))
    _cerrar_turno(sesion)


def _cerrar_turno(sesion: Sesion) -> None:
    """Marca el fin del turno cuando no hay voz que lo marque sola.

    Con voz, "hablando" lo emite ``_responder`` en el primer trozo y "dormido"
    lo pone el reproductor cuando de verdad se calla (Player.on_idle): ponerlo
    aqui seria prematuro, porque la sintesis sigue en su hilo. Sin voz, el
    turno acaba en cuanto termina el texto, y hay que marcarlo a mano.
    """
    if sesion.speaker is None and sesion.hud is not None:
        sesion.hud.set_caption(sesion.ultima_respuesta or None)
        sesion.hud.set_state("dormido")


def _responder(sesion: Sesion, prompt: str) -> None:
    """Genera en streaming, hablando por el camino si hay voz, y guarda lo dicho.

    Con ``speaker``, es el propio ``Speaker.speak_stream`` quien trocea por
    frases y sintetiza sin esperar al final (ver voice/speaker.py); aqui solo
    hace falta pasarle el chorro y un ``echo`` para seguir imprimiendo. Sin
    voz, el bucle de toda la vida: se acumula porque "repite" necesita la
    respuesta entera, y por streaming solo pasan trozos sueltos.
    """
    print("D.O.O.M> ", end="", flush=True)
    texto = ""
    primero = True

    def pintar(trozo: str) -> None:
        # El "hablando" se emite en el primer trozo, no antes: es cuando el
        # modelo empieza a producir y, con voz, cuando arranca la sintesis.
        # Ponerlo al terminar (como estaba) dejaba el orbe en "pensando"
        # mientras D.O.O.M ya hablaba las primeras frases.
        nonlocal primero
        if primero:
            sesion.estado("hablando")
            primero = False
        print(trozo, end="", flush=True)

    historial = _recortar_historial(sesion.historial, sesion.perfil.llm_num_ctx)
    try:
        trozos = sesion.gen.stream(prompt, system=system_prompt(), historial=historial)
        if sesion.speaker is not None:
            texto = sesion.speaker.speak_stream(trozos, echo=pintar)
        else:
            partes: list[str] = []
            for trozo in trozos:
                partes.append(trozo)
                pintar(trozo)
            texto = "".join(partes)
        print()
    except BackendError as e:
        print(f"\n  {e}", file=sys.stderr)
        sesion.estado("error")
    sesion.ultima_respuesta = texto.strip()

    # Un fallo deja ultima_respuesta vacia: no hay turno real que recordar, y
    # guardarlo dejaria un hueco "assistant": "" en el proximo historial.
    if sesion.ultima_respuesta:
        sesion.historial.append({"role": "user", "content": sesion.entrada})
        sesion.historial.append({"role": "assistant", "content": sesion.ultima_respuesta})
