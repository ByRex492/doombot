package com.doombot.quest

import android.content.Context
import com.doombot.quest.ajustes.ServidorAjustes
import com.doombot.quest.datos.Almacen
import com.doombot.quest.ia.Agente
import com.doombot.quest.ia.Catalogo
import com.doombot.quest.ia.ClienteIA
import com.doombot.quest.sistema.Acciones
import com.doombot.quest.sistema.App
import com.doombot.quest.sistema.Tiempo
import com.doombot.quest.voz.Grabadora
import com.doombot.quest.voz.Reflejos
import com.doombot.quest.voz.Voz
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * El que une las piezas: lo que pulsa el usuario en un panel llega aqui, y de aqui al agente, la
 * voz o los ajustes. Los paneles no se hablan entre si ni con el agente (como los Protocol de
 * backends/base.py en escritorio: cada pieza se cambia sin tocar a las demas).
 *
 * ``escena`` son las acciones que solo puede hacer la actividad: mover entidades en el espacio y
 * pedir permisos.
 */
class Controlador(contexto: Context, private val escena: Escena) {

  interface Escena {
    fun recolocar()
    fun restablecerVentanas()
    fun mostrarVentanas(visibles: Boolean)
    fun mostrarAjustes(visible: Boolean)
    fun mostrarApps(visible: Boolean)
    fun pedirMicrofono(alConceder: () -> Unit)
  }

  val ambito = CoroutineScope(SupervisorJob() + Dispatchers.Main)
  val almacen = Almacen(contexto.applicationContext)
  private val ia = ClienteIA(almacen)
  val acciones = Acciones(contexto.applicationContext)
  private val agente = Agente(almacen, ia, acciones)
  private val voz = Voz(contexto.applicationContext, ambito)
  private val grabadora = Grabadora()
  private val servidor = ServidorAjustes(contexto.applicationContext, almacen, ia) { recargar() }
  private var tarea: Job? = null
  private var caducidad: Job? = null

  fun arrancar() {
    recargar()
    ambito.launch {
      while (isActive) {
        refrescarTiempo()
        delay(15 * 60_000L)
      }
    }
    ambito.launch {
      while (isActive) {
        Doom.bateria = runCatching { acciones.bateria() }.getOrNull()
        delay(60_000L)
      }
    }
    Doom.anotar(TipoLinea.COMENTARIO, "A sus ordenes, Mi Señor. Pellizque el microfono para hablarme.")
  }

  /** Vuelve a leer la configuracion (tras guardarla desde el movil o desde las gafas). */
  fun recargar() {
    ambito.launch {
      val c = almacen.config()
      val con = almacen.conClave()
      Doom.config = c
      Doom.conClave = con
      Doom.cadena = c.cadena
      Doom.avisoConfig =
          when {
            con.isEmpty() -> "Sin claves: abra Ajustes y pongalas desde el movil o aqui."
            c.cadena.isEmpty() -> "Hay claves pero ningun modelo en la cadena: elijalos en Ajustes."
            else -> ""
          }
    }
  }

  // -- conversacion -------------------------------------------------------------------------
  fun enviar(texto: String) {
    val t = texto.trim()
    if (t.isEmpty()) return
    if (refleja(t)) return
    if (Doom.ocupado) return
    Doom.anotar(TipoLinea.TU, t)
    Doom.subtitular("TÚ", t)
    tarea =
        ambito.launch {
          Doom.ocupado = true
          Doom.estado(EstadoOrbe.PENSANDO)
          try {
            val respuesta = agente.responder(t)
            Doom.anotar(TipoLinea.RESPUESTA, respuesta)
            Doom.subtitular("D.O.O.M", respuesta)
            voz.hablar(respuesta)
          } catch (e: Exception) {
            Doom.anotar(TipoLinea.ERROR, e.message ?: "Algo ha fallado")
            Doom.subtitular("D.O.O.M", "No he podido responder: ${e.message}")
            Doom.estado(EstadoOrbe.ERROR)
            delay(2500)
            Doom.estado(EstadoOrbe.DORMIDO)
          } finally {
            Doom.ocupado = false
          }
        }
  }

  /** Pulsar el microfono: graba hasta que te callas, transcribe y responde. Pulsar otra vez corta. */
  fun microfono() {
    if (Doom.orbe == EstadoOrbe.ESCUCHANDO) {
      grabadora.detener()
      return
    }
    if (Doom.orbe == EstadoOrbe.HABLANDO) voz.callar() // barge-in: hablarle le hace callar
    escena.pedirMicrofono {
      ambito.launch {
        Doom.estado(EstadoOrbe.ESCUCHANDO)
        Doom.subtitular("", "Le escucho…")
        val wav = grabadora.frase()
        if (wav == null) {
          Doom.estado(EstadoOrbe.DORMIDO)
          Doom.subtitular("", "")
          return@launch
        }
        Doom.estado(EstadoOrbe.PENSANDO)
        val texto =
            runCatching { ia.transcribir(modeloStt(), wav) }
                .getOrElse {
                  Doom.anotar(TipoLinea.ERROR, "No he podido transcribir: ${it.message}")
                  Doom.estado(EstadoOrbe.ERROR)
                  delay(2000)
                  Doom.estado(EstadoOrbe.DORMIDO)
                  return@launch
                }
        if (texto.isBlank()) {
          Doom.estado(EstadoOrbe.DORMIDO)
          return@launch
        }
        Doom.estado(EstadoOrbe.DORMIDO)
        enviar(texto)
      }
    }
  }

  private suspend fun modeloStt(): String {
    val c = almacen.config()
    if (c.stt.isNotBlank()) return c.stt
    val groq = Catalogo.base.first { it.id == "groq" }
    return "groq:${groq.sttSugerido}"
  }

  private fun refleja(texto: String): Boolean {
    val orden = Reflejos.reconocer(texto) ?: return false
    Doom.anotar(TipoLinea.COMENTARIO, "«$texto»: orden directa, sin modelo")
    when (orden) {
      Reflejos.Orden.CALLAR -> callar()
      Reflejos.Orden.RECOLOCAR -> escena.recolocar()
      Reflejos.Orden.OLVIDAR -> olvidar()
      Reflejos.Orden.AJUSTES -> abrirAjustes()
    }
    return true
  }

  fun callar() {
    voz.callar()
    grabadora.detener()
    tarea?.cancel()
    Doom.ocupado = false
    Doom.estado(EstadoOrbe.DORMIDO)
    Doom.subtitular("", "")
  }

  fun olvidar() {
    agente.olvidar()
    Doom.registro.clear()
    Doom.subtitular("", "")
    Doom.anotar(TipoLinea.COMENTARIO, "Conversacion nueva. No recuerdo nada de lo anterior.")
  }

  // -- ajustes ------------------------------------------------------------------------------
  fun abrirAjustes() {
    escena.mostrarAjustes(true)
    Doom.ajustesVisibles = true
    val info = servidor.abrir()
    Doom.servidor = info
    caducidad?.cancel()
    caducidad =
        ambito.launch {
          delay(ServidorAjustes.DURACION)
          servidor.cerrar()
          Doom.servidor = null
        }
  }

  fun cerrarAjustes() {
    servidor.cerrar()
    caducidad?.cancel()
    Doom.servidor = null
    Doom.ajustesVisibles = false
    escena.mostrarAjustes(false)
    recargar()
  }

  fun guardarClave(proveedor: String, clave: String) =
      ambito.launch {
        almacen.guardarClave(proveedor, clave)
        recargar()
        Doom.anotar(TipoLinea.RESULTADO, if (clave.isBlank()) "Clave de $proveedor quitada" else "Clave de $proveedor guardada")
      }

  fun probar(proveedor: String, alTerminar: (String) -> Unit) =
      ambito.launch { alTerminar(withContext(Dispatchers.IO) { ia.probar(proveedor) }) }

  fun modelos(proveedor: String, alTerminar: (List<String>, String?) -> Unit) =
      ambito.launch {
        runCatching { ia.modelos(proveedor) }
            .onSuccess { alTerminar(it, null) }
            .onFailure { alTerminar(emptyList(), it.message) }
      }

  fun guardarConfig(cambio: (Almacen.Config) -> Almacen.Config) =
      ambito.launch {
        almacen.guardar(cambio(almacen.config()))
        recargar()
      }

  fun cambiarCiudad(nombre: String) =
      ambito.launch {
        val r = runCatching { Tiempo.buscar(nombre) }.getOrNull()
        if (r == null) {
          Doom.anotar(TipoLinea.ERROR, "No encuentro la ciudad «$nombre»")
          return@launch
        }
        almacen.guardar(almacen.config().copy(ciudad = r.first, lat = r.second, lon = r.third))
        recargar()
        refrescarTiempo()
      }

  private suspend fun refrescarTiempo() {
    val c = almacen.config()
    runCatching { Tiempo.actual(c.ciudad, c.lat, c.lon) }.onSuccess { Doom.tiempo = it }
  }

  // -- las gafas ----------------------------------------------------------------------------
  fun apps(): List<App> = acciones.apps()

  fun abrirApp(app: App) {
    acciones.abrirPaquete(app)
  }

  fun abrirEnlace(destino: String) {
    if (destino.isNotBlank()) acciones.abrirEnlace(destino)
  }

  fun volumen(subir: Boolean) {
    Doom.anotar(TipoLinea.RESULTADO, acciones.volumen(if (subir) "subir" else "bajar"))
  }

  fun recolocar() = escena.recolocar()

  fun restablecerVentanas() = escena.restablecerVentanas()

  /** Esconder o enseñar todas las ventanas a la vez (la burbuja y el brazalete se quedan). */
  fun alternarVentanas() {
    Doom.ventanasVisibles = !Doom.ventanasVisibles
    escena.mostrarVentanas(Doom.ventanasVisibles)
  }

  fun alternarApps() {
    Doom.appsVisibles = !Doom.appsVisibles
    escena.mostrarApps(Doom.appsVisibles)
  }

  fun cerrar() {
    servidor.cerrar()
    voz.cerrar()
    ambito.cancel()
  }
}
