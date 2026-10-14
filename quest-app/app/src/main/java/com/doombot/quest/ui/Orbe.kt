package com.doombot.quest.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.BlendMode
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.doombot.quest.Controlador
import com.doombot.quest.Doom
import com.doombot.quest.EstadoOrbe
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.exp
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin
import kotlin.random.Random

/**
 * Los parametros de cada estado, copiados de ui/prototipo/hud.html (seccion 2). Interpolar estos
 * numeros, y no cambiar de dibujo, es lo que hace que el orbe se transforme sin saltos.
 */
private data class P(
    val dh: Float, val sat: Float, val lum: Float, val r: Float, val react: Float, val glow: Float,
    val spin: Float, val orbit: Float, val caos: Float, val breath: Float, val bpm: Float,
)

private val ESTADOS =
    mapOf(
        EstadoOrbe.DORMIDO to P(0f, 22f, 42f, .30f, .15f, .30f, .020f, .06f, 0f, .055f, .16f),
        EstadoOrbe.ESCUCHANDO to P(0f, 82f, 60f, .36f, 1.0f, 1.00f, .075f, .14f, 0f, .020f, .55f),
        EstadoOrbe.PENSANDO to P(42f, 70f, 56f, .33f, .10f, .72f, .240f, .85f, 0f, .030f, .90f),
        EstadoOrbe.HABLANDO to P(-16f, 88f, 66f, .35f, .85f, 1.15f, .060f, .20f, 0f, .018f, .45f),
        EstadoOrbe.ERROR to P(170f, 85f, 58f, .32f, .55f, .95f, .500f, .30f, 1f, .040f, 1.6f),
    )

private fun mix(a: P, b: P, k: Float) =
    P(a.dh + (b.dh - a.dh) * k, a.sat + (b.sat - a.sat) * k, a.lum + (b.lum - a.lum) * k, a.r + (b.r - a.r) * k,
        a.react + (b.react - a.react) * k, a.glow + (b.glow - a.glow) * k, a.spin + (b.spin - a.spin) * k,
        a.orbit + (b.orbit - a.orbit) * k, a.caos + (b.caos - a.caos) * k, a.breath + (b.breath - a.breath) * k,
        a.bpm + (b.bpm - a.bpm) * k)

/** El motor del orbe: el estado interpolado y la amplitud suavizada, paso a paso. */
private class Motor {
  var actual = EstadoOrbe.DORMIDO
  var desde = ESTADOS.getValue(EstadoOrbe.DORMIDO)
  var hacia = desde
  var m = desde
  var tMix = 1f
  var amp = 0f
  var ang = 0f
  var sacudida = 0f
  var t = 0f

  fun paso(dt: Float, estado: EstadoOrbe, objetivo: Float) {
    t += dt
    if (estado != actual) {
      desde = m
      hacia = ESTADOS.getValue(estado)
      tMix = 0f
      actual = estado
      if (estado == EstadoOrbe.ERROR) sacudida = 1f
    }
    tMix = min(1f, tMix + dt / 0.5f)
    val k = tMix * tMix * (3 - 2 * tMix)
    m = mix(desde, hacia, k)
    // Ataque rapido, caida lenta (T_ATAQUE y T_CAIDA del prototipo): sin esto, el orbe parpadea.
    val kA = 1 - exp(-dt / 0.040f)
    val kC = 1 - exp(-dt / 0.190f)
    amp += (objetivo - amp) * (if (objetivo > amp) kA else kC)
    sacudida = max(0f, sacudida - dt * 2.2f)
    ang += m.spin * dt * 360f
  }
}

@Composable
fun OrbeAnimado(modifier: Modifier = Modifier) {
  val motor = remember { Motor() }
  var tick by remember { mutableLongStateOf(0L) }
  LaunchedEffect(Unit) {
    var antes = 0L
    while (true) {
      withFrameNanos { ahora ->
        val dt = if (antes == 0L) 0.016f else ((ahora - antes) / 1e9f).coerceAtMost(0.05f)
        antes = ahora
        motor.paso(dt, Doom.orbe, Doom.amplitud)
        tick = ahora
      }
    }
  }
  Canvas(modifier) {
    tick // leerlo hace que se redibuje en cada fotograma
    dibujar(motor)
  }
}

private fun DrawScope.dibujar(mo: Motor) {
  val m = mo.m
  val w = size.minDimension
  val h = 193f + m.dh
  fun color(l: Float, a: Float) =
      Color.hsl(((h % 360f) + 360f) % 360f, (m.sat / 100f).coerceIn(0f, 1f), (l / 100f).coerceIn(0f, 1f), a.coerceIn(0f, 1f))
  val respira = 1 + sin(mo.t * 2 * PI.toFloat() * m.bpm) * m.breath
  val r = w * m.r * 0.78f * respira * (1 + mo.amp * m.react * 0.16f)
  val c = Offset(size.width / 2 + (Random.nextFloat() - .5f) * 14f * mo.sacudida, size.height / 2 + (Random.nextFloat() - .5f) * 14f * mo.sacudida)

  // Halo y nucleo
  drawCircle(Brush.radialGradient(listOf(color(m.lum, .34f * m.glow), Color.Transparent), c, r * 1.9f), r * 1.9f, c, blendMode = BlendMode.Plus)
  drawCircle(
      Brush.radialGradient(
          0f to color(min(96f, m.lum + 32f), .95f * max(.45f, m.glow)),
          .55f to color(m.lum, .55f * m.glow + .15f),
          1f to Color.Transparent,
          center = c,
          radius = r * .62f),
      r * .62f, c)
  // Anillo de marcas, que la voz deforma
  val n = 72
  for (i in 0 until n) {
    val a = Math.toRadians((mo.ang + i * 360f / n).toDouble()).toFloat()
    val onda = sin(i * .9f + mo.t * 7f) * mo.amp * m.react * .12f
    val caos = if (m.caos > .01f) (Random.nextFloat() - .5f) * .08f * m.caos else 0f
    val r1 = r * (.86f + onda + caos)
    val r2 = r1 + r * (if (i % 6 == 0) .11f else .05f)
    drawLine(
        color(m.lum + 14f, .35f + .5f * m.glow * (if (i % 6 == 0) 1f else .6f)),
        Offset(c.x + cos(a) * r1, c.y + sin(a) * r1),
        Offset(c.x + cos(a) * r2, c.y + sin(a) * r2),
        strokeWidth = w * (if (i % 6 == 0) .007f else .004f),
        cap = StrokeCap.Round)
  }
  // Arcos orbitales: protagonistas al pensar
  for (j in 0 until 3) {
    val rr = r * (1.12f + j * .17f)
    val ini = -mo.ang * (1.4f + j * .5f) + j * 120f
    val largo = 63f + 29f * sin(mo.t * .8f + j)
    val trazo = Stroke(width = w * .006f, cap = StrokeCap.Round)
    val tl = Offset(c.x - rr, c.y - rr)
    rotate(0f, c) {
      drawArc(color(m.lum + 10f, m.orbit * (.9f - j * .2f)), ini, largo, false, tl, Size(rr * 2, rr * 2), style = trazo)
      drawArc(color(m.lum + 10f, m.orbit * (.9f - j * .2f)), ini + 180f, largo * .6f, false, tl, Size(rr * 2, rr * 2), style = trazo)
    }
  }
  drawCircle(color(m.lum + 20f, .25f + .25f * m.glow), r * .62f, c, style = Stroke(w * .003f))
}

/** El panel del orbe: la burbuja, su estado, los subtitulos y los mandos basicos. */
@Composable
fun PanelOrbe(ctl: Controlador) {
  Column(
      Modifier.fillMaxSize().padding(8.dp),
      horizontalAlignment = Alignment.CenterHorizontally,
      verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    OrbeAnimado(Modifier.fillMaxWidth().aspectRatio(1f))
    Text(
        Doom.orbe.etiqueta.uppercase(),
        modifier =
            Modifier.clip(RoundedCornerShape(6.dp))
                .background(Color(0x99030A12))
                .border(1.dp, Hud.borde, RoundedCornerShape(6.dp))
                .padding(horizontal = 14.dp, vertical = 5.dp),
        color = Hud.c2,
        fontFamily = Hud.mono,
        fontSize = 12.sp,
        letterSpacing = 5.sp,
        fontWeight = FontWeight.SemiBold)
    Column(Modifier.fillMaxWidth().heightIn(min = 54.dp), horizontalAlignment = Alignment.CenterHorizontally) {
      if (Doom.subtituloQuien.isNotEmpty()) {
        Text(Doom.subtituloQuien, color = Hud.c2, fontFamily = Hud.mono, fontSize = 10.sp, letterSpacing = 2.sp)
      }
      Text(
          Doom.subtitulo.ifEmpty { Doom.avisoConfig },
          color = if (Doom.subtitulo.isEmpty()) Hud.aviso else Color.White,
          fontSize = 15.sp,
          lineHeight = 19.sp,
          textAlign = TextAlign.Center,
          maxLines = 4)
    }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      Boton(if (Doom.orbe == EstadoOrbe.ESCUCHANDO) "Listo" else "Hablar", activo = Doom.orbe == EstadoOrbe.ESCUCHANDO) { ctl.microfono() }
      Boton("Para") { ctl.callar() }
      Boton("Recolocar") { ctl.recolocar() }
    }
  }
}
