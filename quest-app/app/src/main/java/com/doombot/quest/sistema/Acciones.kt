package com.doombot.quest.sistema

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.os.BatteryManager
import com.doombot.quest.Doom
import com.doombot.quest.TipoLinea
import com.doombot.quest.util.Texto
import java.net.URLEncoder
import org.json.JSONArray
import org.json.JSONObject

/** Una aplicacion instalada que se puede abrir. */
data class App(val nombre: String, val paquete: String)

/**
 * Lo que D.O.O.M puede hacer en las gafas: abrir aplicaciones y enlaces, el volumen, la bateria.
 *
 * Es lo que Android deja hacer a una app normal. Cambiar ajustes del sistema (brillo, Wi-Fi,
 * limites de guardian) no esta al alcance de ninguna app de la tienda, asi que no se promete: el
 * prompt del agente lo dice como limitacion.
 */
class Acciones(private val contexto: Context) {

  fun apps(): List<App> {
    val pm = contexto.packageManager
    val intent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
    return pm.queryIntentActivities(intent, PackageManager.MATCH_ALL)
        .map { App(it.loadLabel(pm).toString(), it.activityInfo.packageName) }
        .filter { it.paquete != contexto.packageName }
        .distinctBy { it.paquete }
        .sortedBy { it.nombre.lowercase() }
  }

  fun abrirApp(nombre: String): String {
    val todas = apps()
    val buscado = llano(nombre)
    val app =
        todas.firstOrNull { llano(it.nombre) == buscado }
            ?: todas.firstOrNull { llano(it.nombre).contains(buscado) || buscado.contains(llano(it.nombre)) }
            ?: todas.firstOrNull { it.paquete.contains(buscado.replace(" ", "")) }
            ?: return "Error: no encuentro ninguna app llamada «$nombre». Hay: " +
                todas.take(25).joinToString { it.nombre }
    return abrirPaquete(app)
  }

  fun abrirPaquete(app: App): String {
    val intent =
        contexto.packageManager.getLaunchIntentForPackage(app.paquete)
            ?: return "Error: ${app.nombre} no se puede abrir directamente."
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    contexto.startActivity(intent)
    Doom.anotar(TipoLinea.RESULTADO, "Abierta ${app.nombre}")
    return "Abierta ${app.nombre}."
  }

  fun abrirEnlace(destino: String): String {
    val d = destino.trim()
    val url =
        when {
          d.startsWith("http://") || d.startsWith("https://") -> d
          ' ' !in d && '.' in d -> "https://$d"
          else -> "https://duckduckgo.com/?q=" + URLEncoder.encode(d, "UTF-8")
        }
    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    return runCatching {
          contexto.startActivity(intent)
          Doom.anotar(TipoLinea.RESULTADO, "Abierto $url")
          "Abierto $url en el navegador."
        }
        .getOrElse { "Error: no hay navegador para abrir $url." }
  }

  fun volumen(direccion: String): String {
    val am = contexto.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    val paso = if (llano(direccion).startsWith("baj")) AudioManager.ADJUST_LOWER else AudioManager.ADJUST_RAISE
    repeat(2) { am.adjustStreamVolume(AudioManager.STREAM_MUSIC, paso, AudioManager.FLAG_SHOW_UI) }
    val v = am.getStreamVolume(AudioManager.STREAM_MUSIC)
    val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
    return "Volumen en ${v * 100 / max.coerceAtLeast(1)} %."
  }

  fun bateria(): Int {
    val bm = contexto.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
    return bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
  }

  /** Lo que pide el modelo. Devuelve lo que se le devuelve: un resultado o un "Error: ...". */
  fun ejecutar(nombre: String, args: JSONObject): String {
    Doom.anotar(TipoLinea.ACCION, contar(nombre, args))
    return runCatching {
          when (nombre) {
            "abrir_app" -> abrirApp(args.optString("nombre"))
            "abrir_enlace" -> abrirEnlace(args.optString("destino"))
            "listar_apps" -> "Apps instaladas: " + apps().joinToString { it.nombre }
            "volumen" -> volumen(args.optString("direccion", "subir"))
            "bateria" -> "Bateria al ${bateria()} %."
            else -> "Error: no existe la herramienta $nombre."
          }
        }
        .getOrElse { "Error: ${it.message}" }
        .also { if (it.startsWith("Error")) Doom.anotar(TipoLinea.ERROR, it) }
  }

  private fun contar(nombre: String, args: JSONObject) =
      when (nombre) {
        "abrir_app" -> "Abro ${args.optString("nombre")}"
        "abrir_enlace" -> "Abro ${args.optString("destino")} en el navegador"
        "listar_apps" -> "Miro las apps instaladas"
        "volumen" -> "Volumen: ${args.optString("direccion")}"
        "bateria" -> "Miro la bateria"
        else -> nombre
      }

  companion object {
    private fun funcion(nombre: String, descripcion: String, props: JSONObject = JSONObject(), requeridos: List<String> = emptyList()) =
        JSONObject()
            .put("type", "function")
            .put(
                "function",
                JSONObject()
                    .put("name", nombre)
                    .put("description", descripcion)
                    .put("parameters", JSONObject().put("type", "object").put("properties", props).put("required", JSONArray(requeridos))))

    private fun texto(d: String) = JSONObject().put("type", "string").put("description", d)

    val herramientas: JSONArray =
        JSONArray()
            .put(funcion("abrir_app", "Abre una aplicacion instalada en las gafas por su nombre.",
                JSONObject().put("nombre", texto("Nombre de la app, ej. 'YouTube', 'Navegador'.")), listOf("nombre")))
            .put(funcion("abrir_enlace", "Abre una direccion web, o una busqueda si son palabras, en el navegador de las gafas.",
                JSONObject().put("destino", texto("Direccion (ej. youtube.com) o terminos de busqueda.")), listOf("destino")))
            .put(funcion("listar_apps", "Lista las aplicaciones instaladas en las gafas."))
            .put(funcion("volumen", "Sube o baja el volumen de las gafas.",
                JSONObject().put("direccion", texto("'subir' o 'bajar'.")), listOf("direccion")))
            .put(funcion("bateria", "Dice el nivel de bateria de las gafas."))

    /** Minusculas y sin tildes, para comparar nombres de apps dichos de viva voz. */
    fun llano(texto: String): String = Texto.llano(texto)
  }
}
