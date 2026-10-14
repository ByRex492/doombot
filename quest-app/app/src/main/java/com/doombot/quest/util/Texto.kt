package com.doombot.quest.util

import java.text.Normalizer

/** Texto comparable: minusculas y sin tildes (como normalize() en phrases/matcher.py). */
object Texto {
  fun llano(texto: String): String =
      Normalizer.normalize(texto.lowercase().trim(), Normalizer.Form.NFD).replace(Regex("\\p{Mn}+"), "")
}
