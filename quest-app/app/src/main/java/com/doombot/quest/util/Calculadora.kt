package com.doombot.quest.util

import kotlin.math.abs
import kotlin.math.floor
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.round

/**
 * La herramienta ``calcular``: aritmetica exacta para el modelo (como agent/calculo.py en
 * escritorio), porque un modelo de lenguaje se equivoca haciendo cuentas de cabeza.
 *
 * Un interprete propio y pequeño -``+ - * / ^ %``, parentesis, ``pi``, ``e`` y unas funciones-, nunca
 * ``eval``: una formula es un dato, no codigo.
 */
object Calculadora {
  class ErrorDeFormula(mensaje: String) : IllegalArgumentException(mensaje)

  private val FUNCIONES: Map<String, (Double) -> Double> =
      mapOf(
          "sqrt" to Math::sqrt, "raiz" to Math::sqrt, "abs" to Math::abs,
          "sin" to Math::sin, "cos" to Math::cos, "tan" to Math::tan,
          "asin" to Math::asin, "acos" to Math::acos, "atan" to Math::atan,
          "ln" to { x: Double -> ln(x) }, "log" to { x: Double -> log10(x) }, "exp" to Math::exp,
          "floor" to { x: Double -> floor(x) }, "round" to { x: Double -> round(x) },
      )

  fun evaluar(formula: String): Double {
    val p = Analizador(formula.replace(',', '.').replace('×', '*').replace('÷', '/').replace('−', '-'))
    val v = p.expresion()
    p.saltarBlancos()
    if (!p.fin()) throw ErrorDeFormula("sobra algo en la posicion ${p.pos + 1}")
    if (v.isNaN() || v.isInfinite()) throw ErrorDeFormula("el resultado no es un numero finito")
    return v
  }

  /** El resultado como texto, sin colas de coma flotante (0.1+0.2 -> 0.3). */
  fun formatear(v: Double): String {
    if (abs(v - round(v)) < 1e-9 && abs(v) < 1e15) return round(v).toLong().toString()
    val s = "%.10g".format(java.util.Locale.ROOT, v).trimEnd('0').trimEnd('.')
    return if ('e' in s) s.replace(Regex("\\.?0+e"), "e") else s
  }

  private class Analizador(val s: String) {
    var pos = 0

    fun fin() = pos >= s.length

    fun saltarBlancos() {
      while (!fin() && s[pos].isWhitespace()) pos++
    }

    fun ver(c: Char): Boolean {
      saltarBlancos()
      return !fin() && s[pos] == c
    }

    fun expresion(): Double {
      var v = termino()
      while (true) {
        v = when {
          ver('+') -> { pos++; v + termino() }
          ver('-') -> { pos++; v - termino() }
          else -> return v
        }
      }
    }

    fun termino(): Double {
      var v = potencia()
      while (true) {
        v = when {
          ver('*') -> { pos++; v * potencia() }
          ver('/') -> {
            pos++
            val d = potencia()
            if (d == 0.0) throw ErrorDeFormula("division por cero")
            v / d
          }
          ver('%') -> { pos++; v % potencia() }
          else -> return v
        }
      }
    }

    // ^ asocia por la derecha: 2^3^2 = 2^9.
    fun potencia(): Double {
      val base = unario()
      if (ver('^')) {
        pos++
        return base.pow(potencia())
      }
      return base
    }

    fun unario(): Double {
      if (ver('-')) { pos++; return -unario() }
      if (ver('+')) { pos++; return unario() }
      return primario()
    }

    fun primario(): Double {
      saltarBlancos()
      if (fin()) throw ErrorDeFormula("falta un numero al final")
      val c = s[pos]
      if (c == '(') {
        pos++
        val v = expresion()
        if (!ver(')')) throw ErrorDeFormula("falta cerrar un parentesis")
        pos++
        return v
      }
      if (c.isDigit() || c == '.') {
        val ini = pos
        while (!fin() && (s[pos].isDigit() || s[pos] == '.')) pos++
        if (!fin() && (s[pos] == 'e' || s[pos] == 'E') && pos + 1 < s.length &&
            (s[pos + 1].isDigit() || s[pos + 1] == '-' || s[pos + 1] == '+')) {
          pos += 2
          while (!fin() && s[pos].isDigit()) pos++
        }
        return s.substring(ini, pos).toDoubleOrNull() ?: throw ErrorDeFormula("numero mal escrito: ${s.substring(ini, pos)}")
      }
      if (c.isLetter()) {
        val ini = pos
        while (!fin() && (s[pos].isLetterOrDigit() || s[pos] == '_')) pos++
        val nombre = s.substring(ini, pos).lowercase()
        when (nombre) {
          "pi" -> return Math.PI
          "e" -> return Math.E
        }
        val f = FUNCIONES[nombre] ?: throw ErrorDeFormula("no conozco «$nombre»")
        if (!ver('(')) throw ErrorDeFormula("$nombre necesita parentesis: $nombre(...)")
        pos++
        val v = expresion()
        if (!ver(')')) throw ErrorDeFormula("falta cerrar el parentesis de $nombre")
        pos++
        return f(v)
      }
      throw ErrorDeFormula("no entiendo «$c» en la posicion ${pos + 1}")
    }
  }
}
