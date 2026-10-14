package com.doombot.quest.ia

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
)

object Catalogo {
  val base =
      listOf(
          Proveedor("groq", "Groq", "https://api.groq.com/openai/v1", "https://console.groq.com/keys",
              listOf("openai/gpt-oss-120b", "qwen/qwen3.8-27b"), "whisper-large-v3-turbo"),
          Proveedor("nvidia", "NVIDIA", "https://integrate.api.nvidia.com/v1", "https://build.nvidia.com",
              listOf("nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-ultra-550b-a55b")),
          Proveedor("gemini", "Gemini (Google)", "https://generativelanguage.googleapis.com/v1beta/openai",
              "https://aistudio.google.com/apikey", listOf("gemini-3.5-flash-lite", "gemini-3.8-flash")),
          Proveedor("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "https://openrouter.ai/keys"),
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

class ClienteIA(private val almacen: Almacen) {

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

  /** Un turno de chat; devuelve el ``message`` de la respuesta (texto y, si hay, tool_calls). */
  suspend fun chat(entrada: String, mensajes: JSONArray, herramientas: JSONArray?): JSONObject {
    val (id, modelo) = Catalogo.partir(entrada)
    val (p, clave) = proveedor(id)
    val cuerpo = JSONObject().put("model", modelo).put("messages", mensajes).put("temperature", 0.4)
    if (herramientas != null && herramientas.length() > 0) cuerpo.put("tools", herramientas)
    val r = peticion("POST", "${p.baseUrl}/chat/completions", clave, cuerpo.toString().toByteArray(), "application/json")
    val mensaje = JSONObject(r).getJSONArray("choices").getJSONObject(0).getJSONObject("message")
    // Algunos modelos razonan entre <think>...</think>: eso no es para el usuario.
    val texto = mensaje.optString("content", "")
    if (texto.contains("</think>")) mensaje.put("content", texto.substringAfterLast("</think>").trim())
    return mensaje
  }

  /** Voz a texto (Whisper por API). ``wav`` es un WAV de 16 kHz mono. */
  suspend fun transcribir(entrada: String, wav: ByteArray): String {
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

  /** Una peticion minima para saber si la clave funciona. */
  suspend fun probar(id: String): String =
      runCatching { "Funciona: ${modelos(id).size} modelos disponibles." }.getOrElse { "No funciona: ${it.message}" }

  private suspend fun peticion(metodo: String, url: String, clave: String, cuerpo: ByteArray?, tipo: String = ""): String =
      withContext(Dispatchers.IO) {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
          requestMethod = metodo
          connectTimeout = 15_000
          readTimeout = 60_000
          setRequestProperty("Authorization", "Bearer $clave")
          if (cuerpo != null) {
            doOutput = true
            setRequestProperty("Content-Type", tipo)
          }
        }
        try {
          if (cuerpo != null) c.outputStream.use { it.write(cuerpo) }
          val codigo = c.responseCode
          val texto = (if (codigo in 200..299) c.inputStream else c.errorStream)?.bufferedReader()?.use { it.readText() } ?: ""
          when {
            codigo in 200..299 -> texto
            codigo == 429 || codigo == 503 -> throw LimiteAlcanzado("sin cuota por ahora")
            codigo == 401 || codigo == 403 -> throw IOException("la clave no vale ($codigo)")
            else -> throw IOException("respuesta $codigo: ${texto.take(160)}")
          }
        } finally {
          c.disconnect()
        }
      }
}
