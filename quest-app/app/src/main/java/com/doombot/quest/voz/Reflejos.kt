package com.doombot.quest.voz

import com.doombot.quest.util.Texto

/**
 * La capa refleja: ordenes que se resuelven sin modelo, en microsegundos (port de
 * phrases/matcher.py). "Para" tiene que callar siempre y al instante: no puede depender de que un
 * modelo en la nube responda, ni de su cuota.
 */
object Reflejos {
  enum class Orden { CALLAR, RECOLOCAR, OLVIDAR, AJUSTES }

  private val frases =
      mapOf(
          Orden.CALLAR to listOf("para", "calla", "callate", "silencio", "basta", "stop"),
          Orden.RECOLOCAR to listOf("recoloca", "recolocate", "ven aqui", "ven", "traelo todo", "recolocar"),
          Orden.OLVIDAR to listOf("olvida todo", "nueva conversacion", "empieza de nuevo"),
          Orden.AJUSTES to listOf("ajustes", "abre ajustes", "configuracion"),
      )

  fun reconocer(texto: String): Orden? {
    val t = Texto.llano(texto).replace(Regex("[^a-zñ0-9 ]"), " ").replace(Regex("\\s+"), " ").trim()
      .removePrefix("doom ").removePrefix("jarvis ").trim()
    if (t.isEmpty() || t.split(' ').size > 4) return null // una orden refleja es corta
    return frases.entries.firstOrNull { (_, fs) -> fs.any { t == it } }?.key
  }
}
