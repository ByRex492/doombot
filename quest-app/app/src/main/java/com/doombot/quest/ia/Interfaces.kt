package com.doombot.quest.ia

import org.json.JSONArray
import org.json.JSONObject

/**
 * Los contratos de la IA, como los Protocol de backends/base.py en escritorio: quien los usa no
 * sabe que proveedor hay detras, y una pieza se cambia sin tocar a las demas. ``entrada`` es
 * siempre ``proveedor:modelo``, lo mismo que en la cadena de modelos.
 */
interface LlmProvider {
  /** Un turno de chat; devuelve el ``message`` (texto y, si hay, tool_calls). */
  suspend fun chat(entrada: String, mensajes: JSONArray, herramientas: JSONArray?): JSONObject

  /** Igual, pero llamando a ``alTexto`` con cada trozo de texto segun llega (para hablar antes). */
  suspend fun chatEnStreaming(entrada: String, mensajes: JSONArray, herramientas: JSONArray?, alTexto: (String) -> Unit): JSONObject
}

interface SttProvider {
  /** Voz a texto. ``wav``: 16 kHz mono. */
  suspend fun transcribir(entrada: String, wav: ByteArray): String
}

interface VisionProvider {
  /** Una pregunta sobre una imagen JPEG. */
  suspend fun mirar(entrada: String, pregunta: String, jpeg: ByteArray): String
}

interface TtsProvider {
  /** Texto a audio (WAV), con la voz pedida. */
  suspend fun sintetizar(entrada: String, voz: String, texto: String): ByteArray
}
