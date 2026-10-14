package com.doombot.quest.sistema

import com.doombot.quest.TiempoActual
import java.net.URL
import java.net.URLEncoder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * El tiempo, de Open-Meteo: gratis, sin clave y sin cuenta. Asi el panel funciona desde el primer
 * minuto, antes de configurar ningun proveedor.
 */
object Tiempo {
  suspend fun actual(ciudad: String, lat: Double, lon: Double): TiempoActual =
      withContext(Dispatchers.IO) {
        val url =
            "https://api.open-meteo.com/v1/forecast?latitude=$lat&longitude=$lon" +
                "&current=temperature_2m,weather_code&timezone=auto"
        val actual = JSONObject(URL(url).readText()).getJSONObject("current")
        TiempoActual(ciudad, Math.round(actual.getDouble("temperature_2m")).toInt(), describir(actual.getInt("weather_code")))
      }

  /** Nombre de ciudad -> (nombre, lat, lon), con el buscador de Open-Meteo. */
  suspend fun buscar(nombre: String): Triple<String, Double, Double>? =
      withContext(Dispatchers.IO) {
        val url = "https://geocoding-api.open-meteo.com/v1/search?count=1&language=es&name=" + URLEncoder.encode(nombre, "UTF-8")
        val r = JSONObject(URL(url).readText()).optJSONArray("results") ?: return@withContext null
        if (r.length() == 0) return@withContext null
        val c = r.getJSONObject(0)
        Triple(c.getString("name"), c.getDouble("latitude"), c.getDouble("longitude"))
      }

  // Codigos WMO, los que usa Open-Meteo.
  private fun describir(codigo: Int) =
      when (codigo) {
        0 -> "despejado"
        1, 2 -> "nubes y claros"
        3 -> "nublado"
        45, 48 -> "niebla"
        in 51..57 -> "llovizna"
        in 61..67, in 80..82 -> "lluvia"
        in 71..77, 85, 86 -> "nieve"
        in 95..99 -> "tormenta"
        else -> "—"
      }
}
