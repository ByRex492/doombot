package com.doombot.quest.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.graphics.drawable.toBitmap
import com.doombot.quest.Controlador
import com.doombot.quest.Doom
import com.doombot.quest.TipoLinea
import com.doombot.quest.Ventana
import com.doombot.quest.ia.Catalogo
import com.doombot.quest.sistema.App
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

// -- SISTEMA ---------------------------------------------------------------------------------
@Composable
fun PanelSistema(ctl: Controlador) {
  val ahora by produceState(Date()) { while (true) { value = Date(); delay(1000) } }
  Marco("Sistema", "SYS-01", { ControlesVentana(ctl, Ventana.SISTEMA) }) {
    Etiqueta("Hora")
    Text(SimpleDateFormat("HH:mm", Locale("es", "ES")).format(ahora), color = Hud.c2, fontFamily = Hud.mono, fontSize = 34.sp, fontWeight = FontWeight.SemiBold)
    Text(SimpleDateFormat("EEEE d 'de' MMMM", Locale("es", "ES")).format(ahora), color = Hud.tenue, fontSize = 13.sp)
    Etiqueta(Doom.tiempo?.ciudad ?: "Tiempo")
    Text(Doom.tiempo?.let { "${it.grados} °C · ${it.descripcion}" } ?: "…", color = Hud.texto, fontSize = 15.sp)
    Etiqueta("Gafas")
    Text("Bateria ${Doom.bateria?.let { "$it %" } ?: "…"}", color = Hud.texto, fontSize = 14.sp)
    Etiqueta("Cadena de modelos")
    if (Doom.cadena.isEmpty()) Text("Ninguno todavia", color = Hud.aviso, fontSize = 13.sp)
    // Tres como mucho: con la cabecera de mandos de ventana, mas no caben y cortaban los botones.
    Doom.cadena.take(3).forEachIndexed { i, m -> Text("${i + 1}. $m", color = Hud.c2, fontFamily = Hud.mono, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis) }
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Boton("Ajustes", activo = Doom.ajustesVisibles) { if (Doom.ajustesVisibles) ctl.cerrarAjustes() else ctl.abrirAjustes() }
      Boton("Apps", activo = Doom.appsVisibles) { ctl.alternarApps() }
      Boton("Vol−") { ctl.volumen(false) }
      Boton("Vol+") { ctl.volumen(true) }
    }
  }
}

// -- CONVERSACION ----------------------------------------------------------------------------
@Composable
fun PanelChat(ctl: Controlador) {
  var texto by remember { mutableStateOf("") }
  val lista = rememberLazyListState()
  LaunchedEffect(Doom.registro.size) { if (Doom.registro.isNotEmpty()) lista.animateScrollToItem(Doom.registro.size - 1) }
  Marco("Registro", "LOG", { ControlesVentana(ctl, Ventana.REGISTRO) }) {
    SelectorModo(ctl)
    LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = lista, verticalArrangement = Arrangement.spacedBy(6.dp)) {
      items(Doom.registro) { l ->
        val (marca, color) =
            when (l.tipo) {
              TipoLinea.TU -> "›" to Hud.c2
              TipoLinea.COMENTARIO -> "◇" to Hud.tenue
              TipoLinea.ACCION -> "▸" to Hud.c1
              TipoLinea.RESULTADO -> "└" to Hud.tenue
              TipoLinea.AVISO -> "↻" to Hud.muyTenue
              TipoLinea.ERROR -> "✗" to Hud.mal
              TipoLinea.RESPUESTA -> "D" to Color.White
            }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
          Text(marca, color = color, fontFamily = Hud.mono, fontSize = 12.sp, modifier = Modifier.width(12.dp))
          Text(l.texto, color = if (l.tipo == TipoLinea.RESPUESTA) Color.White else color, fontSize = if (l.tipo == TipoLinea.RESPUESTA) 14.sp else 12.sp)
        }
      }
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      Campo(texto, { texto = it }, "Dime que hago…", Modifier.weight(1f), alEnviar = { ctl.enviar(texto); texto = "" })
      Boton("Enviar") { ctl.enviar(texto); texto = "" }
    }
  }
}

// -- APPS Y ENLACES --------------------------------------------------------------------------
private val ATAJOS = listOf("YouTube" to "youtube.com", "Google" to "google.com", "Wikipedia" to "es.wikipedia.org", "Tiempo" to "aemet.es")

@Composable
fun PanelApps(ctl: Controlador) {
  val contexto = LocalContext.current
  val apps by produceState(emptyList<App>()) { value = withContext(Dispatchers.IO) { ctl.apps() } }
  val iconos = remember { mutableStateMapOf<String, ImageBitmap>() }
  var url by remember { mutableStateOf("") }
  Marco("Aplicaciones", "APP-03", { ControlesVentana(ctl, Ventana.APPS) }) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
      Campo(url, { url = it }, "Direccion o busqueda", Modifier.weight(1f), alEnviar = { ctl.abrirEnlace(url); url = "" })
      Boton("Abrir") { ctl.abrirEnlace(url); url = "" }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { ATAJOS.forEach { (n, u) -> Boton(n) { ctl.abrirEnlace(u) } } }
    LazyVerticalGrid(GridCells.Adaptive(92.dp), Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
      items(apps, key = { it.paquete }) { app ->
        LaunchedEffect(app.paquete) {
          if (app.paquete !in iconos) {
            withContext(Dispatchers.IO) {
              runCatching { contexto.packageManager.getApplicationIcon(app.paquete).toBitmap(64, 64, Bitmap.Config.ARGB_8888).asImageBitmap() }.getOrNull()
            }?.let { iconos[app.paquete] = it }
          }
        }
        Column(
            Modifier.clip(RoundedCornerShape(10.dp)).background(Hud.c1a(0.08f)).border(1.dp, Hud.borde, RoundedCornerShape(10.dp))
                .clickable { ctl.abrirApp(app) }.padding(6.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
          iconos[app.paquete]?.let { Image(it, null, Modifier.size(34.dp)) } ?: Box(Modifier.size(34.dp))
          Text(app.nombre, color = Hud.texto, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
      }
    }
  }
}

// -- AJUSTES: todo se puede hacer desde las gafas, y lo largo, mas comodo desde el movil -------
@Composable
fun PanelAjustes(ctl: Controlador) {
  val cfg = Doom.config
  Marco("Ajustes", "CFG-04", { ControlesVentana(ctl, Ventana.AJUSTES) }) {
    Column(Modifier.weight(1f).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
      // Desde el movil
      Etiqueta("Desde el movil (mas comodo para pegar claves)")
      val info = Doom.servidor
      if (info == null) {
        Boton("Abrir ajustes en el movil") { ctl.abrirAjustes() }
      } else {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
          Qr(info.url, Modifier.size(150.dp))
          Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("PIN", color = Hud.tenue, fontFamily = Hud.mono, fontSize = 10.sp)
            Text(info.pin.chunked(3).joinToString(" "), color = Hud.c2, fontFamily = Hud.mono, fontSize = 30.sp, fontWeight = FontWeight.SemiBold)
            Text("Escanea el QR con el movil (misma Wi-Fi) y escribe el PIN.", color = Hud.tenue, fontSize = 12.sp)
            Text(info.url.substringBefore("?"), color = Hud.c1, fontFamily = Hud.mono, fontSize = 11.sp)
            Text("Se apaga solo a los 10 minutos.", color = Hud.muyTenue, fontSize = 11.sp)
          }
        }
      }

      // Aspecto, como Personalizar en la ventana de escritorio
      SeccionAspecto(ctl)

      // Claves
      Etiqueta("Proveedores y claves")
      Catalogo.todos(cfg).forEach { p -> FilaProveedor(ctl, p.id, p.titulo, p.id in Doom.conClave) }
      // El lector de paginas: funciona sin clave (20 lecturas/min); con la gratuita, 200.
      FilaProveedor(ctl, "jina", "Jina Reader (opcional: lector de paginas)", "jina" in Doom.conClave, conProbar = false)

      // Cadena de modelos
      Etiqueta("Cadena de modelos (responde el primero; si no tiene cuota, el siguiente)")
      cfg.cadena.forEachIndexed { i, m ->
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
          Text("${i + 1}. $m", color = Hud.c2, fontFamily = Hud.mono, fontSize = 12.sp, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
          Boton("↑") { if (i > 0) ctl.guardarConfig { c -> c.copy(cadena = c.cadena.toMutableList().also { it.add(i - 1, it.removeAt(i)) }) } }
          Boton("↓") { if (i < cfg.cadena.size - 1) ctl.guardarConfig { c -> c.copy(cadena = c.cadena.toMutableList().also { it.add(i + 1, it.removeAt(i)) }) } }
          Boton("✕", peligro = true) { ctl.guardarConfig { c -> c.copy(cadena = c.cadena.filterIndexed { j, _ -> j != i }) } }
        }
      }
      AnadirModelo(ctl)

      // Voz, personalidad, ciudad
      Etiqueta("Voz a texto (proveedor:modelo; vacio = Whisper de Groq)")
      var stt by remember(cfg.stt) { mutableStateOf(cfg.stt) }
      Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Campo(stt, { stt = it }, "groq:whisper-large-v3-turbo", Modifier.weight(1f))
        Boton("Guardar") { ctl.guardarConfig { it.copy(stt = stt.trim()) } }
      }
      Etiqueta("Personalidad")
      var perso by remember(cfg.personalidad) { mutableStateOf(cfg.personalidad) }
      Campo(perso, { perso = it }, "Como habla D.O.O.M", Modifier.fillMaxWidth(), lineas = 3)
      Boton("Guardar personalidad") { ctl.guardarConfig { it.copy(personalidad = perso.take(2000)) } }
      Etiqueta("Ciudad del tiempo")
      var ciudad by remember(cfg.ciudad) { mutableStateOf(cfg.ciudad) }
      Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Campo(ciudad, { ciudad = it }, "Madrid", Modifier.weight(1f))
        Boton("Cambiar") { ctl.cambiarCiudad(ciudad) }
      }

      SeccionMemoria(ctl)
      SeccionVozVision(ctl)

      // Controles de la app
      Etiqueta("Controles")
      Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Boton("Recolocar") { ctl.recolocar() }
        Boton("Seguirme", activo = Doom.orbeSigue) { Doom.orbeSigue = !Doom.orbeSigue }
        Boton("Apps", activo = Doom.appsVisibles) { ctl.alternarApps() }
      }
      Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Boton("Vol −") { ctl.volumen(false) }
        Boton("Vol +") { ctl.volumen(true) }
        Boton("Olvidar charla", peligro = true) { ctl.olvidar() }
      }
    }
    Boton("Cerrar ajustes") { ctl.cerrarAjustes() }
  }
}

@Composable
private fun FilaProveedor(ctl: Controlador, id: String, titulo: String, configurada: Boolean, conProbar: Boolean = true) {
  var clave by remember { mutableStateOf("") }
  var resultado by remember { mutableStateOf("") }
  Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(Color(0x22000000)).border(1.dp, Hud.borde, RoundedCornerShape(10.dp)).padding(8.dp),
      verticalArrangement = Arrangement.spacedBy(6.dp)) {
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
      Text(titulo, color = Hud.texto, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
      Text(if (configurada) "clave puesta" else "sin clave", color = if (configurada) Hud.ok else Hud.muyTenue, fontSize = 12.sp)
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
      Campo(clave, { clave = it }, "Clave", Modifier.weight(1f), secreto = true)
      Boton("Guardar") { if (clave.isNotBlank()) { ctl.guardarClave(id, clave); clave = "" } }
      if (conProbar) Boton("Probar") { resultado = "Probando…"; ctl.probar(id) { resultado = it } }
      if (configurada) Boton("Quitar", peligro = true) { ctl.guardarClave(id, "") }
    }
    if (resultado.isNotEmpty()) Text(resultado, color = Hud.tenue, fontSize = 12.sp)
  }
}

@Composable
private fun AnadirModelo(ctl: Controlador) {
  var proveedor by remember { mutableStateOf("") }
  var modelos by remember { mutableStateOf<List<String>>(emptyList()) }
  var aviso by remember { mutableStateOf("") }
  Text("Añadir: elige proveedor y pide sus modelos", color = Hud.tenue, fontSize = 12.sp)
  Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
    Doom.conClave.sorted().forEach { p ->
      Boton(p, activo = p == proveedor) {
        proveedor = p
        aviso = "Pidiendo modelos…"
        modelos = emptyList()
        ctl.modelos(p) { lista, error -> modelos = lista; aviso = error ?: "${lista.size} modelos" }
      }
    }
  }
  if (Doom.conClave.isEmpty()) Text("Pon antes una clave.", color = Hud.aviso, fontSize = 12.sp)
  if (aviso.isNotEmpty()) Text(aviso, color = Hud.muyTenue, fontSize = 11.sp)
  modelos.take(40).forEach { m ->
    Text(
        "+ $m",
        color = Hud.c2,
        fontFamily = Hud.mono,
        fontSize = 12.sp,
        modifier = Modifier.fillMaxWidth().clickable { ctl.guardarConfig { c -> if ("$proveedor:$m" in c.cadena) c else c.copy(cadena = c.cadena + "$proveedor:$m") } }.padding(vertical = 5.dp))
  }
}

@Composable
private fun Qr(texto: String, modifier: Modifier) {
  val matriz = remember(texto) { QRCodeWriter().encode(texto, BarcodeFormat.QR_CODE, 0, 0) }
  Canvas(modifier.background(Color(0xFFE9F7FB)).padding(6.dp)) {
    val n = matriz.width
    val celda = size.minDimension / n
    for (y in 0 until n) for (x in 0 until n) {
      if (matriz.get(x, y)) drawRect(Color(0xFF06121C), androidx.compose.ui.geometry.Offset(x * celda, y * celda), androidx.compose.ui.geometry.Size(celda + .5f, celda + .5f))
    }
  }
}
