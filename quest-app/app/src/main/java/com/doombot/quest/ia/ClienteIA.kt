package com.doombot.quest.ia

import android.util.Base64
import com.doombot.quest.datos.Almacen
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

/**
 * Un proveedor con API compatible con OpenAI. Port de backends/proveedores.py.
 *
 * Aqui solo lo estable: la URL y donde se crea la clave. Que modelos hay se pregunta en tiempo de
 * ejecucion a ``GET /models``; ``sugeridos`` solo sirve para preseleccionar uno de esa lista, si
 * sigue existiendo, cuando el usuario aun no ha elegido.
 */
data class Proveedor(
    val id: String,
    val titulo: String,
    val baseUrl: String,
    val alta: String,
    val sugeridos: List<String> = emptyList(),
    val sttSugerido: String = "",
    val visionSugerido: String = "",
)

object Catalogo {
  val base =
      listOf(
          Proveedor("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys",
              listOf("openai/gpt-oss-120b", "qwen/qwen3.8-27b"), "whisper-large-v3-turbo",
              "meta-llama/llama-4-scout-17b-16e-instruct"),
          Proveedor("nvidia", "NVIDIA", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com",
              listOf("nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-ultra-550b-a55b")),
          Proveedor("gemini", "Gemini (Google)", "https://generativelanguage.googleapis.com/v1beta/openai",
              "https://aistudio.google.com/apikey", listOf("gemini-3.5-flash-lite", "gemini-3.8-flash"),
              visionSugerido = "gemini-3.5-flash-lite"),
          // gpt-oss-120b:free dejo de existir en octubre de 2026; este si, con herramientas (15/10/2026).
          Proveedor("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/keys",
              listOf("nvidia/nemotron-3-super-120b-a12b:free")),
          Proveedor("mistral", "Mistral", "https://api.mistral.ai/v1", "https://console.mistral.ai/api-keys"),
      )

  fun todos(cfg: Almacen.Config): List<Proveedor> =
      base + cfg.propios.map { (id, url) -> Proveedor(id, id, url.trimEnd('/'), "") }

  fun partir(entrada: String): Pair<String, String> {
    val i = entrada.indexOf(':')
    return if (i < 0) entrada.trim().lowercase() to "" else entrada.substring(0, i).trim().lowercase() to entrada.substring(i + 1).trim()
  }
}

/** El proveedor se ha quedado sin cuota gratuita, o esta saturado: se prueba el siguiente. */
class LimiteAlcanzado(mensaje: String) : IOException(mensaje)

class ClienteIA(private val almacen: Almacen) : LlmProvider, SttProvider, VisionProvider, TtsProvider {

  private suspend fun proveedor(id: String): Pair<Proveedor, String> {
    val cfg = almacen.config()
    val p = Catalogo.todos(cfg).firstOrNull { it.id == id } ?: throw IOException("proveedor desconocido: $id")
    val clave = almacen.clave(id)
    if (clave.isBlank()) throw IOException("falta la clave de ${p.titulo} (se pone en Ajustes, desde el movil)")
    return p to clave
  }

  /** Los modelos que ofrece ahora mismo el proveedor. Nunca una lista fija. */
  suspend fun modelos(id: String): List<String> {
    val (p, clave) = proveedor(id)
    val r = peticion("GET", "${p.baseUrl}/models", clave, null)
    val datos = JSONObject(r).optJSONArray("data") ?: JSONArray()
    return (0 until datos.length()).map { datos.getJSONObject(it).getString("id").removePrefix("models/") }.sorted()
  }

  override suspend fun chat(entrada: String, mensajes: JSONArray, herramientas: JSONArray?): JSONObject {
    val (id, modelo) = Catalogo.partir(entrada)
    val (p, clave) = proveedor(id)
    val cuerpo = JSONObject().put("model", modelo).put("messages", mensajes).put("temperature", 0.4)
    if (herramientas != null && herramientas.length() > 0) cuerpo.put("tools", herramientas)
    val r = peticion("POST", "${p.baseUrl}/chat/completions", clave, cuerpo.toString().toByteArray(), "application/json")
    return normalizar(JSONObject(r).getJSONArray("choices").getJSONObject(0).getJSONObject("message"))
  }

  /**
   * Chat con ``stream: true`` (D-021): el texto llega a trozos y ``alTexto`` lo recibe segun llega,
   * para que la voz empiece con la primera frase. Las tool_calls tambien llegan a trozos (por
   * ``index``) y aqui se recomponen. Devuelve el mensaje completo, igual que ``chat``.
   */
  override suspend fun chatEnStreaming(
      entrada: String, mensajes: JSONArray, herramientas: JSONArray?, alTexto: (String) -> Unit,
  ): JSONObject =
      withContext(Dispatchers.IO) {
        val (id, modelo) = Catalogo.partir(entrada)
        val (p, clave) = proveedor(id)
        val cuerpo = JSONObject().put("model", modelo).put("messages", mensajes).put("temperature", 0.4).put("stream", true)
        if (herramientas != null && herramientas.length() > 0) cuerpo.put("tools", herramientas)
        val c = conexion("POST", "${p.baseUrl}/chat/completions", clave, "application/json")
        try {
          c.outputStream.use { it.write(cuerpo.toString().toByteArray()) }
          comprobar(c)
          val texto = StringBuilder()
          val llamadas = sortedMapOf<Int, Triple<StringBuilder, StringBuilder, StringBuilder>>() // id, nombre, args
          val filtro = FiltroPensamiento()
          c.inputStream.bufferedReader().useLines { lineas ->
            for (linea in lineas) {
              if (!linea.startsWith("data:")) continue
              val dato = linea.removePrefix("data:").trim()
              if (dato == "[DONE]") break
              val j = runCatching { JSONObject(dato) }.getOrNull() ?: continue
              val delta = j.optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("delta") ?: continue
              if (!delta.isNull("content")) {
                val trozo = filtro.pasar(delta.optString("content"))
                if (trozo.isNotEmpty()) {
                  texto.append(trozo)
                  alTexto(trozo)
                }
              }
              val tcs = delta.optJSONArray("tool_calls") ?: continue
              for (i in 0 until tcs.length()) {
                val tc = tcs.getJSONObject(i)
                val n = tc.optInt("index", i)
                val acc = llamadas.getOrPut(n) { Triple(StringBuilder(), StringBuilder(), StringBuilder()) }
                if (!tc.isNull("id")) acc.first.append(tc.optString("id"))
                tc.optJSONObject("function")?.let { f ->
                  if (!f.isNull("name")) acc.second.append(f.optString("name"))
                  if (!f.isNull("arguments")) acc.third.append(f.optString("arguments"))
                }
              }
            }
          }
          val mensaje = JSONObject().put("role", "assistant").put("content", texto.toString().trim())
          if (llamadas.isNotEmpty()) {
            val tc = JSONArray()
            llamadas.values.forEachIndexed { i, (cid, nombre, args) ->
              tc.put(
                  JSONObject()
                      .put("id", cid.toString().ifEmpty { "llamada_$i" })
                      .put("type", "function")
                      .put("function", JSONObject().put("name", nombre.toString()).put("arguments", args.toString().ifBlank { "{}" })))
            }
            mensaje.put("tool_calls", tc)
          }
          mensaje
        } finally {
          c.disconnect()
        }
      }

  /** Voz a texto (Whisper por API). ``wav`` es un WAV de 16 kHz mono. */
  override suspend fun transcribir(entrada: String, wav: ByteArray): String {
    val (id, modelo) = Catalogo.partir(entrada)
    val (p, clave) = proveedor(id)
    val limite = "----doom" + System.nanoTime()
    val cuerpo = ByteArrayOutputStream()
    fun campo(nombre: String, valor: String) {
      cuerpo.write("--$limite\r\nContent-Disposition: form-data; name=\"$nombre\"\r\n\r\n$valor\r\n".toByteArray())
    }
    campo("model", modelo)
    campo("language", "es")
    campo("response_format", "json")
    cuerpo.write("--$limite\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voz.wav\"\r\nContent-Type: audio/wav\r\n\r\n".toByteArray())
    cuerpo.write(wav)
    cuerpo.write("\r\n--$limite--\r\n".toByteArray())
    val r = peticion("POST", "${p.baseUrl}/audio/transcriptions", clave, cuerpo.toByteArray(), "multipart/form-data; boundary=$limite")
    return JSONObject(r).optString("text").trim()
  }

  /** Fase 3: una pregunta sobre lo que ve la camara, a un modelo con vision. */
  override suspend fun mirar(entrada: String, pregunta: String, jpeg: ByteArray): String {
    val imagen = "data:image/jpeg;base64," + Base64.encodeToString(jpeg, Base64.NO_WRAP)
    val contenido =
        JSONArray()
            .put(JSONObject().put("type", "text").put("text", pregunta))
            .put(JSONObject().put("type", "image_url").put("image_url", JSONObject().put("url", imagen)))
    val mensajes =
        JSONArray()
            .put(JSONObject().put("role", "system").put("content",
                "Describes lo que ve la camara de unas gafas de realidad mixta, en espanol, breve y concreto. " +
                    "Si hay texto, transcribelo. Si no estas seguro de algo, dilo."))
            .put(JSONObject().put("role", "user").put("content", contenido))
    return chat(entrada, mensajes, null).optString("content").trim()
  }

  /** TTS por API (opcional): ``/audio/speech`` de un proveedor compatible. Devuelve WAV. */
  override suspend fun sintetizar(entrada: String, voz: String, texto: String): ByteArray {
    val (id, modelo) = Catalogo.partir(entrada)
    val (p, clave) = proveedor(id)
    val cuerpo = JSONObject().put("model", modelo).put("input", texto).put("response_format", "wav")
    if (voz.isNotBlank()) cuerpo.put("voice", voz)
    return withContext(Dispatchers.IO) {
      val c = conexion("POST", "${p.baseUrl}/audio/speech", clave, "application/json")
      try {
        c.outputStream.use { it.write(cuerpo.toString().toByteArray()) }
        comprobar(c)
        c.inputStream.use { it.readBytes() }
      } finally {
        c.disconnect()
      }
    }
  }

  /** Una peticion minima para saber si la clave funciona. */
  suspend fun probar(id: String): String =
      runCatching { "Funciona: ${modelos(id).size} modelos disponibles." }.getOrElse { "No funciona: ${it.message}" }

  // -- interno ---------------------------------------------------------------------------------
  private fun normalizar(mensaje: JSONObject): JSONObject {
    // Con tool_calls, content suele venir a null, y org.json lo convierte en el texto "null".
    if (mensaje.isNull("content")) mensaje.put("content", "")
    // Algunos modelos razonan entre <think>...</think>: eso no es para el usuario.
    val texto = mensaje.optString("content", "")
    if (texto.contains("</think>")) mensaje.put("content", texto.substringAfterLast("</think>").trim())
    return mensaje
  }

  private fun conexion(metodo: String, url: String, clave: String, tipo: String): HttpURLConnection =
      (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = metodo
        connectTimeout = 15_000
        readTimeout = 60_000
        setRequestProperty("Authorization", "Bearer $clave")
        if (metodo == "POST") {
          doOutput = true
          setRequestProperty("Content-Type", tipo)
        }
      }

  private fun comprobar(c: HttpURLConnection) {
    val codigo = c.responseCode
    if (codigo in 200..299) return
    val texto = c.errorStream?.bufferedReader()?.use { it.readText() } ?: ""
    when (codigo) {
      429, 503 -> throw LimiteAlcanzado("sin cuota por ahora")
      401, 403 -> throw IOException("la clave no vale ($codigo)")
      else -> throw IOException("respuesta $codigo: ${texto.take(160)}")
    }
  }

  private suspend fun peticion(metodo: String, url: String, clave: String, cuerpo: ByteArray?, tipo: String = ""): String =
      withContext(Dispatchers.IO) {
        val c = conexion(if (cuerpo != null) metodo else "GET", url, clave, tipo)
        try {
          if (cuerpo != null) c.outputStream.use { it.write(cuerpo) }
          comprobar(c)
          c.inputStream.bufferedReader().use { it.readText() }
        } finally {
          c.disconnect()
        }
      }
}

/**
 * Quita lo que un modelo razona entre ``<think>`` y ``</think>`` aunque llegue partido entre
 * trozos del streaming: eso no se dice en voz alta.
 */
class FiltroPensamiento {
  private var dentro = false
  private val pendiente = StringBuilder()

  fun pasar(trozo: String): String {
    pendiente.append(trozo)
    val salida = StringBuilder()
    while (true) {
      val s = pendiente.toString()
      if (dentro) {
        val fin = s.indexOf("</think>")
        if (fin < 0) {
          // Puede que "</think>" este a medias al final: se guarda solo esa cola.
          pendiente.setLength(0)
          pendiente.append(s.takeLast(7))
          return salida.toString()
        }
        dentro = false
        pendiente.setLength(0)
        pendiente.append(s.substring(fin + 8))
      } else {
        val ini = s.indexOf("<think>")
        if (ini < 0) {
          // Si el final podria ser el principio de "<think>", se espera al siguiente trozo.
          val corte = (1..6).firstOrNull { s.endsWith("<think>".take(it)) }?.let { s.length - it } ?: s.length
          salida.append(s, 0, corte)
          pendiente.setLength(0)
          pendiente.append(s.substring(corte))
          return salida.toString()
        }
        salida.append(s, 0, ini)
        dentro = true
        pendiente.setLength(0)
        pendiente.append(s.substring(ini + 7))
      }
    }
  }
}
