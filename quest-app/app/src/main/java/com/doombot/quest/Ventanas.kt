package com.doombot.quest

/**
 * Las ventanas de D.O.O.M en la habitacion. Cada una se registra dos veces en el Spatial SDK -plana
 * (``QuadShapeOptions``) y curva (``CylinderShapeOptions``)-, porque la forma de un panel se fija
 * al registrarlo: curvarla es volver a crearla con el otro id, en el mismo sitio.
 */
enum class Ventana(val titulo: String, val plana: Int, val curva: Int, val ancho: Float, val alto: Float) {
  ORBE("Orbe", R.id.panel_orbe, R.id.panel_orbe_c, 0.42f, 0.58f),
  SISTEMA("Sistema", R.id.panel_sistema, R.id.panel_sistema_c, 0.40f, 0.56f),
  REGISTRO("Registro", R.id.panel_chat, R.id.panel_chat_c, 0.48f, 0.56f),
  APPS("Apps", R.id.panel_apps, R.id.panel_apps_c, 0.62f, 0.38f),
  AJUSTES("Ajustes", R.id.panel_ajustes, R.id.panel_ajustes_c, 0.60f, 0.74f),
}

/** Como esta cada ventana: abierta o minimizada, curva o plana, y su tamaño (escala). */
data class EstadoVentana(val abierta: Boolean = true, val curva: Boolean = false, val escala: Float = 1f) {
  companion object {
    const val ESCALA_MIN = 0.5f
    const val ESCALA_MAX = 2f
    const val PASO = 0.15f

    fun porDefecto(v: Ventana) = EstadoVentana(abierta = v != Ventana.AJUSTES)
  }
}
