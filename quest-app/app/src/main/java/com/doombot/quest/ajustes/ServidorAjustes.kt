package com.doombot.quest.ajustes

import android.content.Context
import com.doombot.quest.Doom
import com.doombot.quest.InfoServidor
import com.doombot.quest.TipoLinea
import com.doombot.quest.datos.Almacen
import com.doombot.quest.ia.Catalogo
import com.doombot.quest.ia.ClienteIA
import com.doombot.quest.sistema.Tiempo
import fi.iki.elonen.NanoHTTPD
import java.net.Inet4Address
import java.net.NetworkInterface
import java.security.SecureRandom
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject

/**
 * Ajustes desde el movil: una pagina web servida por las propias gafas, solo en la red local.
 *
 * Escribir una clave de 50 caracteres con el teclado virtual de las gafas es un suplicio; en el
 * movil se pega. Por eso las gafas sirven una pagina mientras "Ajustes" esta abierto:
 *
 * - el QR lleva un token de un solo uso: sin el, el servidor no responde nada;
 * - ademas hay que escribir el PIN de 6 cifras que se ve en las gafas (3 intentos);
 * - se apaga solo a los 10 minutos, o al cerrar Ajustes.
 *
 * Las claves viajan del movil a las gafas por la red de casa (HTTP, sin salir a internet) y se
 * guardan cifradas (Almacen). La pagina nunca recibe una clave de vuelta, solo si esta puesta.
 */
class ServidorAjustes(
    private val contexto: Context,
    private val almacen: Almacen,
    private val ia: ClienteIA,
    private val alCambiar: () -> Unit,
) : NanoHTTPD(PUERTO) {

  private val azar = SecureRandom()
  private var token = ""
  private var pin = ""
  private var sesion = ""
  private var intentos = 0
  private var caduca = 0L

  fun abrir(): InfoServidor? {
    val ip = ipLocal() ?: return null.also { Doom.anotar(TipoLinea.ERROR, "Sin Wi-Fi: no puedo abrir los ajustes del movil.") }
    token = hex(16)
    pin = (100000 + azar.nextInt(900000)).toString()
    sesion = ""
    intentos = 0
    caduca = System.currentTimeMillis() + DURACION
    if (!wasStarted()) start(SOCKET_READ_TIMEOUT, false)
    return InfoServidor("http://$ip:$PUERTO/?t=$token", pin, caduca)
  }

  fun cerrar() {
    token = ""
    sesion = ""
    if (wasStarted()) stop()
  }

  override fun serve(s: IHTTPSession): Response {
    if (System.currentTimeMillis() > caduca) {
      cerrar()
      Doom.enUi { Doom.servidor = null }
      return texto(Response.Status.FORBIDDEN, "Caducado. Vuelve a abrir Ajustes en las gafas.")
    }
    val cookie = s.cookies.read("doom") ?: ""
    // 1. La pagina: solo con el token del QR, que se gasta al usarlo.
    if (s.uri == "/" && s.method == Method.GET) {
      if (token.isEmpty() || s.parms["t"] != token) return texto(Response.Status.FORBIDDEN, "Enlace no valido.")
      token = ""
      sesion = hex(16)
      val r = newFixedLengthResponse(Response.Status.OK, "text/html; charset=utf-8", pagina())
      r.addHeader("Set-Cookie", "doom=$sesion; Path=/; HttpOnly; SameSite=Strict")
      return r
    }
    if (sesion.isEmpty() || cookie.substringBefore("|") != sesion) return texto(Response.Status.FORBIDDEN, "Sin sesion.")
    val cuerpo = leerJson(s)
    // 2. El PIN, con pocos intentos.
    if (s.uri == "/api/entrar") {
      if (cuerpo.optString("pin") == pin) {
        val r = json(JSONObject().put("ok", true))
        r.addHeader("Set-Cookie", "doom=$sesion|ok; Path=/; HttpOnly; SameSite=Strict")
        return r
      }
      if (++intentos >= 3) {
        cerrar()
        Doom.enUi { Doom.servidor = null }
        Doom.anotar(TipoLinea.AVISO, "Tres PIN incorrectos desde el movil: cierro los ajustes.")
      }
      return json(JSONObject().put("ok", false).put("error", "PIN incorrecto"))
    }
    if (!cookie.endsWith("|ok")) return texto(Response.Status.FORBIDDEN, "Falta el PIN.")
    // 3. La API, ya autenticada.
    return runCatching {
          runBlocking {
            when (s.uri) {
              "/api/estado" -> json(estado())
              "/api/clave" -> {
                almacen.guardarClave(cuerpo.getString("proveedor"), cuerpo.optString("clave"))
                alCambiar()
                json(estado())
              }
              "/api/modelos" -> json(JSONObject().put("modelos", JSONArray(ia.modelos(cuerpo.getString("proveedor")))))
              "/api/probar" -> json(JSONObject().put("resultado", ia.probar(cuerpo.getString("proveedor"))))
              "/api/config" -> {
                guardarConfig(cuerpo)
                alCambiar()
                json(estado())
              }
              "/api/proveedor" -> {
                val c = almacen.config()
                val id = cuerpo.getString("id").lowercase().filter { it.isLetterOrDigit() }
                val propios = c.propios.toMutableMap()
                if (cuerpo.optBoolean("quitar")) propios.remove(id) else propios[id] = cuerpo.getString("url")
                almacen.guardar(c.copy(propios = propios))
                json(estado())
              }
              else -> texto(Response.Status.NOT_FOUND, "No existe.")
            }
          }
        }
        .getOrElse { json(JSONObject().put("error", it.message ?: "error")) }
  }

  private suspend fun estado(): JSONObject {
    val c = almacen.config()
    val con = almacen.conClave()
    val provs = JSONArray()
    for (p in Catalogo.todos(c)) {
      provs.put(
          JSONObject()
              .put("id", p.id)
              .put("titulo", p.titulo)
              .put("alta", p.alta)
              .put("url", p.baseUrl)
              .put("configurada", p.id in con)
              .put("propio", p.id in c.propios)
              .put("sugeridos", JSONArray(p.sugeridos))
              .put("stt", p.sttSugerido))
    }
    return JSONObject()
        .put("proveedores", provs)
        .put("cadena", JSONArray(c.cadena))
        .put("stt", c.stt)
        .put("personalidad", c.personalidad)
        .put("ciudad", c.ciudad)
  }

  private suspend fun guardarConfig(j: JSONObject) {
    var c = almacen.config()
    j.optJSONArray("cadena")?.let { a -> c = c.copy(cadena = (0 until a.length()).map { a.getString(it) }.filter { it.contains(':') }) }
    if (j.has("stt")) c = c.copy(stt = j.getString("stt"))
    if (j.has("personalidad")) c = c.copy(personalidad = j.getString("personalidad").take(2000))
    val ciudad = j.optString("ciudad")
    if (ciudad.isNotBlank() && ciudad != c.ciudad) {
      Tiempo.buscar(ciudad)?.let { (nombre, lat, lon) -> c = c.copy(ciudad = nombre, lat = lat, lon = lon) }
    }
    almacen.guardar(c)
  }

  private fun pagina(): String = contexto.assets.open("ajustes.html").bufferedReader().use { it.readText() }

  private fun leerJson(s: IHTTPSession): JSONObject {
    if (s.method != Method.POST) return JSONObject()
    val archivos = HashMap<String, String>()
    runCatching { s.parseBody(archivos) }
    return runCatching { JSONObject(archivos["postData"] ?: "{}") }.getOrDefault(JSONObject())
  }

  private fun json(j: JSONObject) = newFixedLengthResponse(Response.Status.OK, "application/json", j.toString())

  private fun texto(estado: Response.Status, t: String) = newFixedLengthResponse(estado, "text/plain; charset=utf-8", t)

  private fun hex(n: Int) = ByteArray(n).also { azar.nextBytes(it) }.joinToString("") { "%02x".format(it) }

  private fun ipLocal(): String? =
      NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
          .filter { it.isUp && !it.isLoopback }
          .flatMap { it.inetAddresses.toList() }
          .firstOrNull { it is Inet4Address && it.isSiteLocalAddress }
          ?.hostAddress

  companion object {
    const val PUERTO = 8787
    const val DURACION = 10 * 60 * 1000L
  }
}
