package com.doombot.quest

import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min

/**
 * Los parametros de cada estado, copiados de ui/prototipo/hud.html (seccion 2). Interpolar estos
 * numeros, y no cambiar de dibujo, es lo que hace que el orbe se transforme sin saltos.
 */
data class ParamsOrbe(
    val dh: Float, val sat: Float, val lum: Float, val r: Float, val react: Float, val glow: Float,
    val spin: Float, val orbit: Float, val caos: Float, val breath: Float, val bpm: Float,
)

val ESTADOS_ORBE =
    mapOf(
        EstadoOrbe.DORMIDO to ParamsOrbe(0f, 22f, 42f, .30f, .15f, .30f, .020f, .06f, 0f, .055f, .16f),
        EstadoOrbe.ESCUCHANDO to ParamsOrbe(0f, 82f, 60f, .36f, 1.0f, 1.00f, .075f, .14f, 0f, .020f, .55f),
        EstadoOrbe.PENSANDO to ParamsOrbe(42f, 70f, 56f, .33f, .10f, .72f, .240f, .85f, 0f, .030f, .90f),
        EstadoOrbe.HABLANDO to ParamsOrbe(-16f, 88f, 66f, .35f, .85f, 1.15f, .060f, .20f, 0f, .018f, .45f),
        EstadoOrbe.ERROR to ParamsOrbe(170f, 85f, 58f, .32f, .55f, .95f, .500f, .30f, 1f, .040f, 1.6f),
    )

private fun mezclar(a: ParamsOrbe, b: ParamsOrbe, k: Float) =
    ParamsOrbe(
        a.dh + (b.dh - a.dh) * k, a.sat + (b.sat - a.sat) * k, a.lum + (b.lum - a.lum) * k, a.r + (b.r - a.r) * k,
        a.react + (b.react - a.react) * k, a.glow + (b.glow - a.glow) * k, a.spin + (b.spin - a.spin) * k,
        a.orbit + (b.orbit - a.orbit) * k, a.caos + (b.caos - a.caos) * k, a.breath + (b.breath - a.breath) * k,
        a.bpm + (b.bpm - a.bpm) * k)

/**
 * El motor del orbe: el estado interpolado y la amplitud suavizada, paso a paso. No dibuja: lo usa
 * la burbuja 3D (escena/Orbe3D.kt) para mover sus piezas.
 */
class MotorOrbe {
  private var actual = EstadoOrbe.DORMIDO
  private var desde = ESTADOS_ORBE.getValue(EstadoOrbe.DORMIDO)
  private var hacia = desde
  var m = desde
    private set
  private var tMix = 1f
  /** Amplitud suavizada 0..1. */
  var amp = 0f
    private set
  /** Giro acumulado, en grados. */
  var ang = 0f
    private set
  /** Impulso de temblor del estado ERROR, que se apaga solo. */
  var sacudida = 0f
    private set
  var t = 0f
    private set

  fun paso(dt: Float, estado: EstadoOrbe, objetivo: Float) {
    t += dt
    if (estado != actual) {
      desde = m
      hacia = ESTADOS_ORBE.getValue(estado)
      tMix = 0f
      actual = estado
      if (estado == EstadoOrbe.ERROR) sacudida = 1f
    }
    tMix = min(1f, tMix + dt / 0.5f)
    val k = tMix * tMix * (3 - 2 * tMix)
    m = mezclar(desde, hacia, k)
    // Ataque rapido, caida lenta (T_ATAQUE y T_CAIDA del prototipo): sin esto, el orbe parpadea.
    val kA = 1 - exp(-dt / 0.040f)
    val kC = 1 - exp(-dt / 0.190f)
    amp += (objetivo - amp) * (if (objetivo > amp) kA else kC)
    sacudida = max(0f, sacudida - dt * 2.2f)
    ang += m.spin * dt * 360f
  }

  /** El color del orbe en este instante, con brillo extra ``dl`` y opacidad ``a``. */
  fun color(dl: Float, a: Float): FloatArray = hsl(193f + m.dh, m.sat / 100f, (m.lum + dl) / 100f, a)

  companion object {
    /** HSL -> RGBA en 0..1, para los materiales de la escena. */
    fun hsl(hGrados: Float, s: Float, l: Float, a: Float): FloatArray {
      val h = (((hGrados % 360f) + 360f) % 360f) / 360f
      val ss = s.coerceIn(0f, 1f)
      val ll = l.coerceIn(0f, 1f)
      val q = if (ll < 0.5f) ll * (1 + ss) else ll + ss - ll * ss
      val p = 2 * ll - q
      fun canal(t0: Float): Float {
        var t = t0
        if (t < 0) t += 1f
        if (t > 1) t -= 1f
        return when {
          t < 1f / 6 -> p + (q - p) * 6 * t
          t < 1f / 2 -> q
          t < 2f / 3 -> p + (q - p) * (2f / 3 - t) * 6
          else -> p
        }
      }
      return floatArrayOf(canal(h + 1f / 3), canal(h), canal(h - 1f / 3), a.coerceIn(0f, 1f))
    }
  }
}
