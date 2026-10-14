package com.doombot.quest.voz

/**
 * Trocea por frases lo que llega del streaming (como tts/synth.py, D-021): en cuanto hay una frase
 * completa se manda a la voz, mientras el modelo sigue escribiendo el resto. Asi D.O.O.M empieza a
 * hablar con la primera frase y no al final de la respuesta.
 *
 * Una frase acaba en ``. ! ? …`` o salto de linea seguidos de espacio. Las muy cortas ("Sí.") se
 * juntan con la siguiente para que la voz no suene a golpes. Logica pura, con tests.
 */
class Frases(private val minimo: Int = 24) {
  private val buffer = StringBuilder()

  /** Añade texto y devuelve las frases que ya estan completas. */
  fun anadir(trozo: String): List<String> {
    buffer.append(trozo)
    val salida = ArrayList<String>()
    var desde = 0
    var i = 0
    val s = buffer.toString()
    while (i < s.length) {
      val c = s[i]
      val fin = c == '\n' || ((c == '.' || c == '!' || c == '?' || c == '…') && i + 1 < s.length && s[i + 1].isWhitespace())
      if (fin && !esAbreviatura(s, i)) {
        val frase = s.substring(desde, i + 1).trim()
        if (frase.length >= minimo || c == '\n') {
          if (frase.isNotEmpty()) salida += frase
          desde = i + 1
        }
      }
      i++
    }
    buffer.delete(0, desde)
    return salida
  }

  /** Lo que queda al terminar la respuesta. */
  fun resto(): String = buffer.toString().trim().also { buffer.setLength(0) }

  private fun esAbreviatura(s: String, i: Int): Boolean {
    if (s[i] != '.') return false
    val palabra = s.substring(0, i).takeLastWhile { it.isLetterOrDigit() }.lowercase()
    // "p. ej.", "Sr.", "etc." no cierran frase; un numero ("3.") tampoco si sigue una cifra.
    return palabra in setOf("sr", "sra", "dr", "dra", "ej", "p", "etc", "vs", "aprox", "núm", "num", "pág")
  }
}
