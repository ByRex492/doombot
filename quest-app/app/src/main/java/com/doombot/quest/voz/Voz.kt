package com.doombot.quest.voz

import android.content.Context
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import com.doombot.quest.Doom
import com.doombot.quest.EstadoOrbe
import com.doombot.quest.TipoLinea
import java.util.Locale
import kotlin.math.abs
import kotlin.math.sin
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * La voz de D.O.O.M: el TextToSpeech de Android, gratis y sin conexion.
 *
 * Horizon OS puede no traer ningun motor de voz instalado. Entonces no se rompe nada: se avisa una
 * vez y las respuestas siguen en subtitulos. Mientras habla, el orbe recibe una envolvente
 * silabica simulada, porque el TTS de Android no da la amplitud real (igual que el modo "tts" del
 * prototipo del HUD).
 */
class Voz(contexto: Context, private val ambito: CoroutineScope) {
  private var lista = false
  private var avisado = false
  private var envolvente: Job? = null

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
          override fun onStart(id: String?) {
            Doom.estado(EstadoOrbe.HABLANDO)
            empezarEnvolvente()
          }

          override fun onDone(id: String?) = terminar()

          @Deprecated("Deprecated in Java")
          override fun onError(id: String?) = terminar()
        })
  }

  fun hablar(texto: String) {
    if (!lista) {
      if (!avisado) {
        avisado = true
        Doom.anotar(TipoLinea.AVISO, "Estas gafas no tienen voz de sistema en español: respondo en subtitulos.")
      }
      // Sin voz, el orbe "habla" lo que se tarda en leer.
      Doom.estado(EstadoOrbe.HABLANDO)
      empezarEnvolvente()
      ambito.launch {
        delay((texto.length * 55L).coerceIn(1500, 9000))
        terminar()
      }
      return
    }
    tts.speak(texto, TextToSpeech.QUEUE_FLUSH, null, "doom")
  }

  /** La capa refleja: "para" corta al instante, sin pasar por ningun modelo. */
  fun callar() {
    tts.stop()
    terminar()
  }

  private fun empezarEnvolvente() {
    envolvente?.cancel()
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

  private fun terminar() {
    envolvente?.cancel()
    Doom.enUi {
      Doom.amplitud = 0f
      if (Doom.orbe == EstadoOrbe.HABLANDO) Doom.orbe = EstadoOrbe.DORMIDO
    }
  }

  fun cerrar() {
    tts.shutdown()
  }
}
