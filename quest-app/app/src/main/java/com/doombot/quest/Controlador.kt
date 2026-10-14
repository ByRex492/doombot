package com.doombot.quest

import android.Manifest
import android.content.Context
import com.doombot.quest.ajustes.ServidorAjustes
import com.doombot.quest.datos.Almacen
import com.doombot.quest.datos.Aspecto
import com.doombot.quest.ia.Agente
import com.doombot.quest.ia.Catalogo
import com.doombot.quest.ia.ClienteIA
import com.doombot.quest.ia.LlmProvider
import com.doombot.quest.ia.SttProvider
import com.doombot.quest.ia.VisionProvider
import com.doombot.quest.sistema.Acciones
import com.doombot.quest.sistema.App
import com.doombot.quest.sistema.Tiempo
import com.doombot.quest.vision.Camara
import com.doombot.quest.voz.Frases
import com.doombot.quest.voz.Grabadora
import com.doombot.quest.voz.PalabraActivacion
import com.doombot.quest.voz.Reflejos
import com.doombot.quest.voz.Voz
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/**
 * El que une las piezas: lo que pulsa el usuario en un panel llega aqui, y de aqui al agente, la
 * voz o los ajustes. Los paneles no se hablan entre si ni con el agente (como los Protocol de
 * backends/base.py en escritorio: cada pieza se cambia sin tocar a las demas). El agente solo ve
 * los contratos (``LlmProvider``, ``SttProvider``, ``VisionProvider``).
 *
 * ``escena`` son las acciones que solo puede hacer la actividad: mover entidades en el espacio y
 * pedir permisos.
 */
class Controlador(contexto: Context, private val escena: Escena) : Acciones.Extras {

  interface Escena {
    fun recolocar()
    /** Crea, quita o rehace la ventana segun ``Doom.ventana(v)``: abierta, curva y tamaño. */
    fun mostrarVentana(v: Ventana)
    /** Rehace todas las ventanas abiertas (al activar o quitar las asas de Meta). */
    fun rehacerVentanas()
    /** Pide permisos de Android; ``alTerminar(true)`` si se conceden todos. */
    fun pedirPermisos(permisos: Array<String>, alTerminar: (Boolean) -> Unit)
    /** Crea o quita el panel de informacion del hueco ``n`` (0..2). */
    fun mostrarInfo(n: Int, visible: Boolean)
  }

  val ambito = CoroutineScope(SupervisorJob() + Dispatchers.Main)
  val almacen = Almacen(contexto.applicationContext)
  private val cliente = ClienteIA(almacen)
  private val llm: LlmProvider = cliente
  private val stt: SttProvider = cliente
  private val vision: VisionProvider = cliente
  val acciones = Acciones(contexto.applicationContext).also { it.extras = this }
  private val agente = Agente(almacen, llm, acciones)
  private val palabra = PalabraActivacion(contexto.applicationContext)
  // En cuanto habla, deja de escuchar "hey jarvis": se oiria a si mismo.
  private val voz = Voz(contexto.applicationContext, ambito, cliente).also { it.alHablar = { palabra.detener() } }
  private val grabadora = Grabadora()
  private val camara = Camara(contexto.applicationContext)
  private val servidor = ServidorAjustes(contexto.applicationContext, almacen, cliente) { recargar() }
  private var tarea: Job? = null
  private var caducidad: Job? = null
  private var escucha: Job? = null
  private var vigia: Job? = null
  private var confirmacion: CompletableDeferred<Boolean>? = null

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
    Doom.anotar(TipoLinea.COMENTARIO, "A sus ordenes, Mi Señor. Diga «hey jarvis» o pulse «Hablar».")
    ambito.launch {
      // La palabra de activacion necesita el micro: se pide al arrancar solo si esta activada.
      val c = almacen.config()
      if (c.activacion && c.micro) escena.pedirPermisos(arrayOf(Manifest.permission.RECORD_AUDIO)) { if (it) escucharPalabra() }
    }
  }

  /** Vuelve a leer la configuracion (tras guardarla desde el movil o desde las gafas). */
  fun recargar() {
    ambito.launch {
      val c = almacen.config()
      val con = almacen.conClave()
      Doom.config = c
      Doom.conClave = con
      Doom.cadena = c.cadena
      Doom.aspecto = c.aspecto
      Doom.modo = c.modo
      voz.motorApi = c.tts
      voz.vozApi = c.ttsVoz
      Doom.avisoConfig =
          when {
            con.isEmpty() -> "Sin claves: abra Ajustes y pongalas desde el movil o aqui."
            c.cadena.isEmpty() -> "Hay claves pero ningun modelo en la cadena: elijalos en Ajustes."
            else -> ""
          }
      if (!c.activacion || !c.micro) palabra.detener()
      programarVigilante(c.vigilante)
      Doom.micro = c.micro
      Doom.brazaleteFijo = c.brazaleteFijo
      if (Doom.esquinas != c.esquinas) {
        Doom.esquinas = c.esquinas
        escena.rehacerVentanas()
      }
      // Las ventanas guardadas (curva, tamaño, minimizada). Ajustes siempre empieza cerrada.
      for (v in Ventana.entries) {
        if (v == Ventana.AJUSTES) continue
        val guardada = c.ventanas[v.name] ?: EstadoVentana.porDefecto(v)
        if (guardada != Doom.ventana(v)) {
          Doom.ventanas[v] = guardada
          escena.mostrarVentana(v)
        }
      }
      Doom.appsVisibles = Doom.ventana(Ventana.APPS).abierta
    }
  }

  // -- ventanas -------------------------------------------------------------------------------
  private fun guardarVentanas() {
    val estados = Ventana.entries.associate { v -> v.name to Doom.ventana(v).let { if (v == Ventana.AJUSTES) it.copy(abierta = false) else it } }
    guardarConfig { it.copy(ventanas = estados) }
  }

  private fun cambiarVentana(v: Ventana, cambio: (EstadoVentana) -> EstadoVentana) {
    val nuevo = cambio(Doom.ventana(v)).let { it.copy(escala = it.escala.coerceIn(EstadoVentana.ESCALA_MIN, EstadoVentana.ESCALA_MAX)) }
    Doom.ventanas[v] = nuevo
    escena.mostrarVentana(v)
    Doom.appsVisibles = Doom.ventana(Ventana.APPS).abierta
    guardarVentanas()
  }

  /** Abrir o minimizar. Ajustes ademas enciende o apaga el servidor del movil. */
  fun alternarVentana(v: Ventana) {
    if (v == Ventana.AJUSTES) {
      if (Doom.ventana(v).abierta) cerrarAjustes() else abrirAjustes()
      return
    }
    cambiarVentana(v) { it.copy(abierta = !it.abierta) }
  }

  fun minimizar(v: Ventana) = if (v == Ventana.AJUSTES) cerrarAjustes() else cambiarVentana(v) { it.copy(abierta = false) }

  /** ``v`` null: todas a la vez (si alguna esta plana, todas curvas; si no, todas planas). */
  fun curvar(v: Ventana? = null) {
    if (v != null) {
      cambiarVentana(v) { it.copy(curva = !it.curva) }
      return
    }
    val curvar = Ventana.entries.any { !Doom.ventana(it).curva }
    Ventana.entries.forEach { w -> cambiarVentana(w) { it.copy(curva = curvar) } }
  }

  fun escalar(v: Ventana? = null, mas: Boolean) {
    val paso = if (mas) EstadoVentana.PASO else -EstadoVentana.PASO
    (if (v != null) listOf(v) else Ventana.entries).forEach { w -> cambiarVentana(w) { it.copy(escala = it.escala + paso) } }
  }

  fun alternarFijarBrazalete() {
    Doom.brazaleteFijo = !Doom.brazaleteFijo
    guardarConfig { it.copy(brazaleteFijo = Doom.brazaleteFijo) }
  }

  fun alternarEsquinas() {
    Doom.esquinas = !Doom.esquinas
    escena.rehacerVentanas()
    guardarConfig { it.copy(esquinas = Doom.esquinas) }
  }

  /** El interruptor general del micro: apagado, ni "hey jarvis" ni "Hablar". */
  fun alternarMicro() {
    val encender = !Doom.micro
    Doom.micro = encender
    guardarConfig { it.copy(micro = encender) }
    if (!encender) {
      palabra.detener()
      escucha?.cancel()
      grabadora.detener()
      Doom.anotar(TipoLinea.COMENTARIO, "Microfono apagado: no le escucho hasta que lo encienda en el brazalete.")
    } else {
      Doom.anotar(TipoLinea.COMENTARIO, "Microfono encendido.")
      ambito.launch {
        if (almacen.config().activacion) escena.pedirPermisos(arrayOf(Manifest.permission.RECORD_AUDIO)) { if (it) escucharPalabra() }
      }
    }
  }

  fun siguienteModo() {
    val todos = com.doombot.quest.ia.Modos.todos
    val i = todos.indexOfFirst { it.id == Doom.modo }
    cambiarModo(todos[(i + 1) % todos.size].id)
  }

  /** Pasa al siguiente tema: los fijos y luego los perfiles propios. */
  fun siguienteTema() {
    val ids = Aspecto.TEMAS.map { it.id } + Doom.aspecto.perfiles.map { it.id }
    val i = ids.indexOf(Doom.aspecto.tema)
    aspecto { it.conTema(ids[(i + 1).mod(ids.size)]) }
  }

  // -- conversacion -------------------------------------------------------------------------
  fun enviar(texto: String) {
    val t = texto.trim()
    if (t.isEmpty()) return
    // Hay una pregunta de confirmacion pendiente: esta frase es la respuesta, no un pedido.
    confirmacion?.let {
      Doom.anotar(TipoLinea.TU, t)
      it.complete(Reflejos.esAfirmacion(t))
      return
    }
    if (recordar(t)) return
    if (refleja(t)) return
    if (Doom.ocupado) return
    Doom.anotar(TipoLinea.TU, t)
    Doom.subtitular("TÚ", t)
    // Ocupado ya, antes de lanzar: asi "hey jarvis" no vuelve a abrir el micro entretanto.
    Doom.ocupado = true
    tarea =
        ambito.launch {
          Doom.estado(EstadoOrbe.PENSANDO)
          val frases = Frases()
          val dicho = StringBuilder()
          try {
            val respuesta =
                agente.responder(t) { trozo ->
                  // Streaming: subtitulos segun llega, y cada frase completa a la voz (D-021).
                  Doom.enUi {
                    dicho.append(trozo)
                    Doom.subtitular("D.O.O.M", dicho.toString().trim())
                    frases.anadir(trozo).forEach { voz.frase(it) }
                  }
                }
            Doom.enUi {
              frases.resto().takeIf { it.isNotEmpty() }?.let { voz.frase(it) }
              // Si el modelo no fue por streaming (o no dijo nada antes), se dice entera.
              if (dicho.isBlank()) voz.hablar(respuesta)
              Doom.anotar(TipoLinea.RESPUESTA, respuesta)
              Doom.subtitular("D.O.O.M", respuesta)
            }
          } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
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
    if (!Doom.micro) {
      Doom.anotar(TipoLinea.AVISO, "El microfono esta apagado: enciendalo en el brazalete.")
      return
    }
    escena.pedirPermisos(arrayOf(Manifest.permission.RECORD_AUDIO)) { concedido ->
      if (!concedido) {
        Doom.anotar(TipoLinea.AVISO, "Sin permiso de microfono: puede escribirme en el registro.")
        return@pedirPermisos
      }
      ambito.launch { escucharFrase() }
    }
  }

  /** Graba una frase, la transcribe y la manda. La usan el boton y la palabra de activacion. */
  private suspend fun escucharFrase() {
    palabra.detener() // un solo AudioRecord a la vez
    Doom.estado(EstadoOrbe.ESCUCHANDO)
    Doom.subtitular("", "Le escucho…")
    val wav = grabadora.frase()
    if (wav == null) {
      Doom.estado(EstadoOrbe.DORMIDO)
      Doom.subtitular("", "")
      reanudarPalabra()
      return
    }
    Doom.estado(EstadoOrbe.PENSANDO)
    val texto =
        runCatching { stt.transcribir(modeloStt(), wav) }
            .getOrElse {
              Doom.anotar(TipoLinea.ERROR, "No he podido transcribir: ${it.message}")
              Doom.estado(EstadoOrbe.ERROR)
              delay(2000)
              Doom.estado(EstadoOrbe.DORMIDO)
              reanudarPalabra()
              return
            }
    Doom.estado(EstadoOrbe.DORMIDO)
    if (texto.isNotBlank()) enviar(texto)
    reanudarPalabra()
  }

  // -- "hey jarvis" ---------------------------------------------------------------------------
  /**
   * El bucle de la palabra de activacion: escucha, y al oirla graba la frase. Mientras D.O.O.M
   * habla no escucha (se oiria a si mismo); "para" sigue funcionando con el boton.
   */
  private fun escucharPalabra() {
    if (escucha?.isActive == true) return
    escucha =
        ambito.launch {
          if (!palabra.lista) {
            Doom.subtitular("", "Preparando «hey jarvis»…")
            palabra.preparar()?.let {
              Doom.anotar(TipoLinea.AVISO, "$it. Use el boton «Hablar».")
              Doom.subtitular("", "")
              return@launch
            }
            Doom.subtitular("", "")
            Doom.anotar(TipoLinea.COMENTARIO, "«Hey jarvis» listo: le escucho sin que pulse nada.")
          }
          Doom.palabraActiva = true
          try {
            while (isActive && almacen.config().let { it.activacion && it.micro }) {
              while (voz.hablando || Doom.ocupado || Doom.orbe == EstadoOrbe.ESCUCHANDO) delay(300)
              if (palabra.esperar()) {
                voz.callar()
                escucharFrase()
                return@launch // escucharFrase la reanuda al terminar
              } else if (!almacen.config().activacion) break
              delay(200)
            }
          } finally {
            Doom.palabraActiva = false
          }
        }
  }

  private fun reanudarPalabra() {
    ambito.launch {
      if (almacen.config().let { it.activacion && it.micro }) {
        escucha?.cancel()
        escucha = null
        escucharPalabra()
      }
    }
  }

  fun alternarActivacion() {
    guardarConfig { it.copy(activacion = !it.activacion) }
    ambito.launch {
      delay(150)
      if (almacen.config().activacion) {
        escena.pedirPermisos(arrayOf(Manifest.permission.RECORD_AUDIO)) { if (it) escucharPalabra() }
      } else {
        palabra.detener()
        escucha?.cancel()
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
      Reflejos.Orden.OLVIDAR_HECHO -> olvidarUltimoHecho()
    }
    return true
  }

  /** "Recuerda que...": se apunta sin modelo y va desde ya en cada prompt (identify en escritorio). */
  private fun recordar(texto: String): Boolean {
    val hecho = Reflejos.recordatorio(texto) ?: return false
    Doom.anotar(TipoLinea.TU, texto)
    anadirHecho(hecho)
    val dicho = "Anotado, Mi Señor: $hecho."
    Doom.subtitular("D.O.O.M", dicho)
    voz.hablar(dicho)
    return true
  }

  fun anadirHecho(hecho: String) {
    val h = hecho.trim().take(300)
    if (h.isEmpty()) return
    guardarConfig { c -> if (h in c.hechos) c else c.copy(hechos = (c.hechos + h).takeLast(Almacen.MAX_HECHOS)) }
    Doom.anotar(TipoLinea.RESULTADO, "Anotado sobre usted: $h")
  }

  fun quitarHecho(hecho: String) = guardarConfig { c -> c.copy(hechos = c.hechos - hecho) }

  private fun olvidarUltimoHecho() {
    val ultimo = Doom.config.hechos.lastOrNull()
    if (ultimo == null) {
      Doom.anotar(TipoLinea.COMENTARIO, "No hay nada apuntado que olvidar.")
      return
    }
    quitarHecho(ultimo)
    Doom.anotar(TipoLinea.RESULTADO, "Olvidado: $ultimo")
  }

  fun callar() {
    voz.callar()
    grabadora.detener()
    tarea?.cancel()
    confirmacion?.complete(false)
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

  // -- Acciones.Extras: lo que el agente necesita de la escena y de la voz -----------------------
  /**
   * Confirmacion hablada (D-031): se pregunta en voz alta y en el orbe, con botones; la siguiente
   * frase (dicha o escrita) es la respuesta. Silencio durante 30 s o cualquier cosa que no sea un
   * "si" claro es un no.
   */
  override suspend fun confirmar(pregunta: String): Boolean {
    val d = CompletableDeferred<Boolean>()
    confirmacion = d
    Doom.enUi {
      Doom.pregunta = pregunta
      Doom.subtitular("D.O.O.M", pregunta)
    }
    voz.hablar(pregunta)
    // Con la palabra de activacion puesta, se escucha la respuesta sin tener que decir "hey jarvis".
    if (almacen.config().activacion) {
      ambito.launch {
        while (voz.hablando) delay(150)
        if (confirmacion === d) escucharFrase()
      }
    }
    val r = withTimeoutOrNull(30_000) { d.await() } ?: false
    confirmacion = null
    Doom.enUi { Doom.pregunta = null }
    Doom.anotar(TipoLinea.RESULTADO, if (r) "Confirmado" else "No confirmado: no hago nada")
    return r
  }

  fun responderPregunta(si: Boolean) {
    confirmacion?.complete(si)
  }

  /** Fase 3: una foto bajo demanda, con el indicador de camara encendido mientras dura. */
  override suspend fun mirar(pregunta: String): String {
    val permisos = arrayOf(Manifest.permission.CAMERA, "horizonos.permission.HEADSET_CAMERA")
    val concedido = CompletableDeferred<Boolean>()
    Doom.enUi { escena.pedirPermisos(permisos) { concedido.complete(it) } }
    if (!concedido.await()) return "Error: sin permiso de camara. El usuario puede darlo en los ajustes de la app."
    Doom.enUi { Doom.camara = true }
    return try {
      val jpeg = camara.foto()
      vision.mirar(modeloVision(), pregunta, jpeg)
    } catch (e: Exception) {
      "Error: no he podido mirar (${e.message})."
    } finally {
      Doom.enUi { Doom.camara = false }
    }
  }

  private suspend fun modeloVision(): String {
    val c = almacen.config()
    if (c.vision.isNotBlank()) return c.vision
    val groq = Catalogo.base.first { it.id == "groq" }
    return "groq:${groq.visionSugerido}"
  }

  /**
   * Modo vigilante (apagado por defecto): un fotograma cada N segundos, y solo se avisa si hay algo
   * que merezca la pena. Cada fotograma es una peticion: cuidado con la cuota gratuita.
   */
  private fun programarVigilante(segundos: Int) {
    vigia?.cancel()
    if (segundos <= 0) return
    vigia =
        ambito.launch {
          delay(segundos * 1000L)
          while (isActive) {
            if (!Doom.ocupado && !voz.hablando) {
              val r = mirar("Modo vigilante: si ves algo que el usuario deba saber (un peligro, algo que se cae, una persona que entra), dilo en una frase. Si no, responde exactamente: nada.")
              val limpio = r.trim().trimEnd('.').lowercase()
              if (!r.startsWith("Error") && limpio != "nada") {
                Doom.anotar(TipoLinea.AVISO, "Vigilante: $r")
                voz.hablar(r)
              }
            }
            delay(segundos * 1000L)
          }
        }
  }

  override fun mostrarPanel(titulo: String, texto: String): String {
    val n = Doom.infos.indexOfFirst { it == null }.takeIf { it >= 0 } ?: 0
    Doom.enUi {
      Doom.infos[n] = Info(titulo.ifBlank { "Información" }.take(60), texto.take(4000))
      escena.mostrarInfo(n, true)
    }
    return "Panel «$titulo» colocado delante del usuario; lo puede mover con la mano."
  }

  fun cerrarInfo(n: Int) {
    Doom.infos[n] = null
    escena.mostrarInfo(n, false)
  }

  override suspend fun config(): Almacen.Config = almacen.config()

  // -- ajustes ------------------------------------------------------------------------------
  fun abrirAjustes() {
    Doom.ventanas[Ventana.AJUSTES] = Doom.ventana(Ventana.AJUSTES).copy(abierta = true)
    escena.mostrarVentana(Ventana.AJUSTES)
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
    Doom.ventanas[Ventana.AJUSTES] = Doom.ventana(Ventana.AJUSTES).copy(abierta = false)
    escena.mostrarVentana(Ventana.AJUSTES)
    recargar()
  }

  fun guardarClave(proveedor: String, clave: String) =
      ambito.launch {
        almacen.guardarClave(proveedor, clave)
        recargar()
        Doom.anotar(TipoLinea.RESULTADO, if (clave.isBlank()) "Clave de $proveedor quitada" else "Clave de $proveedor guardada")
      }

  fun probar(proveedor: String, alTerminar: (String) -> Unit) =
      ambito.launch { alTerminar(withContext(Dispatchers.IO) { cliente.probar(proveedor) }) }

  fun modelos(proveedor: String, alTerminar: (List<String>, String?) -> Unit) =
      ambito.launch {
        runCatching { cliente.modelos(proveedor) }
            .onSuccess { alTerminar(it, null) }
            .onFailure { alTerminar(emptyList(), it.message) }
      }

  // Leer, cambiar y escribir de una en una: dos cambios seguidos (soltar dos deslizadores, un
  // perfil nuevo y su nombre) no deben pisarse leyendo los dos la configuracion de antes.
  private val escritura = Mutex()

  fun guardarConfig(cambio: (Almacen.Config) -> Almacen.Config) =
      ambito.launch {
        escritura.withLock { almacen.guardar(cambio(almacen.config())) }
        recargar()
      }

  fun cambiarCiudad(nombre: String) =
      ambito.launch {
        val r = runCatching { Tiempo.buscar(nombre) }.getOrNull()
        if (r == null) {
          Doom.anotar(TipoLinea.ERROR, "No encuentro la ciudad «$nombre»")
          return@launch
        }
        guardarConfig { it.copy(ciudad = r.first, lat = r.second, lon = r.third) }.join()
        refrescarTiempo()
      }

  private suspend fun refrescarTiempo() {
    val c = almacen.config()
    runCatching { Tiempo.actual(c.ciudad, c.lat, c.lon) }.onSuccess { Doom.tiempo = it }
  }

  // -- modo y aspecto -------------------------------------------------------------------------
  fun cambiarModo(id: String) {
    Doom.modo = id
    guardarConfig { it.copy(modo = id) }
  }

  /**
   * Un cambio de aspecto se ve al momento. ``guardar`` es falso mientras se arrastra un
   * deslizador: se guarda al soltarlo, no a cada fotograma.
   */
  fun aspecto(guardar: Boolean = true, cambio: (Aspecto) -> Aspecto) {
    val nuevo = Aspecto.limpiar(cambio(Doom.aspecto))
    Doom.aspecto = nuevo
    if (guardar) guardarConfig { it.copy(aspecto = nuevo) }
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

  fun alternarApps() = alternarVentana(Ventana.APPS)

  fun cerrar() {
    servidor.cerrar()
    palabra.cerrar()
    vigia?.cancel()
    voz.cerrar()
    ambito.cancel()
  }
}
