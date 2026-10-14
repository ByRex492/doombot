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

    const val PERSONALIDAD =
        "Eres D.O.O.M., el asistente del usuario, al estilo de JARVIS: elegante, preciso y con un " +
            "punto de ironia britanica. Le llamas 'Mi Señor'. Respondes en espanol, breve, porque " +
            "tus respuestas se leen como subtitulos y se oyen en voz alta."
  }
}

private fun JSONArray?.cadenas(): List<String> =
    if (this == null) emptyList() else (0 until length()).map { getString(it) }.filter { it.isNotBlank() }
