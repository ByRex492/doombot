package com.doombot.quest.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.doombot.quest.Controlador
import com.doombot.quest.Doom
import com.doombot.quest.datos.Aspecto
import com.doombot.quest.ia.Modos

// -- MODOS (D-038): global o una skill, en la cabecera del registro ---------------------------
@Composable
fun SelectorModo(ctl: Controlador) {
  Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Modos.todos.forEach { m ->
      val activo = Doom.modo == m.id
      val color = if (m.color.isEmpty()) Hud.c1 else colorDe(m.color)
      Row(
          Modifier.clip(RoundedCornerShape(14.dp))
              .background(if (activo) color.copy(alpha = 0.22f) else Color(0x22000000))
              .border(1.dp, if (activo) color else Hud.borde, RoundedCornerShape(14.dp))
              .clickable { ctl.cambiarModo(m.id) }
              .padding(horizontal = 10.dp, vertical = 6.dp),
          verticalAlignment = Alignment.CenterVertically,
          horizontalArrangement = Arrangement.spacedBy(6.dp),
      ) {
        Box(Modifier.size(8.dp).clip(CircleShape).background(color))
        Text(m.titulo, color = if (activo) Color.White else Hud.tenue, fontSize = 11.sp, fontFamily = Hud.mono)
      }
    }
  }
}

// -- PERSONALIZAR (D-036): temas, perfiles propios, colores, brillo y velocidad ----------------
@Composable
fun SeccionAspecto(ctl: Controlador) {
  val a = Doom.aspecto
  Etiqueta("Tema")
  Rejilla(Aspecto.TEMAS.map { Triple(it.id, it.nombre, it.c1 to it.c2) }, a.tema) { ctl.aspecto { x -> x.conTema(it) } }

  Etiqueta("Mis perfiles")
  val propios = a.perfiles.map { Triple(it.id, it.nombre, it.c1 to it.c2) }
  Rejilla(propios, a.tema, nuevo = a.perfiles.size < Aspecto.MAX_PERFILES, alNuevo = { ctl.aspecto { it.crearPerfil() } }) { id ->
    ctl.aspecto { it.conTema(id) }
  }

  val activo = a.perfilActivo
  Text(
      when {
        activo != null -> "Editando «${activo.nombre}»: los cambios de color se guardan en el perfil."
        a.tema == "propio" -> "Colores sin guardar: ponles nombre y guardalos como perfil."
        else -> "Al cambiar un color, el tema pasa a «propio»; guardalo como perfil para conservarlo."
      },
      color = Hud.muyTenue,
      fontSize = 11.sp)
  EditorColor("Principal", a.c1, ctl, principal = true)
  EditorColor("Secundario", a.c2, ctl, principal = false)

  // Nombre y acciones del perfil
  var nombre by remember(activo?.id, activo?.nombre) { mutableStateOf(activo?.nombre ?: "") }
  var borrando by remember(activo?.id) { mutableStateOf(false) }
  Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Campo(nombre, { nombre = it.take(Aspecto.LARGO_NOMBRE) }, "Nombre del perfil", Modifier.weight(1f),
        alEnviar = { if (activo != null) ctl.aspecto { it.renombrar(activo.id, nombre) } else ctl.aspecto { it.crearPerfil(nombre) } })
    if (activo == null) {
      Boton("Guardar como perfil") { ctl.aspecto { it.crearPerfil(nombre) } }
    } else {
      Boton("Renombrar") { ctl.aspecto { it.renombrar(activo.id, nombre) } }
    }
  }
  if (activo != null) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Boton("Duplicar") { ctl.aspecto { it.crearPerfil("${activo.nombre} (copia)") } }
      // Borrar se confirma con un segundo pellizco, como en la ventana de escritorio.
      Boton(if (borrando) "¿Borrar «${activo.nombre}»? Otra vez" else "Borrar perfil", peligro = true) {
        if (borrando) ctl.aspecto { it.borrarPerfil(activo.id) } else borrando = true
      }
    }
  }

  Deslizador("Brillo y resplandor", a.luz, 0f..1.6f, ctl) { x, v -> x.copy(luz = v) }
  Deslizador("Velocidad de animacion", a.velocidad, 0.2f..2f, ctl) { x, v -> x.copy(velocidad = v) }
  Boton("Restablecer aspecto") { ctl.aspecto { it.restablecido() } }
}

/** Una rejilla de muestras de tema: el orbe en pequeño con sus dos colores y el nombre. */
@Composable
private fun Rejilla(
    temas: List<Triple<String, String, Pair<String, String>>>,
    activo: String,
    nuevo: Boolean = false,
    alNuevo: () -> Unit = {},
    alElegir: (String) -> Unit,
) {
  val celdas: List<Any> = temas + (if (nuevo) listOf("+") else emptyList())
  celdas.chunked(3).forEach { fila ->
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      fila.forEach { celda ->
        if (celda is Triple<*, *, *>) {
          val id = celda.first as String
          val colores = celda.third as Pair<*, *>
          Muestra(celda.second as String, colorDe(colores.first as String), colorDe(colores.second as String), id == activo, Modifier.weight(1f)) {
            alElegir(id)
          }
        } else {
          Box(
              Modifier.weight(1f).height(58.dp).clip(RoundedCornerShape(8.dp)).border(1.dp, Hud.borde, RoundedCornerShape(8.dp))
                  .clickable(onClick = alNuevo),
              contentAlignment = Alignment.Center) {
                Text("+ NUEVO PERFIL", color = Hud.c1, fontFamily = Hud.mono, fontSize = 10.sp, letterSpacing = 1.sp)
              }
        }
      }
      repeat(3 - fila.size) { Box(Modifier.weight(1f)) }
    }
  }
}

@Composable
private fun Muestra(nombre: String, c1: Color, c2: Color, activo: Boolean, modifier: Modifier, alPulsar: () -> Unit) {
  Box(
      modifier
          .height(58.dp)
          .clip(RoundedCornerShape(8.dp))
          .background(Brush.radialGradient(listOf(c2, c1, c1.copy(alpha = 0.25f), Color(0xFF03060B))))
          .border(if (activo) 2.dp else 1.dp, if (activo) Color.White else Hud.borde, RoundedCornerShape(8.dp))
          .clickable(onClick = alPulsar),
      contentAlignment = Alignment.BottomCenter) {
        Text(
            nombre.uppercase(),
            Modifier.fillMaxWidth().background(Color(0x99000000)).padding(vertical = 4.dp, horizontal = 4.dp),
            color = Color(0xFFE8F6FB),
            fontFamily = Hud.mono,
            fontSize = 9.sp,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            fontWeight = FontWeight.SemiBold)
      }
}

/**
 * Sin selector de color nativo en las gafas: tono, saturacion y luz con tres deslizadores, que
 * se aciertan bien con el pellizco. Se ve al arrastrar; se guarda al soltar.
 */
@Composable
private fun EditorColor(titulo: String, hex: String, ctl: Controlador, principal: Boolean) {
  val (h, s, l) = hslDe(colorDe(hex))
  Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
    Box(Modifier.size(22.dp).clip(RoundedCornerShape(4.dp)).background(colorDe(hex)).border(1.dp, Hud.borde, RoundedCornerShape(4.dp)))
    Text("$titulo  $hex", color = Hud.texto, fontFamily = Hud.mono, fontSize = 12.sp)
  }
  fun cambiar(nh: Float, ns: Float, nl: Float, guardar: Boolean) =
      ctl.aspecto(guardar) { it.conColor(principal, hexDe(Color.hsl(nh.coerceIn(0f, 359.9f), ns.coerceIn(0f, 1f), nl.coerceIn(0.05f, 0.95f)))) }
  Fila3("Tono", h / 360f, { cambiar(it * 360f, s, l, false) }, { cambiar(h, s, l, true) })
  Fila3("Saturacion", s, { cambiar(h, it, l, false) }, { cambiar(h, s, l, true) })
  Fila3("Luz", l, { cambiar(h, s, it, false) }, { cambiar(h, s, l, true) })
}

@Composable
private fun Fila3(nombre: String, valor: Float, alCambiar: (Float) -> Unit, alSoltar: () -> Unit) {
  Row(verticalAlignment = Alignment.CenterVertically) {
    Text(nombre, color = Hud.tenue, fontSize = 11.sp, modifier = Modifier.width(78.dp))
    Slider(
        valor.coerceIn(0f, 1f), alCambiar, Modifier.weight(1f), onValueChangeFinished = alSoltar,
        colors = SliderDefaults.colors(thumbColor = Hud.c2, activeTrackColor = Hud.c1, inactiveTrackColor = Hud.borde))
  }
}

@Composable
private fun Deslizador(nombre: String, valor: Float, rango: ClosedFloatingPointRange<Float>, ctl: Controlador, cambio: (Aspecto, Float) -> Aspecto) {
  Text("$nombre  ${(valor * 100).toInt()} %", color = Hud.texto, fontSize = 12.sp, fontFamily = Hud.mono)
  Slider(
      valor, { v -> ctl.aspecto(false) { cambio(it, v) } }, Modifier.fillMaxWidth(), valueRange = rango,
      onValueChangeFinished = { ctl.aspecto(true) { it } },
      colors = SliderDefaults.colors(thumbColor = Hud.c2, activeTrackColor = Hud.c1, inactiveTrackColor = Hud.borde))
}

// -- MEMORIA: lo que sabe del usuario ("recuerda que...") ---------------------------------------
@Composable
fun SeccionMemoria(ctl: Controlador) {
  Etiqueta("Lo que sé de usted (diga «recuerda que…»)")
  val hechos = Doom.config.hechos
  if (hechos.isEmpty()) Text("Nada todavia.", color = Hud.muyTenue, fontSize = 12.sp)
  hechos.forEach { h ->
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Text("· $h", color = Hud.texto, fontSize = 12.sp, modifier = Modifier.weight(1f))
      Boton("✕", peligro = true) { ctl.quitarHecho(h) }
    }
  }
  var nuevo by remember { mutableStateOf("") }
  Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Campo(nuevo, { nuevo = it }, "Algo sobre usted", Modifier.weight(1f), alEnviar = { ctl.anadirHecho(nuevo); nuevo = "" })
    Boton("Añadir") { ctl.anadirHecho(nuevo); nuevo = "" }
  }
}

// -- VOZ, VISION Y AUTOMATIZACIONES ------------------------------------------------------------
@Composable
fun SeccionVozVision(ctl: Controlador) {
  val cfg = Doom.config
  Etiqueta("Escucha y camara")
  Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Boton(if (cfg.activacion) "«Hey jarvis»: si" else "«Hey jarvis»: no", activo = cfg.activacion) { ctl.alternarActivacion() }
  }
  val pasos = listOf(0, 30, 60, 300)
  Text("Modo vigilante (un fotograma cada N s; gasta cuota)", color = Hud.tenue, fontSize = 12.sp)
  Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    pasos.forEach { s -> Boton(if (s == 0) "Apagado" else "$s s", activo = cfg.vigilante == s) { ctl.guardarConfig { it.copy(vigilante = s) } } }
  }
  CampoGuardado("Vision (proveedor:modelo; vacio = Llama 4 Scout de Groq)", cfg.vision, "groq:meta-llama/llama-4-scout-17b-16e-instruct") { v ->
    ctl.guardarConfig { it.copy(vision = v) }
  }
  CampoGuardado("Voz por API (proveedor:modelo; vacio = la voz de las gafas)", cfg.tts, "proveedor:modelo") { v -> ctl.guardarConfig { it.copy(tts = v) } }
  CampoGuardado("Nombre de la voz por API (opcional)", cfg.ttsVoz, "voz") { v -> ctl.guardarConfig { it.copy(ttsVoz = v) } }

  Etiqueta("n8n (flujos con confirmacion hablada)")
  CampoGuardado("Direccion de n8n", cfg.n8nUrl, "http://192.168.1.10:5678") { v -> ctl.guardarConfig { it.copy(n8nUrl = v) } }
  cfg.flujos.forEach { (nombre, ruta) ->
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Text("· $nombre → $ruta", color = Hud.texto, fontSize = 12.sp, fontFamily = Hud.mono, modifier = Modifier.weight(1f))
      Boton("✕", peligro = true) { ctl.guardarConfig { it.copy(flujos = it.flujos - nombre) } }
    }
  }
  var nombre by remember { mutableStateOf("") }
  var ruta by remember { mutableStateOf("") }
  Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Campo(nombre, { nombre = it }, "Nombre hablado", Modifier.weight(1f))
    Campo(ruta, { ruta = it }, "webhook/ruta", Modifier.weight(1f))
    Boton("Añadir") {
      if (nombre.isNotBlank() && ruta.isNotBlank()) {
        val n = nombre.trim()
        val r = ruta.trim()
        ctl.guardarConfig { it.copy(flujos = it.flujos + (n to r)) }
        nombre = ""
        ruta = ""
      }
    }
  }
}

@Composable
private fun CampoGuardado(titulo: String, valor: String, pista: String, alGuardar: (String) -> Unit) {
  Text(titulo, color = Hud.tenue, fontSize = 12.sp)
  var v by remember(valor) { mutableStateOf(valor) }
  Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Campo(v, { v = it }, pista, Modifier.weight(1f), alEnviar = { alGuardar(v.trim()) })
    Boton("Guardar") { alGuardar(v.trim()) }
  }
}

// -- PANELES DE INFORMACION (fase 4): los coloca el agente, se mueven con la mano -------------
@Composable
fun PanelInfo(ctl: Controlador, n: Int) {
  val info = Doom.infos.getOrNull(n)
  Marco(info?.titulo ?: "Información", "INF-0${n + 1}") {
    Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState())) {
      Text(info?.texto ?: "", color = Hud.texto, fontSize = 13.sp, lineHeight = 17.sp)
    }
    Boton("Cerrar") { ctl.cerrarInfo(n) }
  }
}
