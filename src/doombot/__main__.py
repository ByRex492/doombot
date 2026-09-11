"""Punto de entrada.

    python -m doombot            diagnostico del equipo
    python -m doombot chat       modo interactivo, con memoria y ordenes
    python -m doombot "pregunta" se la lanza al modelo del perfil activo
    python -m doombot micro         lista los microfonos disponibles
    python -m doombot micro probar  graba con el configurado, mide y transcribe
    python -m doombot micro probar 12   fuerza el dispositivo 12
    python -m doombot escuchar      espera la palabra de activacion y transcribe
    python -m doombot escuchar tecla   usa una pulsacion en vez de la palabra

El diagnostico es lo primero que conviene ejecutar al sentarse en una maquina
distinta: dice que perfil ha elegido y por que, que es la pregunta que surge
cuando el asistente se comporta distinto de lo esperado.
"""

from __future__ import annotations

import sys

from doombot import __version__, profiles
from doombot.backends.base import BackendError
from doombot.backends.ollama import OllamaGenerator
from doombot.config import settings
from doombot.identity import resumen, system_prompt
from doombot.paths import PROJECT_ROOT, data_dir

# El prompt se construye a partir de lo que esta instalacion sabe hacer de
# verdad. Ver doombot/identity.py: con uno fijo, el modelo afirmaba haber
# abierto programas y prometia recordar cosas sin haber memoria alguna.
SYSTEM = system_prompt()


def diagnostico() -> int:
    cfg = settings()

    try:
        perfil = profiles.current()
    except (RuntimeError, OSError) as e:
        print(f"No se pudo determinar el perfil: {e}", file=sys.stderr)
        return 1

    vram = profiles.detect_vram_mb()

    print(f"D.O.O.M {__version__}")
    print(f"  proyecto   {PROJECT_ROOT}")
    print(f"  datos      {data_dir()}")
    print()
    print(f"  VRAM       {vram} MiB" if vram else "  VRAM       sin GPU detectada")
    print(f"  perfil     {perfil.name}  ({perfil.description})")
    print()
    print(
        f"  modelo     {perfil.llm_model}  ctx={perfil.llm_num_ctx}  "
        # 0 es el centinela de "que decida Ollama": mostrarlo como 0 hacia
        # leer que no se descarga ninguna capa a la GPU, justo lo contrario.
        f"num_gpu={perfil.llm_num_gpu or 'auto'}"
    )
    print(f"  voz        {perfil.stt_model}  {perfil.stt_device}/{perfil.stt_compute}")
    print(f"  ollama     {cfg.ollama_host}{'  (remoto)' if cfg.is_remote_ollama else ''}")

    gen = OllamaGenerator.from_profile(perfil, cfg)
    if gen.is_available():
        instalados = gen.installed_models()
        tiene = any(m.split(":")[0] == perfil.llm_model.split(":")[0] for m in instalados)
        print(f"  estado     responde, {len(instalados)} modelos instalados")
        if not tiene:
            print(f"             falta {perfil.llm_model}: ollama pull {perfil.llm_model}")
    else:
        print("  estado     sin respuesta (¿Ollama arrancado?)")

    # D-010: dos modelos residentes no caben con Whisper y el TTS. Solo se avisa
    # donde importa: en una GPU pequena nunca entra un segundo modelo.
    import os

    if vram >= 8192 and os.environ.get("OLLAMA_MAX_LOADED_MODELS") != "1":
        print("             falta OLLAMA_MAX_LOADED_MODELS=1 (D-010)")

    print()
    print(f"  sabe hacer {resumen()}")
    return 0


def preguntar(texto: str) -> int:
    """Lanza una pregunta al modelo del perfil activo, en streaming.

    Se usa ``stream`` y no ``generate`` para ver salir el texto segun se
    genera: es la misma via que usara la voz, y sirve para notar de inmediato
    si el modelo se ha quedado repartido entre CPU y GPU.
    """
    try:
        gen = OllamaGenerator.from_profile(profiles.current())
        for trozo in gen.stream(texto, system=SYSTEM):
            print(trozo, end="", flush=True)
        print()
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    except (RuntimeError, OSError) as e:
        print(f"{e}", file=sys.stderr)
        return 1
    return 0


def microfono(probar: bool = False, dispositivo: str | None = None) -> int:
    """Lista los microfonos, o graba con el configurado y lo transcribe.

    Existe porque el fallo mas comun de la capa de voz no esta en el modelo sino
    en el dispositivo: se graba del microfono equivocado, o de uno silenciado, y
    el sintoma es una transcripcion vacia que parece un fallo de Whisper.
    """
    from doombot.voice.capture import Microphone, listar_microfonos

    cfg = settings()
    try:
        if not probar:
            print("Microfonos disponibles:")
            for d in listar_microfonos():
                print(f"  {d}")
            print()
            print(f"  configurado  {cfg.audio_input or '(predeterminado del sistema)'}")
            print("  cambiar      DOOMBOT_AUDIO_INPUT en .env, con parte del nombre")
            return 0

        mic = Microphone(dispositivo) if dispositivo else Microphone.from_settings(cfg)
        print(f"Microfono: {mic.device_name}")
        print("Habla cuando quieras. Se detiene solo al detectar silencio.")
        print()

        ancho = 40

        def barra(nivel: float) -> None:
            lleno = int(nivel * ancho)
            print("\r  " + "#" * lleno + " " * (ancho - lleno), end="", flush=True)

        grabacion = mic.record_until_silence(on_level=barra)
        print(
            f"\r  {grabacion.duration:.1f} s de audio en {grabacion.elapsed:.1f} s reales, "
            f"pico {grabacion.peak:.3f}{' ' * ancho}"
        )

        with grabacion:
            if grabacion.parece_mudo:
                print()
                if grabacion.peak == 0.0:
                    # Cero exacto no es un microfono flojo: es que no llega ni
                    # una muestra distinta de cero. El dispositivo abierto no es
                    # el que capta, aunque su nombre parezca el correcto.
                    print("  Pico 0.000 exacto: ese dispositivo no entrega senal.")
                    print("  Prueba otro indice de la lista:")
                    print("      python -m doombot micro probar 12")
                else:
                    print("  El audio esta practicamente mudo.")
                    print("  Revisa que el microfono no este silenciado y que sea el correcto.")
                return 1

            from doombot.backends.whisper import WhisperTranscriber

            perfil = profiles.current()
            print(f"  transcribiendo con {perfil.stt_model} en {perfil.stt_device}...")
            r = WhisperTranscriber.from_profile(perfil).transcribe_detailed(grabacion.path)
            print()
            print(f"  «{r.text}»")
            print()
            print(f"  idioma {r.language}   RTF {r.rtf:.2f}   {r.elapsed:.1f} s")
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    return 0


def escuchar(manual: bool = False) -> int:
    """Bucle de voz en modo diagnostico: imprime estados y lo que oye.

    Es el comando con el que se valida la Capa 2 en un equipo con microfono. Con
    ``manual`` se dispara pulsando una tecla en vez de diciendo la palabra, que
    es como se depura sin depender de que el detector te oiga.
    """
    from doombot.backends.whisper import WhisperTranscriber
    from doombot.voice import Listener, Microphone, PushToTalk, WakeWord

    try:
        perfil = profiles.current()
        mic = Microphone.from_settings()
        detector = PushToTalk() if manual else WakeWord()

        print(f"Microfono: {mic.device_name}")
        print(f"Activacion: {detector.name}")
        print("Ctrl+C para salir.\n")

        escucha = Listener(
            mic,
            WhisperTranscriber.from_profile(perfil),
            detector,
            on_state=lambda e: print(f"  [{e}]"),
        )
        for oido in escucha.listen():
            print(f"  «{oido.text}»")
            print(f"  ({oido.seconds:.1f} s, pico {oido.peak:.2f}, {oido.detection.word})\n")
    except KeyboardInterrupt:
        print()
    except BackendError as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] in ("micro", "microfono"):
        probar = len(args) > 1 and args[1] in ("probar", "test")
        return microfono(probar=probar, dispositivo=args[2] if len(args) > 2 else None)
    if args and args[0] in ("escuchar", "oir"):
        return escuchar(manual=len(args) > 1 and args[1] in ("tecla", "manual"))
    if args and args[0] in ("chat", "-i", "--interactivo"):
        from doombot.chat import run

        return run()
    if args and args[0] in ("voz", "voice"):
        # El bucle manos libres: palabra de activacion -> escucha -> LLM -> voz.
        # "voz tecla" dispara pulsando en vez de diciendo la palabra, para
        # depurar sin depender de que el detector oiga.
        from doombot.chat import run_voz

        return run_voz(manual=len(args) > 1 and args[1] in ("tecla", "manual"))
    if args and args[0] in ("voz-descargar", "descargar-voz"):
        from doombot.paths import models_dir
        from doombot.tts.download import asegurar_modelos

        asegurar_modelos(models_dir() / "kokoro")
        return 0
    if args:
        return preguntar(" ".join(args))
    return diagnostico()


if __name__ == "__main__":
    raise SystemExit(main())
