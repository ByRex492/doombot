package com.doombot.quest.datos

/**
 * Como se ve D.O.O.M en las gafas: el mismo modelo que Personalizar en la ventana de escritorio
 * (``ventana/preferencias.py``, D-036). Temas fijos, perfiles de color propios con nombre, brillo y
 * velocidad de la animacion.
 *
 * Todo lo que llega -de los paneles o de la pagina del movil- pasa por ``limpiar``: solo colores
 * ``#rrggbb``, numeros en su rango y perfiles completos. Es logica pura, sin Android, para poder
 * probarla en la JVM.
 */
data class Perfil(val id: String, val nombre: String, val c1: String, val c2: String)

data class TemaFijo(val id: String, val nombre: String, val c1: String, val c2: String)

data class Aspecto(
    /** Un tema fijo, "propio" (colores sin guardar) o el id de un perfil propio. */
    val tema: String = "jarvis",
    val c1: String = "#29d3ff",
    val c2: String = "#8ff3ff",
    /** Brillo y resplandor, 0..1,6 como en escritorio. */
    val luz: Float = 1f,
    /** Velocidad de la animacion del orbe, 0,2..2. */
    val velocidad: Float = 1f,
    val perfiles: List<Perfil> = emptyList(),
) {
  val perfilActivo: Perfil?
    get() = perfiles.firstOrNull { it.id == tema }

  companion object {
    /** Los mismos seis temas que la ventana de escritorio (``TEMAS`` en ``ui/ventana/doom.html``). */
    val TEMAS =
        listOf(
            TemaFijo("jarvis", "Jarvis", "#29d3ff", "#8ff3ff"),
            TemaFijo("holograma", "Holograma", "#ffae2b", "#ffd88a"),
            TemaFijo("neon", "Neón", "#ff2bd6", "#2bf0ff"),
            TemaFijo("matriz", "Matriz", "#36ff8a", "#b6ffd1"),
            TemaFijo("glaciar", "Glaciar", "#a8d8ff", "#ffffff"),
            TemaFijo("carmesi", "Carmesí", "#ff3b4e", "#ffb3ba"),
        )
    const val MAX_PERFILES = 24
    const val LARGO_NOMBRE = 32
    private val COLOR = Regex("^#[0-9a-fA-F]{6}$")
    private val ID_PERFIL = Regex("^perfil-[a-z0-9]{1,16}$")

    fun esColor(c: String?) = c != null && COLOR.matches(c)

    /** Nombre en una linea, sin caracteres de control y con un largo razonable. */
    fun nombreLimpio(nombre: String): String =
        nombre.map { if (it.isISOControl() || Character.getType(it) == Character.FORMAT.toInt()) ' ' else it }
            .joinToString("")
            .split(Regex("\\s+"))
            .filter { it.isNotEmpty() }
            .joinToString(" ")
            .take(LARGO_NOMBRE)

    /** Los perfiles validos, sin ids repetidos y con tope. Uno roto se descarta entero. */
    fun perfilesLimpios(perfiles: List<Perfil>): List<Perfil> {
      val vistos = HashSet<String>()
      val salida = ArrayList<Perfil>()
      for (p in perfiles) {
        if (!ID_PERFIL.matches(p.id) || !vistos.add(p.id)) continue
        val nombre = nombreLimpio(p.nombre)
        if (nombre.isEmpty() || !esColor(p.c1) || !esColor(p.c2)) continue
        salida += Perfil(p.id, nombre, p.c1.lowercase(), p.c2.lowercase())
        if (salida.size == MAX_PERFILES) break
      }
      return salida
    }

    fun limpiar(a: Aspecto): Aspecto {
      val perfiles = perfilesLimpios(a.perfiles)
      val propio = perfiles.firstOrNull { it.id == a.tema }
      val fijos = TEMAS.map { it.id } + "propio"
      val tema = if (a.tema in fijos || propio != null) a.tema else "jarvis"
      var c1 = if (esColor(a.c1)) a.c1.lowercase() else "#29d3ff"
      var c2 = if (esColor(a.c2)) a.c2.lowercase() else "#8ff3ff"
      // Con un perfil propio activo mandan sus colores: asi no se separan del perfil.
      if (propio != null) {
        c1 = propio.c1
        c2 = propio.c2
      }
      return Aspecto(
          tema = tema,
          c1 = c1,
          c2 = c2,
          luz = if (a.luz.isFinite()) a.luz.coerceIn(0f, 1.6f) else 1f,
          velocidad = if (a.velocidad.isFinite()) a.velocidad.coerceIn(0.2f, 2f) else 1f,
          perfiles = perfiles,
      )
    }

    /** "Perfil 1", "Perfil 2"... o el nombre pedido, si no esta ya cogido. */
    fun nombreLibre(perfiles: List<Perfil>, base: String = ""): String {
      val usados = perfiles.map { it.nombre }.toSet()
      val b = nombreLimpio(base)
      if (b.isNotEmpty() && b !in usados) return b
      var n = 1
      while (true) {
        val c = (if (b.isNotEmpty()) "$b ${n + 1}" else "Perfil $n").take(LARGO_NOMBRE)
        if (c !in usados) return c
        n++
      }
    }

    fun idNuevo(): String =
        "perfil-" + (java.lang.Long.toString(System.currentTimeMillis(), 36) +
            java.lang.Long.toString((Math.random() * 1_679_616).toLong(), 36)).take(16)
  }

  // -- cambios, siempre devolviendo un Aspecto nuevo -------------------------------------------
  fun conTema(id: String): Aspecto {
    TEMAS.firstOrNull { it.id == id }?.let { return copy(tema = id, c1 = it.c1, c2 = it.c2) }
    perfiles.firstOrNull { it.id == id }?.let { return copy(tema = id, c1 = it.c1, c2 = it.c2) }
    return this
  }

  /** Cambiar un color: en el perfil activo si lo hay; si no, el tema pasa a «propio». */
  fun conColor(principal: Boolean, color: String): Aspecto {
    if (!esColor(color)) return this
    val c = color.lowercase()
    val activo = perfilActivo
    val nuevo = if (principal) copy(c1 = c) else copy(c2 = c)
    if (activo == null) return nuevo.copy(tema = "propio")
    val editado = if (principal) activo.copy(c1 = c) else activo.copy(c2 = c)
    return nuevo.copy(perfiles = perfiles.map { if (it.id == activo.id) editado else it })
  }

  fun crearPerfil(nombre: String = "", id: String = idNuevo()): Aspecto {
    if (perfiles.size >= MAX_PERFILES) return this
    val p = Perfil(id, nombreLibre(perfiles, nombre), c1, c2)
    return copy(perfiles = perfiles + p, tema = p.id)
  }

  fun renombrar(id: String, nombre: String): Aspecto {
    val limpio = nombreLimpio(nombre)
    if (limpio.isEmpty()) return this
    return copy(perfiles = perfiles.map { if (it.id == id) it.copy(nombre = limpio) else it })
  }

  /** Los colores se quedan como «propio»: borrar el perfil no cambia lo que se ve. */
  fun borrarPerfil(id: String): Aspecto =
      copy(perfiles = perfiles.filter { it.id != id }, tema = if (tema == id) "propio" else tema)

  /** Vuelve al aspecto de fabrica, pero los perfiles guardados se quedan. */
  fun restablecido(): Aspecto = Aspecto(perfiles = perfiles)
}
