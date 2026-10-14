package com.doombot.quest

import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/** Los cinco estados del orbe, los mismos de ui/prototipo/hud.html en el repo de escritorio. */
enum class EstadoOrbe(val etiqueta: String) {
  DORMIDO("dormido"),
  ESCUCHANDO("escuchando"),
  PENSANDO("pensando"),
  HABLANDO("hablando"),
  ERROR("error"),
}

/** Cada linea del registro. El tipo decide como se pinta, igual que en la ventana de escritorio. */
enum class TipoLinea { TU, COMENTARIO, ACCION, RESULTADO, AVISO, ERROR, RESPUESTA }

data class Linea(val tipo: TipoLinea, val texto: String)

data class TiempoActual(val ciudad: String, val grados: Int, val descripcion: String)

data class InfoServidor(val url: String, val pin: String, val caduca: Long)

/** Un panel de informacion que el agente coloca en la habitacion (fase 4). */
data class Info(val titulo: String, val texto: String)

/**
 * El estado que comparten todos los paneles.
 *
 * Los paneles son ComposeViews distintos, cada uno en su entidad: lo que uno cambia (el orbe pasa a
 * "pensando") lo tienen que ver los demas sin conocerse entre si. Un solo objeto con estado de
 * Compose lo resuelve sin mas piezas. Se escribe siempre desde el hilo principal (``enUi``): Compose
 * tolera escrituras desde otros hilos, pero mezclarlas con el dibujado da parpadeos dificiles de
 * reproducir.
 */
object Doom {
  var orbe by mutableStateOf(EstadoOrbe.DORMIDO)
  /** Amplitud objetivo 0..1 (micro al escuchar, envolvente al hablar). El orbe la suaviza. */
  var amplitud by mutableFloatStateOf(0f)
  var subtituloQuien by mutableStateOf("")
  var subtitulo by mutableStateOf("")
  val registro = mutableStateListOf<Linea>()
  var tiempo by mutableStateOf<TiempoActual?>(null)
  var cadena by mutableStateOf<List<String>>(emptyList())
  var avisoConfig by mutableStateOf("")
  var servidor by mutableStateOf<InfoServidor?>(null)
  var ajustesVisibles by mutableStateOf(false)
  var appsVisibles by mutableStateOf(true)
  var orbeSigue by mutableStateOf(false)
  var ocupado by mutableStateOf(false)
  var bateria by mutableStateOf<Int?>(null)
  var config by mutableStateOf(com.doombot.quest.datos.Almacen.Config())
  /** Proveedores con clave puesta: para decir "configurada" sin tener la clave en la interfaz. */
  var conClave by mutableStateOf<Set<String>>(emptySet())
  /**
   * Lo que se pinta ahora: aparte de ``config`` porque al arrastrar un deslizador de color se ve
   * al instante, y solo se guarda al soltarlo.
   */
  var aspecto by mutableStateOf(com.doombot.quest.datos.Aspecto())
  var modo by mutableStateOf("global")
  /** Pregunta de confirmacion pendiente (n8n): el orbe la enseña con botones Si/No. */
  var pregunta by mutableStateOf<String?>(null)
  /** La camara esta capturando: el HUD lo enseña siempre (fase 3). */
  var camara by mutableStateOf(false)
  /** "Hey jarvis" escuchando. */
  var palabraActiva by mutableStateOf(false)
  /** Los tres huecos de paneles de informacion; null = libre. */
  val infos = mutableStateListOf<Info?>(null, null, null)

  private val principal = Handler(Looper.getMainLooper())

  fun enUi(accion: () -> Unit) {
    if (Looper.myLooper() == Looper.getMainLooper()) accion() else principal.post(accion)
  }

  fun anotar(tipo: TipoLinea, texto: String) = enUi {
    registro.add(Linea(tipo, texto))
    while (registro.size > 60) registro.removeAt(0)
  }

  fun estado(nuevo: EstadoOrbe) = enUi { orbe = nuevo }

  fun subtitular(quien: String, texto: String) = enUi {
    subtituloQuien = quien
    subtitulo = texto
  }
}
