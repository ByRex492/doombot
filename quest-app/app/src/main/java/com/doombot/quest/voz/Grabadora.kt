package com.doombot.quest.voz

import android.annotation.SuppressLint
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.doombot.quest.Doom
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sqrt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

/**
 * Graba una frase del microfono de las gafas y la devuelve como WAV de 16 kHz mono.
 *
 * Se corta sola: tras haber oido voz, 1,2 s de silencio cierran la frase (un VAD por energia, sin
 * modelo). Mientras graba, empuja la amplitud al orbe para que "escuche" de verdad.
 */
class Grabadora {
  @Volatile private var parar = false

  fun detener() {
    parar = true
  }

  @SuppressLint("MissingPermission") // el permiso se pide antes de llamar (DoomActivity)
  suspend fun frase(maxMs: Long = 15_000): ByteArray? =
      withContext(Dispatchers.IO) {
        parar = false
        val tam = AudioRecord.getMinBufferSize(TASA, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT).coerceAtLeast(4096)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, TASA, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, tam)
        if (rec.state != AudioRecord.STATE_INITIALIZED) return@withContext null
        val pcm = ByteArrayOutputStream()
        val trozo = ShortArray(TASA / 20) // 50 ms
        var huboVoz = false
        var silencioMs = 0L
        val inicio = System.currentTimeMillis()
        rec.startRecording()
        try {
          while (isActive && !parar && System.currentTimeMillis() - inicio < maxMs) {
            val n = rec.read(trozo, 0, trozo.size)
            if (n <= 0) continue
            var suma = 0.0
            val bb = ByteBuffer.allocate(n * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (i in 0 until n) {
              suma += trozo[i] * trozo[i].toDouble()
              bb.putShort(trozo[i])
            }
            pcm.write(bb.array())
            val rms = sqrt(suma / n) / 32768.0
            Doom.amplitud = (rms * 9).toFloat().coerceIn(0f, 1f)
            if (rms > UMBRAL) {
              huboVoz = true
              silencioMs = 0
            } else if (huboVoz) {
              silencioMs += 50
              if (silencioMs >= 1200) break
            }
          }
        } finally {
          rec.stop()
          rec.release()
          Doom.amplitud = 0f
        }
        if (!huboVoz) null else wav(pcm.toByteArray())
      }

  private fun wav(pcm: ByteArray): ByteArray {
    val b = ByteBuffer.allocate(44 + pcm.size).order(ByteOrder.LITTLE_ENDIAN)
    b.put("RIFF".toByteArray()).putInt(36 + pcm.size).put("WAVE".toByteArray())
    b.put("fmt ".toByteArray()).putInt(16).putShort(1).putShort(1).putInt(TASA).putInt(TASA * 2).putShort(2).putShort(16)
    b.put("data".toByteArray()).putInt(pcm.size).put(pcm)
    return b.array()
  }

  companion object {
    private const val TASA = 16_000
    private const val UMBRAL = 0.02
  }
}
