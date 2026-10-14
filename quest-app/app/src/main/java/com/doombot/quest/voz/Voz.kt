package com.doombot.quest.voz

import android.content.Context
import android.media.MediaPlayer
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.doombot.quest.Doom
import com.doombot.quest.EstadoOrbe
import com.doombot.quest.TipoLinea
import com.doombot.quest.ia.TtsProvider
import java.io.File
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.abs
import kotlin.math.sin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * La voz de D.O.O.M, por frases (D-021): cada frase entra en una cola y suena en cuanto la anterior
 * acaba, mientras el modelo sigue escribiendo.
 *
 * Dos motores, elegidos en Ajustes:
 * - el TextToSpeech de Android (por defecto): gratis y sin conexion. Horizon OS puede no traer voz
 *   en español; entonces se avisa una vez y se responde en subtitulos.
 * - TTS por API (opcional, ``proveedor:modelo`` y voz): ``/audio/speech`` de un proveedor compatible.
 *
 * Mientras habla, el orbe recibe una envolvente silabica simulada (ni el TTS de Android ni el
 * reproductor dan la amplitud real, igual que el modo "tts" del prototipo del HUD).
 */
class Voz(private val contexto: Context, private val ambito: CoroutineScope, private val apiTts: TtsProvider) {
  private var lista = false
  private var avisado = false
  private var envolvente: Job? = null
  private val pendientes = AtomicInteger(0)
  private var cola = Channel<String>(Channel.UNLIMITED)
  private var reproductor: Job? = null
  private var mp: MediaPlayer? = null
  /** ``proveedor:modelo`` del TTS por API; vacio = TextToSpeech de Android. */
  var motorApi = ""
  var vozApi = ""
  /** Se llama al encolar cada frase (el Controlador para la escucha de "hey jarvis"). */
  var alHablar: (() -> Unit)? = null

  private val tts: TextToSpeech =
      TextToSpeech(contexto) { estado ->
        if (estado == TextToSpeech.SUCCESS) {
          val r = tts.setLanguage(Locale("es", "ES"))
          lista = r != TextToSpeech.LANG_MISSING_DATA && r != TextToSpeech.LANG_NOT_SUPPORTED
        }
      }

  init {
    tts.setOnUtteranceProgressListener(
        object : UtteranceProgressListener() {
          override fun onStart(id: String?) = empezar()

          override fun onDone(id: String?) = unaMenos()

          @Deprecated("Deprecated in Java")
          override fun onError(id: String?) = unaMenos()
        })
    arrancarReproductor()
  }

  /** Toda la respuesta de una vez (lo que no viene por streaming: ordenes, avisos). */
  fun hablar(texto: String) {
    callar()
    frase(texto)
  }

  /** Una frase a la cola. */
  fun frase(texto: String) {
    val t = texto.trim()
    if (t.isEmpty()) return
    alHablar?.invoke()
    pendientes.incrementAndGet()
    when {
      motorApi.isNotBlank() -> cola.trySend(t)
      lista -> tts.speak(t, TextToSpeech.QUEUE_ADD, null, "doom" + System.nanoTime())
      else -> sinVoz(t)
    }
  }

  /** La capa refleja y el barge-in: "para" corta al instante, sin pasar por ningun modelo. */
  fun callar() {
    tts.stop()
    cola.cancel()
    cola = Channel(Channel.UNLIMITED)
    reproductor?.cancel()
    runCatching { mp?.stop() }
    runCatching { mp?.release() }
    mp = null
    arrancarReproductor()
    pendientes.set(0)
    terminar()
  }

  private fun sinVoz(texto: String) {
    if (!avisado) {
      avisado = true
      Doom.anotar(TipoLinea.AVISO, "Estas gafas no tienen voz de sistema en español: respondo en subtitulos.")
    }
    // Sin voz, el orbe "habla" lo que se tarda en leer.
    empezar()
    ambito.launch {
      delay((texto.length * 55L).coerceIn(1200, 9000))
      unaMenos()
    }
  }

  /** El TTS por API: una frase detras de otra, cada una sintetizada mientras suena la anterior. */
  private fun arrancarReproductor() {
    val miCola = cola
    reproductor =
        ambito.launch(Dispatchers.IO) {
          for (frase in miCola) {
            val wav =
                runCatching { apiTts.sintetizar(motorApi, vozApi, frase) }
                    .getOrElse {
                      Doom.anotar(TipoLinea.AVISO, "TTS por API no responde (${it.message}): uso la voz de las gafas.")
                      motorApi = ""
                      null
                    }
            if (wav == null) {
              if (lista) tts.speak(frase, TextToSpeech.QUEUE_ADD, null, "doom" + System.nanoTime()) else sinVoz(frase)
              continue
            }
            val f = File.createTempFile("doom", ".wav", contexto.cacheDir).apply { writeBytes(wav) }
            empezar()
            suspendCancellableCoroutine { cont ->
              val p = MediaPlayer()
              mp = p
              p.setDataSource(f.absolutePath)
              p.setOnCompletionListener { cont.resume(Unit) }
              p.setOnErrorListener { _, _, _ -> cont.resume(Unit); true }
              cont.invokeOnCancellation { runCatching { p.stop() } }
              p.prepare()
              p.start()
            }
            runCatching { mp?.release() }
            mp = null
            f.delete()
            unaMenos()
          }
        }
  }

  private fun empezar() {
    Doom.estado(EstadoOrbe.HABLANDO)
    if (envolvente?.isActive == true) return
    envolvente =
        ambito.launch(Dispatchers.Main) {
          var t = 0.0
          while (isActive) {
            t += 0.05
            Doom.amplitud = (0.35 + 0.55 * abs(sin(t * 7.0) * sin(t * 2.3))).toFloat()
            delay(50)
          }
        }
  }

  private fun unaMenos() {
    if (pendientes.decrementAndGet() <= 0) {
      pendientes.set(0)
      terminar()
    }
  }

  /** ¿Queda algo por decir? Para no volver a escuchar "hey jarvis" con su propia voz. */
  val hablando: Boolean
    get() = pendientes.get() > 0

  private fun terminar() {
    envolvente?.cancel()
    Doom.enUi {
      Doom.amplitud = 0f
      if (Doom.orbe == EstadoOrbe.HABLANDO) Doom.orbe = EstadoOrbe.DORMIDO
    }
  }

  fun cerrar() {
    callar()
    tts.shutdown()
  }
}
