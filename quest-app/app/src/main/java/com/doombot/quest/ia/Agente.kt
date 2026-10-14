package com.doombot.quest.ia

import com.doombot.quest.Doom
import com.doombot.quest.TipoLinea
import com.doombot.quest.datos.Almacen
import com.doombot.quest.sistema.Acciones
import java.io.IOException
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

/**
 * El agente de las gafas: el modelo decide y las herramientas actuan (como agent/bucle.py).
 *
 * Mas pequeño que el de escritorio a proposito. Las herramientas son las que tienen sentido en unas
 * gafas -abrir apps y enlaces, el volumen, la bateria- y ninguna borra ni envia nada, asi que no
 * hace falta confirmacion. Los modelos van en cadena (D-034): si uno se queda sin cuota, el
 * siguiente, avisando con una linea tranquila y no con un error (D-039).
 */
class Agente(private val almacen: Almacen, private val ia: ClienteIA, private val acciones: Acciones) {

  private val historial = JSONArray()
  private val apartados = HashMap<String, Long>()

  fun olvidar() {
    while (historial.length() > 0) historial.remove(0)
  }

  suspend fun responder(pedido: String): String {
    val cfg = almacen.config()
    if (cfg.cadena.isEmpty()) {
      return "Aun no tengo ningun modelo, Mi Señor. Abra Ajustes y configureme desde el movil."
    }
    historial.put(JSONObject().put("role", "user").put("content", pedido))
    recortar()
    repeat(MAX_PASOS) {
      val mensajes = JSONArray().put(JSONObject().put("role", "system").put("content", sistema(cfg)))
      for (i in 0 until historial.length()) mensajes.put(historial.get(i))
      val mensaje = enCadena(cfg.cadena, mensajes)
      val llamadas = mensaje.optJSONArray("tool_calls")
      if (llamadas == null || llamadas.length() == 0) {
        val texto = mensaje.optString("content").trim().ifBlank { "(sin respuesta)" }
        historial.put(JSONObject().put("role", "assistant").put("content", texto))
        return texto
      }
      historial.put(mensaje)
      for (i in 0 until llamadas.length()) {
        val ll = llamadas.getJSONObject(i)
        val f = ll.getJSONObject("function")
        val args = runCatching { JSONObject(f.optString("arguments").ifBlank { "{}" }) }.getOrDefault(JSONObject())
        val salida = acciones.ejecutar(f.getString("name"), args)
        historial.put(
            JSONObject().put("role", "tool").put("tool_call_id", ll.optString("id")).put("content", salida))
      }
    }
    return "He llegado al limite de pasos sin terminar. Digame como sigo."
  }

  private suspend fun enCadena(cadena: List<String>, mensajes: JSONArray): JSONObject {
    val ahora = System.currentTimeMillis()
    val orden = cadena.sortedBy { if ((apartados[it] ?: 0L) > ahora) 1 else 0 }
    val fallos = mutableListOf<String>()
    for (entrada in orden) {
      try {
        val r = ia.chat(entrada, mensajes, Acciones.herramientas)
        if (fallos.isNotEmpty()) Doom.anotar(TipoLinea.AVISO, "cambio a $entrada: ${fallos.joinToString("; ")}")
        Doom.enUi { Doom.cadena = cadena }
        return r
      } catch (e: LimiteAlcanzado) {
        apartados[entrada] = ahora + 60_000
        fallos += "$entrada sin cuota por ahora"
      } catch (e: IOException) {
        fallos += "$entrada no responde (${e.message})"
      }
    }
    throw IOException("Ningun modelo ha respondido: " + fallos.joinToString("; "))
  }

  private fun sistema(cfg: Almacen.Config): String {
    val hora = SimpleDateFormat("EEEE d 'de' MMMM yyyy, HH:mm", Locale("es", "ES")).format(Date())
    return listOf(
            cfg.personalidad,
            "Vives en unas gafas Meta Quest, en realidad mixta: el usuario ve su habitacion y a ti " +
                "como un orbe con paneles flotantes que mueve con las manos. Fecha y hora: $hora.",
            "Puedes: abrir aplicaciones instaladas en las gafas, abrir enlaces o busquedas en el " +
                "navegador, subir o bajar el volumen, y decir la bateria. Usa las herramientas para eso.",
            "Limitaciones: no ves la habitacion todavia, ni recuerdas nada entre sesiones, ni puedes " +
                "cambiar ajustes del sistema de las gafas. Si te piden algo que no puedes hacer, dilo en una frase.",
            "Nunca afirmes haber hecho algo que una herramienta no haya confirmado. No inventes datos.",
            "Responde en una a tres frases, sin listas ni markdown: se lee como subtitulo y se oye en voz alta.",
        )
        .joinToString("\n")
  }

  private fun recortar() {
    // Las capas gratuitas limitan tokens por minuto: la conversacion no crece sin fin.
    while (historial.length() > 24) historial.remove(0)
    while (historial.length() > 0 && historial.getJSONObject(0).optString("role") != "user") historial.remove(0)
  }

  companion object {
    private const val MAX_PASOS = 5
  }
}
