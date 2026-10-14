package com.doombot.quest.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.doombot.quest.Doom
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/**
 * Los colores del HUD de escritorio (D-036). c1 y c2 salen del aspecto elegido (tema o perfil
 * propio): al leerlos dentro de un composable, Compose repinta solo cuando cambian.
 */
object Hud {
  val c1: Color
    get() = colorDe(Doom.aspecto.c1)
  val c2: Color
    get() = colorDe(Doom.aspecto.c2)
  /** El tono de c1 en grados: el orbe gira su color alrededor de el, como en escritorio. */
  val tono: Float
    get() = tonoDe(c1)
  val luz: Float
    get() = Doom.aspecto.luz
  val texto = Color(0xFFD6ECF4)
  val tenue = Color(0xFF8AA3B2)
  val muyTenue = Color(0xFF4F6576)
  val ok = Color(0xFF3DFFA0)
  val mal = Color(0xFFFF4D5E)
  val aviso = Color(0xFFFFAB2E)
  val borde: Color
    get() = c1.copy(alpha = 0.4f)
  val panel = Brush.verticalGradient(listOf(Color(0xD9041420), Color(0xCC020A12)))
  val mono = FontFamily.Monospace

  /** c1 con transparencia: los fondos de botones y casillas. */
  fun c1a(alfa: Float) = c1.copy(alpha = alfa)
}

/** ``#rrggbb`` a Color; si llega algo raro, el cian de Jarvis. */
fun colorDe(hex: String): Color =
    hex.removePrefix("#").toLongOrNull(16)?.takeIf { hex.length == 7 }?.let { Color(0xFF000000 or it) } ?: Color(0xFF29D3FF)

fun hexDe(c: Color): String =
    "#%02x%02x%02x".format((c.red * 255).roundToInt(), (c.green * 255).roundToInt(), (c.blue * 255).roundToInt())

/** (tono 0..360, saturacion 0..1, luminosidad 0..1) de un color. */
fun hslDe(c: Color): Triple<Float, Float, Float> {
  val mx = max(c.red, max(c.green, c.blue))
  val mn = min(c.red, min(c.green, c.blue))
  val l = (mx + mn) / 2f
  if (mx == mn) return Triple(0f, 0f, l)
  val d = mx - mn
  val s = if (l > 0.5f) d / (2f - mx - mn) else d / (mx + mn)
  val h =
      when (mx) {
        c.red -> ((c.green - c.blue) / d + (if (c.green < c.blue) 6f else 0f))
        c.green -> ((c.blue - c.red) / d + 2f)
        else -> ((c.red - c.green) / d + 4f)
      } * 60f
  return Triple(h, s, l)
}

fun tonoDe(c: Color): Float = hslDe(c).first

/** El marco de cada panel: cabecera con etiqueta y codigo, como en la ventana de escritorio. */
@Composable
fun Marco(
    etiqueta: String,
    codigo: String,
    controles: (@Composable () -> Unit)? = null,
    contenido: @Composable ColumnScope.() -> Unit,
) {
  Column(
      Modifier.fillMaxSize()
          .clip(RoundedCornerShape(16.dp))
          .background(Hud.panel)
          .border(BorderStroke(1.dp, Hud.borde), RoundedCornerShape(16.dp))
          .padding(horizontal = 16.dp, vertical = 12.dp),
      verticalArrangement = Arrangement.spacedBy(8.dp),
  ) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
      Text(etiqueta.uppercase(), color = Hud.c1, fontFamily = Hud.mono, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, letterSpacing = 3.sp)
      if (controles != null) controles() else Text(codigo, color = Hud.muyTenue, fontFamily = Hud.mono, fontSize = 11.sp, letterSpacing = 1.sp)
    }
    contenido()
  }
}

@Composable
fun Etiqueta(texto: String) =
    Text(texto.uppercase(), color = Hud.tenue, fontFamily = Hud.mono, fontSize = 10.sp, letterSpacing = 2.sp, fontWeight = FontWeight.SemiBold)

/** Boton grande: con la mano, un objetivo pequeño cuesta de acertar. */
@Composable
fun Boton(texto: String, modifier: Modifier = Modifier, activo: Boolean = false, peligro: Boolean = false, alPulsar: () -> Unit) {
  val color = if (peligro) Hud.mal else if (activo) Color.White else Hud.c2
  Text(
      texto.uppercase(),
      modifier =
          modifier
              .clip(RoundedCornerShape(8.dp))
              .background(if (activo) Hud.c1a(0.2f) else Hud.c1a(0.08f))
              .border(1.dp, if (activo) Hud.c1 else Hud.borde, RoundedCornerShape(8.dp))
              .clickable(onClick = alPulsar)
              .padding(horizontal = 12.dp, vertical = 9.dp),
      color = color,
      fontFamily = Hud.mono,
      fontSize = 12.sp,
      letterSpacing = 1.sp,
      fontWeight = FontWeight.SemiBold,
  )
}

@Composable
fun Campo(
    valor: String,
    alCambiar: (String) -> Unit,
    pista: String,
    modifier: Modifier = Modifier,
    secreto: Boolean = false,
    lineas: Int = 1,
    alEnviar: (() -> Unit)? = null,
) {
  OutlinedTextField(
      value = valor,
      onValueChange = alCambiar,
      modifier = modifier,
      placeholder = { Text(pista, color = Hud.muyTenue, fontSize = 12.sp) },
      singleLine = lineas == 1,
      minLines = lineas,
      maxLines = if (lineas == 1) 1 else lineas + 2,
      textStyle = TextStyle(color = Hud.texto, fontFamily = Hud.mono, fontSize = 13.sp),
      visualTransformation = if (secreto) PasswordVisualTransformation() else VisualTransformation.None,
      keyboardOptions =
          KeyboardOptions(
              keyboardType = if (secreto) KeyboardType.Password else KeyboardType.Text,
              imeAction = if (alEnviar != null) ImeAction.Send else ImeAction.Default),
      keyboardActions = KeyboardActions(onSend = { alEnviar?.invoke() }),
      colors =
          OutlinedTextFieldDefaults.colors(
              focusedBorderColor = Hud.c1,
              unfocusedBorderColor = Hud.borde,
              cursorColor = Hud.c2,
              focusedContainerColor = Color(0x66000000),
              unfocusedContainerColor = Color(0x44000000)),
  )
}

@Composable
fun Fila(contenido: @Composable () -> Unit) =
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) { contenido() }
