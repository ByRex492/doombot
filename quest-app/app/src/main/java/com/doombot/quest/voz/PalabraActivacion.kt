package com.doombot.quest.voz

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.nio.FloatBuffer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

/**
 * "Hey jarvis" en las gafas: openWakeWord con onnxruntime-android, el mismo modelo que la palabra
 * de activacion del escritorio (voice/wake.py).
 *
 * Es el mismo flujo que la libreria de Python, paso a paso:
 * 1. cada 80 ms (1280 muestras a 16 kHz) se calcula el espectrograma mel de lo nuevo (con 480
 *    muestras de contexto) y se escala como alli (``x/10 + 2``);
 * 2. con las ultimas 76 filas mel, el modelo de *embedding* da un vector de 96;
 * 3. con los ultimos 16 vectores, el modelo de la palabra da la probabilidad.
 *
 * Los tres modelos (unos 3,5 MB) se bajan la primera vez de la release oficial de openWakeWord y
 * se quedan en las gafas, como hace el escritorio en ``models_dir()``: no van en el repositorio.
 * Escuchar siempre es barato -solo busca un patron acustico- y nada sale de las gafas.
 */
class PalabraActivacion(private val contexto: Context) {
  private val carpeta = File(contexto.filesDir, "openwakeword")
  private var env: OrtEnvironment? = null
  private var mel: OrtSession? = null
  private var emb: OrtSession? = null
  private var palabra: OrtSession? = null
  @Volatile private var parar = false

  val lista: Boolean
    get() = palabra != null

  /** Baja los modelos si faltan y los carga. Devuelve un error legible, o null si todo va bien. */
  suspend fun preparar(): String? =
      withContext(Dispatchers.IO) {
        runCatching {
              carpeta.mkdirs()
              for (m in MODELOS) {
                val f = File(carpeta, m)
                if (!f.exists() || f.length() < 10_000) bajar("$RELEASE/$m", f)
              }
              val e = OrtEnvironment.getEnvironment()
              val op = OrtSession.SessionOptions().apply { setIntraOpNumThreads(1) }
              env = e
              mel = e.createSession(File(carpeta, MODELOS[0]).absolutePath, op)
              emb = e.createSession(File(carpeta, MODELOS[1]).absolutePath, op)
              palabra = e.createSession(File(carpeta, MODELOS[2]).absolutePath, op)
              null
            }
            .getOrElse { "No he podido preparar «hey jarvis»: ${it.message}" }
      }

  fun detener() {
    parar = true
  }

  /**
   * Escucha hasta oir la palabra (devuelve true) o hasta ``detener()`` (false). ``alNivel`` recibe
   * el nivel del micro, por si el orbe quiere respirar con el.
   */
  @SuppressLint("MissingPermission") // el permiso se pide antes (DoomActivity)
  suspend fun esperar(umbral: Float = 0.5f): Boolean =
      withContext(Dispatchers.IO) {
        val e = env ?: return@withContext false
        val m = mel ?: return@withContext false
        val em = emb ?: return@withContext false
        val p = palabra ?: return@withContext false
        parar = false
        val tam = AudioRecord.getMinBufferSize(TASA, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT).coerceAtLeast(TROZO * 4)
        val rec = AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, TASA, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, tam)
        if (rec.state != AudioRecord.STATE_INITIALIZED) return@withContext false
        // Estado de streaming, como AudioFeatures de openWakeWord: audio con contexto, filas mel y vectores.
        var cola = FloatArray(0)
        val filasMel = ArrayList<FloatArray>()
        repeat(76) { filasMel += FloatArray(32) { 1f } }
        val vectores = ArrayList<FloatArray>()
        val corto = ShortArray(TROZO)
        val nombreMel = m.inputNames.first()
        val nombreEmb = em.inputNames.first()
        val nombrePal = p.inputNames.first()
        var seguidas = 0
        rec.startRecording()
        try {
          while (isActive && !parar) {
            var leidas = 0
            while (leidas < TROZO && !parar) {
              val n = rec.read(corto, leidas, TROZO - leidas)
              if (n <= 0) break
              leidas += n
            }
            if (leidas < TROZO) continue
            // 1. Mel de lo nuevo, con 480 muestras de contexto (los valores int16 tal cual, sin normalizar).
            val nuevo = FloatArray(TROZO) { corto[it].toFloat() }
            val entrada = cola + nuevo
            cola = entrada.copyOfRange(maxOf(0, entrada.size - CONTEXTO), entrada.size)
            val filas =
                OnnxTensor.createTensor(e, FloatBuffer.wrap(entrada), longArrayOf(1, entrada.size.toLong())).use { t ->
                  m.run(mapOf(nombreMel to t)).use { r -> aplanar(r[0].value) }
                }
            for (f in filas) filasMel += FloatArray(32) { f[it] / 10f + 2f }
            while (filasMel.size > 120) filasMel.removeAt(0)
            // 2. Un vector con las ultimas 76 filas.
            val ventana = FloatArray(76 * 32)
            filasMel.takeLast(76).forEachIndexed { i, f -> f.copyInto(ventana, i * 32) }
            val vector =
                OnnxTensor.createTensor(e, FloatBuffer.wrap(ventana), longArrayOf(1, 76, 32, 1)).use { t ->
                  em.run(mapOf(nombreEmb to t)).use { r -> aplanar(r[0].value).first() }
                }
            vectores += vector
            while (vectores.size > 16) vectores.removeAt(0)
            if (vectores.size < 16) continue
            // 3. La probabilidad de la palabra con los ultimos 16 vectores.
            val entradaPal = FloatArray(16 * 96)
            vectores.forEachIndexed { i, v -> v.copyInto(entradaPal, i * 96, 0, 96) }
            val prob =
                OnnxTensor.createTensor(e, FloatBuffer.wrap(entradaPal), longArrayOf(1, 16, 96)).use { t ->
                  p.run(mapOf(nombrePal to t)).use { r -> aplanar(r[0].value).first().first() }
                }
            // Dos ventanas seguidas por encima del umbral: un ruido suelto no la dispara.
            seguidas = if (prob >= umbral) seguidas + 1 else 0
            if (seguidas >= 2) return@withContext true
          }
        } catch (ex: Exception) {
          Log.w("DOOM", "palabra de activacion: ${ex.message}")
        } finally {
          rec.stop()
          rec.release()
        }
        false
      }

  fun cerrar() {
    parar = true
    runCatching { mel?.close(); emb?.close(); palabra?.close() }
  }

  companion object {
    private const val TASA = 16_000
    private const val TROZO = 1280 // 80 ms
    private const val CONTEXTO = 160 * 3 // lo que openWakeWord deja de solape entre trozos
    private const val RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
    private val MODELOS = listOf("melspectrogram.onnx", "embedding_model.onnx", "hey_jarvis_v0.1.onnx")

    private fun bajar(url: String, destino: File) {
      val c = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 15_000
        readTimeout = 60_000
        instanceFollowRedirects = true
      }
      try {
        if (c.responseCode !in 200..299) throw java.io.IOException("$url: respuesta ${c.responseCode}")
        val tmp = File(destino.parentFile, destino.name + ".part")
        c.inputStream.use { i -> tmp.outputStream().use { i.copyTo(it) } }
        if (!tmp.renameTo(destino)) throw java.io.IOException("no puedo guardar ${destino.name}")
      } finally {
        c.disconnect()
      }
    }

    /** Las salidas de ONNX son arrays anidados de float: se aplanan a filas de la ultima dimension. */
    @Suppress("UNCHECKED_CAST")
    private fun aplanar(v: Any?): List<FloatArray> =
        when (v) {
          is FloatArray -> listOf(v)
          is Array<*> -> v.flatMap { aplanar(it) }
          else -> emptyList()
        }
  }
}
