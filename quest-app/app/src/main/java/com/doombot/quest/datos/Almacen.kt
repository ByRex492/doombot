package com.doombot.quest.datos

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.first
import org.json.JSONArray
import org.json.JSONObject

private val Context.ds: DataStore<Preferences> by preferencesDataStore(name = "doom")

/**
 * La configuracion de D.O.O.M en las gafas.
 *
 * Nada de esto sale del dispositivo ni vive en el codigo. Las claves de los proveedores se cifran
 * con una clave AES que genera y guarda el Android Keystore -no se puede extraer del chip-, y lo
 * cifrado va a DataStore. El resto (la cadena de modelos, la personalidad, la ciudad) no es secreto
 * y se guarda tal cual.
 */
class Almacen(private val contexto: Context) {

  data class Config(
      /** Modelos por orden de preferencia, ``proveedor:modelo`` (como DOOMBOT_MODELOS). */
      val cadena: List<String> = emptyList(),
      /** Transcripcion de voz, ``proveedor:modelo``. Vacio = el sugerido de Groq si hay clave. */
      val stt: String = "",
      val personalidad: String = PERSONALIDAD,
      val ciudad: String = "Madrid",
      val lat: Double = 40.4168,
      val lon: Double = -3.7038,
      /** Proveedores compatibles con OpenAI que el usuario ha anadido: id -> base_url. */
      val propios: Map<String, String> = emptyMap(),
      /** Temas, perfiles de color propios, brillo y velocidad (Personalizar, D-036). */
      val aspecto: Aspecto = Aspecto(),
      /** El modo de la conversacion: global o una skill (D-038). */
      val modo: String = "global",
      /** Hechos sobre el usuario, siempre en el prompt ("recuerda que..."). */
      val hechos: List<String> = emptyList(),
      /** Modelo con vision para "¿que estoy viendo?", ``proveedor:modelo``. Vacio = el sugerido de Groq. */
      val vision: String = "",
      /** TTS por API, ``proveedor:modelo``. Vacio = el TextToSpeech de Android (gratis, sin conexion). */
      val tts: String = "",
      val ttsVoz: String = "",
      /** "Hey jarvis": escuchar siempre la palabra de activacion. */
      val activacion: Boolean = true,
      /** Modo vigilante: un fotograma cada N segundos. 0 = apagado (por defecto: gasta cuota). */
      val vigilante: Int = 0,
      /** n8n (D-030): la URL base y la lista blanca de flujos, nombre hablado -> ruta del webhook. */
      val n8nUrl: String = "",
      val flujos: Map<String, String> = emptyMap(),
      /** Las ventanas: abierta, curva y tamaño de cada una (por el nombre del enum). */
      val ventanas: Map<String, com.doombot.quest.EstadoVentana> = emptyMap(),
      val brazaleteFijo: Boolean = false,
      val esquinas: Boolean = false,
      val micro: Boolean = true,
  )

  suspend fun config(): Config {
    val crudo = contexto.ds.data.first()[CONFIG] ?: return Config()
    return runCatching {
      val j = JSONObject(crudo)
      Config(
          cadena = j.optJSONArray("cadena").cadenas(),
          stt = j.optString("stt"),
          personalidad = j.optString("personalidad").ifBlank { PERSONALIDAD },
          ciudad = j.optString("ciudad", "Madrid"),
          lat = j.optDouble("lat", 40.4168),
          lon = j.optDouble("lon", -3.7038),
          propios =
              j.optJSONObject("propios")?.let { p -> p.keys().asSequence().associateWith { p.getString(it) } }
                  ?: emptyMap(),
          aspecto = aspectoDe(j.optJSONObject("aspecto")),
          modo = j.optString("modo", "global").ifBlank { "global" },
          hechos = j.optJSONArray("hechos").cadenas().take(MAX_HECHOS),
          vision = j.optString("vision"),
          tts = j.optString("tts"),
          ttsVoz = j.optString("ttsVoz"),
          activacion = j.optBoolean("activacion", true),
          vigilante = j.optInt("vigilante", 0).coerceIn(0, 3600),
          n8nUrl = j.optString("n8nUrl"),
          flujos =
              j.optJSONObject("flujos")?.let { f -> f.keys().asSequence().associateWith { f.getString(it) } }
                  ?: emptyMap(),
          ventanas =
              j.optJSONObject("ventanas")?.let { v ->
                v.keys().asSequence().associateWith { k ->
                  val e = v.getJSONObject(k)
                  com.doombot.quest.EstadoVentana(
                      abierta = e.optBoolean("abierta", true),
                      curva = e.optBoolean("curva", false),
                      escala = e.optDouble("escala", 1.0).toFloat().coerceIn(com.doombot.quest.EstadoVentana.ESCALA_MIN, com.doombot.quest.EstadoVentana.ESCALA_MAX))
                }
              } ?: emptyMap(),
          brazaleteFijo = j.optBoolean("brazaleteFijo", false),
          esquinas = j.optBoolean("esquinas", false),
          micro = j.optBoolean("micro", true),
      )
    }.getOrDefault(Config())
  }

  suspend fun guardar(c: Config) {
    val j =
        JSONObject()
            .put("cadena", JSONArray(c.cadena))
            .put("stt", c.stt)
            .put("personalidad", c.personalidad)
            .put("ciudad", c.ciudad)
            .put("lat", c.lat)
            .put("lon", c.lon)
            .put("propios", JSONObject(c.propios))
            .put("aspecto", aspectoJson(Aspecto.limpiar(c.aspecto)))
            .put("modo", c.modo)
            .put("hechos", JSONArray(c.hechos.take(MAX_HECHOS)))
            .put("vision", c.vision)
            .put("tts", c.tts)
            .put("ttsVoz", c.ttsVoz)
            .put("activacion", c.activacion)
            .put("vigilante", c.vigilante.coerceIn(0, 3600))
            .put("n8nUrl", c.n8nUrl.trim().trimEnd('/'))
            .put("flujos", JSONObject(c.flujos))
            .put(
                "ventanas",
                JSONObject().also { o ->
                  c.ventanas.forEach { (k, e) -> o.put(k, JSONObject().put("abierta", e.abierta).put("curva", e.curva).put("escala", e.escala.toDouble())) }
                })
            .put("brazaleteFijo", c.brazaleteFijo)
            .put("esquinas", c.esquinas)
            .put("micro", c.micro)
    contexto.ds.edit { it[CONFIG] = j.toString() }
  }

  suspend fun clave(proveedor: String): String {
    val cifrada = contexto.ds.data.first()[claveDe(proveedor)] ?: return ""
    return runCatching { descifrar(cifrada) }.getOrDefault("")
  }

  suspend fun guardarClave(proveedor: String, clave: String) {
    contexto.ds.edit {
      if (clave.isBlank()) it.remove(claveDe(proveedor)) else it[claveDe(proveedor)] = cifrar(clave.trim())
    }
  }

  /** Los proveedores con clave, para decir "configurada" sin ensenar la clave. */
  suspend fun conClave(): Set<String> =
      contexto.ds.data.first().asMap().keys.map { it.name }.filter { it.startsWith("clave_") }.map { it.removePrefix("clave_") }.toSet()

  // -- cifrado ---------------------------------------------------------------------------------
  private fun claveDe(proveedor: String) = stringPreferencesKey("clave_" + proveedor.lowercase())

  private fun secreto(): SecretKey {
    val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
    (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
    val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
    gen.init(
        KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build())
    return gen.generateKey()
  }

  private fun cifrar(texto: String): String {
    val c = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, secreto()) }
    val datos = c.iv + c.doFinal(texto.toByteArray())
    return Base64.encodeToString(datos, Base64.NO_WRAP)
  }

  private fun descifrar(b64: String): String {
    val datos = Base64.decode(b64, Base64.NO_WRAP)
    val c = Cipher.getInstance("AES/GCM/NoPadding")
    c.init(Cipher.DECRYPT_MODE, secreto(), GCMParameterSpec(128, datos.copyOfRange(0, 12)))
    return String(c.doFinal(datos.copyOfRange(12, datos.size)))
  }

  companion object {
    private const val ALIAS = "doom_claves"
    private val CONFIG = stringPreferencesKey("config")
    const val MAX_HECHOS = 50

    /** El aspecto desde JSON (DataStore o la pagina del movil), ya limpio. */
    fun aspectoDe(j: JSONObject?): Aspecto {
      if (j == null) return Aspecto()
      val perfiles = j.optJSONArray("perfiles")
      val lista =
          if (perfiles == null) emptyList()
          else
              (0 until perfiles.length()).mapNotNull { i ->
                perfiles.optJSONObject(i)?.let { p ->
                  Perfil(p.optString("id"), p.optString("nombre"), p.optString("c1"), p.optString("c2"))
                }
              }
      return Aspecto.limpiar(
          Aspecto(
              tema = j.optString("tema", "jarvis"),
              c1 = j.optString("c1", "#29d3ff"),
              c2 = j.optString("c2", "#8ff3ff"),
              luz = j.optDouble("luz", 1.0).toFloat(),
              velocidad = j.optDouble("velocidad", 1.0).toFloat(),
              perfiles = lista,
          ))
    }

    fun aspectoJson(a: Aspecto): JSONObject {
      val perfiles = JSONArray()
      a.perfiles.forEach { p -> perfiles.put(JSONObject().put("id", p.id).put("nombre", p.nombre).put("c1", p.c1).put("c2", p.c2)) }
      return JSONObject()
          .put("tema", a.tema)
          .put("c1", a.c1)
          .put("c2", a.c2)
          .put("luz", a.luz.toDouble())
          .put("velocidad", a.velocidad.toDouble())
          .put("perfiles", perfiles)
    }

    const val PERSONALIDAD =
        "Eres D.O.O.M., el asistente del usuario, al estilo de JARVIS: elegante, preciso y con un " +
            "punto de ironia britanica. Le llamas 'Mi Señor'. Respondes en espanol, breve, porque " +
            "tus respuestas se leen como subtitulos y se oyen en voz alta."
  }
}

private fun JSONArray?.cadenas(): List<String> =
    if (this == null) emptyList() else (0 until length()).map { getString(it) }.filter { it.isNotBlank() }
