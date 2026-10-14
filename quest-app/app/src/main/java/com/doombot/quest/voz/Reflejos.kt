package com.doombot.quest.voz

import com.doombot.quest.util.Texto

/**
 * La capa refleja: ordenes que se resuelven sin modelo, en microsegundos (port de
 * phrases/matcher.py). "Para" tiene que callar siempre y al instante: no puede depender de que un
 * modelo en la nube responda, ni de su cuota.
 */
object Reflejos {
  enum class Orden { CALLAR, RECOLOCAR, OLVIDAR, AJUSTES, OLVIDAR_HECHO }

  private val frases =
      mapOf(
          Orden.CALLAR to listOf("para", "calla", "callate", "silencio", "basta", "stop"),
          Orden.RECOLOCAR to listOf("recoloca", "recolocate", "ven aqui", "ven", "traelo todo", "recolocar"),
          Orden.OLVIDAR to listOf("olvida todo", "nueva conversacion", "empieza de nuevo"),
          Orden.AJUSTES to listOf("ajustes", "abre ajustes", "configuracion"),
          Orden.OLVIDAR_HECHO to listOf("olvida eso", "olvida lo ultimo", "borra eso", "no recuerdes eso"),
      )

  // "recuerda que yo...": un hecho sobre el usuario, que va siempre en el prompt (identify en
  // memory/orders.py). Se guarda tal cual lo dijo, sin pasar por ningun modelo.
  private val recordar = listOf("recuerda que ", "acuerdate de que ", "apunta que ", "quiero que sepas que ", "ten en cuenta que ")

  private fun normal(texto: String) =
      Texto.llano(texto).replace(Regex("[^a-zñ0-9 ]"), " ").replace(Regex("\\s+"), " ").trim()
          .removePrefix("doom ").removePrefix("jarvis ").trim()

  // Respuesta a "¿confirmo?" antes de una accion real (D-031, es_afirmacion en escritorio):
  // silencio, "no" o cualquier otra cosa que no este aqui es negativa. Ante la duda, no ejecutar.
  private val afirmativas = setOf("si", "confirmo", "adelante", "hazlo", "vale", "claro", "dale", "afirmativo")

  fun esAfirmacion(texto: String): Boolean = normal(texto).split(' ').any { it in afirmativas }

  fun reconocer(texto: String): Orden? {
    val t = normal(texto)
    if (t.isEmpty() || t.split(' ').size > 4) return null // una orden refleja es corta
    return frases.entries.firstOrNull { (_, fs) -> fs.any { t == it } }?.key
  }

  /**
   * Lo que hay que recordar, o null si la frase no es un "recuerda que...". Se devuelve con las
   * palabras originales (tildes y mayusculas), no las normalizadas.
   */
  fun recordatorio(texto: String): String? {
    val t = normal(texto)
    val prefijo = recordar.firstOrNull { t.startsWith(it) } ?: return null
    // Las palabras del prefijo, contadas en la frase original para cortarla por el mismo sitio.
    val palabras = prefijo.trim().split(' ').size
    val original = texto.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
    val inicio = original.indexOfFirst { Texto.llano(it).trim(',', '.', '¡', '!', ':') !in setOf("doom", "jarvis", "") }
    val resto = original.drop(inicio + palabras).joinToString(" ").trim().trimEnd('.', '!')
    return resto.ifEmpty { null }
  }
}
