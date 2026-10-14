package com.doombot.quest.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.doombot.quest.Controlador
import com.doombot.quest.Doom
import com.doombot.quest.EstadoOrbe
import com.doombot.quest.Ventana
import com.doombot.quest.ia.Modos
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay

/**
 * El brazalete de la muñeca izquierda: todo D.O.O.M a mano, como el reloj de un traje. Se pulsa
 * con la otra mano (pellizco o tocandolo con el dedo). Desde aqui se abren y minimizan las ventanas,
 * se curvan, se cambian de tamaño, y se enciende o apaga el microfono.
 */
@Composable
fun PanelBrazalete(ctl: Controlador) {
  val ahora by produceState(Date()) { while (true) { value = Date(); delay(10_000) } }
  Column(
      Modifier.fillMaxSize()
          .clip(RoundedCornerShape(14.dp))
          .background(Hud.panel)
          .border(1.dp, Hud.borde, RoundedCornerShape(14.dp))
          .padding(10.dp),
      verticalArrangement = Arrangement.spacedBy(6.dp),
  ) {
    // Cabecera: estado del orbe, hora y si el brazalete esta fijado.
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Box(Modifier.size(9.dp).clip(CircleShape).background(if (Doom.orbe == EstadoOrbe.ERROR) Hud.mal else Hud.c1))
      Text("D.O.O.M · ${Doom.orbe.etiqueta.uppercase()}", color = Hud.c2, fontFamily = Hud.mono, fontSize = 10.sp, fontWeight = FontWeight.SemiBold,
          modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
      Text(SimpleDateFormat("HH:mm", Locale("es", "ES")).format(ahora), color = Hud.tenue, fontFamily = Hud.mono, fontSize = 10.sp)
    }

    Seccion("Voz")
    FilaTeclas {
      Tecla(if (Doom.orbe == EstadoOrbe.ESCUCHANDO) "Listo" else "Hablar", activa = Doom.orbe == EstadoOrbe.ESCUCHANDO) { ctl.microfono() }
      Tecla(if (Doom.micro) "Micro sí" else "Micro no", activa = Doom.micro, peligro = !Doom.micro) { ctl.alternarMicro() }
      Tecla("Para") { ctl.callar() }
    }
    FilaTeclas {
      Tecla(if (Doom.config.activacion) "Jarvis sí" else "Jarvis no", activa = Doom.config.activacion) { ctl.alternarActivacion() }
      Tecla(if (Doom.config.vigilante > 0) "Vigía sí" else "Vigía no", activa = Doom.config.vigilante > 0) {
        ctl.guardarConfig { it.copy(vigilante = if (it.vigilante > 0) 0 else 60) }
      }
      Tecla("Modo: ${Modos.de(Doom.modo).titulo.take(5)}") { ctl.siguienteModo() }
    }

    Seccion("Ventanas")
    // Pulsar abre o minimiza; encendida = abierta.
    Ventana.entries.chunked(3).forEach { fila ->
      FilaTeclas { fila.forEach { v -> Tecla(v.titulo, activa = Doom.ventana(v).abierta) { ctl.alternarVentana(v) } } }
    }
    FilaTeclas {
      val todasCurvas = Ventana.entries.all { Doom.ventana(it).curva }
      Tecla(if (todasCurvas) "Planas" else "Curvas", activa = todasCurvas) { ctl.curvar() }
      Tecla("Tamaño −") { ctl.escalar(mas = false) }
      Tecla("Tamaño +") { ctl.escalar(mas = true) }
    }
    FilaTeclas {
      Tecla("Recolocar") { ctl.recolocar() }
      Tecla("Seguirme", activa = Doom.orbeSigue) { Doom.orbeSigue = !Doom.orbeSigue }
      Tecla("Esquinas", activa = Doom.esquinas) { ctl.alternarEsquinas() }
    }

    Seccion("Más")
    FilaTeclas {
      Tecla("Tema") { ctl.siguienteTema() }
      Tecla("Vol −") { ctl.volumen(false) }
      Tecla("Vol +") { ctl.volumen(true) }
    }
    FilaTeclas {
      Tecla(if (Doom.brazaleteFijo) "Fijado" else "Fijar", activa = Doom.brazaleteFijo) { ctl.alternarFijarBrazalete() }
      Tecla("Olvidar", peligro = true) { ctl.olvidar() }
      Tecla("Ajustes", activa = Doom.ventana(Ventana.AJUSTES).abierta) { ctl.alternarVentana(Ventana.AJUSTES) }
    }
  }
}

@Composable
private fun Seccion(texto: String) =
    Text(texto.uppercase(), color = Hud.muyTenue, fontFamily = Hud.mono, fontSize = 8.sp, letterSpacing = 2.sp)

@Composable
private fun FilaTeclas(contenido: @Composable RowScope.() -> Unit) =
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(5.dp), content = contenido)

/** Una tecla del brazalete: tres por fila, para acertar con el dedo. */
@Composable
private fun RowScope.Tecla(texto: String, activa: Boolean = false, peligro: Boolean = false, alPulsar: () -> Unit) {
  Text(
      texto.uppercase(),
      modifier =
          Modifier.weight(1f)
              .clip(RoundedCornerShape(7.dp))
              .background(if (activa) Hud.c1a(0.24f) else Color(0x22000000))
              .border(1.dp, if (peligro) Hud.mal else if (activa) Hud.c1 else Hud.borde, RoundedCornerShape(7.dp))
              .clickable(onClick = alPulsar)
              .padding(vertical = 8.dp, horizontal = 2.dp),
      color = if (peligro) Hud.mal else if (activa) Color.White else Hud.c2,
      fontFamily = Hud.mono,
      fontSize = 9.sp,
      textAlign = TextAlign.Center,
      maxLines = 1,
      overflow = TextOverflow.Ellipsis,
  )
}

/** Los mandos de cada ventana, en su cabecera: curvar, tamaño y minimizar. */
@Composable
fun ControlesVentana(ctl: Controlador, v: Ventana) {
  Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
    MiniTecla(if (Doom.ventana(v).curva) "▭" else "◠") { ctl.curvar(v) }
    MiniTecla("−") { ctl.escalar(v, mas = false) }
    MiniTecla("+") { ctl.escalar(v, mas = true) }
    MiniTecla("_") { ctl.minimizar(v) }
  }
}

@Composable
private fun MiniTecla(texto: String, alPulsar: () -> Unit) {
  Box(
      Modifier.size(26.dp).clip(RoundedCornerShape(6.dp)).background(Hud.c1a(0.1f)).border(1.dp, Hud.borde, RoundedCornerShape(6.dp))
          .clickable(onClick = alPulsar),
      contentAlignment = Alignment.Center) {
        Text(texto, color = Hud.c2, fontFamily = Hud.mono, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
      }
}
