package com.doombot.quest.sistema

import com.doombot.quest.util.Texto
import java.net.HttpURLConnection
import java.net.URL

/**
 * Dispara flujos de n8n por webhook, solo los de la lista blanca (port de actions/n8n.py, D-030).
 *
 * Un webhook no tiene modo "plan": en cuanto llega la peticion, el flujo corre de verdad. Por eso
 * la salvaguarda es doble, igual que en escritorio: el nombre dicho tiene que estar en la lista
 * (lo que no esta no dispara nada, solo avisa de cuales si) y antes de dispararlo se confirma de
 * palabra (D-031). D.O.O.M siempre inicia; n8n no puede iniciar nada en las gafas.
 */
object N8n {
  /** La ruta del flujo dicho, comparando sin tildes ni mayusculas (llega de Whisper). */
  fun ruta(nombre: String, flujos: Map<String, String>): String? {
    val buscado = llano(nombre)
    return flujos.entries.firstOrNull { llano(it.key) == buscado }?.value
  }

  fun disponibles(flujos: Map<String, String>): String = flujos.keys.sorted().joinToString().ifEmpty { "(ninguno configurado)" }

  /** Bloquea hasta que n8n responde: es la automatizacion corriendo, no una lectura. */
  fun disparar(base: String, ruta: String): String {
    if (base.isBlank()) return "Error: falta la direccion de n8n (Ajustes, desde el movil)."
    val url = base.trimEnd('/') + "/" + ruta.trimStart('/')
    val c = (URL(url).openConnection() as HttpURLConnection).apply {
      requestMethod = "POST"
      connectTimeout = 5_000
      readTimeout = 300_000
      doOutput = true
      setRequestProperty("Content-Type", "application/json")
    }
    return try {
      c.outputStream.use { it.write("""{"origen":"doom-quest"}""".toByteArray()) }
      val codigo = c.responseCode
      if (codigo !in 200..299) "Error: n8n devolvio $codigo. Comprueba que el webhook exista y este activo."
      else "Flujo disparado. " + (c.inputStream.bufferedReader().use { it.readText() }.take(300))
    } catch (e: java.io.IOException) {
      "Error: no hay respuesta de n8n en $base (${e.message})."
    } finally {
      c.disconnect()
    }
  }

  private fun llano(s: String) = Texto.llano(s).replace(Regex("[^a-z0-9ñ ]"), " ").split(' ').filter { it.isNotEmpty() }.joinToString(" ")
}
