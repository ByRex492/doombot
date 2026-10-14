package com.doombot.quest

import com.doombot.quest.ia.Catalogo
import com.doombot.quest.voz.Reflejos
import com.doombot.quest.voz.Reflejos.Orden
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** La capa refleja recibe lo que devuelve Whisper: signos, mayusculas, tildes y el nombre delante. */
class ReflejosTest {
  @Test
  fun reconoce_las_ordenes_tal_como_llegan_de_la_voz() {
    assertEquals(Orden.CALLAR, Reflejos.reconocer("¡Para!"))
    assertEquals(Orden.CALLAR, Reflejos.reconocer("DOOM, cállate."))
    assertEquals(Orden.RECOLOCAR, Reflejos.reconocer("Ven aquí"))
    assertEquals(Orden.AJUSTES, Reflejos.reconocer("abre ajustes"))
  }

  @Test
  fun una_frase_que_solo_contiene_la_palabra_no_es_una_orden() {
    // "para" dentro de una pregunta va al modelo, no corta la conversacion.
    assertNull(Reflejos.reconocer("para qué sirve esto"))
    assertNull(Reflejos.reconocer("ábreme youtube para ver un vídeo de cocina"))
  }

  @Test
  fun proveedor_y_modelo_se_parten_por_los_primeros_dos_puntos() {
    assertEquals("groq" to "openai/gpt-oss-120b", Catalogo.partir("groq:openai/gpt-oss-120b"))
    assertEquals("openrouter" to "openai/gpt-oss-120b:free", Catalogo.partir("OpenRouter:openai/gpt-oss-120b:free"))
  }
}
